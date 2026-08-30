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

echo "==> cargo publish dry-run (all publishable crates)"
for pkg in ontographia-core ontographia-adapters ontographia-schema ontographia-cli; do
  echo "--- $pkg"
  cargo publish -p "$pkg" --dry-run --allow-dirty
done

echo "==> maturin wheel build"
if command -v uv >/dev/null 2>&1; then
  uv sync --group dev
  uv run maturin build --release --out /tmp/ontographia-release-check-dist
else
  pip install maturin
  maturin build --release --out /tmp/ontographia-release-check-dist
fi
ls -la /tmp/ontographia-release-check-dist/*.whl

echo "release check ok"
