#!/usr/bin/env bash
# Read workspace.package.version from the root Cargo.toml.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CARGO_TOML="${ROOT}/Cargo.toml"

workspace_version() {
  awk '
    /^\[workspace\.package\]/ { in_pkg = 1; next }
    /^\[/ { in_pkg = 0 }
    in_pkg && /^version = "/ {
      gsub(/^version = "|"$/, "", $0)
      print $0
      exit
    }
  ' "$CARGO_TOML"
}

workspace_version
