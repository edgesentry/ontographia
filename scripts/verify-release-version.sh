#!/usr/bin/env bash
# Ensure git tag vX.Y.Z matches [workspace.package] version in Cargo.toml and
# that every derived manifest and lockfile carries the same version.
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

NPM_JSON="bindings/typescript/package.json"
NPM_VERSION="$(awk -F'"' '/"version":/ { print $4; exit }' "$NPM_JSON")"
if [[ "$NPM_VERSION" != "$CARGO" ]]; then
  echo "version mismatch: ${NPM_JSON} ${NPM_VERSION:-<missing>} != Cargo.toml workspace version ${CARGO}" >&2
  echo "Run scripts/sync-version.sh to rewrite the npm manifests from Cargo.toml." >&2
  exit 1
fi

WASM_JSON="bindings/wasm/package.json"
WASM_VERSION="$(awk -F'"' '/"version":/ { print $4; exit }' "$WASM_JSON")"
if [[ "$WASM_VERSION" != "$CARGO" ]]; then
  echo "version mismatch: ${WASM_JSON} ${WASM_VERSION:-<missing>} != Cargo.toml workspace version ${CARGO}" >&2
  echo "Run scripts/sync-version.sh to rewrite both npm manifests from Cargo.toml." >&2
  exit 1
fi

LOCK_WS_COUNT="$(
  awk '
    function flush() {
      if (inblock && has_name && !has_source) workspace++
    }
    /^\[\[package\]\]/ { flush(); inblock = 1; has_name = 0; has_source = 0; next }
    /^\[/ { flush(); inblock = 0; has_name = 0; has_source = 0; next }
    inblock && /^name = "/ { has_name = 1 }
    inblock && /^source = / { has_source = 1 }
    END { flush(); print workspace + 0 }
  ' Cargo.lock
)"
if [[ "$LOCK_WS_COUNT" -eq 0 ]]; then
  echo "failed to read workspace packages from Cargo.lock (no blocks without source)" >&2
  exit 1
fi

LOCK_MISMATCHES="$(
  awk -v want="$CARGO" '
    function flush() {
      if (inblock && has_name && !has_source) {
        if (version == "") printf "%s <missing>\n", name
        else if (version != want) printf "%s %s\n", name, version
      }
    }
    /^\[\[package\]\]/ { flush(); inblock = 1; has_name = 0; has_source = 0; name = ""; version = ""; next }
    /^\[/ { flush(); inblock = 0; has_name = 0; has_source = 0; name = ""; version = ""; next }
    inblock && /^name = "/ {
      name = $0
      sub(/^name = "/, "", name)
      sub(/"$/, "", name)
      has_name = 1
    }
    inblock && /^version = "/ {
      version = $0
      sub(/^version = "/, "", version)
      sub(/"$/, "", version)
    }
    inblock && /^source = / { has_source = 1 }
    END { flush() }
  ' Cargo.lock
)"
if [[ -n "$LOCK_MISMATCHES" ]]; then
  echo "version mismatch: Cargo.lock workspace packages differ from Cargo.toml workspace version ${CARGO}:" >&2
  while IFS= read -r mismatch; do
    echo "  ${mismatch}" >&2
  done <<< "$LOCK_MISMATCHES"
  echo "Run scripts/sync-version.sh to rewrite Cargo.lock from Cargo.toml." >&2
  exit 1
fi

PLOCK_JSON="bindings/typescript/package-lock.json"
# shellcheck disable=SC2016  # the JS code is literal; $ is a template literal
if ! PLOCK_VERSIONS="$(node -e '
const fs = require("node:fs");
const file = process.argv[1];
let data;
try {
  data = JSON.parse(fs.readFileSync(file, "utf8"));
} catch (error) {
  console.error(`failed to parse ${file}: ${error.message}`);
  process.exit(2);
}
const top = data.version ?? "<missing>";
const root = data.packages?.[""]?.version ?? "<missing>";
process.stdout.write(`${top} ${root}`);
' "$PLOCK_JSON")"; then
  echo "failed to read ${PLOCK_JSON}" >&2
  exit 1
fi
PLOCK_TOP="${PLOCK_VERSIONS%% *}"
PLOCK_ROOT="${PLOCK_VERSIONS#* }"
if [[ "$PLOCK_TOP" != "$CARGO" ]]; then
  echo "version mismatch: ${PLOCK_JSON} version ${PLOCK_TOP} != Cargo.toml workspace version ${CARGO}" >&2
  echo "Run scripts/sync-version.sh to rewrite the TypeScript lockfile from Cargo.toml." >&2
  exit 1
fi
if [[ "$PLOCK_ROOT" != "$CARGO" ]]; then
  echo "version mismatch: ${PLOCK_JSON} packages[\"\"].version ${PLOCK_ROOT} != Cargo.toml workspace version ${CARGO}" >&2
  echo "Run scripts/sync-version.sh to rewrite the TypeScript lockfile from Cargo.toml." >&2
  exit 1
fi

echo "release version ok: ${CARGO} (npm ${NPM_VERSION}, wasm ${WASM_VERSION}, Cargo.lock, package-lock.json)"
