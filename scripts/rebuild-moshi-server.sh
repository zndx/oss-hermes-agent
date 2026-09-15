#!/usr/bin/env bash
# Rebuild cargo moshi-server against the current devenv Nix glibc.
#
# The binary is Nix-linked (PT_INTERP = nix ld-linux). After nix GC or a
# devenv upgrade the old interpreter path 127s as:
#   ~/.cargo/bin/moshi-server: cannot execute: required file not found
# Inverse of Gaius tinybox-ninja.sh: do not use host gcc.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="${ROOT}/.devenv/profile/bin:${HOME}/.cargo/bin:${PATH:-}"
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export PATH="${CUDA_HOME}/bin:${PATH}"
export CUDA_COMPUTE_CAP="${CUDA_COMPUTE_CAP:-89}"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-/raid/build/hermes/moshi-server-target}"

for cmd in cargo cc cmake nvcc pkg-config; do
  command -v "$cmd" >/dev/null || {
    echo "DENY: $cmd missing (enter the Hermes devenv shell)" >&2
    exit 1
  }
done

cc_path="$(command -v cc)"
case "$cc_path" in
  /nix/store/*) ;;
  *)
    echo "DENY: cc is $cc_path — need devenv Nix gcc-wrapper, not host gcc" >&2
    exit 1
    ;;
esac

mkdir -p "$CARGO_TARGET_DIR"
echo "cc=$cc_path"
echo "nvcc=$(nvcc --version | tail -1)"
echo "openssl=$(pkg-config --modversion openssl 2>/dev/null || echo missing)"
echo "target=$CARGO_TARGET_DIR"
echo "cuda_compute_cap=$CUDA_COMPUTE_CAP"

cargo install --features cuda moshi-server@0.6.4 --force

real="${CARGO_HOME:-$HOME/.cargo}/bin/moshi-server"
interp="$(readelf -l "$real" | sed -n 's/.*\[Requesting program interpreter: \(.*\)\]/\1/p')"
echo "PT_INTERP=$interp"
if [[ -z "$interp" || ! -e "$interp" ]]; then
  echo "DENY: rebuilt binary interpreter missing: ${interp:-unset}" >&2
  exit 1
fi

wrap="${ROOT}/.devenv/profile/bin/moshi-server"
if [[ -x "$wrap" ]]; then
  "$wrap" --help >/dev/null
  echo "wrap_ok $wrap"
fi
echo "ok $real"
