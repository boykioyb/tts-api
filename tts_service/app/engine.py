"""Thin adapter around the VieNeu library.

Everything model-specific lives here, so if the upstream VieNeu API shifts you only
touch this file. Inference is serialized with a lock: a single model instance is not
guaranteed thread-safe and a single GPU/CPU processes one clip at a time anyway.
"""
from __future__ import annotations

import logging
import threading
from typing import Iterator

import numpy as np

from app import config
from app.voices import VoiceCatalog

logger = logging.getLogger(__name__)


class TtsEngine:
    def __init__(self) -> None:
        # Imported lazily so the module can be inspected without pulling in the model.
        from vieneu import Vieneu

        logger.info("Loading VieNeu (backend=%s, precision=%s)...", config.BACKEND, config.PRECISION)
        kwargs = {"backend": config.BACKEND}
        if config.BACKEND == "onnx":
            kwargs["precision"] = config.PRECISION
        self._vieneu = Vieneu(**kwargs)
        self._lock = threading.Lock()
        self.catalog = VoiceCatalog(self._vieneu)
        logger.info("VieNeu ready (%d preset voices).", len(self.catalog.list()))

    def _build_kwargs(self, text: str, voice: str | None, style: str | None,
                      ref_audio_path: str | None, denoise: bool) -> dict:
        kwargs: dict = {"text": text}
        if ref_audio_path:
            # Voice cloning path: reference clip wins over preset voice/style.
            kwargs["ref_audio"] = ref_audio_path
            kwargs["denoise"] = denoise
        else:
            # Accept either a voice_id (slug) or a raw name; VieNeu needs the name.
            kwargs["voice"] = self.catalog.resolve(voice or config.DEFAULT_VOICE)
            kwargs["style"] = style or config.DEFAULT_STYLE
        # Sampling knobs (see config). Steadier than VieNeu's random defaults; the
        # infer variants all accept temperature/top_k and tolerate the rest via **kwargs.
        kwargs["temperature"] = config.TEMPERATURE
        kwargs["top_k"] = config.TOP_K
        kwargs["repetition_penalty"] = config.REPETITION_PENALTY
        return kwargs

    def synthesize(self, text: str, voice: str | None = None, style: str | None = None,
                   ref_audio_path: str | None = None, denoise: bool = False) -> np.ndarray:
        kwargs = self._build_kwargs(text, voice, style, ref_audio_path, denoise)
        with self._lock:
            try:
                audio = self._vieneu.infer(**kwargs)
            except ModuleNotFoundError as exc:
                # The speaker encoder used for cloning needs torch + torchaudio,
                # which the default torch-free (onnx) image omits. Presets still work.
                if ref_audio_path:
                    raise RuntimeError(
                        "voice cloning requires torch + torchaudio "
                        "(not installed in the default torch-free image)"
                    ) from exc
                raise
        return np.asarray(audio, dtype=np.float32)

    def synthesize_stream(self, text: str, voice: str | None = None,
                          style: str | None = None) -> Iterator[np.ndarray]:
        voice = self.catalog.resolve(voice or config.DEFAULT_VOICE)
        with self._lock:
            for chunk in self._vieneu.infer_stream(text, voice=voice):
                yield np.asarray(chunk, dtype=np.float32)

    def list_voices(self) -> list[dict]:
        return self.catalog.list()
