"""Voice catalog: assigns a stable, URL-safe id to each voice and resolves an id
(or name) to what VieNeu's `infer(voice=...)` expects.

Two sources are merged:
  * presets   — VieNeu's built-in voices, keyed by human name; resolve() returns
                the name string.
  * custom    — cloned voices enrolled into custom_voices.json as a precomputed
                {speaker_emb, codes} payload; resolve() returns that dict, so
                synthesis needs no reference clip (and no torch) at serve time.

We derive a deterministic slug id per voice so the HTTP API can follow the
ElevenLabs convention (id in the path, name for display).
"""
from __future__ import annotations

import json
import os
import re
import unicodedata

CUSTOM_VOICES_PATH = os.getenv(
    "TTS_CUSTOM_VOICES",
    os.path.join(os.path.dirname(__file__), "data", "custom_voices.json"),
)


def _region_from(meta: dict) -> str:
    # VieNeu presets have no explicit region key; it's encoded positionally in the
    # description as "Giới · Vùng · Phong cách...", e.g. "Nam · Bắc · Phong cách tin tức".
    if meta.get("region"):
        return str(meta["region"])
    parts = [p.strip() for p in str(meta.get("description", "")).split("·")]
    return parts[1] if len(parts) >= 3 else ""


def slugify(name: str) -> str:
    # đ/Đ don't decompose under NFD, so map them explicitly first.
    s = name.replace("Đ", "D").replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")  # drop combining marks
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "voice"


class VoiceCatalog:
    def __init__(self, vieneu) -> None:
        # Prefer the in-memory preset dict (has full metadata). Fall back to the
        # public API, which only yields (description, name).
        raw = getattr(vieneu, "_preset_voices", None)
        if isinstance(raw, dict):
            entries = [(name, meta if isinstance(meta, dict) else {}) for name, meta in raw.items()]
        else:
            entries = [(name, {"description": desc}) for desc, name in vieneu.list_preset_voices()]

        self._voices: list[dict] = []
        self._id_to_name: dict[str, str] = {}
        self._names: set[str] = set()
        self._payload_by_name: dict[str, dict] = {}  # custom voices only
        self._used_ids: set[str] = set()

        for name, meta in entries:
            vid = self._unique_id(name)
            self._id_to_name[vid] = name
            self._names.add(name)
            self._voices.append({
                "voice_id": vid,
                "name": name,
                "description": str(meta.get("description", name)),
                "gender": str(meta.get("gender", "")),
                "region": _region_from(meta),
                "style": str(meta.get("style", "")),
                "category": "premade",
            })

        self._load_custom()

    def _unique_id(self, name: str) -> str:
        vid = base = slugify(name)
        n = 2
        while vid in self._used_ids:  # disambiguate slug collisions deterministically
            vid = f"{base}-{n}"
            n += 1
        self._used_ids.add(vid)
        return vid

    def _load_custom(self) -> None:
        if not os.path.isfile(CUSTOM_VOICES_PATH):
            return
        data = json.load(open(CUSTOM_VOICES_PATH, encoding="utf-8"))
        for v in data.get("voices", []):
            name = v["name"]
            vid = v.get("voice_id") or self._unique_id(name)
            self._used_ids.add(vid)
            self._id_to_name[vid] = name
            self._names.add(name)
            # Payload passed straight to infer(voice=...); no ref clip / torch needed.
            self._payload_by_name[name] = {"speaker_emb": v["speaker_emb"], "codes": v["codes"]}
            self._voices.append({
                "voice_id": vid,
                "name": name,
                "description": str(v.get("description", name)),
                "gender": str(v.get("gender", "")),
                "region": str(v.get("region", "")),
                "style": str(v.get("style", "tu_nhien")),
                "category": "cloned",
            })

    def list(self) -> list[dict]:
        return self._voices

    def resolve(self, id_or_name: str):
        """Resolve an id or name to what infer() wants: a name string for presets,
        or a {speaker_emb, codes} dict for cloned voices. Raises on unknown input."""
        name = self._id_to_name.get(id_or_name)
        if name is None:
            name = id_or_name if id_or_name in self._names else None
        if name is None:
            raise ValueError(f"unknown voice: {id_or_name!r}")
        if name in self._payload_by_name:
            return self._payload_by_name[name]
        return name
