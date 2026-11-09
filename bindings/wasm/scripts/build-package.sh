#!/usr/bin/env bash
# Build the browser WebAssembly module and stage an npm package.
#
# Output is derived from Cargo.lock and the pinned Rust toolchain in
# rust-toolchain.version. Nothing is published.
#
#   bindings/wasm/scripts/build-package.sh
#   bindings/wasm/scripts/build-package.sh --pack --out /tmp/ontographia-wasm
#   bindings/wasm/scripts/build-package.sh --source-only   # for `npm pack` here
#
# --source-only copies the module next to index.js so a direct `npm pack` in
# bindings/wasm includes it (the npm `prepack` script uses this).
#
# Layout under --out:
#   package/                    npm pack root (wasm + JS + types + README + LICENSE)
#   build-info.json             version, toolchain, wasm SHA-256
#   edgesentry-ontographia-wasm-<version>.tgz   only with --pack
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pkg="$(cd "$here/.." && pwd)"
root="$(cd "$pkg/../.." && pwd)"

pack=0
source_only=0
out="${WASM_NPM_OUT:-$pkg/dist}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pack) pack=1 ;;
    --source-only) source_only=1 ;;
    --out)
      out="${2:-}"
      if [[ -z "$out" ]]; then
        echo "error: --out requires a directory" >&2
        exit 1
      fi
      shift
      ;;
    -h|--help)
      sed -n '1,20p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

cd "$root"

version="$(bash scripts/workspace-version.sh)"
manifest_version="$(node -p 'require("./bindings/wasm/package.json").version')"
if [[ "$version" != "$manifest_version" ]]; then
  echo "error: bindings/wasm/package.json ${manifest_version} != workspace version ${version}" >&2
  echo "Run scripts/bump-version.sh ${version} so both npm packages stay in lockstep." >&2
  exit 1
fi

toolchain="${WASM_RUST_TOOLCHAIN:-$(tr -d '[:space:]' < "$pkg/rust-toolchain.version")}"
if [[ -z "$toolchain" ]]; then
  echo "error: bindings/wasm/rust-toolchain.version is empty" >&2
  exit 1
fi

if ! rustc "+$toolchain" --version >/dev/null 2>&1; then
  echo "installing Rust ${toolchain}" >&2
  rustup toolchain install "$toolchain" --profile minimal --no-self-update
fi
if ! rustup target list --installed --toolchain "$toolchain" | grep -qx "wasm32-unknown-unknown"; then
  echo "installing wasm32-unknown-unknown for Rust ${toolchain}" >&2
  rustup target add --toolchain "$toolchain" wasm32-unknown-unknown
fi

# Size-first release profile. CARGO_PROFILE_* applies to every dependency unit
# without fighting `-C embed-bitcode` in RUSTFLAGS.
CARGO_PROFILE_RELEASE_OPT_LEVEL=z \
CARGO_PROFILE_RELEASE_LTO=true \
CARGO_PROFILE_RELEASE_PANIC=abort \
CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 \
CARGO_PROFILE_RELEASE_STRIP=symbols \
  cargo "+$toolchain" build --locked -p ontographia-wasm --release --target wasm32-unknown-unknown

wasm="$root/target/wasm32-unknown-unknown/release/ontographia_wasm.wasm"
if [[ ! -f "$wasm" ]]; then
  echo "error: expected $wasm after the build" >&2
  exit 1
fi

if [[ "$source_only" -eq 1 ]]; then
  cp "$wasm" "$pkg/ontographia_wasm.wasm"
  chmod 0644 "$pkg/ontographia_wasm.wasm"
  cp "$root/LICENSE" "$pkg/LICENSE"
  echo "staged $pkg/ontographia_wasm.wasm and LICENSE for npm pack (Rust ${toolchain})"
  exit 0
fi

mkdir -p "$out"
stage="$out/package"
rm -rf "$stage"
mkdir -p "$stage"

cp "$wasm" "$stage/ontographia_wasm.wasm"
chmod 0644 "$stage/ontographia_wasm.wasm"
cp "$pkg/index.js" "$pkg/index.d.ts" "$pkg/README.md" "$stage/"
# The published manifest does not need development/publish guards. Keeping the
# source prepublishOnly path would break inside a tarball.
node -e '
const { readFileSync, writeFileSync } = require("node:fs");
const manifest = JSON.parse(readFileSync(process.argv[1], "utf8"));
delete manifest.scripts;
writeFileSync(process.argv[2], `${JSON.stringify(manifest, null, 2)}\n`);
' "$pkg/package.json" "$stage/package.json"
cp "$root/LICENSE" "$stage/LICENSE"

sha="$(node -e 'const {createHash}=require("node:crypto");const {readFileSync}=require("node:fs");process.stdout.write(createHash("sha256").update(readFileSync(process.argv[1])).digest("hex"))' "$wasm")"
cat > "$out/build-info.json" <<EOF
{
  "name": "@edgesentry/ontographia-wasm",
  "version": "${version}",
  "rustToolchain": "${toolchain}",
  "target": "wasm32-unknown-unknown",
  "wasm": "ontographia_wasm.wasm",
  "wasmBytes": $(wc -c < "$wasm" | tr -d ' '),
  "wasmSha256": "${sha}",
  "cargoLock": "Cargo.lock"
}
EOF

echo "staged @edgesentry/ontographia-wasm@${version} (Rust ${toolchain})"
echo "wasm sha256 ${sha}"

if [[ "$pack" -eq 1 ]]; then
  filename="$(cd "$stage" && npm pack --ignore-scripts --pack-destination "$out" --json | node -e 'let raw="";process.stdin.on("data",(chunk)=>{raw+=chunk});process.stdin.on("end",()=>{const parsed=JSON.parse(raw);process.stdout.write(parsed[0].filename)})')"
  echo "packed $out/$filename"
fi
