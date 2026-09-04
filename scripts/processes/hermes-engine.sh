#!/usr/bin/env bash
# devenv / systemd process wrapper for the Hermes lattice engine.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

export HERMES_ADVERTISE_HOST="${HERMES_ADVERTISE_HOST:-${SIGNALS_ADVERTISE_HOST:-tinybox.dev.vista.zndx.org}}"
export HERMES_ENGINE_TARGET="${HERMES_ENGINE_TARGET:-127.0.0.1:50651}"
export SIGNALS_ENGINE_TARGET="${SIGNALS_ENGINE_TARGET:-127.0.0.1:50551}"

exec python -m hsengine
