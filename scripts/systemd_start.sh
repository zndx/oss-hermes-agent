#!/usr/bin/env bash
# signals.target membership hook. devenv owns engine+dashboard
# (`devenv up -d`). Accept is Engine/Status :50651 and dashboard :9119.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="/usr/local/bin:/usr/bin:/bin:${HOME}/.nix-profile/bin:${PATH:-}"
# shellcheck source=lib/systemd-unit.sh
source "$ROOT/scripts/lib/systemd-unit.sh"

POLL_ITERS="${HERMES_SYSTEMD_POLL_ITERS:-120}"
POLL_SLEEP="${HERMES_SYSTEMD_POLL_SLEEP:-5}"

export_unit_runtime

if unit_already_ready && compose_visible; then
  info "already READY (Engine/Status :${GRPC_PORT}, dashboard :${UI_PORT}) — skip up"
  exit 0
fi

if ! compose_visible; then
  info "starting devenv graph (devenv up -d; engine :${GRPC_PORT} dashboard :${UI_PORT})"
  if ! lattice_up; then
    info "up reported failure — will still poll (stack may already be live)"
  fi
fi

for i in $(seq 1 "$POLL_ITERS"); do
  n=$(listener_count)
  if [[ "${n:-0}" -gt 1 ]]; then
    info "Guru: #EN.00000014.DUALBIND ${n} listeners on :${GRPC_PORT}" >&2
    ss -ltnpH 2>/dev/null | grep -E ":${GRPC_PORT}[[:space:]]" >&2 || true
    exit 1
  fi
  if unit_already_ready && compose_visible; then
    info "compose-owned Engine/Status ready on :${GRPC_PORT} dashboard :${UI_PORT} (iter=$i)"
    exit 0
  fi
  if (( i % 6 == 0 )); then
    info "waiting… iter=$i status=$(status_ok && echo ok || echo no) ui=$(ui_ok && echo ok || echo no) listeners=${n:-0} compose=$(compose_visible && echo yes || echo no)"
  fi
  sleep "$POLL_SLEEP"
done

info "timed out waiting for compose-owned Engine/Status on :${GRPC_PORT}" >&2
ss -ltnH 2>/dev/null | grep -E ":(${GRPC_PORT}|${UI_PORT})[[:space:]]" >&2 || true
exit 1
