#!/usr/bin/env bash
# Pre-release validation: version match, tag availability, full release-check.
# Used by the Release workflow and documented for local CLI use.
set -euo pipefail

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "usage: $0 <X.Y.Z>" >&2
  exit 1
fi

VERSION="${VERSION#v}"
RELEASE_TAG="v${VERSION}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bash scripts/verify-release-version.sh "${RELEASE_TAG}"
bash scripts/verify-tag-not-exists.sh "${RELEASE_TAG}"
bash scripts/release-check.sh

echo "preflight ok for ${RELEASE_TAG}"
