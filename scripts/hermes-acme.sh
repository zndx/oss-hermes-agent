#!/usr/bin/env bash
# Issue or renew a publicly trusted cert for the AgentRTC Listen FQDN.
#
# Let's Encrypt via Cloudflare DNS-01 (no :80/:443 required). The same
# name can still terminate at Cloudflare's edge on 443 with Cloudflare's
# own cert; this file is what Caddy presents on :9120 to browsers
# (calendar join, getUserMedia) — including WARP clients that hit origin.
#
#   secretspec set HERMES_ACME_EMAIL
#   # Token: this lab already has CLOUDFLARE_API_TOKEN in the environment.
#   # secretspec 0.8 dotenv is the devenv default; env is a valid provider:
#   #   secretspec run --provider env -- ./scripts/hermes-acme.sh
#   # or copy once: secretspec import env
#   ./scripts/hermes-acme.sh
#   devenv restart caddy                      # pick up certs (pathExists)
#
# Place existing LE/ZeroSSL PEMs at
#   $DEVENV_STATE/lego/certificates/$DOMAIN.crt
#   $DEVENV_STATE/lego/certificates/$DOMAIN.key
# to skip issuance.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${HERMES_TLS_DOMAIN:-tinybox.dev.vista.zndx.org}"
EMAIL="${HERMES_ACME_EMAIL:-}"
STATE="${DEVENV_STATE:-$ROOT/.devenv/state}"
LEGO_PATH="${HERMES_LEGO_PATH:-$STATE/lego}"
CRT="$LEGO_PATH/certificates/${DOMAIN}.crt"
KEY="$LEGO_PATH/certificates/${DOMAIN}.key"

if [[ "${1:-}" == "status" ]]; then
  if [[ -f "$CRT" && -f "$KEY" ]]; then
    openssl x509 -in "$CRT" -noout -issuer -subject -dates 2>/dev/null || ls -l "$CRT"
    exit 0
  fi
  echo "no public cert at $CRT (Caddy will use tls internal for $DOMAIN)" >&2
  exit 1
fi

# If the CF token is not in this process yet, re-exec under secretspec's
# env provider (reads CLOUDFLARE_* from the parent environment).
if [[ -z "${CLOUDFLARE_API_TOKEN:-}${CLOUDFLARE_DNS_API_TOKEN:-}" ]] \
   && [[ -z "${HERMES_ACME_NO_SECRETSPEC_ENV:-}" ]] \
   && command -v secretspec >/dev/null 2>&1; then
  export HERMES_ACME_NO_SECRETSPEC_ENV=1
  exec secretspec run --provider env -- "$0" "$@"
fi

if [[ -z "$EMAIL" ]]; then
  echo "hermes-acme: set HERMES_ACME_EMAIL (ACME account)." >&2
  exit 1
fi

TOKEN="${CLOUDFLARE_DNS_API_TOKEN:-${CLOUDFLARE_API_TOKEN:-}}"
if [[ -z "$TOKEN" ]]; then
  echo "hermes-acme: need CLOUDFLARE_API_TOKEN (or CLOUDFLARE_DNS_API_TOKEN) in the environment." >&2
  echo "  secretspec run --provider env -- $0 $*" >&2
  exit 1
fi
export CF_DNS_API_TOKEN="$TOKEN"

if ! command -v lego >/dev/null 2>&1; then
  echo "hermes-acme: lego not on PATH (devenv packages)." >&2
  exit 127
fi

mkdir -p "$LEGO_PATH"
cmd=(lego --accept-tos --email "$EMAIL" --path "$LEGO_PATH" --dns cloudflare -d "$DOMAIN")
if [[ -f "$CRT" && -f "$KEY" ]]; then
  echo "hermes-acme: renewing $DOMAIN" >&2
  "${cmd[@]}" renew --days 30
else
  echo "hermes-acme: issuing Let's Encrypt cert for $DOMAIN via Cloudflare DNS-01" >&2
  "${cmd[@]}" run
fi

if [[ ! -f "$CRT" || ! -f "$KEY" ]]; then
  echo "hermes-acme: expected $CRT and $KEY after lego" >&2
  exit 1
fi
echo "hermes-acme: public cert ready. Restart Caddy so devenv re-evals tls files." >&2
