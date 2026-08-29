# schemas/

JSON Schema specifications — **reference only**; runtime types live in Rust (`crates/ontographia-core/src/com/`).

| Schema | Describes |
|--------|-----------|
| [`com.schema.json`](com.schema.json) | Canonical Ontology Model (COM) |
| [`native_ontology.schema.json`](native_ontology.schema.json) | Native YAML ontology format (`.native.yaml`) |

## Related

- COM implementation: [`crates/ontographia-core/src/com/mod.rs`](../crates/ontographia-core/src/com/mod.rs)
- Intent JSON schema is generated at runtime via `Engine.intent_json_schema()` (not a static file here)
- Sample ontologies validating against these shapes: [`examples/`](../examples/)
- Agent routing: [AGENTS.md](../AGENTS.md)
