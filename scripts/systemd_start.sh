#!/usr/bin/env bash
# Peer-unit start: bring the devenv engine graph up and wait for Engine/Status.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${1:-}" == "--help" ]]; then
  echo "usage: $0   # devenv up -d && wait for zndx.engine.v1.Engine/Status project=hermes"
  exit 0
fi

devenv up -d
PY="$ROOT/.devenv/state/venv/bin/python"
deadline=$((SECONDS + 90))
while (( SECONDS < deadline )); do
  if [[ -x "$PY" ]] && "$PY" "$ROOT/scripts/hermes_status_ok.py"; then
    exit 0
  fi
  sleep 2
done
echo "DENY: hermes engine did not answer Engine/Status as project=hermes" >&2
exit 1
