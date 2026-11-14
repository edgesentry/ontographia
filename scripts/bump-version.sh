#!/usr/bin/env bash
# Bump the single source of truth: Cargo.toml [workspace.package].version,
# then derive the other manifests and lockfiles with scripts/sync-version.sh.
# Python reads the same version via maturin (pyproject.toml dynamic = ["version"]).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: scripts/bump-version.sh <X.Y.Z> [options]

Sets [workspace.package].version in Cargo.toml, then runs
scripts/sync-version.sh to update the internal dependencies, both npm
manifests, Cargo.lock, and bindings/typescript/package-lock.json.

Options:
  --commit    Stage the five version files and create commit "chore: release vX.Y.Z"
  --tag       Create annotated tag vX.Y.Z locally (avoid — use Release workflow instead)
  --push      Push current branch and tag to origin (avoid for releases)
  --no-test   Skip cargo test --workspace

Examples:
  scripts/bump-version.sh 0.2.0
  scripts/bump-version.sh 0.2.0 --commit --tag
  scripts/bump-version.sh 0.2.0 --commit --tag --push
EOF
}

NEW=""
DO_COMMIT=0
DO_TAG=0
DO_PUSH=0
DO_TEST=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --commit) DO_COMMIT=1 ;;
    --tag) DO_TAG=1; DO_COMMIT=1 ;;
    --push) DO_PUSH=1 ;;
    --no-test) DO_TEST=0 ;;
    -h|--help) usage; exit 0 ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [[ -n "$NEW" ]]; then
        echo "unexpected extra argument: $1" >&2
        exit 1
      fi
      NEW="$1"
      ;;
  esac
  shift
done

if [[ -z "$NEW" ]]; then
  usage >&2
  exit 1
fi

if [[ ! "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$ ]]; then
  echo "invalid semver: $NEW" >&2
  exit 1
fi

CURRENT="$(bash scripts/workspace-version.sh)"
if [[ "$CURRENT" == "$NEW" ]]; then
  echo "workspace version already $NEW"
else
  if ! awk -v new="$NEW" '
    /^\[workspace\.package\]/ { in_pkg = 1 }
    /^\[/ && !/^\[workspace\.package\]/ { in_pkg = 0 }
    in_pkg && /^version = "/ {
      print "version = \"" new "\""
      found = 1
      next
    }
    { print }
    END { if (!found) exit 2 }
  ' Cargo.toml > Cargo.toml.tmp; then
    rm -f Cargo.toml.tmp
    echo "failed to update [workspace.package] version in Cargo.toml" >&2
    exit 1
  fi
  cat Cargo.toml.tmp > Cargo.toml
  rm -f Cargo.toml.tmp
  echo "bumped workspace version: $CURRENT -> $NEW"
fi

bash scripts/sync-version.sh

if [[ "$DO_TEST" -eq 1 ]]; then
  cargo test --workspace
fi

if [[ "$DO_COMMIT" -eq 1 ]]; then
  git add Cargo.toml Cargo.lock bindings/typescript/package.json bindings/typescript/package-lock.json bindings/wasm/package.json
  if git diff --cached --quiet; then
    echo "nothing to commit"
  else
    git commit -m "chore: release v${NEW}"
  fi
fi

if [[ "$DO_TAG" -eq 1 ]]; then
  bash scripts/verify-release-version.sh "v${NEW}"
  if git rev-parse "v${NEW}" >/dev/null 2>&1; then
    echo "tag v${NEW} already exists" >&2
    exit 1
  fi
  git tag -a "v${NEW}" -m "Release v${NEW}"
  echo "created tag v${NEW}"
fi

if [[ "$DO_PUSH" -eq 1 ]]; then
  git push origin HEAD
  if [[ "$DO_TAG" -eq 1 ]]; then
    git push origin "v${NEW}"
  fi
fi

echo "done. workspace version: $(bash scripts/workspace-version.sh)"
