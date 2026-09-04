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
export SIGNALS_ENGINE_TARGET="${SIGNALS_ENGINE_TARGET:-127.0.0.1:50551}"
export PYTHONPATH=""

exec "${VENV}/bin/python" -m hsengine
