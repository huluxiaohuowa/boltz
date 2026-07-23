#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

REGISTRY="${REGISTRY:-swr.cn-east-3.myhuaweicloud.com/huluxiaohuowa}"
PLATFORM_TAG="${PLATFORM_TAG:-thor_$(date +%Y%m%d)}"
ENV_FILE="${ENV_FILE:-.env.web}"
COMPONENT="${COMPONENT:-web}"
PUSH="${PUSH:-1}"

log() { echo "[INFO] $*"; }
err() { echo "[ERROR] $*" >&2; }
die() { err "$*"; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  ./build_image.sh [--component web|protein-prep-thor|protein-prep-amd|all] [--tag thor_YYYYMMDD] [--registry REGISTRY] [--no-push]

Image naming follows the ictrek app convention:
  ${REGISTRY}/${image_name}:${PLATFORM_TAG}

Examples:
  ./build_image.sh
  ./build_image.sh --component web --tag thor_20260723
  PROTEIN_PREP_THOR_BASE_IMAGE=<l4t/cuda-base> ./build_image.sh --component protein-prep-thor
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
    --build-arg "WEB_BASE_IMAGE=${WEB_BASE_IMAGE:-python:3.11-slim}"
}

build_protein_prep_thor() {
  load_env_if_present
  [[ -n "${PROTEIN_PREP_THOR_BASE_IMAGE:-}" ]] || die "PROTEIN_PREP_THOR_BASE_IMAGE is required for protein-prep-thor"
  build_and_push "boltz-protein-prep" "Dockerfile.protein-prep.thor" \
    --build-arg "PROTEIN_PREP_THOR_BASE_IMAGE=${PROTEIN_PREP_THOR_BASE_IMAGE}"
}

build_protein_prep_amd() {
  load_env_if_present
  build_and_push "boltz-protein-prep" "Dockerfile.protein-prep.amd" \
    --build-arg "PROTEIN_PREP_AMD_BASE_IMAGE=${PROTEIN_PREP_AMD_BASE_IMAGE:-debian:bookworm-slim}"
}

require_env_file
case "$COMPONENT" in
  web)
    build_web
    ;;
  protein-prep-thor)
    build_protein_prep_thor
    ;;
  protein-prep-amd)
    build_protein_prep_amd
    ;;
  all)
    build_web
    if [[ -n "${PROTEIN_PREP_THOR_BASE_IMAGE:-}" ]]; then
      build_protein_prep_thor
    else
      log "Skipping protein-prep-thor: PROTEIN_PREP_THOR_BASE_IMAGE is not set"
    fi
    ;;
  *)
    die "unsupported component: $COMPONENT"
    ;;
esac
