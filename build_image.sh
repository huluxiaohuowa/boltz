#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

REGISTRY="${REGISTRY:-swr.cn-east-3.myhuaweicloud.com/huluxiaohuowa}"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) DEFAULT_PLATFORM_TAG="amd_$(date +%Y%m%d)" ;;
  aarch64|arm64) DEFAULT_PLATFORM_TAG="arm_$(date +%Y%m%d)" ;;
  *) DEFAULT_PLATFORM_TAG="${ARCH}_$(date +%Y%m%d)" ;;
esac
PLATFORM_TAG="${PLATFORM_TAG:-$DEFAULT_PLATFORM_TAG}"
ENV_FILE="${ENV_FILE:-.env.web}"
COMPONENT="${COMPONENT:-web}"
PUSH="${PUSH:-1}"

log() { echo "[INFO] $*"; }
err() { echo "[ERROR] $*" >&2; }
die() { err "$*"; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  ./build_image.sh [--component web|host-metrics|protein-prep-arm|protein-prep-amd|ligand-prep-arm|ligand-prep-amd|all] [--tag amd_YYYYMMDD|arm_YYYYMMDD] [--registry REGISTRY] [--no-push]

Image naming follows the ictrek app convention:
  ${REGISTRY}/${image_name}:${PLATFORM_TAG}

Examples:
  ./build_image.sh
  ./build_image.sh --component web --tag arm_20260724
  PROTEIN_PREP_ARM_BASE_IMAGE=<arm64-cpu-base> ./build_image.sh --component protein-prep-arm --tag arm_20260724
  LIGAND_PREP_ARM_BASE_IMAGE=<arm64-cpu-base> ./build_image.sh --component ligand-prep-arm --tag arm_20260724

Mirror overrides:
  CONDA_FORGE_CHANNEL=https://mirrors.ustc.edu.cn/anaconda/cloud/conda-forge \
    ./build_image.sh --component protein-prep-arm --tag arm_YYYYMMDD
  CONDA_FORGE_CHANNEL=https://mirrors.cloud.tencent.com/anaconda/cloud/conda-forge \
    ./build_image.sh --component protein-prep-amd --tag amd_YYYYMMDD
  CONDA_FORGE_CHANNEL=https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge \
    ./build_image.sh --component protein-prep-arm --tag arm_YYYYMMDD
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --component)
      COMPONENT="${2:?missing component}"
      shift 2
      ;;
    --tag)
      PLATFORM_TAG="${2:?missing tag}"
      shift 2
      ;;
    --registry)
      REGISTRY="${2:?missing registry}"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:?missing env file}"
      shift 2
      ;;
    --no-push)
      PUSH=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

require_env_file() {
  [[ -f "$ENV_FILE" ]] || die "env file not found: $ENV_FILE"
}

load_env_if_present() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
}

build_and_push() {
  local image_name="$1"
  local dockerfile="$2"
  local image="${REGISTRY}/${image_name}:${PLATFORM_TAG}"
  shift 2

  log "Building ${image} from ${dockerfile}"
  if docker buildx version >/dev/null 2>&1; then
    docker buildx build --load --provenance=false --sbom=false -f "$dockerfile" -t "$image" "$@" .
  else
    DOCKER_BUILDKIT=0 docker build -f "$dockerfile" -t "$image" "$@" .
  fi

  if [[ "$PUSH" == "1" ]]; then
    log "Pushing ${image}"
    docker push "$image"
  fi

  docker image inspect "$image" --format '{{.Id}}'
}

build_web() {
  load_env_if_present
  build_and_push "boltz-web" "Dockerfile.web" \
    --build-arg "WEB_BASE_IMAGE=${WEB_BASE_IMAGE:-python:3.11-slim}" \
    --build-arg "NODE_BASE_IMAGE=${NODE_BASE_IMAGE:-node:24-bookworm-slim}" \
    --build-arg "NPM_REGISTRY=${NPM_REGISTRY:-https://registry.npmmirror.com}" \
    --build-arg "PIP_INDEX_URL=${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple}" \
    --build-arg "PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST:-mirrors.aliyun.com}" \
    --build-arg "APT_MIRROR=${APT_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/debian}" \
    --build-arg "APT_SECURITY_MIRROR=${APT_SECURITY_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/debian-security}"
}

build_host_metrics() {
  load_env_if_present
  build_and_push "boltz-host-metrics" "Dockerfile.host-metrics" \
    --build-arg "HOST_METRICS_BASE_IMAGE=${HOST_METRICS_BASE_IMAGE:-python:3.11-slim}" \
    --build-arg "APT_MIRROR=${APT_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/debian}" \
    --build-arg "APT_SECURITY_MIRROR=${APT_SECURITY_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/debian-security}"
}

