#!/usr/bin/env bash
# Pre-release validation. Version defaults to [workspace.package] in Cargo.toml.
# Used by Release check, Release preflight, and local CLI. See docs/release.md.
#
# Order: version, release.yml invariants, registry reachability, public npm
# package presence, npm pack dry-run, then tag availability, then
# scripts/release-check.sh (tests, cargo publish --dry-run, wheels).
# The package check runs before the immutable-tag check so a run on a
# version that already shipped still reports whether the five packages exist.
# Nothing here publishes. GitHub Actions does not read NPM_TRUST_TOKEN.
# Outside Actions, a local NPM_TRUST_TOKEN opts into the publisher list.
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
node scripts/check-release-workflow.mjs
bash scripts/check-registry-reachability.sh
node scripts/check-npm-trusted-publishers.mjs
node scripts/package-npm-dry-run.mjs
bash scripts/verify-tag-not-exists.sh "${RELEASE_TAG}"
bash scripts/release-check.sh

echo "preflight ok for ${RELEASE_TAG}"
