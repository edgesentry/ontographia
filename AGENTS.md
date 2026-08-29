# AGENTS.md

High-level guide for AI agents working in this repository.  
**Do not treat this file as the full manual** — it routes you to canonical docs and code paths and states non-negotiable rules.

## What this project is

Ontographia converts **ontology definitions** (many formats) + **Intent JSON** into **deterministic, parameter-bound Cypher 25** for Neo4j.  
LLMs must **not** emit Cypher strings; they emit Intent JSON constrained by the ontology schema.

```
Ontology → Adapter → COM → validate(Intent) → QueryAst → Emitter → CYPHER 25 + params
```

## Golden rules

1. **Never generate raw Cypher in agent/LLM output paths** — only Intent JSON, then call `Engine.build()`.
2. **Ontology is the source of truth** for valid `class`, `relationship`, and `property` names.
3. **Filter values are always bound** as `$param_N`; do not string-concatenate user input into queries.
4. **Default dialect is `cypher25`** (`CYPHER 25` prefix, `FILTER` clause). Use `cypher5` only for legacy Neo4j.
5. **Prefer extending existing crates** (`ontographia-core`, `ontographia-adapters`) over parallel implementations in bindings.
6. **Do not edit plan files** in `.cursor/plans/` unless explicitly asked.

## Document map (read these, don't re-write them)

| Need | Canonical doc |
|------|----------------|
| Project overview, quick start | [README.md](README.md) |
| Neo4j setup, seed data, query execution walkthrough | [docs/end-to-end-neo4j.md](docs/end-to-end-neo4j.md) |
| LLM / agent workflow for Intent extraction | [skills/ontographia-cypher-builder/SKILL.md](skills/ontographia-cypher-builder/SKILL.md) |
| COM JSON Schema | [schemas/com.schema.json](schemas/com.schema.json) |
| Native ontology YAML Schema | [schemas/native_ontology.schema.json](schemas/native_ontology.schema.json) |

If content exists in one of the above, **link to it** instead of copying tables, tutorials, or long examples into issues, PRs, or new markdown files.

## Repository map

```
crates/ontographia-core/       COM, Intent, validate, QueryAst, emitters, Engine
crates/ontographia-adapters/   Ontology adapters + AdapterRegistry
crates/ontographia-ffi/        C ABI for Go / other languages
bindings/python/               PyO3 module (`ontographia.Engine`)
bindings/go/                   cgo wrapper
examples/                      Sample ontologies + neo4j seed + demo scripts
schemas/                       JSON Schemas (spec reference)
docs/                          Human/agent tutorials (not duplicated here)
skills/                        Agent Skill templates
```

### Key entry points (code)

| Task | Location |
|------|----------|
| Load ontology (auto-detect format) | `ontographia_adapters::load_ontology_from_path` |
| Build query | `ontographia_core::engine::Engine::build` |
| Intent validation | `crates/ontographia-core/src/validate.rs` |
| Cypher 25 emission | `crates/ontographia-core/src/emit/cypher25.rs` |
| Add ontology format | `crates/ontographia-adapters/src/` + register in `registry.rs` |
| Python API | `bindings/python/src/lib.rs` |

## Standard agent workflows

### A. Generate a query from an ontology

1. Pick or load ontology under `examples/` or user-provided path.
2. Obtain Intent JSON (from user, or via LLM with `intent_json_schema()` — see Skill doc).
3. `Engine::build(intent, Dialect::Cypher25)` (Rust) or `engine.build(intent)` (Python).
4. Return `{ query, params }` only.

Details & examples: [docs/end-to-end-neo4j.md](docs/end-to-end-neo4j.md) §5–6.

### B. Run against Neo4j

1. Ensure Neo4j 2025.06+ with Cypher 25 (`./scripts/start_neo4j.sh --seed`).
2. Load seed: `./scripts/load_neo4j_seed.sh` (or `examples/neo4j/seed.cypher` manually).
3. Execute generated query with params via Neo4j driver or `examples/run_neo4j_demo.py --execute`.

Full steps: [docs/end-to-end-neo4j.md](docs/end-to-end-neo4j.md).

### C. Add or change ontology support

1. Implement `OntologyAdapter` in `ontographia-adapters`.
2. Map to `CanonicalOntology` (COM) — do not bypass COM.
3. Add test + example file under `examples/`.
4. Run `cargo test --workspace`.

COM types: `crates/ontographia-core/src/com/mod.rs`.

### D. Extend query capabilities

1. Extend `Intent` / `QueryAst` in core (not in bindings).
2. Update validation against COM.
3. Update all emitters affected (`cypher25`, `cypher5`, `gql`).
4. Add unit tests in `emit/` and integration tests in `crates/ontographia-adapters/tests/`.

## Supported ontology formats

`.native.yaml`, `.ttl`, `.owl`, `.jsonld`, `.linkml.yaml`, `.shacl.ttl`, `.skos.ttl`, `.obo`  
Detection and routing: `crates/ontographia-adapters/src/registry.rs`.

Sample domain (same semantics, different syntax): `examples/manufacturing.*`.

## Commands (minimal)

```bash
cargo test --workspace
./scripts/start_neo4j.sh --seed
cargo run -p ontographia-adapters --example intent_to_cypher -- examples/manufacturing.native.yaml
uv sync --group dev && uv run maturin develop --release   # Python bindings
python examples/run_neo4j_demo.py --ontology examples/manufacturing.native.yaml
python scripts/neo4j_integration_test.py   # Neo4j e2e (mock LLM Intent -> Cypher -> execute)
```

## Testing expectations

- **Unit tests** in `ontographia-core` and adapter modules.
- **Integration tests** in `crates/ontographia-adapters/tests/integration.rs` (e2e ontology → Cypher).
- **CI**: `.github/workflows/ci.yml` — do not disable without reason.

When changing emitters or validation, run the full workspace test suite.

## Out of scope for agents (unless explicitly requested)

- Implementing LLM API calls inside the Rust/Python core (Intent extraction stays in the app/agent layer).
- RDF reification / full OWL reasoning.
- Neo4j schema migration tooling (use Cypher seed scripts or external tools).
- Duplicating tutorial content into new markdown files.

## License

Apache-2.0 — see [LICENSE](LICENSE).
