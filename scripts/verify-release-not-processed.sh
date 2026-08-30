#!/usr/bin/env bash
# Fail if this release version was already processed (re-release / workflow re-run).
# Use at the start of the Release workflow after the GitHub Release is published.
set -euo pipefail

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  echo "usage: $0 <vX.Y.Z>" >&2
  exit 1
fi

TAG="${TAG#v}"
RELEASE_TAG="v${TAG}"

git fetch --tags origin

for sentinel in "release-processed/${RELEASE_TAG}" "bindings/go/${RELEASE_TAG}"; do
  if git ls-remote --tags origin "refs/tags/${sentinel}" | grep -q .; then
    echo "error: release ${RELEASE_TAG} was already processed (refs/tags/${sentinel} exists)" >&2
    echo "tags are immutable; bump the version in Cargo.toml and publish a new release" >&2
    exit 1
  fi
done

if command -v gh >/dev/null 2>&1 && [[ -n "${GH_TOKEN:-${GITHUB_TOKEN:-}}" ]]; then
  asset_count="$(gh release view "$RELEASE_TAG" --json assets -q '.assets | length' 2>/dev/null || echo 0)"
  if [[ "$asset_count" -gt 0 ]]; then
    echo "error: release ${RELEASE_TAG} already has ${asset_count} uploaded asset(s)" >&2
    exit 1
  fi
fi

echo "release ${RELEASE_TAG} has not been processed yet"
