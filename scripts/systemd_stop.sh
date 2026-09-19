#!/usr/bin/env bash
# Full unit stop: devenv down for the shared login/systemd graph.
# Does not GPU-wipe sibling leases (thinking lives on Gaius).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="/usr/local/bin:/usr/bin:/bin:${HOME}/.nix-profile/bin:${PATH:-}"
# shellcheck source=lib/systemd-unit.sh
source "$ROOT/scripts/lib/systemd-unit.sh"

export_unit_runtime
info "stop (shared devenv graph; XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-})"
lattice_down

if [[ "$(listener_count)" -gt 0 ]]; then
  info "WARN :${GRPC_PORT} still listening after stop" >&2
  ss -ltnpH 2>/dev/null | grep -E ":${GRPC_PORT}[[:space:]]" >&2 || true
  exit 1
fi
info ":${GRPC_PORT} free"
