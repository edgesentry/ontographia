#!/usr/bin/env bash
# Pre-release validation: version match, tag availability, full release-check.
# Version defaults to [workspace.package] version in Cargo.toml when omitted.
# Used by Release check, Release preflight, and local CLI. See docs/release.md.
set -euo pipefail

VERSION="${1:-}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -z "$VERSION" ]]; then
  VERSION="$(bash scripts/workspace-version.sh)"
fi

VERSION="${VERSION#v}"
RELEASE_TAG="v${VERSION}"

bash scripts/verify-release-version.sh "${RELEASE_TAG}"
bash scripts/verify-tag-not-exists.sh "${RELEASE_TAG}"
bash scripts/release-check.sh

echo "preflight ok for ${RELEASE_TAG}"
