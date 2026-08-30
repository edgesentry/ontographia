# Repository layout

Directory index for the monorepo. Tutorials and usage guides live in this docs site — not in per-directory READMEs.

| Path | Contents |
|------|----------|
| [`crates/`](https://github.com/edgesentry/ontographia/tree/main/crates) | Rust engine: core, adapters, schema, FFI, CLI — see [Rust](rust.md) |
| [`bindings/`](https://github.com/edgesentry/ontographia/tree/main/bindings) | [Python](python.md) (PyO3) and [Go](go.md) (cgo) bindings |
| [`examples/`](https://github.com/edgesentry/ontographia/tree/main/examples) | Sample ontologies, Neo4j seed, demo scripts |
| [`schemas/`](https://github.com/edgesentry/ontographia/tree/main/schemas) | COM and native ontology JSON Schemas |
| [`scripts/`](https://github.com/edgesentry/ontographia/tree/main/scripts) | Neo4j setup, CI tests, LiteLLM helpers, release scripts |
| [`skills/`](https://github.com/edgesentry/ontographia/tree/main/skills) | Agent Skill templates (Intent extraction) |

## `crates/` workspace

| Crate | Role |
|-------|------|
| `ontographia-core` | COM, Intent, validation, QueryAst, emitters, `Engine` |
| `ontographia-adapters` | Multi-format ontology parsers → COM |
| `ontographia-schema` | COM → Neo4j schema DDL + offline catalog diff |
| `ontographia-ffi` | C ABI for Go and other bindings |
| `ontographia-cli` | `build` and `schema` subcommands |

## `examples/` highlights

| Path | Purpose |
|------|---------|
| `manufacturing.*` | Same domain in native YAML, TTL, JSON-LD, LinkML, OBO |
| `neo4j/seed.cypher` | Cypher 25 seed graph |
| `neo4j/schema.json`, `constraints.cypher` | Expected graph catalog and UNIQUE constraints |
| `run_neo4j_demo.py` | Intent → Cypher → optional Neo4j execute |
| `run_llm_e2e.py` | Local-only LLM Intent extraction E2E |
| `llm/` | Provider-agnostic Intent extraction (not used in CI) |

Details: [Neo4j walkthrough](end-to-end-neo4j.md), [Ontology & graph alignment](ontology-graph-alignment.md).

## `schemas/`

| File | Describes |
|------|-----------|
| `com.schema.json` | Canonical Ontology Model (COM) |
| `native_ontology.schema.json` | Native YAML ontology (`.native.yaml`) |

Intent JSON Schema is generated at runtime via `Engine.intent_json_schema()` (not a static file).
