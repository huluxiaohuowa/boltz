#!/usr/bin/env bash
set -euo pipefail

APP_NAME="boltz"
APP_ID="com.ictrek.boltz"
ROUTER_GROUP_ID="com-ictrek-boltz"
ROUTER_PAGE_ID="boltz"
ROUTER_IFRAME_SRC="/app/com.ictrek.boltz/"
ROUTER_HASH_PATH="#/app/com.ictrek.boltz/com-ictrek-boltz/boltz"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/src"
DIST_DIR="${ROOT_DIR}/dist"
STAGE_DIR="${DIST_DIR}/staging"
PACKAGE_ROOT="${DIST_DIR}/package-root"
VERSION_FILE="${ROOT_DIR}/VERSION"

log() { echo "[INFO] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

read_version() {
  [[ -f "$VERSION_FILE" ]] || echo "0.0.1" > "$VERSION_FILE"
  tr -d '[:space:]' < "$VERSION_FILE"
}

render_text_file() {
  local src="$1"
  local dst="$2"
  sed "s/__APP_VERSION__/${APP_VERSION}/g" "$src" > "$dst"
}

validate_templates() {
  grep -q "id: ${APP_ID}" "${STAGE_DIR}/manifest.yml" || die "manifest app id mismatch"
  grep -q "id: ${ROUTER_GROUP_ID}" "${STAGE_DIR}/routers.yml" || die "router group id mismatch"
  grep -q "id: ${ROUTER_PAGE_ID}" "${STAGE_DIR}/routers.yml" || die "router page id mismatch"
  grep -q "iframe-src: ${ROUTER_IFRAME_SRC}" "${STAGE_DIR}/routers.yml" || die "router iframe-src mismatch"
  grep -q "entry-point: true" "${STAGE_DIR}/routers.yml" || die "router missing entry-point"
  grep -q "embed: true" "${STAGE_DIR}/routers.yml" || die "router missing embed"
  grep -q 'HeadersRegexp(`Sec-Fetch-Dest`, `document`)' "${STAGE_DIR}/docker-compose.yml" || die "compose missing document redirect router"
  grep -q "${ROUTER_HASH_PATH}" "${STAGE_DIR}/docker-compose.yml" || die "compose redirect target mismatch"
  ! grep -R "__APP_VERSION__" "${STAGE_DIR}" >/dev/null || die "unrendered placeholder remains"
}

main() {
  require_cmd tar
  require_cmd sed

  [[ -n "${BOLTZ_WEB_IMAGE:-}" ]] || die "BOLTZ_WEB_IMAGE is required"
  APP_VERSION="${PACKAGE_VERSION:-$(read_version)}"

  rm -rf "$DIST_DIR"
  mkdir -p "$STAGE_DIR" "$PACKAGE_ROOT"

  render_text_file "${SRC_DIR}/manifest.yml" "${STAGE_DIR}/manifest.yml"
  cp "${SRC_DIR}/docker-compose.yml" "${STAGE_DIR}/docker-compose.yml"
  cp "${SRC_DIR}/configs.yml" "${STAGE_DIR}/configs.yml"
  cp "${SRC_DIR}/routers.yml" "${STAGE_DIR}/routers.yml"
  cp "${SRC_DIR}/README.zh-CN.md" "${STAGE_DIR}/README.zh-CN.md"
  cp "${SRC_DIR}/README.en.md" "${STAGE_DIR}/README.en.md"
  cat > "${STAGE_DIR}/.env" <<EOF
BOLTZ_WEB_IMAGE=${BOLTZ_WEB_IMAGE}
EOF

  validate_templates

  tar -C "$STAGE_DIR" -czf "${PACKAGE_ROOT}/app.tar.gz" .
  tar -C "$PACKAGE_ROOT" -cf "${DIST_DIR}/${APP_NAME}_${APP_VERSION}_pull.tar" app.tar.gz

  log "created ${DIST_DIR}/${APP_NAME}_${APP_VERSION}_pull.tar"
}

main "$@"
