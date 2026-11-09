# @edgesentry/ontographia-wasm

Browser **WebAssembly** build of Ontographia. It compiles ontology bytes plus Intent JSON into parameter-bound **Cypher 25** inside a browser `WebAssembly` instance. No Node addon, no koffi, no server call, and no LLM.

This package is the generic browser engine. The Node-native package [`@edgesentry/ontographia`](https://www.npmjs.com/package/@edgesentry/ontographia) (koffi over `libontographia_ffi`) is separate and unchanged.

- Package source: [`bindings/wasm`](https://github.com/edgesentry/ontographia/tree/main/bindings/wasm)
- User guide: [docs/wasm.md](https://github.com/edgesentry/ontographia/blob/main/docs/wasm.md)
- Rust crate: `examples/plm/browser-spike/wasm` (`ontographia-wasm`, not published to crates.io)

The release workflow uploads the tarball; registry upload happens only in the **Release** workflow with npm Trusted Publishing (OIDC). `npm publish` from a laptop, an agent, or this directory is forbidden.

## Install

```bash
npm install @edgesentry/ontographia-wasm
```

The tarball contains the `.wasm` module, the ES module binding (`index.js`), TypeScript declarations (`index.d.ts`), and the license.

## Usage

```js
import { loadOntographia } from "@edgesentry/ontographia-wasm";

const ontology = new Uint8Array(await (await fetch("/ontologies/plm.native.yaml")).arrayBuffer());
const intent = {
  start: { class: "Part", alias: "bracket" },
  traverse: [
    { relationship: "CONTAINS", direction: "in", to: { class: "Assembly", alias: "assembly" } },
  ],
  filter: [{ alias: "bracket", property: "part_number", op: "eq", value: "DEMO-BRKT-01" }],
  return: [{ alias: "assembly", property: "part_number", as_name: "part_number" }],
  limit: 20,
};

const engine = await loadOntographia(); // ./ontographia_wasm.wasm next to index.js
const { query, params } = engine.buildCypher(ontology, intent, {
  dialect: "cypher25",
  ontologyPathHint: "plm.native.yaml",
});
```

`loadOntographia` accepts:

| Source | Behaviour |
|--------|-----------|
| omitted | Fetches `ontographia_wasm.wasm` next to `index.js` (same origin) |
| `string` / `URL` | Fetches that URL (same origin recommended) |
| `Response` | Reads the body |
| `Uint8Array` / `ArrayBuffer` / `ArrayBufferView` | Uses the bytes directly, no fetch |

`buildCypher` accepts ontology bytes (or a string) and an Intent object (or JSON string). It returns `{ query, params }`. Validation failures throw `OntographiaWasmError`; the message comes from the Rust core.

### Node (headless)

Node has no `file://` fetch. Read the module and pass bytes:

```js
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { loadOntographia } from "@edgesentry/ontographia-wasm";

const require = createRequire(import.meta.url);
const packageDir = dirname(require.resolve("@edgesentry/ontographia-wasm"));
const engine = await loadOntographia(readFileSync(join(packageDir, "ontographia_wasm.wasm")));
```

Node 22+.

## Vite and static hosts

The default source is a relative URL resolved with `new URL("./ontographia_wasm.wasm", import.meta.url)`, so Vite copies the asset and the browser fetches it from the same origin. If your bundler needs an explicit asset import:

```js
import wasmUrl from "@edgesentry/ontographia-wasm/ontographia_wasm.wasm?url";
import { loadOntographia } from "@edgesentry/ontographia-wasm";

const engine = await loadOntographia(wasmUrl);
```

Any static host works (S3, GitHub Pages, Cloudflare Pages, nginx, `python3 -m http.server`). Serve over HTTP; `file://` will not work. There is **no runtime external fetch**, no CDN, and no remote script.

## Content Security Policy

The module is self-contained. A typical policy:

```text
script-src 'self' 'wasm-unsafe-eval';
connect-src 'self';
```

- `'wasm-unsafe-eval'` (Chrome/Edge/Firefox) permits `WebAssembly.instantiate`; the binding never calls `eval` or `new Function`.
- `connect-src 'self'` is enough for the default same-origin `.wasm` fetch. Pass bytes (or a preloaded `Response`) if the policy must not allow `connect-src`.
- No external origin is contacted by this package.

## Size

Release profile: `opt-level=z`, fat LTO, `panic=abort`, `codegen-units=1`, stripped. The module has zero imports and exports only `memory` plus the ABI functions. Approximate size is **~500 KiB raw / ~173 KiB gzip**; run the build to refresh `build-info.json`.

## Build from source

From the repository root:

```bash
bash bindings/wasm/scripts/build-package.sh --pack
node bindings/wasm/scripts/smoke-packed.mjs --tarball \
  bindings/wasm/dist/edgesentry-ontographia-wasm-$(bash scripts/workspace-version.sh).tgz
```

`npm pack` inside `bindings/wasm` runs the same build through `prepack`, so a direct pack also contains the `.wasm`, JS binding, and types.

The build uses `Cargo.lock` (`--locked`) and the Rust toolchain in [`rust-toolchain.version`](rust-toolchain.version). `WASM_RUST_TOOLCHAIN` overrides the pin for a local experiment. Output:

```text
bindings/wasm/dist/
├── package/                                  # npm pack root
├── build-info.json                           # version, toolchain, wasm SHA-256
└── edgesentry-ontographia-wasm-<version>.tgz  # --pack
```

The version is read from [`Cargo.toml`](../../Cargo.toml) `[workspace.package] version` and must match this package's `package.json`. `scripts/bump-version.sh` updates both npm manifests.

## Scope

In scope: ontology bytes + Intent JSON → Cypher 25/5/GQL + params in a browser `WebAssembly` instance.

Out of scope: Neo4j connectivity or execution, graph seeding, LLM/Intent extraction, schema DDL/diff, and any deploy. The wasm build imports the workspace `ontographia-core` and `ontographia-adapters` crates; it does not fork query logic.

## License

Apache-2.0. See [LICENSE](../../LICENSE).
