#!/usr/bin/env bash
# Test scripts/sync-version.sh and scripts/verify-release-version.sh on a
# temporary copy of this checkout. Runs offline; the copy never touches git.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/ontographia-version-sync.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT HUP INT TERM

VERSION_FILES="Cargo.toml Cargo.lock bindings/typescript/package.json bindings/typescript/package-lock.json bindings/wasm/package.json"

# Changed-line counts produced by the 0.1.8 -> 0.1.9 bump (#162): the workspace
# version, the three internal dependencies, one version per workspace package in
# Cargo.lock, and the two version fields in each npm manifest.
EXPECTED_CARGO_TOML_LINES=4
EXPECTED_CARGO_LOCK_LINES=8
EXPECTED_NPM_JSON_LINES=1
EXPECTED_WASM_JSON_LINES=1
EXPECTED_PACKAGE_LOCK_LINES=2

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_eq() {
  if [[ "$1" != "$2" ]]; then
    fail "$3: expected '$2', got '$1'"
  fi
}

if ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: this test needs a git checkout (it copies tracked files with git ls-files)" >&2
  exit 1
fi

copy_tree() {
  local dest="$1"
  mkdir -p "$dest"
  git -C "$ROOT" ls-files --cached --others --exclude-standard -z |
    while IFS= read -r -d '' file; do
      mkdir -p "$dest/$(dirname "$file")"
      cp -p "$ROOT/$file" "$dest/$file"
    done
}

