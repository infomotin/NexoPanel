#!/usr/bin/env bash
set -euo pipefail

# Build a self-contained NexoPanel release tarball with pre-built Nuxt 3 frontend assets.
VERSION="${1:-1.0.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="${REPO_ROOT}/dist"
STAGE_DIR="${DIST_DIR}/nexopanel-${VERSION}"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"

# Build Nuxt 3 static SPA with relative /api/v1 base for single-port serving
pushd "${REPO_ROOT}/frontend" >/dev/null
NUXT_PUBLIC_API_BASE="/api/v1" npm run generate
popd >/dev/null

# Copy backend (excluding venv & pycache), prebuilt frontend .output/public, and scripts
mkdir -p "${STAGE_DIR}/backend" "${STAGE_DIR}/frontend/.output" "${STAGE_DIR}/scripts"
rsync -a --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' "${REPO_ROOT}/backend/" "${STAGE_DIR}/backend/"
cp -r "${REPO_ROOT}/frontend/.output/public" "${STAGE_DIR}/frontend/.output/"
cp "${REPO_ROOT}/scripts/install.sh" "${STAGE_DIR}/scripts/"
cp "${REPO_ROOT}/README.md" "${STAGE_DIR}/"
cp "${REPO_ROOT}/LICENSE" "${STAGE_DIR}/"

tar -czf "${DIST_DIR}/nexopanel-${VERSION}-linux.tar.gz" -C "$DIST_DIR" "nexopanel-${VERSION}"
rm -rf "$STAGE_DIR"

echo "Built release package: ${DIST_DIR}/nexopanel-${VERSION}-linux.tar.gz"
