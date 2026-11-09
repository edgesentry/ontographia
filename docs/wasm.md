# Browser WASM (`@edgesentry/ontographia-wasm`)

`@edgesentry/ontographia-wasm` is the browser build of the same Ontographia engine. It compiles ontology bytes plus Intent JSON into parameter-bound **Cypher 25** inside a browser `WebAssembly` instance. There is no Node addon (koffi), no server call, and no LLM.

The Node-native package [`@edgesentry/ontographia`](https://www.npmjs.com/package/@edgesentry/ontographia) is separate and unchanged.

```text
Ontology bytes + Intent JSON
        │
        ▼
@edgesentry/ontographia-wasm  (wasm32-unknown-unknown)
        │  ontographia-core + ontographia-adapters
        ▼
CYPHER 25 + $params
```

## Install

```bash
npm install @edgesentry/ontographia-wasm
```

Registry upload happens only in the GitHub Actions **Release** workflow, on the `vX.Y.Z` tag, with npm Trusted Publishing (OIDC). The package version follows `[workspace.package] version` in the root `Cargo.toml`. Until the first Release, build the tarball from a checkout (below).

The tarball contains:

| File | Purpose |
|------|---------|
| `ontographia_wasm.wasm` | Module with zero imports; exports `memory` plus the ABI |
| `index.js` | ES module loader (`loadOntographia`, `OntographiaWasmError`) |
| `index.d.ts` | TypeScript declarations |
| `README.md`, `LICENSE` | Package docs and Apache-2.0 license |

## Import path and usage

```js
import { loadOntographia, OntographiaWasmError } from "@edgesentry/ontographia-wasm";

const engine = await loadOntographia(); // ./ontographia_wasm.wasm next to index.js
try {
  const { query, params } = engine.buildCypher(ontologyBytes, intent, {
    dialect: "cypher25",
    ontologyPathHint: "plm.native.yaml",
  });
} catch (error) {
  if (error instanceof OntographiaWasmError) {
    console.error(error.message); // Rust validation/build error
  }
}
```

`loadOntographia(source?)` accepts:

| Source | Behaviour |
|--------|-----------|
| omitted | Same-origin fetch of `ontographia_wasm.wasm` next to `index.js` |
| `string` / `URL` | Fetch that URL |
| `Response` | Read its body |
| `Uint8Array` / `ArrayBuffer` / `ArrayBufferView` | Use the bytes directly (Node, preloaded assets) |

`engine.abiVersion` is `1`. `buildCypher(ontology, intent, options)` returns `{ query, params }`; validation and emission stay in Rust. `intent` may be an object or a JSON string. `ontology` may be bytes or a string.

## Vite (same-origin asset)

The default source uses `new URL("./ontographia_wasm.wasm", import.meta.url)`, which Vite treats as an asset URL. The browser then fetches the `.wasm` from the same origin as the JS chunk.

If a bundler needs an explicit asset import:

```js
import wasmUrl from "@edgesentry/ontographia-wasm/ontographia_wasm.wasm?url";
import { loadOntographia } from "@edgesentry/ontographia-wasm";

const engine = await loadOntographia(wasmUrl);
```

Keep the asset on the application origin. Do not proxy the module through a third-party CDN.

## Static hosts

Any HTTP static host works: nginx, S3, GitHub Pages, Cloudflare Pages, `python3 -m http.server`. `file://` does not work because the default path uses `fetch`.

The repository demo is a plain static page: [`examples/plm/browser-spike`](https://github.com/edgesentry/ontographia/tree/main/examples/plm/browser-spike).

## CSP

The module makes no external requests and does not call `eval` or `new Function`. A restrictive policy that still works:

```text
script-src 'self' 'wasm-unsafe-eval';
connect-src 'self';
```

- `'wasm-unsafe-eval'` allows `WebAssembly.instantiate` in current Chrome, Edge, and Firefox.
- `connect-src 'self'` covers the default same-origin `.wasm` fetch. If the policy must not allow `connect-src` at all, pass the module bytes (or a preloaded `Response`) to `loadOntographia` and skip the fetch.
- No CDN, remote script, or third-party origin is involved.

## Node (headless smoke)

Node has no `file://` fetch. Read the module and pass bytes:

```js
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { loadOntographia } from "@edgesentry/ontographia-wasm";

const require = createRequire(import.meta.url);
const dir = dirname(require.resolve("@edgesentry/ontographia-wasm"));
const engine = await loadOntographia(readFileSync(join(dir, "ontographia_wasm.wasm")));
```

Node.js 22+.

## Build the package from a checkout

```bash
bash bindings/wasm/scripts/build-package.sh --pack

# Install the packed tarball in a clean directory and compile every PLM Intent.
node bindings/wasm/scripts/smoke-packed.mjs \
  --tarball bindings/wasm/dist/edgesentry-ontographia-wasm-$(bash scripts/workspace-version.sh).tgz
```

`build-package.sh` builds the existing `ontographia-wasm` crate with the pinned toolchain in `bindings/wasm/rust-toolchain.version`, `--locked` (so `Cargo.lock` fixes dependencies), and the size-first release profile. Output:

```text
bindings/wasm/dist/
├── package/                                   # npm pack root
├── build-info.json                            # version, toolchain, wasm SHA-256
└── edgesentry-ontographia-wasm-<version>.tgz
```

`wasm-bindgen` / `wasm-pack` are intentionally not used. The crate exports a small hand-written C ABI with zero imports, and `bindings/wasm/index.js` is the complete typed binding. Adding `wasm-bindgen` would add generated glue and a second toolchain pin without changing the query surface; the spike README records the same decision.

Release preflight runs `node scripts/package-wasm-npm-dry-run.mjs`, which builds and packs the tarball and asserts the wasm, JS, types, README, and LICENSE are present.

## Release

The Release workflow has two wasm jobs, both on the existing `vX.Y.Z` tag pattern:

| Job | Role |
|-----|------|
| `package-wasm-npm` | Build with the pinned toolchain, pack, install the tarball, smoke all fixed PLM Intents, upload the tarball artifact |
| `publish-wasm-npm` | Gated by `PUBLISH_TO_REGISTRIES=true`; npm Trusted Publishing (OIDC), no npm token, provenance enabled by npm for this public repository |

The GitHub Release also gets `edgesentry-ontographia-wasm-<version>.tgz`, alongside the Node-native tarballs.

Before the first publish, create `@edgesentry/ontographia-wasm` under the npm `edgesentry` organization with a placeholder version, then add the same Trusted Publisher used by the other packages (`release.yml`, empty environment, **Allow npm publish**). See [Release](release.md#npm-trusted-publishing-maintainer-once-per-package).

`npm publish` from a laptop, an agent, or `bindings/wasm` is forbidden.
