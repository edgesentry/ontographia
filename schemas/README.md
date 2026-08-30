# schemas/

JSON Schema specifications — runtime types live in Rust (`crates/ontographia-core/src/com/`).

| Schema | Describes |
|--------|-----------|
| [`com.schema.json`](com.schema.json) | Canonical Ontology Model (COM) |
| [`native_ontology.schema.json`](native_ontology.schema.json) | Native YAML ontology (`.native.yaml`) |

Intent JSON Schema is generated at runtime via `Engine.intent_json_schema()`. See [docs/architecture.md](../docs/architecture.md) and [docs/repository-layout.md](../docs/repository-layout.md).
