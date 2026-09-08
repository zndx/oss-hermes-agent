#!/usr/bin/env bash
# Copy lego ACME account + certs to Proton Drive (rclone protondrive).
#
# One-time: log in to Proton Drive in a browser (creates encryption keys),
# then:
#   rclone config
#     n) New remote  name=proton  storage=protondrive
# Official Linux GUI is not out yet; rclone 1.64+ is the system-wide client.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="${DEVENV_STATE:-$ROOT/.devenv/state}"
LEGO="${HERMES_LEGO_PATH:-$STATE/lego}"
RCLONE="${RCLONE:-rclone}"

utc_quarter() {
  local y m
  y="$(date -u +%Y)"
  m="$(date -u +%-m)"
  echo "${y}Q$(( (m - 1) / 3 + 1 ))"
}

# tinybox.dev.vista.zndx.org → box=tinybox realm=vista
# tinybox.vista.zndx.org     → box=tinybox realm=vista
box_realm_from_fqdn() {
  local host="${HERMES_TLS_DOMAIN:-${HERMES_ADVERTISE_HOST:-tinybox.dev.vista.zndx.org}}"
  host="${host%%:*}"
  local IFS=.
  # shellcheck disable=SC2206
  local p=($host)
  local n=${#p[@]}
  BOX="${HERMES_BACKUP_BOX:-${p[0]:-tinybox}}"
  if [[ -n "${HERMES_BACKUP_REALM:-}" ]]; then
    REALM="$HERMES_BACKUP_REALM"
  elif (( n >= 5 )); then
    REALM="${p[2]}"
  elif (( n >= 4 )); then
    REALM="${p[1]}"
  else
    REALM="vista"
  fi
}

box_realm_from_fqdn
DEFAULT_REMOTE="proton:archive/$(utc_quarter)/${REALM}/${BOX}/acme-lego"
REMOTE="${HERMES_ACME_BACKUP_REMOTE:-$DEFAULT_REMOTE}"

if [[ ! -d "$LEGO/accounts" || ! -d "$LEGO/certificates" ]]; then
  echo "hermes-acme-backup: no lego tree at $LEGO" >&2
  exit 1
fi

if ! "$RCLONE" version >/dev/null 2>&1; then
  echo "hermes-acme-backup: rclone missing (need v1.64+ for protondrive)" >&2
  exit 127
fi

if ! "$RCLONE" listremotes 2>/dev/null | grep -qx "proton:"; then
  echo "hermes-acme-backup: no rclone remote named proton." >&2
  echo "  Log in to Proton Drive in a browser once, then: rclone config" >&2
  exit 2
fi

umask 077
"$RCLONE" copy "$LEGO" "$REMOTE" \
  --checksum \
  --create-empty-src-dirs \
  --protondrive-replace-existing-draft=true \
  --retries 3 \
  --low-level-retries 10
echo "hermes-acme-backup: synced $LEGO -> $REMOTE"
