#!/usr/bin/env bash
# Fail if an immutable release tag already exists on origin.
# Use before triggering the Release workflow.
set -euo pipefail

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  echo "usage: $0 <vX.Y.Z>" >&2
  exit 1
fi

TAG="${TAG#v}"
RELEASE_TAG="v${TAG}"

git fetch --tags origin

check_absent() {
  local ref="$1"
  if git ls-remote --tags origin "$ref" | grep -q .; then
    echo "error: tag already exists: ${ref#refs/tags/} (tags are immutable; bump the version)" >&2
    exit 1
  fi
}

check_absent "refs/tags/${RELEASE_TAG}"
check_absent "refs/tags/release-processed/${RELEASE_TAG}"
check_absent "refs/tags/bindings/go/${RELEASE_TAG}"

echo "tag ${RELEASE_TAG} is available"
