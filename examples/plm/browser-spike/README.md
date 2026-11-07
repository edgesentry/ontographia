# Browser / WASM spike (#155)

Path **A**: Intent JSON + ontology bytes → validate/build → **Cypher 25 + params inside the browser**, with no Node addon, no native library, and no server-side engine. The module is a thin `wasm32-unknown-unknown` build of the same `ontographia-core` + `ontographia-adapters` crates that power `otg`, so it cannot drift from the CLI.

```text
examples/plm/browser-spike/
├── wasm/            # ontographia-wasm crate: hand-written C ABI over core/adapters
├── web/             # static demo page + loader (no bundler, no wasm-bindgen)
└── scripts/         # build-wasm.sh, size.mjs, verify-node.mjs
```

Nothing here is a second implementation of query building. `bindings/typescript` still targets Node via koffi; this spike only adds the browser path.

## Quick start

```bash
# 1. Build the module (installs wasm32-unknown-unknown if missing)
examples/plm/browser-spike/scripts/build-wasm.sh

# 2. Serve the repository root — the page fetches the real fixtures
python3 -m http.server 8000

# 3. Open
#    http://localhost:8000/examples/plm/browser-spike/web/
```

The page loads [`../plm.native.yaml`](../plm.native.yaml) and every chip from [`../chips.json`](../chips.json), then compiles the selected `intent_path` with the WASM module. `?lang=ja` / `?lang=en` pins the locale and `?chip=affected_bop` deep-links a chip, which is also how the headless checks below select one.

`file://` will not work: the page and loader use `fetch`, so use any static server (Python, `npx serve`, S3, GitHub Pages, Cloudflare Pages, …). No deploy is performed by this repository.

## Bundle size

Measured with `scripts/size.mjs` after the size-first release build (`opt-level=z`, fat LTO, `panic=abort`, `codegen-units=1`, stripped). The module has **zero imports** and ships only `memory` plus five functions.

| Artifact | Raw | gzip |
|----------|-----|------|
| `ontographia_wasm.wasm` | 513,437 B (501.4 KiB) | 177,272 B (173.1 KiB) |

Sizes include the YAML/JSON-LD/Turtle/OWL/SHACL/SKOS adapters, because format detection is part of the same `load_ontology` entry point. A native-only cost like `rio_turtle` is small relative to `serde_json` + `schemars`. Re-run `scripts/build-wasm.sh` to refresh the numbers; `scripts/size.mjs` also writes `web/bundle-size.json`, which the page displays in its footer.

## API notes

The ABI is deliberately plain so it works on any static host without a JS toolchain:

| Export | Signature | Notes |
|--------|-----------|-------|
| `otg_abi_version` | `() -> u32` | Currently `1` |
| `otg_alloc` | `(len: usize) -> *mut u8` | Input buffer; free with `otg_free_input(ptr, len)` |
| `otg_build` | `(onto_ptr, onto_len, intent_ptr, intent_len, hint_ptr, hint_len, dialect_ptr, dialect_len) -> *mut u8` | Result buffer, or null on a null required pointer |
| `otg_free_input` | `(ptr, len)` | Frees an `otg_alloc` buffer |
| `otg_free_result` | `(ptr)` | Frees an `otg_build` buffer (length is in the header) |

- Strings are UTF-8. Result buffers are `[u32 little-endian payload length][JSON payload]`.
- Payload is `{"query": "...", "params": {...}}` or `{"error": "..."}`. Errors are data, not traps; panics are caught and returned as `{"error": "panic while building query"}`.
- `hint_ptr`/`dialect_ptr` may be null. The dialect defaults to `cypher25`; the hint is used only for adapter detection (pass `plm.native.yaml`).
- Memory can grow during `otg_alloc`, so the wrapper re-reads `memory.buffer` after every allocation.

[`web/ontographia-wasm.js`](web/ontographia-wasm.js) is the entire JavaScript binding — about 160 lines, no dependencies:

```js
import { loadOntographia } from "./ontographia-wasm.js";

const engine = await loadOntographia(); // or pass wasm bytes / a Response
const { query, params } = engine.buildCypher(ontologyBytes, intent, {
  dialect: "cypher25",
  ontologyPathHint: "plm.native.yaml",
});
```

## Verify

```bash
# Rust ABI/core tests (host)
cargo test -p ontographia-wasm

# Load the built .wasm in Node's WebAssembly API and compile all five Intents
node examples/plm/browser-spike/scripts/verify-node.mjs
```

Parity check against the native CLI (all five chips):

```bash
# wasm results
node examples/plm/browser-spike/scripts/verify-node.mjs --json > /tmp/wasm.json

# native results, then diff — queries and params must be identical
cargo run -q -p ontographia-cli --bin otg -- build --json \
  --ontology examples/plm/plm.native.yaml \
  --intent examples/plm/intents/01_affected_products.json
```

Headless browser check (Chrome; the page must be served, not opened from `file://`):

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --virtual-time-budget=40000 --dump-dom \
  "http://127.0.0.1:8000/examples/plm/browser-spike/web/?chip=affected_products&lang=en"
```

The dumped DOM must contain the same `CYPHER 25 …` text as `otg build`. Use a generous virtual-time budget (≈40 s): headless virtual time can advance past an in-flight intent `fetch` and leave the placeholder visible, which looks like a failure even though the page works.

## Usage notes for `ontographia-plm-demo` (paste-ready)

**English**

> The PLM demo can compile chips fully client-side. Build `examples/plm/browser-spike/scripts/build-wasm.sh`, copy `web/ontographia-wasm.js` and `web/ontographia_wasm.wasm` into the demo's static assets, and call `buildCypher(ontologyBytes, intent, { dialect: "cypher25", ontologyPathHint: "plm.native.yaml" })`. It returns `{ query, params }` deterministically from the same core crates as `otg`, with no Node addon, no server call, and no LLM. Bundle cost is ~501 KiB raw / ~173 KiB gzip. Keep chip labels bilingual (`label_ja` / `label_en`) and switch text without changing the bound Intent.

**日本語**

> PLM デモのチップはブラウザ内だけで Cypher に変換できます。`examples/plm/browser-spike/scripts/build-wasm.sh` を実行し、`web/ontographia-wasm.js` と `web/ontographia_wasm.wasm` をデモの静的アセットに配置したうえで、`buildCypher(ontologyBytes, intent, { dialect: "cypher25", ontologyPathHint: "plm.native.yaml" })` を呼び出してください。`{ query, params }` が返り、`otg` と同じコアクレートで決定的に生成されます。Node アドオンもサーバー呼び出しも LLM も不要です。バンドルサイズは raw 約 501 KiB / gzip 約 173 KiB です。チップのラベルは `label_ja` / `label_en` の二言語を保ち、バインド済み Intent を変えずに表示だけ切り替えてください。

## Scope and caveats

- **In scope:** ontology bytes + Intent → Cypher 25/5/GQL + params, executed in a real browser `WebAssembly` instance.
- **Out of scope (unchanged):** Neo4j connectivity/execution, graph seeding, LLM/Intent extraction, prompt subsetting, schema DDL/diff, 3D UI, and any deploy. The fixture is still demo seed data consumed by the app, not by this module.
- Generated `.wasm` and `web/bundle-size.json` are gitignored; run the build script first.
- The ABI is a spike surface, not a published package. If a real browser product needs typed arrays, streaming, or multiple simultaneous engines, revisit `wasm-bindgen` and a JS facade rather than extending this hand-written ABI ad hoc.
- The wasm build uses the workspace `ontographia-core`/`ontographia-adapters` crates; do not fork their logic here.
