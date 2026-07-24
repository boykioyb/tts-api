"""Runtime configuration for the TTS worker, sourced from environment variables."""
import os

# VieNeu backend: "onnx" (CPU, torch-free) or "torch" (GPU/CPU).
BACKEND = os.getenv("TTS_BACKEND", "onnx")
PRECISION = os.getenv("TTS_PRECISION", "fp32")

# Fallbacks when a request omits voice/style and provides no reference clip.
DEFAULT_VOICE = os.getenv("TTS_DEFAULT_VOICE", "Phạm Tuyên")
DEFAULT_STYLE = os.getenv("TTS_DEFAULT_STYLE", "tu_nhien")

# VieNeu v3 Turbo emits 48 kHz float32; kept configurable in case a model changes it.
SAMPLE_RATE = int(os.getenv("TTS_SAMPLE_RATE", "48000"))

PORT = int(os.getenv("TTS_GRPC_PORT", "50051"))
MAX_WORKERS = int(os.getenv("TTS_MAX_WORKERS", "4"))
MAX_MESSAGE_MB = int(os.getenv("TTS_MAX_MESSAGE_MB", "64"))