cargo_dep_versions() {
  awk '
    /^\[workspace\.dependencies\]/ { in_deps = 1; next }
    /^\[/ { in_deps = 0 }
    in_deps && /^ontographia-/ {
      if (match($0, /version = "[^"]+"/)) {
        v = substr($0, RSTART, RLENGTH)
        sub(/^version = "/, "", v)
        sub(/"$/, "", v)
        print v
      }
    }
  ' "$1"
}

lock_workspace_versions() {
  awk '
    function flush() {
      if (inblock && has_name && !has_source) print name " " version
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
  ' "$1"
}

# Print every package block that has a source line (registry packages).
registry_blocks() {
  awk '
    function flush() {
      if (inblock && has_source) printf "%s", block
    }
    /^\[\[package\]\]/ {
      flush()
      inblock = 1
      has_source = 0
      block = $0 "\n"
      next
    }
    /^\[/ { flush(); inblock = 0; next }
    inblock {
      block = block $0 "\n"
      if ($0 ~ /^source = /) has_source = 1
    }
    END { flush() }
  ' "$1"
}

set_workspace_version() {
  awk -v new="$1" '
    /^\[workspace\.package\]/ { in_pkg = 1 }
    /^\[/ && !/^\[workspace\.package\]/ { in_pkg = 0 }
    in_pkg && /^version = "/ { print "version = \"" new "\""; found = 1; next }
    { print }
    END { if (!found) exit 2 }
  ' Cargo.toml > Cargo.toml.tmp || {
    rm -f Cargo.toml.tmp
    fail "could not edit [workspace.package] version in Cargo.toml"
  }
  cat Cargo.toml.tmp > Cargo.toml
  rm -f Cargo.toml.tmp
}

set_lock_package_version() {
  awk -v target="$1" -v new="$2" '
    /^\[\[package\]\]/ { inblock = 1; name = "" }
    /^\[/ && !/^\[\[package\]\]/ { inblock = 0; name = "" }
    inblock && /^name = "/ {
      name = $0
      sub(/^name = "/, "", name)
      sub(/"$/, "", name)
    }
    inblock && name == target && /^version = "/ { print "version = \"" new "\""; found = 1; next }
    { print }
    END { if (!found) exit 2 }
  ' Cargo.lock > Cargo.lock.tmp || {
    rm -f Cargo.lock.tmp
    fail "could not edit $1 version in Cargo.lock"
  }
  cat Cargo.lock.tmp > Cargo.lock
  rm -f Cargo.lock.tmp
}

snapshot_checksums() {
  local out="$1"
  : > "$out"
  local file
  for file in $VERSION_FILES; do
    cksum "$file" >> "$out"
  done
}

changed_lines() {
  # One changed line contributes one '-' and one '+' line; count the additions.
  diff -u "$1" "$2" | grep -c '^+[^+]' || true
}

assert_json_version() {
  local file="$1" expected="$2" actual
  actual="$(node -p "JSON.parse(require('node:fs').readFileSync('$file', 'utf8')).version")"
  assert_eq "$actual" "$expected" "$file version"
}

plock_top() {
  node -p "JSON.parse(require('node:fs').readFileSync('bindings/typescript/package-lock.json', 'utf8')).version"
}

plock_root() {
  node -p "JSON.parse(require('node:fs').readFileSync('bindings/typescript/package-lock.json', 'utf8')).packages[''].version"
}

assert_all_versions() {
  local expected="$1" v name version
  assert_eq "$(bash scripts/workspace-version.sh)" "$expected" "workspace version"
  for v in $(cargo_dep_versions Cargo.toml); do
    assert_eq "$v" "$expected" "Cargo.toml internal dependency version"
  done
  assert_json_version bindings/typescript/package.json "$expected"
  assert_json_version bindings/wasm/package.json "$expected"
  lock_workspace_versions Cargo.lock | while read -r name version; do
    assert_eq "$version" "$expected" "Cargo.lock package ${name}"
  done
  assert_eq "$(plock_top)" "$expected" "package-lock.json version"
  assert_eq "$(plock_root)" "$expected" "package-lock.json packages[\"\"].version"
}

copy_tree "$TMP/repo" || fail "could not copy the working tree to $TMP/repo"
cd "$TMP/repo"

for file in $VERSION_FILES; do
  mkdir -p "$TMP/orig/$(dirname "$file")"
  cp -p "$file" "$TMP/orig/$file"
done

lock_count_before="$(lock_workspace_versions "$TMP/orig/Cargo.lock" | wc -l | tr -d ' ')"
[[ "$lock_count_before" -gt 0 ]] || fail "no workspace packages found in the original Cargo.lock"
dep_count_before="$(cargo_dep_versions "$TMP/orig/Cargo.toml" | wc -l | tr -d ' ')"
[[ "$dep_count_before" -gt 0 ]] || fail "no internal ontographia-* dependencies found in the original Cargo.toml"

echo "==> bump-version.sh 9.8.7 --no-test"
bash scripts/bump-version.sh 9.8.7 --no-test

assert_all_versions 9.8.7
assert_eq "$(lock_workspace_versions Cargo.lock | wc -l | tr -d ' ')" "$lock_count_before" "Cargo.lock workspace package count"
assert_eq "$(cargo_dep_versions Cargo.toml | wc -l | tr -d ' ')" "$dep_count_before" "Cargo.toml internal dependency count"

lock_workspace_versions "$TMP/orig/Cargo.lock" | awk '{ print $1 }' | sort > "$TMP/lock_names_before"
lock_workspace_versions Cargo.lock | awk '{ print $1 }' | sort > "$TMP/lock_names_after"
if ! diff -u "$TMP/lock_names_before" "$TMP/lock_names_after" >/dev/null; then
  fail "Cargo.lock workspace package names changed"
fi

registry_blocks "$TMP/orig/Cargo.lock" > "$TMP/registry_before"
registry_blocks Cargo.lock > "$TMP/registry_after"
if ! diff -u "$TMP/registry_before" "$TMP/registry_after" >/dev/null; then
  fail "Cargo.lock registry packages changed (only workspace packages may change)"
fi

echo "==> verify-release-version.sh v9.8.7"
bash scripts/verify-release-version.sh v9.8.7

echo "==> changed lines match the 0.1.9 bump shape"
assert_eq "$(changed_lines "$TMP/orig/Cargo.toml" Cargo.toml)" "$EXPECTED_CARGO_TOML_LINES" "changed lines in Cargo.toml"
assert_eq "$(changed_lines "$TMP/orig/Cargo.lock" Cargo.lock)" "$EXPECTED_CARGO_LOCK_LINES" "changed lines in Cargo.lock"
assert_eq "$(changed_lines "$TMP/orig/bindings/typescript/package.json" bindings/typescript/package.json)" "$EXPECTED_NPM_JSON_LINES" "changed lines in bindings/typescript/package.json"
assert_eq "$(changed_lines "$TMP/orig/bindings/wasm/package.json" bindings/wasm/package.json)" "$EXPECTED_WASM_JSON_LINES" "changed lines in bindings/wasm/package.json"
assert_eq "$(changed_lines "$TMP/orig/bindings/typescript/package-lock.json" bindings/typescript/package-lock.json)" "$EXPECTED_PACKAGE_LOCK_LINES" "changed lines in bindings/typescript/package-lock.json"

echo "==> sync-version.sh is idempotent"
snapshot_checksums "$TMP/checksums.before"
sync_output="$(bash scripts/sync-version.sh)"
printf '%s\n' "$sync_output"
snapshot_checksums "$TMP/checksums.after"
if ! diff -u "$TMP/checksums.before" "$TMP/checksums.after" >/dev/null; then
  fail "second sync-version.sh run changed a version file"
fi
if printf '%s\n' "$sync_output" | grep -q '^updated '; then
  fail "second sync-version.sh run reported an update"
fi

echo "==> edit only [workspace.package] version, then sync"
set_workspace_version 9.8.8
assert_eq "$(bash scripts/workspace-version.sh)" "9.8.8" "workspace version after editing Cargo.toml"
for v in $(cargo_dep_versions Cargo.toml); do
  assert_eq "$v" "9.8.7" "Cargo.toml internal dependency before sync"
done
bash scripts/sync-version.sh
assert_all_versions 9.8.8
bash scripts/verify-release-version.sh v9.8.8

echo "==> stale Cargo.lock fails verification"
set_lock_package_version ontographia-adapters 9.8.7
if bash scripts/verify-release-version.sh v9.8.8 > "$TMP/verify_stale_lock.out" 2>&1; then
  fail "verify-release-version.sh accepted a stale Cargo.lock"
fi
grep -q 'Cargo.lock' "$TMP/verify_stale_lock.out" || fail "stale Cargo.lock message does not name Cargo.lock"
grep -q 'scripts/sync-version.sh' "$TMP/verify_stale_lock.out" || fail "stale Cargo.lock message does not suggest scripts/sync-version.sh"
bash scripts/sync-version.sh >/dev/null
bash scripts/verify-release-version.sh v9.8.8

echo "==> stale package-lock.json fails verification"
# shellcheck disable=SC2016  # the JS code is literal; $ is a template literal
node -e '
const fs = require("node:fs");
const file = "bindings/typescript/package-lock.json";
const data = JSON.parse(fs.readFileSync(file, "utf8"));
data.packages[""].version = "9.8.7";
fs.writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`);
'
if bash scripts/verify-release-version.sh v9.8.8 > "$TMP/verify_stale_plock.out" 2>&1; then
  fail "verify-release-version.sh accepted a stale package-lock.json"
fi
grep -q 'package-lock.json' "$TMP/verify_stale_plock.out" || fail "stale package-lock.json message does not name the file"
grep -q 'scripts/sync-version.sh' "$TMP/verify_stale_plock.out" || fail "stale package-lock.json message does not suggest scripts/sync-version.sh"
bash scripts/sync-version.sh >/dev/null
bash scripts/verify-release-version.sh v9.8.8

echo "==> cargo metadata --locked"
if ! cargo metadata --locked --format-version 1 --no-deps --offline >/dev/null; then
  echo "note: cargo metadata --offline failed; retrying without --offline"
  cargo metadata --locked --format-version 1 --no-deps >/dev/null
fi

echo "version sync test ok"
