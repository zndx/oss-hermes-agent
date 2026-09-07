#!/usr/bin/env bash
# Resident moshi-server supervisor for devenv. CUDA starts only when the
# engine POSTs /interactive/on (after declaring the Activity to Signals).
# This process never talks to Kubernetes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Devenv wrap first (Nix glibc). rustup cargo last so we never exec the
# unwrapped ELF against Ubuntu libc.
# shellcheck disable=SC1091
[[ -f "${HOME}/.cargo/env" ]] && source "${HOME}/.cargo/env"
export PATH="${ROOT}/.devenv/profile/bin:${PATH:-}:${HOME}/.cargo/bin"
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export PATH="${CUDA_HOME}/bin:${PATH}"
export HF_HOME="${HF_HOME:-/raid/cache/huggingface}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

PY="${ROOT}/.devenv/state/venv/bin/python"
[[ -x "$PY" ]] || {
  echo "DENY: devenv venv python missing" >&2
  exit 1
}
command -v moshi-server >/dev/null 2>&1 || {
  echo "DENY: moshi-server not installed" >&2
  exit 1
}

exec "$PY" -m hsengine.engine.moshi_supervisor
