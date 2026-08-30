# Rust

The Rust workspace owns the full pipeline: ontology adapters, COM, Intent validation, QueryAst, and Cypher emitters. Language bindings are thin wrappers around `Engine::build()`.

## Crates

| Crate | Role |
|-------|------|
| `ontographia-adapters` | Format detection, `OntologyAdapter`, `load_ontology_from_path` |
| `ontographia-core` | COM, Intent, validation, AST, emitters, `Engine` |
| `ontographia-schema` | COM → Neo4j graph schema, constraint DDL, catalog diff |
| `ontographia-ffi` | Stable C ABI for Go and other FFI callers |
| `ontographia-cli` | `build` and `schema` subcommands |

## Install

From [crates.io](https://crates.io) (after a release):

```bash
cargo add ontographia-core ontographia-adapters
# optional: schema tooling
cargo add ontographia-schema
# CLI
cargo install ontographia-cli
```

From a git checkout:

```bash
cargo test --workspace
cargo build -p ontographia-cli --release
```

## Library usage

```rust
use ontographia_adapters::load_ontology_from_path;
use ontographia_core::emit::Dialect;
use ontographia_core::engine::Engine;
use ontographia_core::intent::Intent;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let ontology = load_ontology_from_path("examples/manufacturing.native.yaml")?;
    let engine = Engine::new(ontology);

    // Optional: JSON Schema for LLM / tool constrained decoding
    let _schema = engine.intent_json_schema();

    let intent: Intent = serde_json::from_str(include_str!("../examples/sample_intent.json"))?;
    let emitted = engine.build(intent, Dialect::Cypher25)?;

    println!("{}", emitted.query);
    println!("{:?}", emitted.params);
    Ok(())
}
```

`Engine::build()` runs `validate_intent` → `build_ast` → `emit_query`. Same ontology + Intent + dialect always yields the same `{ query, params }`.

## CLI

```bash
# Build Cypher from ontology + Intent JSON file
ontographia build \
  --ontology examples/manufacturing.native.yaml \
  --intent examples/sample_intent.json \
  --json

# Emit Neo4j schema artifacts (constraints, schema.json)
ontographia schema examples/manufacturing.native.yaml --json-out schema.json
ontographia schema examples/manufacturing.native.yaml \
  --snapshot examples/neo4j/catalog.snapshot.json
```

## Examples & tests

```bash
cargo test --workspace
cargo run -p ontographia-adapters --example intent_to_cypher -- examples/manufacturing.native.yaml
bash scripts/cli_smoke_test.sh
```

## Schema tooling

`ontographia-schema` derives expected Neo4j labels and relationship types from COM, emits `CREATE CONSTRAINT` DDL, and diffs against an offline catalog snapshot. See [Ontology & graph alignment](ontology-graph-alignment.md).

## Code entry points

| Task | Location |
|------|----------|
| Build a query | `ontographia-core/src/engine.rs` |
| Validate Intent | `ontographia-core/src/validate.rs` |
| Emit Cypher 25 | `ontographia-core/src/emit/cypher25.rs` |
| COM types | `ontographia-core/src/com/mod.rs` |
| Load ontology | `ontographia-adapters/src/lib.rs`, `registry.rs` |
| Add a format | New module under `ontographia-adapters/src/` + `registry.rs` |
| Graph schema / constraints | `ontographia-schema/src/` (`from_com`, `emit`, `diff`) |
| E2E adapter tests | `ontographia-adapters/tests/integration.rs` |

## Next steps

- Full pipeline design: [Architecture](architecture.md)
- Run against Neo4j with seed data: [Neo4j walkthrough](end-to-end-neo4j.md)
