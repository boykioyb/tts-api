"""Runtime configuration for the TTS worker, sourced from environment variables."""
import os

# VieNeu backend: "onnx" (CPU, torch-free) or "torch" (GPU/CPU).
BACKEND = os.getenv("TTS_BACKEND", "onnx")
PRECISION = os.getenv("TTS_PRECISION", "fp32")

# Fallbacks when a request omits voice/style and provides no reference clip.
DEFAULT_VOICE = os.getenv("TTS_DEFAULT_VOICE", "Phạm Tuyên")
DEFAULT_STYLE = os.getenv("TTS_DEFAULT_STYLE", "tu_nhien")

# Sampling knobs passed to VieNeu.infer(). The upstream defaults (temperature=1.0)
# are quite random for a TTS read — clones especially wobble ("lúc rõ lúc không").
# Lowering temperature makes delivery steadier and more consistent; top_k /
# repetition_penalty further tame drift. Tune via env without touching code.
TEMPERATURE = float(os.getenv("TTS_TEMPERATURE", "0.7"))
TOP_K = int(os.getenv("TTS_TOP_K", "40"))
REPETITION_PENALTY = float(os.getenv("TTS_REPETITION_PENALTY", "1.3"))

# VieNeu v3 Turbo emits 48 kHz float32; kept configurable in case a model changes it.
SAMPLE_RATE = int(os.getenv("TTS_SAMPLE_RATE", "48000"))

PORT = int(os.getenv("TTS_GRPC_PORT", "50051"))
MAX_WORKERS = int(os.getenv("TTS_MAX_WORKERS", "4"))
MAX_MESSAGE_MB = int(os.getenv("TTS_MAX_MESSAGE_MB", "64"))
