#!/usr/bin/env bash
# Shared helpers for scripts/systemd_{start,stop}.sh.
# signals.target membership hook. devenv owns the process graph.

: "${ROOT:?systemd-unit.sh: ROOT must be set}"

GRPC_PORT="${HERMES_ENGINE_GRPC_PORT:-50651}"
UI_PORT="${HERMES_DASHBOARD_PORT:-9119}"
UNIT_NAME="${HERMES_SYSTEMD_UNIT:-hermes.service}"

info() { echo "hermes.service: $*"; }

export_unit_runtime() {
  if [[ -d "/run/user/$(id -u)" ]]; then
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  fi
  export HOME="${HOME:-/home/rch}"
  export SIGNALS_PLUGINS="${SIGNALS_PLUGINS:-$HOME/local/src/wxs/signals-plugins}"
}

_devenv_lc() {
  export_unit_runtime
  /bin/bash -lc "cd \"$ROOT\" && export PATH=\"/usr/local/bin:\$PATH\" && \
    export XDG_RUNTIME_DIR=\"${XDG_RUNTIME_DIR:-}\" && \
    export HOME=\"${HOME:-}\" && \
    export SIGNALS_PLUGINS=\"${SIGNALS_PLUGINS:-}\" && \
    $*"
}

lattice_up() {
  _devenv_lc "devenv up -d"
}

lattice_down() {
  _devenv_lc "devenv processes down || true" || true
}

listener_count() {
  ss -ltnH 2>/dev/null | grep -cE ":${GRPC_PORT}[[:space:]]" || true
}

status_ok() {
  local py="${ROOT}/.devenv/state/venv/bin/python"
  [[ -x "$py" ]] || return 1
  "$py" "$ROOT/scripts/hermes_status_ok.py" >/dev/null 2>&1
}

ui_ok() {
  ss -ltnH 2>/dev/null | grep -qE ":${UI_PORT}[[:space:]]"
}

compose_visible() {
  if _devenv_lc "devenv processes list" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

unit_already_ready() {
  status_ok && ui_ok
}
