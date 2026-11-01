#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET_DIR="${CARGO_TARGET_DIR:-target}"
OTG="${TARGET_DIR}/release/otg"

if [[ ! -x "$OTG" ]]; then
  cargo build --release -p ontographia-cli
fi

smoke_build_and_schema() {
  local bin="$1"
  local out schema_out
  out="$("$bin" build \
    --ontology examples/manufacturing.native.yaml \
    --intent examples/sample_intent.json \
    --json)"
  echo "$out" | grep -q '"query"'
  echo "$out" | grep -q 'CYPHER 25'

  schema_out="$(mktemp)"
  "$bin" schema examples/manufacturing.native.yaml --out "$schema_out" >/dev/null
  grep -q 'CONSTRAINT' "$schema_out"
  rm -f "$schema_out"
}

smoke_build_and_schema "$OTG"

# Release archives copy this file to `ontographia` for the current tap formula.
# The compiled command name stays `otg`.
COPY_DIR="$(mktemp -d)"
trap 'rm -rf "$COPY_DIR"' EXIT
cp "$OTG" "${COPY_DIR}/ontographia"
chmod +x "${COPY_DIR}/ontographia"
smoke_build_and_schema "${COPY_DIR}/ontographia"

"$OTG" --version | grep -q '^otg '
"${COPY_DIR}/ontographia" --version | grep -q '^otg '

echo "cli smoke test ok"
