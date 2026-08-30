#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BIN="${CARGO_TARGET_DIR:-target}/release/ontographia"
if [[ ! -x "$BIN" ]]; then
  cargo build --release -p ontographia-cli
fi

OUT="$("$BIN" build \
  --ontology examples/manufacturing.native.yaml \
  --intent examples/sample_intent.json \
  --json)"
echo "$OUT" | grep -q '"query"'
echo "$OUT" | grep -q 'CYPHER 25'

SCHEMA_OUT="$(mktemp)"
trap 'rm -f "$SCHEMA_OUT"' EXIT
"$BIN" schema examples/manufacturing.native.yaml --out "$SCHEMA_OUT" >/dev/null
grep -q 'CONSTRAINT' "$SCHEMA_OUT"

echo "cli smoke test ok"
