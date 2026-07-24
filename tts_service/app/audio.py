"""Audio post-processing: resampling and container/codec encoding.

Kept separate from the gRPC server so encoding concerns live in one place. Heavy
optional deps (soxr, lameenc) are imported lazily so a build that never resamples
or emits MP3 doesn't need them installed.
"""
from __future__ import annotations

import io

import numpy as np


def _to_int16(samples: np.ndarray) -> np.ndarray:
    return (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")


def resample(samples: np.ndarray, src_sr: int, dst_sr: int) -> tuple[np.ndarray, int]:
    if not dst_sr or dst_sr == src_sr:
        return samples, src_sr
    import soxr

    out = soxr.resample(samples, src_sr, dst_sr)
    return np.asarray(out, dtype=np.float32), dst_sr


def encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def encode_mp3(samples: np.ndarray, sample_rate: int, bitrate_kbps: int = 128) -> bytes:
    import lameenc

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate_kbps or 128)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(1)          # VieNeu output is mono
    encoder.set_quality(2)           # 0=best/slowest .. 9=worst/fastest
    data = encoder.encode(_to_int16(samples).tobytes())
    data += encoder.flush()
    return bytes(data)  # lameenc returns a bytearray; protobuf `bytes` needs real bytes
