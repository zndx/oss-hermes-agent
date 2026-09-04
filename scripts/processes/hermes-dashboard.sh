#!/usr/bin/env bash
# devenv process: Hermes web dashboard on LAN + WARP (Zero Trust hostname).
# Non-loopback bind requires dashboard auth (secretspec).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

VENV="${ROOT}/.devenv/state/venv"
HERMES="${VENV}/bin/hermes"
if [[ ! -x "$HERMES" ]]; then
  echo "DENY: devenv venv missing hermes at ${HERMES}" >&2
  echo "  Run: devenv tasks run devenv:python:uv" >&2
  exit 1
fi

export HERMES_ADVERTISE_HOST="${HERMES_ADVERTISE_HOST:-${SIGNALS_ADVERTISE_HOST:-tinybox.dev.vista.zndx.org}}"
HOST="${HERMES_DASHBOARD_BIND_HOST:-0.0.0.0}"
PORT="${HERMES_DASHBOARD_PORT:-9119}"
export HERMES_DASHBOARD_PUBLIC_URL="${HERMES_DASHBOARD_PUBLIC_URL:-http://${HERMES_ADVERTISE_HOST}:${PORT}}"
export PYTHONPATH=""

# secretspec provider=dotenv writes gitignored .env; process-compose does not
# always inject it. Source here so `devenv up -d` can start the dashboard.
# Tests set HERMES_DASHBOARD_IGNORE_DOTENV=1 so a developer .env cannot leak.
if [[ -z "${HERMES_DASHBOARD_IGNORE_DOTENV:-}" && -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
export HERMES_DASHBOARD_BASIC_AUTH_USERNAME="${HERMES_DASHBOARD_BASIC_AUTH_USERNAME:-hermes}"

if [[ -z "${HERMES_DASHBOARD_BASIC_AUTH_PASSWORD:-}" && -z "${HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH:-}" ]]; then
  echo "DENY: non-loopback dashboard requires auth." >&2
  echo "  secretspec set HERMES_DASHBOARD_BASIC_AUTH_PASSWORD" >&2
  echo "  secretspec set HERMES_DASHBOARD_BASIC_AUTH_SECRET   # optional, stable sessions" >&2
  exit 1
fi

echo "hermes dashboard bind=${HOST}:${PORT} public_url=${HERMES_DASHBOARD_PUBLIC_URL}"
exec "$HERMES" dashboard --host "$HOST" --port "$PORT" --no-open
