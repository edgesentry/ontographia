#!/usr/bin/env bash
# Copy the workspace version from Cargo.toml into every derived manifest and
# lockfile. Idempotent, offline, and rewrites a file only when it changes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: scripts/sync-version.sh

Reads [workspace.package] version from Cargo.toml and writes it to:
  - the internal ontographia-* entries in [workspace.dependencies] (Cargo.toml)
  - bindings/typescript/package.json
  - bindings/wasm/package.json
  - workspace packages in Cargo.lock (blocks without a source line)
  - bindings/typescript/package-lock.json (top-level version and packages[""])

Idempotent and needs no network. Options:
  -h, --help  Show this help

Examples:
  scripts/sync-version.sh
EOF
}

case "${1:-}" in
  "")
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    echo "unknown argument: $1" >&2
    usage >&2
    exit 1
    ;;
esac
if [[ $# -gt 1 ]]; then
  echo "unexpected extra argument: $2" >&2
  usage >&2
  exit 1
fi

NEW="$(bash scripts/workspace-version.sh)"
if [[ -z "$NEW" ]]; then
  echo "failed to read [workspace.package] version from Cargo.toml" >&2
  exit 1
fi
if [[ ! "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$ ]]; then
  echo "invalid workspace version in Cargo.toml: $NEW" >&2
  exit 1
fi

TMPROOT="${TMPDIR:-/tmp}/ontographia-sync-version"
report() {
  local file="$1"
  local tmp="$2"
  if cmp -s "$file" "$tmp"; then
    rm -f "$tmp"
    echo "${file} already ${NEW}"
  else
    # Copy over the original so its permissions are preserved.
    cat "$tmp" > "$file"
    rm -f "$tmp"
    echo "updated ${file} -> ${NEW}"
  fi
}

# [workspace.dependencies]: internal ontographia-* entries.
cargo_tmp="$(mktemp "$TMPROOT.XXXXXX")"
if ! awk -v new="$NEW" '
  /^\[workspace\.dependencies\]/ { in_deps = 1; found = 1 }
  /^\[/ && !/^\[workspace\.dependencies\]/ { in_deps = 0 }
  in_deps && /^ontographia-/ {
    n++
    gsub(/version = "[^"]+"/, "version = \"" new "\"")
  }
  { print }
  END { if (!found || n == 0) exit 2 }
' Cargo.toml > "$cargo_tmp"; then
  rm -f "$cargo_tmp"
  echo "failed to update Cargo.toml: expected a [workspace.dependencies] section with ontographia-* entries" >&2
  exit 1
fi
report Cargo.toml "$cargo_tmp"

# npm manifests: the first two-space "version" field is the top-level one.
sync_npm_package_version() {
  local file="$1"
  local tmp
  tmp="$(mktemp "$TMPROOT.XXXXXX")"
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
    rm -f "$tmp"
    echo "failed to update ${file}: no top-level version field" >&2
    exit 1
  fi
  report "$file" "$tmp"
}

sync_npm_package_version bindings/typescript/package.json
sync_npm_package_version bindings/wasm/package.json

# Cargo.lock: workspace packages are the blocks without a source line.
lock_members="$(
  awk '
    function flush() {
      if (inblock && has_name && !has_source) print name
    }
    /^\[\[package\]\]/ { flush(); inblock = 1; has_name = 0; has_source = 0; name = ""; next }
    /^\[/ { flush(); inblock = 0; has_name = 0; has_source = 0; name = ""; next }
    inblock && /^name = "/ {
      name = $0
      sub(/^name = "/, "", name)
      sub(/"$/, "", name)
      has_name = 1
    }
    inblock && /^source = / { has_source = 1 }
    END { flush() }
  ' Cargo.lock
)"
if [[ -z "$lock_members" ]]; then
  echo "failed to parse Cargo.lock: no workspace packages (blocks without source) found" >&2
  exit 1
fi
lock_members="$(printf '%s\n' "$lock_members" | tr '\n' ' ')"

lock_tmp="$(mktemp "$TMPROOT.XXXXXX")"
if ! awk -v new="$NEW" -v names="$lock_members" '
  BEGIN {
    count = split(names, list, " ")
    total = 0
    for (i = 1; i <= count; i++) {
      if (list[i] != "") { want[list[i]] = 1; total++ }
    }
  }
  /^\[\[package\]\]/ { inblock = 1; name = "" }
  /^\[/ && !/^\[\[package\]\]/ { inblock = 0; name = "" }
  inblock && /^name = "/ {
    name = $0
    sub(/^name = "/, "", name)
    sub(/"$/, "", name)
  }
  inblock && name != "" && (name in want) && /^version = "/ {
    updated++
    print "version = \"" new "\""
    next
  }
  { print }
  END { if (updated != total) exit 3 }
' Cargo.lock > "$lock_tmp"; then
  rm -f "$lock_tmp"
  echo "failed to update Cargo.lock: could not rewrite the version of every workspace package" >&2
  exit 1
fi
report Cargo.lock "$lock_tmp"

# bindings/typescript/package-lock.json: only the two root version fields.
plock_tmp="$(mktemp "$TMPROOT.XXXXXX")"
# shellcheck disable=SC2016  # the JS code is literal; $ is a template literal
if ! node -e '
const fs = require("node:fs");
const [file, version] = process.argv.slice(1);
let data;
try {
  data = JSON.parse(fs.readFileSync(file, "utf8"));
} catch (error) {
  console.error(`failed to parse ${file}: ${error.message}`);
  process.exit(2);
}
if (
  typeof data.version !== "string" ||
  !data.packages ||
  typeof data.packages[""] !== "object" ||
  data.packages[""] === null ||
  typeof data.packages[""].version !== "string"
) {
  console.error(`failed to update ${file}: missing top-level version or packages[""].version`);
  process.exit(3);
}
data.version = version;
data.packages[""].version = version;
process.stdout.write(`${JSON.stringify(data, null, 2)}\n`);
' bindings/typescript/package-lock.json "$NEW" > "$plock_tmp"; then
  rm -f "$plock_tmp"
  echo "failed to update bindings/typescript/package-lock.json" >&2
  exit 1
fi
report bindings/typescript/package-lock.json "$plock_tmp"
