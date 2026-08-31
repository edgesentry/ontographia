#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> lint: reject Cursor-style code fences in docs/"
if grep -rEn '```[0-9]+:[0-9]+:' docs/; then
  echo "error: Cursor-style code fences (e.g. \`\`\`27:31:path) are not valid MkDocs syntax" >&2
  exit 1
fi

echo "==> build: mkdocs build --strict"
mkdocs build --strict

assert_mermaid_page() {
  local rel="$1"
  local html="$ROOT/site/$rel/index.html"
  if [[ ! -f "$html" ]]; then
    echo "error: expected built page at site/$rel/index.html" >&2
    exit 1
  fi
  if ! grep -q '<pre class="mermaid">' "$html"; then
    echo "error: site/$rel/index.html is missing a Mermaid diagram block" >&2
    exit 1
  fi
  if ! grep -q 'javascripts/mermaid.js' "$html"; then
    echo "error: site/$rel/index.html does not load javascripts/mermaid.js" >&2
    exit 1
  fi
}

echo "==> assert: built HTML structure"
ARCH="$ROOT/site/architecture/index.html"
if [[ ! -f "$ARCH" ]]; then
  echo "error: expected built page at site/architecture/index.html" >&2
  exit 1
fi
if ! grep -q '<h2 id="design-principles">Design principles</h2>' "$ARCH"; then
  echo "error: architecture page is missing the Design principles heading" >&2
  exit 1
fi
if grep -q '```[0-9]\+:[0-9]\+:' "$ARCH"; then
  echo "error: architecture page still contains Cursor-style fence markers" >&2
  exit 1
fi
if ! grep -q 'validate_intent' "$ARCH"; then
  echo "error: architecture page is missing expected Rust snippet content" >&2
  exit 1
fi

assert_mermaid_page architecture
assert_mermaid_page end-to-end-neo4j
assert_mermaid_page release

echo "docs check ok"
