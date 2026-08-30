#!/usr/bin/env bash
# Run local preflight checks, then trigger the Release workflow on GitHub Actions.
# Version is read from Cargo.toml ([workspace.package] version).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(bash scripts/workspace-version.sh)"
RELEASE_TAG="v${VERSION}"

bash scripts/preflight-release.sh

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI is required to trigger the Release workflow" >&2
  exit 1
fi

echo "==> triggering Release workflow for ${RELEASE_TAG} (from Cargo.toml)"
gh workflow run Release --ref main
echo "watch: gh run watch --workflow Release"
