#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET_DIR="${CARGO_TARGET_DIR:-target}"
OTG="${TARGET_DIR}/release/otg"

# Always rebuild. CI restores `target/` from a cache that can contain an older
# `otg` (build/schema only). Skipping cargo when that file is executable runs
# the stale binary, which rejects `execute`.
cargo build --release -p ontographia-cli

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

# Read-only execute does not need a live Neo4j for these checks.
# Missing settings exit 2. A variable-length hop range exits 1 and is not sent.
smoke_execute() {
  local bin="$1"
  "$bin" execute --help | grep -q -- '--neo4j-uri'
  "$bin" execute --help | grep -q 'read-only'

  local err code
  set +e
  err="$(
    env -u NEO4J_URI -u NEO4J_USERNAME -u NEO4J_USER -u NEO4J_PASSWORD \
      -u NEO4J_DATABASE -u ONTOGRAPHIA_ONTOLOGY \
      "$bin" execute \
        --ontology examples/manufacturing.native.yaml \
        --intent examples/sample_intent.json \
        2>&1 >/dev/null
  )"
  code=$?
  set -e
  test "$code" -eq 2
  echo "$err" | grep -q 'Neo4j is not configured'

  local wide
  wide="$(mktemp)"
  cat >"$wide" <<'EOF'
{
  "start": { "class": "Product", "alias": "product" },
  "traverse": [
    {
      "relationship": "has_part",
      "direction": "out",
      "to": { "class": "Part", "alias": "part" },
      "min_hops": 1,
      "max_hops": 4
    }
  ],
  "return": [{ "alias": "part" }]
}
EOF
  set +e
  err="$(
    "$bin" execute \
      --ontology examples/manufacturing.native.yaml \
      --intent "$wide" \
      --neo4j-uri bolt://127.0.0.1:1 \
      --neo4j-user neo4j \
      --neo4j-password secret \
      2>&1 >/dev/null
  )"
  code=$?
  set -e
  rm -f "$wide"
  test "$code" -eq 1
  echo "$err" | grep -q 'hop range 1..4'
  echo "$err" | grep -q 'single hop'
  if echo "$err" | grep -q 'secret'; then
    echo "otg execute leaked the Neo4j password" >&2
    exit 1
  fi
}

smoke_execute "$OTG"
smoke_execute "${COPY_DIR}/ontographia"

echo "cli smoke test ok"
