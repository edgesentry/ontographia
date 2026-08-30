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

echo "==> cargo publish dry-run (publishable library crates)"
for pkg in ontographia-core ontographia-adapters ontographia-schema; do
  echo "--- $pkg"
  cargo publish -p "$pkg" --dry-run --allow-dirty
done

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
