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

# uv-managed CPython lives under ~/.local/share/uv/python. The devenv venv's
# python (and the hermes script shebang) is a symlink into that tree. The
# jail mounts /nix but not $HOME, so execvp returns ENOENT unless the
# interpreter prefix is bound. Returns the .../uv/python directory, or empty.
hermes_bwrap_uv_python_dir() {
  local cmd real install
  cmd="${1:-}"
  [[ -n "$cmd" && -e "$cmd" ]] || return 0
  real="$(readlink -f "$cmd" 2>/dev/null || true)"
  [[ -n "$real" ]] || return 0
  case "$real" in
    /nix/*|/usr/*|/bin/*) return 0 ;;
  esac
  # .../uv/python/cpython-X.Y.Z-.../bin/python
  install="$(dirname "$(dirname "$(dirname "$real")")")"
  [[ "$(basename "$install")" == "python" ]] || return 0
  [[ "$(basename "$(dirname "$install")")" == "uv" ]] || return 0
  [[ -d "$install" ]] || return 0
  printf '%s\n' "$install"
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
    --unshare-user --die-with-parent
  )
  # Dashboard must see the host gateway PID (hermes-gateway.service).
  # --unshare-pid gives a private /proc so /api/status reports stopped
  # even when the user unit is running — chat then looks "unavailable"
  # and UI "Restart gateway" cannot observe the process it just spawned.
  if [[ "${HERMES_BWRAP_SHARE_PID:-0}" != "1" ]]; then
    args+=(--unshare-pid)
  fi
  args+=(
    --dev /dev
    --proc /proc
    --tmpfs /tmp
    --dir /home
    --dir /home/hermes
    --bind "$host_hermes" /home/hermes/.hermes
    # Persist host HERMES_HOME path too: gateway_state.json records
    # /home/rch/.hermes while the jail's get_hermes_home() is
    # /home/hermes/.hermes. Without this bind, inode/string compare fails
    # and /api/status reports the live gateway as stopped.
    --dir "$(dirname "$host_hermes")"
    --bind "$host_hermes" "$host_hermes"
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
    # llm-wiki and /obsidian follow WIKI_PATH / OBSIDIAN_VAULT_PATH. Keep the
    # vault on the HERMES_HOME bind (named profile or common Hermes storage).
    # Do not bind $HOME/wiki — Hermes-created notes do not belong in the
    # operator home.
    --setenv WIKI_PATH /home/hermes/.hermes/wiki
    --setenv OBSIDIAN_VAULT_PATH /home/hermes/.hermes/wiki
    --setenv HERMES_DASHBOARD_FILES_ROOT "$root"
  )
  mkdir -p "$host_hermes/wiki"
  if [[ -n "$rustfs" && -d "$rustfs" ]]; then
    args+=(--bind "$rustfs" "$rustfs")
  fi

  local n
  for n in /dev/nvidia*; do
    [[ -e "$n" ]] || continue
    args+=(--dev-bind "$n" "$n")
  done
  hf="${HF_HOME:-}"
  if [[ -n "$hf" ]]; then
    mkdir -p "$hf"
    args+=(--bind "$hf" "$hf")
  fi

  # Editable signals-hsengine lives outside this checkout.
  local sp="${SIGNALS_PLUGINS:-}"
  if [[ -n "$sp" && -d "$sp" ]]; then
    args+=(--bind "$sp" "$sp")
  fi
  # Quiet preprint extracts run Gaius docling. The tree is outside this checkout.
  local gaius="${GAIUS_ROOT:-}"
  if [[ -n "$gaius" && -d "$gaius" ]]; then
    args+=(--bind "$gaius" "$gaius")
  fi

  # install.sh developer checkouts symlink $HERMES_HOME/plugins/<name> at a
  # tree outside the jail (this checkout + ~/.hermes). Follow those links.
  # If the target is <repo>/plugins/<name> and that repo ships hsengine
  # (signals-plugins), bind the repo root too — editable signals-hsengine
  # lives there, not under plugins/signals-listen.
  local dest src repo
  if [[ -d "$host_hermes/plugins" ]]; then
    for dest in "$host_hermes/plugins"/*; do
      [[ -L "$dest" ]] || continue
      src="$(readlink -f "$dest" 2>/dev/null || true)"
      [[ -n "$src" && -d "$src" ]] || continue
      args+=(--bind "$src" "$src")
      if [[ "$(basename "$(dirname "$src")")" == "plugins" ]]; then
        repo="$(dirname "$(dirname "$src")")"
        if [[ -d "$repo/hsengine" ]]; then
          args+=(--bind "$repo" "$repo")
        fi
      fi
    done
  fi

  # Engine execs the venv python; the dashboard execs the hermes script,
  # whose shebang is that same symlink. Bind the prefix for both.
  local uv_dir seen="" cmd
  seen="|"
  for cmd in "${root}/.devenv/state/venv/bin/python" "$1"; do
    uv_dir="$(hermes_bwrap_uv_python_dir "$cmd")"
    [[ -n "$uv_dir" && "$seen" != *"|${uv_dir}|"* ]] || continue
    seen="${seen}${uv_dir}|"
    args+=(--ro-bind "$uv_dir" "$uv_dir")
  done

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
