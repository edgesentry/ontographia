#!/usr/bin/env bash
# Build the `ontographia-wasm` module and refresh the demo's size report.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../../.." && pwd)"
out="$here/../web/ontographia_wasm.wasm"

cd "$root"

if ! rustup target list --installed 2>/dev/null | grep -qx "wasm32-unknown-unknown"; then
  echo "installing wasm32-unknown-unknown target" >&2
  rustup target add wasm32-unknown-unknown
fi

# Size-first release profile, supplied through CARGO_PROFILE_* so it applies to
# every dependency unit without fighting `-C embed-bitcode` in RUSTFLAGS.
CARGO_PROFILE_RELEASE_OPT_LEVEL=z \
CARGO_PROFILE_RELEASE_LTO=true \
CARGO_PROFILE_RELEASE_PANIC=abort \
CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 \
CARGO_PROFILE_RELEASE_STRIP=symbols \
  cargo build -p ontographia-wasm --release --target wasm32-unknown-unknown

cp "$root/target/wasm32-unknown-unknown/release/ontographia_wasm.wasm" "$out"
node "$here/size.mjs"

echo "built $out"
echo "serve the repository root and open:"
echo "  http://localhost:8000/examples/plm/browser-spike/web/"
