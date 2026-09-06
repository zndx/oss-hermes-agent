#!/usr/bin/env bash
# Kyutai STT on the agent-rtc YK leaf. Admit 1 GPU token, then run moshi-server.
# No whisper/CPU path: if YK or CUDA or moshi-server is missing, exit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

export KUBECONFIG="$HOME/.config/kube/rke2.yaml"
# rustup
# shellcheck disable=SC1091
[[ -f "${HOME}/.cargo/env" ]] && source "${HOME}/.cargo/env"
export PATH="${HOME}/.cargo/bin:${PATH:-}"
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export PATH="${CUDA_HOME}/bin:${PATH}"
export HF_HOME="${HF_HOME:-/raid/cache/huggingface}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

PY="${ROOT}/.devenv/state/venv/bin/python"
command -v moshi-server >/dev/null 2>&1 || {
  echo "DENY: moshi-server not installed (cargo install --features cuda moshi-server@0.6.4)" >&2
  exit 1
}
[[ -x "$PY" ]] || {
  echo "DENY: devenv venv python missing" >&2
  exit 1
}

"$PY" -m hsengine.engine.yk_sentinel admit

STATE="${ROOT}/.devenv/state/moshi"
mkdir -p "$STATE/static" "$STATE/logs" "$HF_HOME"
PID_FILE="$STATE/moshi-stt.pid"
GPU_INDEX="$("$PY" -c "from hsengine.engine.yk_sentinel import lease_one_gpu; print(lease_one_gpu($$))")"
export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
echo $$ > "$PID_FILE"

cleanup() {
  rm -f "$PID_FILE"
  "$PY" -m hsengine.engine.yk_sentinel release || true
}
trap cleanup EXIT

CONFIG="${MOSHI_STT_CONFIG:-$ROOT/hsengine/moshi/stt-1b.toml}"
PORT="${MOSHI_STT_PORT:-5080}"
cd "$STATE"
exec moshi-server worker --config "$CONFIG" --port "$PORT"
