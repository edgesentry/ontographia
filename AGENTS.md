# AGENTS.md

High-level guide for AI agents working in this repository.  
**Do not treat this file as the full manual** — canonical tutorials live in [`docs/`](docs/) ([published site](https://edgesentry.github.io/ontographia/)). Link instead of copying tables or long examples into issues, PRs, or new markdown files.

## What this project is

Ontographia converts **ontology definitions** + **Intent JSON** into **deterministic, parameter-bound Cypher 25** for Neo4j. Overview and golden rules: [docs/index.md](docs/index.md).

## Agent-only rules

5. **Prefer extending existing crates** (`ontographia-core`, `ontographia-adapters`) over parallel implementations in bindings.
6. **Do not edit plan files** in `.cursor/plans/` unless explicitly asked.

## Document map

| Need | Canonical doc |
|------|----------------|
| Overview, install, formats, dialects | [docs/index.md](docs/index.md) |
| Repository directories | [docs/repository-layout.md](docs/repository-layout.md) |
| Rust / Python / Go usage | [docs/rust.md](docs/rust.md), [docs/python.md](docs/python.md), [docs/go.md](docs/go.md) |
| Architecture (pipeline, COM, Intent, AST, emitters) | [docs/architecture.md](docs/architecture.md) |
| Related work (Text2Cypher / adaptive decoding) | [docs/related-work.md](docs/related-work.md) |
| Intent-layer evaluation baselines | [docs/evaluation.md](docs/evaluation.md) |
| Graph schema DDL + offline catalog diff | [docs/architecture.md](docs/architecture.md) (Graph schema governance), [docs/ontology-graph-alignment.md](docs/ontology-graph-alignment.md) |
| Neo4j setup, seed data, execution | [docs/end-to-end-neo4j.md](docs/end-to-end-neo4j.md) |
| LLM / agent Intent extraction | [skills/ontographia-cypher-builder/SKILL.md](skills/ontographia-cypher-builder/SKILL.md) |
| LiteLLM local setup | [docs/litellm-local.md](docs/litellm-local.md) |
| Release | [docs/release.md](docs/release.md) |
| CodeQL | [docs/codeql-setup.md](docs/codeql-setup.md) |
| COM / native ontology JSON Schema | [schemas/com.schema.json](schemas/com.schema.json), [schemas/native_ontology.schema.json](schemas/native_ontology.schema.json) |

Per-directory READMEs are **indexes only** — route humans and agents to `docs/`.

### Key entry points (code)

| Task | Location |
|------|----------|
| Load ontology (auto-detect format) | `ontographia_adapters::load_ontology_from_path` |
| Build query | `ontographia_core::engine::Engine::build` |
| Intent validation | `crates/ontographia-core/src/validate.rs` |
| Cypher 25 emission | `crates/ontographia-core/src/emit/cypher25.rs` |
| Add ontology format | `crates/ontographia-adapters/src/` + `registry.rs` |
| Graph schema / constraints from COM | `crates/ontographia-schema/src/` (`from_com`, `emit`, `diff`) |
| Python API | `bindings/python/src/lib.rs` |

## Standard agent workflows

| Goal | Doc |
|------|-----|
| Generate a query from an ontology | [docs/end-to-end-neo4j.md](docs/end-to-end-neo4j.md) §5–6, [docs/rust.md](docs/rust.md) |
| Run against Neo4j | [docs/end-to-end-neo4j.md](docs/end-to-end-neo4j.md) |
| Add or change ontology support | [docs/architecture.md](docs/architecture.md) (Stage 1), `crates/ontographia-adapters/` |
| Extend query capabilities | [docs/architecture.md](docs/architecture.md) (Extension points) |

## Commands (minimal)

```bash
cargo test --workspace
./scripts/start_neo4j.sh --seed
cargo run -p ontographia-adapters --example intent_to_cypher -- examples/manufacturing.native.yaml
cargo run -p ontographia-cli -- schema examples/manufacturing.native.yaml
uv sync --group dev && uv run maturin develop --release
cargo build --release -p ontographia-ffi && cd bindings/go && go test ./...
python examples/run_neo4j_demo.py --ontology examples/manufacturing.native.yaml
python scripts/neo4j_integration_test.py
```

## Testing expectations

- **Unit tests** in `ontographia-core` and adapter modules.
- **Integration tests** in `crates/ontographia-adapters/tests/integration.rs`.
- **CI**: `.github/workflows/ci.yml` — do not disable without reason.

When changing emitters or validation, run `cargo test --workspace`.

## Out of scope for agents (unless explicitly requested)

- LLM API calls inside the Rust/Python core (Intent extraction stays in the app/agent layer).
- RDF reification / full OWL reasoning.
- Neo4j live introspection or migration execution (`ontographia-schema` is offline DDL + catalog diff only).
- Duplicating tutorial content into new markdown files.

## License

Apache-2.0 — see [LICENSE](LICENSE).
