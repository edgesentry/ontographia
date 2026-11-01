# bindings/typescript

Node.js bindings for Ontographia. They load `libontographia_ffi` with [koffi](https://koffi.dev/) and call `ontographia_build_cypher_from_json`. Validation and Cypher emission stay in the Rust engine. This package does not build query text itself.

npm name (not published yet): **`@edgesentry/ontographia`**. Scoped to the GitHub org so it does not take the unscoped `ontographia` name. Change it before the first publish if the org picks a different scope.

User-facing guide (`docs/typescript.md`, mkdocs nav) is intentionally not in this tree yet.

## Requirements

- Node.js **22+** (CI smoke: Node 22 and the current LTS, Node 26)
- `libontographia_ffi` on disk (`.so` / `.dylib` / `.dll`)

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

1. `ONTOGRAPHIA_FFI_LIB` (absolute or relative path to the file)
2. `$ONTOGRAPHIA_FFI_DIR/libontographia_ffi.so` (or the platform file name)
3. `<repo>/target/release`, then `<repo>/target/debug`
4. The dynamic loader's default search path (`LD_LIBRARY_PATH`, `DYLD_LIBRARY_PATH`, Windows `PATH`)

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
