#!/usr/bin/env bash
# Cheap devenv enterShell notices: Signals plugins vs GitHub, this fork vs
# NousResearch/hermes-agent. Network at most once per hour (stamp in DEVENV_STATE).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_ROOT="${HERMES_HOME:-$HOME/.hermes}"
META="$HOME_ROOT/plugins/.install-metadata.json"
STAMP="${DEVENV_STATE:-$ROOT/.devenv/state}/enter-update-check.stamp"
TTL_S="${HERMES_ENTER_CHECK_TTL_S:-3600}"
PLUGINS=(signals-oip signals-memory signals-compact)
PLUGINS_GIT="${SIGNALS_PLUGINS_GIT:-git@github.com:weathership/signals-plugins.git}"
PLUGINS_REF="${SIGNALS_PLUGINS_REF:-refs/heads/trunk}"

now="$(date +%s)"
if [[ -f "$STAMP" ]]; then
  age=$((now - $(stat -c %Y "$STAMP" 2>/dev/null || echo 0)))
else
  age=$((TTL_S + 1))
fi
need_net=0
[[ "$age" -ge "$TTL_S" ]] && need_net=1

git_ls() {
  timeout 4 git ls-remote --heads "$1" "${2#refs/heads/}" 2>/dev/null | awk '{print $1; exit}'
}

# --- signals-plugins: install if missing; notice if GitHub trunk moved ---
missing=()
for p in "${PLUGINS[@]}"; do
  [[ -e "$HOME_ROOT/plugins/$p" ]] || missing+=("$p")
done
if ((${#missing[@]})); then
  if command -v hermes >/dev/null 2>&1; then
    for p in "${missing[@]}"; do
      hermes plugins install "weathership/signals-plugins/plugins/$p" --no-enable || true
    done
  else
    echo "  signals-plugins: missing ${missing[*]} (hermes not on PATH)"
  fi
fi

if [[ "$need_net" -eq 1 ]]; then
  tip="$(git_ls "$PLUGINS_GIT" "$PLUGINS_REF" || true)"
  mkdir -p "$(dirname "$STAMP")"
  date -Iseconds >"$STAMP" 2>/dev/null || : >"$STAMP"
else
  tip=""
fi

if [[ -n "$tip" && -f "$META" ]]; then
  installed="$(python3 -c "
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
try:
    data = json.loads(p.read_text())
except Exception:
    sys.exit(0)
revs = {str((data.get(n) or {}).get('revision') or '') for n in sys.argv[2:]}
print(next(iter(revs)) if len(revs)==1 else 'mixed')
" "$META" "${PLUGINS[@]}")"
  if [[ -n "$installed" && "$installed" != "$tip" ]]; then
    echo "  signals-plugins: GitHub trunk ${tip:0:7} (installed ${installed:0:7})"
    echo "    hermes plugins install weathership/signals-plugins/plugins/signals-oip --force --no-enable"
    echo "    hermes plugins install weathership/signals-plugins/plugins/signals-memory --force --no-enable"
    echo "    hermes plugins install weathership/signals-plugins/plugins/signals-compact --force --no-enable"
  fi
fi

# --- hermes-agent: notice if HEAD is behind NousResearch main ---
cd "$ROOT"
if git remote get-url upstream >/dev/null 2>&1; then
  if [[ "$need_net" -eq 1 ]]; then
    timeout 8 git fetch -q upstream 2>/dev/null || true
  fi
  if git rev-parse -q --verify upstream/main >/dev/null; then
    behind="$(git rev-list --count HEAD..upstream/main 2>/dev/null || echo 0)"
    if [[ "${behind:-0}" -gt 0 ]]; then
      echo "  upstream: $behind commit(s) on NousResearch/hermes-agent main not in HEAD"
      echo "    ./scripts/merge-upstream.sh --merge && git push origin HEAD"
    fi
  fi
fi
