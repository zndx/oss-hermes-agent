#!/usr/bin/env bash
# Follow-only: validate config/supervision/hermes.textproto with the local
# Nautilus binary (Phase 0 — parse + tree invariants). Gaius leads adapters.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTANCE="${1:-$ROOT/config/supervision/hermes.textproto}"
NAUTILUS="${NAUTILUS_BIN:-}"
if [[ -z "$NAUTILUS" ]]; then
  for c in \
    "$HOME/local/src/zndx/gaius/external/nautilus/target/release/nautilus" \
    "$HOME/local/src/zndx/nautilus/target/release/nautilus" \
    "$HOME/local/src/zndx/nautilus/target/debug/nautilus"
  do
    [[ -x "$c" ]] && NAUTILUS="$c" && break
  done
fi
PROTO="${SIGNALS_PROTOCOL_PROTO:-$ROOT/components/signals-protocol/proto}"

if [[ ! -x "$NAUTILUS" ]]; then
  echo "nautilus binary not found at $NAUTILUS" >&2
  echo "build: SIGNALS_PROTOCOL_PROTO=$PROTO cargo build --manifest-path $HOME/local/src/zndx/nautilus/Cargo.toml" >&2
  exit 2
fi

exec "$NAUTILUS" validate "$INSTANCE"
