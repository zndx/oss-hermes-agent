# Shared bubblewrap jail for Hermes devenv processes (engine + dashboard).
# Source this file; then: hermes_bwrap_exec <cmd> [args...]
#
# Fake HOME=/home/hermes with the host ~/.hermes bind-mounted so Path.home()
# and profile listing keep working. The checkout stays at its real path
# (venv shebangs / HERMES_DASHBOARD_FILES_ROOT). Host $HOME is not mounted,
# so /home/rch is only an empty prefix of the bind path.
#
# HERMES_BWRAP=0          skip jail (tests / debug)
# HERMES_BWRAP_PRINT=1    print the bwrap argv, then exec
# HERMES_BWRAP_BIN        override binary
hermes_bwrap_bin() {
  if [[ -n "${HERMES_BWRAP_BIN:-}" ]]; then
    [[ -x "${HERMES_BWRAP_BIN}" ]] || return 1
    printf '%s\n' "${HERMES_BWRAP_BIN}"
    return 0
  fi
  if command -v bwrap >/dev/null 2>&1; then
    command -v bwrap
    return 0
  fi
  local profile
  profile="${HERMES_ROOT:-}/.devenv/profile/bin/bwrap"
  if [[ -n "${HERMES_ROOT:-}" && -x "$profile" ]]; then
    printf '%s\n' "$profile"
    return 0
  fi
  return 1
}

hermes_bwrap_exec() {
  if [[ "${HERMES_BWRAP:-1}" == "0" ]]; then
    exec "$@"
  fi
  local bwrap root host_home host_hermes rustfs
  root="${HERMES_ROOT:-$(pwd)}"
  HERMES_ROOT="$root"
  bwrap="$(hermes_bwrap_bin)" || {
    echo "DENY: bubblewrap (bwrap) not found — refuse to start unsandboxed." >&2
    echo "  devenv.nix includes pkgs.bubblewrap; re-enter the devenv shell." >&2
    echo "  Or: HERMES_BWRAP=0 to skip (debug only)." >&2
    exit 1
  }
  host_home="${HOME}"
  host_hermes="${HERMES_HOME:-$host_home/.hermes}"
  mkdir -p "$host_hermes"
  rustfs="${RUSTFS_DATA_DIR:-}"

  local -a args=(
    --unshare-user --unshare-pid --die-with-parent
    --dev /dev
    --proc /proc
    --tmpfs /tmp
    --dir /home
    --dir /home/hermes
    --bind "$host_hermes" /home/hermes/.hermes
    --bind "$root" "$root"
    --ro-bind /nix /nix
    --ro-bind-try /usr /usr
    --ro-bind-try /bin /bin
    --ro-bind-try /lib /lib
    --ro-bind-try /lib64 /lib64
    --ro-bind-try /etc/resolv.conf /etc/resolv.conf
    --ro-bind-try /etc/ssl /etc/ssl
    --ro-bind-try /etc/pki /etc/pki
    --ro-bind-try /etc/nsswitch.conf /etc/nsswitch.conf
    --ro-bind-try /etc/hosts /etc/hosts
    --ro-bind-try /etc/localtime /etc/localtime
    --chdir "$root"
    --setenv HOME /home/hermes
    --setenv USER hermes
    --setenv HERMES_HOME /home/hermes/.hermes
    --setenv HERMES_DASHBOARD_FILES_ROOT "$root"
  )
  if [[ -n "$rustfs" && -d "$rustfs" ]]; then
    args+=(--bind "$rustfs" "$rustfs")
  fi

  if [[ "${HERMES_BWRAP_PRINT:-0}" == "1" ]]; then
    printf 'bwrap' >&2
    local a
    for a in "${args[@]}"; do
      printf ' %q' "$a" >&2
    done
    printf ' --' >&2
    for a in "$@"; do
      printf ' %q' "$a" >&2
    done
    printf '\n' >&2
  fi
  exec "$bwrap" "${args[@]}" -- "$@"
}