build_protein_prep_arm() {
  load_env_if_present
  build_and_push "boltz-protein-prep" "Dockerfile.protein-prep.arm" \
    --build-arg "PROTEIN_PREP_ARM_BASE_IMAGE=${PROTEIN_PREP_ARM_BASE_IMAGE:-debian:bookworm-slim}" \
    --build-arg "APT_MIRROR=${APT_MIRROR:-http://mirrors.tuna.tsinghua.edu.cn/debian}" \
    --build-arg "APT_SECURITY_MIRROR=${APT_SECURITY_MIRROR:-http://mirrors.tuna.tsinghua.edu.cn/debian-security}" \
    --build-arg "MINIFORGE_BASE_URL=${MINIFORGE_BASE_URL:-https://mirrors.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease}" \
    --build-arg "CONDA_FORGE_CHANNEL=${CONDA_FORGE_CHANNEL:-https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge}"
}

build_protein_prep_amd() {
  load_env_if_present
  build_and_push "boltz-protein-prep" "Dockerfile.protein-prep.amd" \
    --build-arg "PROTEIN_PREP_AMD_BASE_IMAGE=${PROTEIN_PREP_AMD_BASE_IMAGE:-debian:bookworm-slim}" \
    --build-arg "APT_MIRROR=${APT_MIRROR:-http://mirrors.tuna.tsinghua.edu.cn/debian}" \
    --build-arg "APT_SECURITY_MIRROR=${APT_SECURITY_MIRROR:-http://mirrors.tuna.tsinghua.edu.cn/debian-security}" \
    --build-arg "MINIFORGE_BASE_URL=${MINIFORGE_BASE_URL:-https://mirrors.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease}" \
    --build-arg "CONDA_FORGE_CHANNEL=${CONDA_FORGE_CHANNEL:-https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge}"
}

build_ligand_prep_arm() {
  load_env_if_present
  build_and_push "boltz-ligand-prep" "Dockerfile.ligand-prep.arm" \
    --build-arg "LIGAND_PREP_ARM_BASE_IMAGE=${LIGAND_PREP_ARM_BASE_IMAGE:-debian:bookworm-slim}" \
    --build-arg "APT_MIRROR=${APT_MIRROR:-http://mirrors.tuna.tsinghua.edu.cn/debian}" \
    --build-arg "APT_SECURITY_MIRROR=${APT_SECURITY_MIRROR:-http://mirrors.tuna.tsinghua.edu.cn/debian-security}" \
    --build-arg "MINIFORGE_BASE_URL=${MINIFORGE_BASE_URL:-https://mirrors.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease}" \
    --build-arg "CONDA_FORGE_CHANNEL=${CONDA_FORGE_CHANNEL:-https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge}"
}

build_ligand_prep_amd() {
  load_env_if_present
  build_and_push "boltz-ligand-prep" "Dockerfile.ligand-prep.amd" \
    --build-arg "LIGAND_PREP_AMD_BASE_IMAGE=${LIGAND_PREP_AMD_BASE_IMAGE:-debian:bookworm-slim}" \
    --build-arg "APT_MIRROR=${APT_MIRROR:-http://mirrors.tuna.tsinghua.edu.cn/debian}" \
    --build-arg "APT_SECURITY_MIRROR=${APT_SECURITY_MIRROR:-http://mirrors.tuna.tsinghua.edu.cn/debian-security}" \
    --build-arg "MINIFORGE_BASE_URL=${MINIFORGE_BASE_URL:-https://mirrors.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease}" \
    --build-arg "CONDA_FORGE_CHANNEL=${CONDA_FORGE_CHANNEL:-https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge}"
}

require_env_file
case "$COMPONENT" in
  web)
    build_web
    ;;
  host-metrics)
    build_host_metrics
    ;;
  protein-prep-arm)
    build_protein_prep_arm
    ;;
  protein-prep-amd)
    build_protein_prep_amd
    ;;
  ligand-prep-arm)
    build_ligand_prep_arm
    ;;
  ligand-prep-amd)
    build_ligand_prep_amd
    ;;
  all)
    build_web
    build_host_metrics
    if [[ "$(uname -m)" == "aarch64" || "$(uname -m)" == "arm64" ]]; then
      build_protein_prep_arm
      build_ligand_prep_arm
    else
      build_protein_prep_amd
      build_ligand_prep_amd
    fi
    ;;
  *)
    die "unsupported component: $COMPONENT"
    ;;
esac
