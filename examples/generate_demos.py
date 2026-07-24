#!/usr/bin/env python3
"""Generate a demo MP3 for every preset voice.

Runs VieNeu directly, reusing the worker's own voice catalog (app.voices) and MP3
encoder (app.audio), then writes examples/demos/<voice_id>.mp3 for each voice using
that voice's default style.

Usage:  python examples/generate_demos.py
Requires: pip install vieneu lameenc   (soxr only if you resample)
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tts_service"))

import numpy as np  # noqa: E402
from vieneu import Vieneu  # noqa: E402

from app import audio  # noqa: E402
from app.voices import VoiceCatalog  # noqa: E402

OUT_DIR = os.path.join(HERE, "demos")
SAMPLE_RATE = 48000
DEMO_TEXT = "Xin chào, tôi là {name}. Đây là giọng đọc tiếng Việt của VieNeu — bạn thấy nghe thế nào?"


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Loading VieNeu...", flush=True)
    vieneu = Vieneu(backend="onnx")
    voices = VoiceCatalog(vieneu).list()
    print(f"{len(voices)} voices -> {OUT_DIR}\n", flush=True)

    for i, v in enumerate(voices, 1):
        vid, name, style = v["voice_id"], v["name"], (v["style"] or "tu_nhien")
        text = DEMO_TEXT.format(name=name)
        t0 = time.time()
        wav = np.asarray(vieneu.infer(text=text, voice=name, style=style), dtype=np.float32)
        with open(os.path.join(OUT_DIR, f"{vid}.mp3"), "wb") as fh:
            fh.write(audio.encode_mp3(wav, SAMPLE_RATE, 128))
        print(f"[{i:2}/{len(voices)}] {vid:<12} {style:<11} "
              f"{wav.shape[0] / SAMPLE_RATE:4.1f}s  ({time.time() - t0:4.1f}s)", flush=True)

    print("\nDone.")


if __name__ == "__main__":
    main()
