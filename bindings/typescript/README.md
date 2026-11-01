# bindings/typescript

Node.js bindings for Ontographia. They load `libontographia_ffi` with [koffi](https://koffi.dev/) and call `ontographia_build_cypher_from_json`. Validation and Cypher emission stay in the Rust engine. This package does not build query text itself.

npm name: **`@edgesentry/ontographia`**. Scoped so it does not take the unscoped `ontographia` name. Registry upload is the GitHub Actions **Release** workflow only ([docs/release.md](../../docs/release.md)), and only when `PUBLISH_TO_REGISTRIES` is `true` and `NPM_TOKEN` is set. `npm publish` from a laptop, an agent, or this directory is forbidden. The package is not on npm until that workflow runs.

User-facing guide (`docs/typescript.md`, mkdocs nav) is intentionally not in this tree yet.

## Requirements

- Node.js **22+** (CI smoke: Node 22 and the current LTS, Node 26)
- `libontographia_ffi` (`.so` / `.dylib` / `.dll`), from the npm platform package or a local build

## Install from npm

```bash
npm install @edgesentry/ontographia
```

npm also installs one optional platform package, which contains the prebuilt shared library:

| Package | Host |
|---------|------|
| `@edgesentry/ontographia-linux-x64` | Linux x64, glibc |
| `@edgesentry/ontographia-linux-arm64` | Linux arm64, glibc |
| `@edgesentry/ontographia-darwin-arm64` | macOS Apple Silicon |
| `@edgesentry/ontographia-win32-x64` | Windows x64 |

musl/Alpine, macOS Intel, and Windows arm64 are not in that set. Point `ONTOGRAPHIA_FFI_LIB` at your own build.

The native library is not inside the main tarball. `bindings/typescript/package.json` in git does not list those optional dependencies: they are not on npm while you are developing, and `npm ci` here must succeed without them. `scripts/package-npm.mjs` writes `optionalDependencies` into the tarball. Only Release may upload that tarball. `prepublishOnly` fails `npm publish` in this directory. `scripts/publish-npm.sh` also refuses to run unless the process is the Release workflow.

## Install from a checkout

From the repository root:

```bash
cargo build --release -p ontographia-ffi
cd bindings/typescript
npm ci
npm test
npm run demo
```

`npm test` compiles TypeScript, typechecks an `Intent` fixture, and runs the Node test runner against `examples/manufacturing.native.yaml` and `examples/sample_intent.json`.

The loader looks for the shared library in this order:

1. `ONTOGRAPHIA_FFI_LIB` (absolute or relative path). This override wins. A missing file is an error; the loader does not continue.
2. `$ONTOGRAPHIA_FFI_DIR/<platform file name>` when that variable is set
3. The npm platform package (`@edgesentry/ontographia-<platform>`)
4. `<repo>/target/release`, then `<repo>/target/debug`, when this package sits inside the git checkout
5. The dynamic loader's default search path (`LD_LIBRARY_PATH`, `DYLD_LIBRARY_PATH`, Windows `PATH`)

A custom build therefore replaces the prebuild. The prebuild replaces `target/` so an npm install does not need a Rust checkout.

## API

```js
import { Engine, buildCypherFromFiles } from "@edgesentry/ontographia";

const result = buildCypherFromFiles(
  "examples/manufacturing.native.yaml",
  {
    start: { class: "Product", alias: "product" },
    return: [{ alias: "product" }],
  },
  "cypher25",
);

console.log(result.query);
console.log(result.params);
```

| Export | Role |
|--------|------|
| `buildCypherFromFiles(path, intent, dialect?)` | Read an ontology file, compile Intent JSON |
| `buildCypher(bytes, intent, dialect?, pathHint?)` | Same, with ontology bytes already in memory |
| `Engine.load(path)` / `Engine.fromBytes(data, pathHint?)` | Hold the ontology, then `engine.build(intent, dialect?)` |
| `OntographiaError` | Validation, dialect, I/O, and loader failures |

`intent` is an object matching the Rust `Intent` struct, or a JSON string. `dialect` defaults to `"cypher25"` (`"cypher5"`, `"gql"`). Unknown dialects and unknown Intent keys throw `OntographiaError`.

Types live in the package entry (`Intent`, `BuildResult`, and the nested structs).

`Engine.intent_json_schema()` is not exposed: the C ABI does not return the schema. Generate it from Rust or Python (`Engine.intent_json_schema()`).

## Execute

This package only compiles Intent JSON to Cypher plus parameters. It does not open Neo4j. Read-only execution is the Python `otg` CLI (`ontographia[cli]`, [docs/otg.md](../../docs/otg.md)). The Rust `ontographia` CLI builds queries and schema DDL; it does not execute them.

## Golden rule

Callers (including an LLM) supply Intent JSON. The binding forwards that JSON to Rust. It never invents Cypher.
