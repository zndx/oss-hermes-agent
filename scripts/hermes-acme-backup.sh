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
REMOTE="${HERMES_ACME_BACKUP_REMOTE:-proton:archive/tinybox/acme-lego}"
RCLONE="${RCLONE:-rclone}"

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
