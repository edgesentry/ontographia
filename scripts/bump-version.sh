#!/usr/bin/env bash
# Bump the single source of truth: Cargo.toml [workspace.package].version
# Python reads the same version via maturin (pyproject.toml dynamic = ["version"]).
# bindings/typescript/package.json and bindings/wasm/package.json are kept equal
# so npm packs match the workspace.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: scripts/bump-version.sh <X.Y.Z> [options]

Updates [workspace.package].version in Cargo.toml, bindings/typescript/package.json,
and bindings/wasm/package.json.

Options:
  --commit    Stage Cargo.toml and create commit "chore: release vX.Y.Z"
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

sync_npm_package_version() {
  local file="$1"
  local tmp
  tmp="$(mktemp)"
  if ! awk -v new="$NEW" '
    !done && /^  "version": "/ {
      comma = ($0 ~ /,$/) ? "," : ""
      print "  \"version\": \"" new "\"" comma
      done = 1
      next
    }
    { print }
    END { if (!done) exit 2 }
  ' "$file" > "$tmp"; then
    echo "failed to update ${file}" >&2
    rm -f "$tmp"
    exit 1
  fi
  if ! cmp -s "$file" "$tmp"; then
    mv "$tmp" "$file"
    echo "bumped ${file} -> ${NEW}"
  else
    rm -f "$tmp"
    echo "${file} already ${NEW}"
  fi
}

CURRENT="$(bash scripts/workspace-version.sh)"
if [[ "$CURRENT" == "$NEW" ]]; then
  echo "workspace version already $NEW"
else
  awk -v new="$NEW" '
    /^\[workspace\.package\]/ { in_pkg = 1; in_deps = 0 }
    /^\[workspace\.dependencies\]/ { in_deps = 1; in_pkg = 0 }
    /^\[/ && !/^\[workspace\.package\]/ && !/^\[workspace\.dependencies\]/ { in_pkg = 0; in_deps = 0 }
    in_pkg && /^version = "/ {
      print "version = \"" new "\""
      next
    }
    in_deps && /^ontographia-/ {
      gsub(/version = "[^"]+"/, "version = \"" new "\"")
    }
    { print }
  ' Cargo.toml > Cargo.toml.tmp
  mv Cargo.toml.tmp Cargo.toml
  echo "bumped workspace version: $CURRENT -> $NEW"
fi

sync_npm_package_version bindings/typescript/package.json
sync_npm_package_version bindings/wasm/package.json

if [[ "$DO_TEST" -eq 1 ]]; then
  cargo test --workspace
fi

if [[ "$DO_COMMIT" -eq 1 ]]; then
  git add Cargo.toml bindings/typescript/package.json bindings/wasm/package.json
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
