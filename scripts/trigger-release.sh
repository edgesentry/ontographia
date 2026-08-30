#!/usr/bin/env bash
# Run local preflight checks, then trigger the Release workflow on GitHub Actions.
set -euo pipefail

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "usage: $0 <X.Y.Z>" >&2
  exit 1
fi

VERSION="${VERSION#v}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bash scripts/preflight-release.sh "${VERSION}"

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI is required to trigger the Release workflow" >&2
  exit 1
fi

echo "==> triggering Release workflow for v${VERSION}"
gh workflow run Release --ref main -f "version=${VERSION}"
echo "watch: gh run watch --workflow Release"
