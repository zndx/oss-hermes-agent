#!/usr/bin/env bash
# Resident Nautilus for project=hermes — same binary as Gaius, this instance.
# Observer must outlive the engine: a dark engine is unknown Backlog slots,
# not a startup failure. Do not bwrap this process.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

pick_bin() {
  if [[ -n "${NAUTILUS_BIN:-}" && -x "${NAUTILUS_BIN}" ]]; then
    printf '%s\n' "$NAUTILUS_BIN"
    return 0
  fi
  local c
  for c in \
    "$HOME/local/src/zndx/gaius/external/nautilus/target/release/nautilus" \
    "$HOME/local/src/zndx/nautilus/target/release/nautilus" \
    "$HOME/local/src/zndx/nautilus/target/debug/nautilus"
  do
    if [[ -x "$c" ]]; then
      printf '%s\n' "$c"
      return 0
    fi
  done
  return 1
}

BIN="$(pick_bin)" || {
  echo "DENY: nautilus binary not found (#NT.00000001.NOINSTANCE)" >&2
  echo "  Build Gaius's crate: cargo build --release --manifest-path ~/local/src/zndx/gaius/external/nautilus/Cargo.toml" >&2
  echo "  Or set NAUTILUS_BIN." >&2
  exit 1
}

export NAUTILUS_INSTANCE="${NAUTILUS_INSTANCE:-$ROOT/config/supervision/hermes.textproto}"
export NAUTILUS_ENGINE="${NAUTILUS_ENGINE:-127.0.0.1:50651}"
export NAUTILUS_BIND="${NAUTILUS_BIND:-127.0.0.1:50661}"
export NAUTILUS_DIRECTIVES="${NAUTILUS_DIRECTIVES:-observe}"
# Journal on the federation object plane (one bucket, namespaced by project).
export NAUTILUS_RUSTFS_URL="${NAUTILUS_RUSTFS_URL:-s3://signals-nautilus/}"
export NAUTILUS_RUSTFS_ENDPOINT="${NAUTILUS_RUSTFS_ENDPOINT:-http://127.0.0.1:9010}"
export SIGNALS_RUSTFS_KEY="${SIGNALS_RUSTFS_KEY:-rustfsadmin}"
export SIGNALS_RUSTFS_SECRET="${SIGNALS_RUSTFS_SECRET:-rustfsadmin}"

"$BIN" validate "$NAUTILUS_INSTANCE" --quiet | tail -1

echo "Starting nautilus (hermes)"
echo "  bin=$BIN"
echo "  instance=$NAUTILUS_INSTANCE"
echo "  engine=$NAUTILUS_ENGINE bind=$NAUTILUS_BIND directives=$NAUTILUS_DIRECTIVES"
echo "  journal=$NAUTILUS_RUSTFS_URL via $NAUTILUS_RUSTFS_ENDPOINT"
exec "$BIN" serve --instance "$NAUTILUS_INSTANCE"
