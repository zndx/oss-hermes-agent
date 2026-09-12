#!/usr/bin/env bash
# devenv / systemd process wrapper for the Hermes lattice engine.
# Interpreter is the devenv-managed venv (.devenv/state/venv), never a
# uv-downloaded .venv and never the host python.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

VENV="${ROOT}/.devenv/state/venv"
if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "DENY: devenv venv missing at ${VENV}" >&2
  echo "  Run: devenv tasks run devenv:python:uv" >&2
  exit 1
fi

export HERMES_ADVERTISE_HOST="${HERMES_ADVERTISE_HOST:-${SIGNALS_ADVERTISE_HOST:-tinybox.dev.vista.zndx.org}}"
export HERMES_ENGINE_TARGET="${HERMES_ENGINE_TARGET:-127.0.0.1:50651}"
export HF_HOME="${HF_HOME:-/raid/cache/huggingface}"
export SIGNALS_ENGINE_TARGET="${SIGNALS_ENGINE_TARGET:-127.0.0.1:50551}"
export SIGNALS_PLUGINS="${SIGNALS_PLUGINS:-$HOME/local/src/wxs/signals-plugins}"
export PYTHONPATH=""

# secretspec provider=dotenv writes gitignored .env; process-compose does
# not always inject it. Source here so AgentRTC sees CEREBRAS_API_KEY
# (same pattern as hermes-dashboard.sh).
if [[ -z "${HERMES_ENGINE_IGNORE_DOTENV:-}" && -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

# shellcheck source=../lib/hermes-bwrap.sh
source "$ROOT/scripts/lib/hermes-bwrap.sh"
HERMES_ROOT="$ROOT"
hermes_bwrap_exec "${VENV}/bin/python" -m hsengine
