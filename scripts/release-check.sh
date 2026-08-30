#!/usr/bin/env bash
# Pre-release validation: tests, publish dry-runs, and wheel build.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> workspace version: $(bash scripts/workspace-version.sh)"

echo "==> cargo test --workspace"
cargo test --workspace

echo "==> CLI smoke test"
bash scripts/cli_smoke_test.sh

# Only ontographia-core can be dry-run against crates.io before this version is published.
# ontographia-adapters / -schema depend on ontographia-core = "^X.Y.Z"; cargo publish --dry-run
# and cargo package resolve that from crates.io, so they fail until core is published.
# Workspace tests + CLI build above already validate dependents via path deps.
echo "==> cargo publish dry-run (ontographia-core)"
cargo publish -p ontographia-core --dry-run --allow-dirty

echo "==> CLI release build (depends on workspace crates; validated via build, not publish dry-run)"
cargo build --release -p ontographia-cli

echo "==> maturin wheel build (3.11, 3.12, 3.13)"
mkdir -p /tmp/ontographia-release-check-dist
for py in 3.11 3.12 3.13; do
  echo "--- Python ${py}"
  uv python install "${py}"
  uv sync --group dev
  uv run --python "${py}" maturin build --release --out /tmp/ontographia-release-check-dist
done
ls -la /tmp/ontographia-release-check-dist/*.whl

echo "release check ok"
