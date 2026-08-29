# crates/

Rust workspace — engine core, ontology adapters, and C FFI.

| Crate | Role |
|-------|------|
| [`ontographia-core/`](ontographia-core/) | COM, Intent, validation, QueryAst, emitters, `Engine` |
| [`ontographia-adapters/`](ontographia-adapters/) | Multi-format ontology parsers → COM |
| [`ontographia-ffi/`](ontographia-ffi/) | C ABI consumed by Go and other language bindings |

## Where to start

| Task | Entry point |
|------|-------------|
| Build a query | [`ontographia-core/src/engine.rs`](ontographia-core/src/engine.rs) |
| Validate Intent | [`ontographia-core/src/validate.rs`](ontographia-core/src/validate.rs) |
| Emit Cypher 25 | [`ontographia-core/src/emit/cypher25.rs`](ontographia-core/src/emit/cypher25.rs) |
| COM types | [`ontographia-core/src/com/mod.rs`](ontographia-core/src/com/mod.rs) |
| Load ontology (auto-detect) | [`ontographia-adapters/src/lib.rs`](ontographia-adapters/src/lib.rs), [`registry.rs`](ontographia-adapters/src/registry.rs) |
| Add a format | New module under [`ontographia-adapters/src/`](ontographia-adapters/src/) + register in `registry.rs` |
| E2E adapter tests | [`ontographia-adapters/tests/integration.rs`](ontographia-adapters/tests/integration.rs) |

## Canonical docs

- Agent workflows (extend core, add adapters): [AGENTS.md](../AGENTS.md)
- COM / Intent JSON Schemas: [schemas/](../schemas/)
- Tutorial & Neo4j walkthrough: [docs/end-to-end-neo4j.md](../docs/end-to-end-neo4j.md)
