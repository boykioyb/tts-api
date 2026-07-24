#!/usr/bin/env python3
"""Enroll a cloned voice as a first-class, addressable voice.

Encodes a reference clip ONCE into a persistent speaker embedding + codes and
writes it to tts_service/app/data/custom_voices.json. After this the voice shows
up in GET /v1/voices and is usable by its id everywhere — and synthesis needs no
reference clip (or torch) at serve time, because the embedding is precomputed.

Usage:
  python examples/enroll_voice.py --ref clip.wav --name "Sora Narrator" \
      --gender male --region "Bắc" --style tu_nhien --description "..."

Enrolling requires torch + torchaudio (the speaker encoder). Serving does not.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tts_service"))

import numpy as np  # noqa: E402
from vieneu import Vieneu  # noqa: E402

from app.voices import CUSTOM_VOICES_PATH, slugify  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="reference clip (wav), 3–8s")
    ap.add_argument("--name", required=True)
    ap.add_argument("--voice-id", default=None,
                    help="stable id; defaults to slug(name). Set explicitly to keep an id "
                         "across renames (id is decoupled from display name).")
    ap.add_argument("--gender", default="")
    ap.add_argument("--region", default="")
    ap.add_argument("--style", default="tu_nhien")
    ap.add_argument("--description", default="")
    args = ap.parse_args()

    v = Vieneu(backend="onnx")
    emb, codes = v.engine.prepare_reference(args.ref, denoise=True, use_ref_codes=True)

    entry = {
        "voice_id": args.voice_id or slugify(args.name),
        "name": args.name,
        "description": args.description or f"{args.name} (cloned)",
        "gender": args.gender,
        "region": args.region,
        "style": args.style,
        "speaker_emb": [round(float(x), 6) for x in np.asarray(emb).reshape(-1)],
        "codes": np.asarray(codes, dtype=int).tolist(),
    }

    data = {"voices": []}
    if os.path.isfile(CUSTOM_VOICES_PATH):
        data = json.load(open(CUSTOM_VOICES_PATH, encoding="utf-8"))
    # replace any existing voice with the same id (idempotent re-enroll)
    data["voices"] = [x for x in data.get("voices", []) if x.get("voice_id") != entry["voice_id"]]
    data["voices"].append(entry)

    os.makedirs(os.path.dirname(CUSTOM_VOICES_PATH), exist_ok=True)
    with open(CUSTOM_VOICES_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)

    print(f"enrolled '{entry['name']}' -> id={entry['voice_id']} "
          f"(emb={len(entry['speaker_emb'])}d, codes={np.asarray(codes).shape}) "
          f"into {CUSTOM_VOICES_PATH}")


if __name__ == "__main__":
    main()
