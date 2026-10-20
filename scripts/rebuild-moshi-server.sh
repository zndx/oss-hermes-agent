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

for cmd in cargo cmake nvcc pkg-config; do
  command -v "$cmd" >/dev/null || {
    echo "DENY: $cmd missing (enter the Hermes devenv shell)" >&2
    exit 1
  }
done

# CUDA 12.4 nvcc rejects gcc 15. Host gcc 11/12 produces Ubuntu PT_INTERP
# (glibc 2.35) and then wrap's nix libstdc++ dies on GLIBC_2.39. Use a
# Nix gcc-wrapper 13 so PT_INTERP stays nix ld-linux.
pick_nix_gcc13() {
  if [[ -n "${MOSHI_CC:-}" && -x "${MOSHI_CC}" ]]; then
    printf '%s\n' "$MOSHI_CC"
    return 0
  fi
  local g
  for g in /nix/store/*-gcc-wrapper-13.3.*/bin/gcc /nix/store/*-gcc-wrapper-13.*/bin/gcc; do
    if [[ -x "$g" ]]; then
      printf '%s\n' "$g"
      return 0
    fi
  done
  echo "DENY: no Nix gcc-wrapper-13 (CUDA 12.4). Set MOSHI_CC or add pkgs.gcc13 to devenv.nix" >&2
  return 1
}

cc_path="$(pick_nix_gcc13)"
cxx_path="${MOSHI_CXX:-${cc_path%/gcc}/g++}"
[[ -x "$cxx_path" ]] || {
  echo "DENY: g++ missing next to $cc_path" >&2
  exit 1
}
export CC="$cc_path" CXX="$cxx_path"
export CUDAHOSTCXX="$cxx_path"
export CMAKE_CUDA_HOST_COMPILER="$cc_path"
export NVCC_PREPEND_FLAGS="-ccbin ${cc_path}"
# sentencepiece-sys 0.11.3 omits <cstdint> (gcc 15 error); gcc 13 is enough.
# PyO3 0.23 (moshi-server 0.6.4) does not link CPython 3.14. Pin the profile
# interpreter moshi-python (pkgs.python311), not the Hermes venv on PATH.
py311=""
moshi_py="${ROOT}/.devenv/profile/bin/moshi-python"
if [[ -x "$moshi_py" ]]; then
  py311="$(readlink -f "$moshi_py")"
fi
if [[ -z "$py311" || ! -x "$py311" ]]; then
  wrap="${ROOT}/.devenv/profile/bin/moshi-server"
  if [[ -f "$wrap" ]] && [[ "$(cat "$wrap")" =~ (/nix/store/[^:[:space:]]+-python3-3\.11\.[^/]+)/lib ]]; then
    cand="${BASH_REMATCH[1]}/bin/python3.11"
    [[ -x "$cand" ]] && py311="$cand"
  fi
fi
libdir=""
if [[ -n "$py311" ]]; then
  libdir="$(dirname "$(dirname "$py311")")/lib"
fi
if [[ -z "$py311" || ! -e "${libdir}/libpython3.11.so.1.0" ]]; then
  echo "DENY: moshi-python missing libpython3.11.so.1.0 (rebuild the devenv profile)" >&2
  exit 1
fi
export PYO3_PYTHON="$py311"
export PYTHON_SYS_EXECUTABLE="$py311"

mkdir -p "$CARGO_TARGET_DIR"
echo "cc=$cc_path"
echo "cxx=$cxx_path"
echo "pyo3_python=$PYO3_PYTHON"
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
