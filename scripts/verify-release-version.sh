#!/usr/bin/env bash
# Ensure git tag vX.Y.Z matches [workspace.package] version in Cargo.toml.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TAG="${1:-${GITHUB_REF_NAME:-}}"
if [[ -z "$TAG" ]]; then
  echo "usage: $0 <tag-or-vX.Y.Z>" >&2
  exit 1
fi

TAG="${TAG#v}"
CARGO="$(bash scripts/workspace-version.sh)"

if [[ ! "$TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$ ]]; then
  echo "invalid semver tag: $TAG" >&2
  exit 1
fi

if [[ "$TAG" != "$CARGO" ]]; then
  echo "version mismatch: tag v${TAG} != Cargo.toml workspace version ${CARGO}" >&2
  exit 1
fi

echo "release version ok: ${CARGO}"
