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
base_url="${MINIFORGE_BASE_URL:-https://mirrors.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease}"
url="${base_url%/}/Miniforge3-Linux-${installer_arch}.sh"

curl -fsSL "${url}" -o "${installer}"
bash "${installer}" -b -p "${prefix}"
rm -f "${installer}"
"${prefix}/bin/conda" config --system --remove-key channels >/dev/null 2>&1 || true
"${prefix}/bin/conda" config --system --add channels "${CONDA_FORGE_CHANNEL:-https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge}"
"${prefix}/bin/conda" config --system --set channel_priority strict
