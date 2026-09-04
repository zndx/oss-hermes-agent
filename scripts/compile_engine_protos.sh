#!/usr/bin/env bash
# Compile Protocol Buffers for the Hermes lattice engine.
#
# Usage: ./scripts/compile_engine_protos.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NATIVE="$ROOT/hsengine/engine/proto"
ZNDX="$ROOT/components/signals-protocol/proto"
OUT="$ROOT/hsengine/engine/generated"

if ! python -c "import grpc_tools.protoc" 2>/dev/null; then
  echo "Error: grpcio-tools not installed. Run: uv sync --extra engine" >&2
  exit 1
fi

mkdir -p "$OUT"
touch "$OUT/__init__.py"

echo "Compiling hermes.engine.HermesEngine"
python -m grpc_tools.protoc \
  -I "$NATIVE" \
  --python_out="$OUT" --pyi_out="$OUT" --grpc_python_out="$OUT" \
  "$NATIVE/hermes_engine.proto"

echo "Compiling zndx.engine.v1.Engine"
python -m grpc_tools.protoc \
  -I "$ZNDX" \
  --python_out="$OUT" --pyi_out="$OUT" --grpc_python_out="$OUT" \
  "$ZNDX/zndx/engine/v1/engine.proto"

echo "Compiling inference.GRPCInferenceService (OIP)"
python -m grpc_tools.protoc \
  -I "$ZNDX" \
  --python_out="$OUT" --pyi_out="$OUT" --grpc_python_out="$OUT" \
  "$ZNDX/inference/v2/open_inference_grpc.proto"

mkdir -p \
  "$OUT/zndx/engine/v1" \
  "$OUT/inference/v2"
touch \
  "$OUT/zndx/__init__.py" \
  "$OUT/zndx/engine/__init__.py" \
  "$OUT/zndx/engine/v1/__init__.py" \
  "$OUT/inference/__init__.py" \
  "$OUT/inference/v2/__init__.py"

# grpc_tools emits absolute imports; rewrite into the hsengine package.
sed -i 's/^import hermes_engine_pb2/from . import hermes_engine_pb2/' \
  "$OUT/hermes_engine_pb2_grpc.py"
sed -i 's/^from zndx\.engine\.v1 import/from hsengine.engine.generated.zndx.engine.v1 import/' \
  "$OUT/zndx/engine/v1/engine_pb2_grpc.py"
if [[ -f "$OUT/inference/v2/open_inference_grpc_pb2_grpc.py" ]]; then
  sed -i 's/^from inference\.v2 import/from hsengine.engine.generated.inference.v2 import/' \
    "$OUT/inference/v2/open_inference_grpc_pb2_grpc.py"
  sed -i 's/^import open_inference_grpc_pb2/from . import open_inference_grpc_pb2/' \
    "$OUT/inference/v2/open_inference_grpc_pb2_grpc.py"
fi

echo "OK generated → $OUT"
