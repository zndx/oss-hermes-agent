#!/usr/bin/env bash
# Fetch NousResearch/hermes-agent (read-only `upstream`) and merge `main`.
#
#   ./scripts/merge-upstream.sh           # fetch + report lag
#   ./scripts/merge-upstream.sh --merge   # merge upstream/main into HEAD
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! git remote get-url upstream >/dev/null 2>&1; then
  git remote add upstream git@github.com:NousResearch/hermes-agent.git
fi
git remote set-url --push upstream DISABLE
git config remote.upstream.fetch '+refs/heads/main:refs/remotes/upstream/main'

git fetch upstream --prune

behind="$(git rev-list --count HEAD..upstream/main)"
ahead="$(git rev-list --count upstream/main..HEAD)"
echo "HEAD $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short HEAD)"
echo "upstream/main @ $(git rev-parse --short upstream/main)  behind=$behind  ahead=$ahead"

if [[ "${1:-}" != "--merge" ]]; then
  if [[ "$behind" -gt 0 ]]; then
    echo "Merge with: $0 --merge"
    git log --oneline --no-decorate HEAD..upstream/main | head -20
    [[ "$behind" -gt 20 ]] && echo "... ($behind commits)"
  fi
  exit 0
fi

if [[ "$behind" -eq 0 ]]; then
  echo "already up to date with upstream/main"
  exit 0
fi

git merge --no-edit upstream/main
echo "merged. Publish: git push origin HEAD"
