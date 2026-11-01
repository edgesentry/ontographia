#!/usr/bin/env bash
# Claim a release version before builds start (prevents re-runs on the same tag).
set -euo pipefail

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  echo "usage: $0 <vX.Y.Z>" >&2
  exit 1
fi

TAG="${TAG#v}"
RELEASE_TAG="v${TAG}"
CLAIM="release-processed/${RELEASE_TAG}"
# Tag the checked-out commit. The release workflow checks out vX.Y.Z first.
# On a manual dispatch the commit that started the run can differ from the
# main commit the release tag points at, so this script uses HEAD only.
SHA="$(git rev-parse HEAD)"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git tag -a "$CLAIM" "$SHA" -m "Release processing claimed for ${RELEASE_TAG}"
git push origin "$CLAIM"
echo "claimed ${CLAIM}"
