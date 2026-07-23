#!/usr/bin/env bash
set -euo pipefail

prefix="${1:-/opt/conda}"
arch="$(uname -m)"

case "${arch}" in
  x86_64)
    installer_arch="x86_64"
    ;;
  aarch64|arm64)
    installer_arch="aarch64"
    ;;
  *)
    echo "unsupported architecture: ${arch}" >&2
    exit 1
    ;;
esac

installer="/tmp/Miniforge3-Linux-${installer_arch}.sh"
url="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-${installer_arch}.sh"

curl -fsSL "${url}" -o "${installer}"
bash "${installer}" -b -p "${prefix}"
rm -f "${installer}"
"${prefix}/bin/conda" config --system --set channel_priority strict
