#!/usr/bin/env bash
# Authenticated curl against the Hermes dashboard using secretspec.
# Never prints the password. Usage:
#   ./scripts/dashboard-curl.sh /api/files
#   ./scripts/dashboard-curl.sh /api/health
# Extra curl flags after the path:
#   ./scripts/dashboard-curl.sh /api/files -o /tmp/files.json
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PATH="${ROOT}/.devenv/profile/bin:${PATH:-}"

if ! command -v secretspec >/dev/null 2>&1; then
  echo "DENY: secretspec is not on PATH (enter the devenv shell)" >&2
  exit 1
fi

BASE="${HERMES_DASHBOARD_URL:-http://127.0.0.1:9119}"
if [[ $# -lt 1 ]]; then
  echo "usage: $0 <path-or-url> [curl-args...]" >&2
  exit 2
fi
TARGET="$1"
shift
case "$TARGET" in
  http://*|https://*) URL="$TARGET" ;;
  /*) URL="${BASE}${TARGET}" ;;
  *) URL="${BASE}/${TARGET}" ;;
esac

PROVIDER="${SECRETSPEC_PROVIDER:-dotenv}"
export _DASH_BASE="$BASE" _DASH_URL="$URL"
exec secretspec run --provider "$PROVIDER" -- bash -c '
  set -euo pipefail
  user="${HERMES_DASHBOARD_BASIC_AUTH_USERNAME:-hermes}"
  pass="${HERMES_DASHBOARD_BASIC_AUTH_PASSWORD:-}"
  if [[ -z "$pass" ]]; then
    echo "DENY: HERMES_DASHBOARD_BASIC_AUTH_PASSWORD is unset (secretspec set ...)" >&2
    exit 1
  fi
  jar="$(mktemp)"
  trap "rm -f \"$jar\"" EXIT
  login_json="$(
    u="$user" p="$pass" python3 -c "import json,os; print(json.dumps({\"provider\":\"basic\",\"username\":os.environ[\"u\"],\"password\":os.environ[\"p\"]}))" \
    | curl -sS -c "$jar" -b "$jar" -H "content-type: application/json" \
        --data-binary @- "${_DASH_BASE}/auth/password-login"
  )"
  python3 -c "import json,sys; d=json.loads(sys.argv[1]); raise SystemExit(0 if d.get(\"ok\") is True else 1)" "$login_json" \
    || { echo "DENY: dashboard login failed" >&2; exit 1; }
  exec curl -sS -b "$jar" "$_DASH_URL" "$@"
' bash "$@"
