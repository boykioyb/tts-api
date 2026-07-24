#!/usr/bin/env bash
# Generate Python gRPC stubs from protos/tts.proto into a package directory.
# Usage: bash scripts/gen_protos.sh [output_dir]   (default: app/generated)
set -euo pipefail

# Prefer `python`, fall back to `python3` (macOS/dev boxes often lack `python`).
PY="$(command -v python || command -v python3)"

OUT="${1:-app/generated}"
mkdir -p "$OUT"
touch "$OUT/__init__.py"

"$PY" -m grpc_tools.protoc \
  -I protos \
  --python_out="$OUT" \
  --grpc_python_out="$OUT" \
  --pyi_out="$OUT" \
  protos/tts.proto

# The generated *_grpc.py uses a top-level `import tts_pb2`, which breaks once the
# files live inside a package. Rewrite it to a package-relative import so the same
# `from app.generated import tts_pb2, tts_pb2_grpc` works in both services.
"$PY" - "$OUT" <<'PY'
import pathlib, sys
grpc_file = pathlib.Path(sys.argv[1]) / "tts_pb2_grpc.py"
text = grpc_file.read_text()
text = text.replace("import tts_pb2 as tts__pb2", "from . import tts_pb2 as tts__pb2")
grpc_file.write_text(text)
print(f"stubs generated in {sys.argv[1]}")
PY
