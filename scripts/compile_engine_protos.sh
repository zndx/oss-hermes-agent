#!/usr/bin/env bash
# Compile Protocol Buffers for the lattice engine.
# hsengine lives in signals-plugins; this wrapper forwards.
set -euo pipefail
sp="${SIGNALS_PLUGINS:-$HOME/local/src/wxs/signals-plugins}"
script="$sp/scripts/compile_engine_protos.sh"
if [[ ! -x "$script" ]]; then
  echo "DENY: $script missing (SIGNALS_PLUGINS=$sp)" >&2
  exit 1
fi
exec "$script" "$@"
