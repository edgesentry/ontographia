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

echo "==> maturin wheel build"
mkdir -p /tmp/ontographia-release-check-dist
if command -v uv >/dev/null 2>&1; then
  uv sync --group dev
  # Use the interpreter from setup-python / uv pin, not a machine-specific path in .python-version
  uv run --python "$(command -v python3)" maturin build --release --out /tmp/ontographia-release-check-dist
else
  python3 -m pip install maturin
  maturin build --release --out /tmp/ontographia-release-check-dist
fi
ls -la /tmp/ontographia-release-check-dist/*.whl

echo "release check ok"
