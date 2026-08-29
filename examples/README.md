# examples/

Sample ontologies, Neo4j seed data, and runnable demos. All manufacturing files share the **same semantics** in different syntaxes.

## Ontology files (manufacturing domain)

| File | Format |
|------|--------|
| [`manufacturing.native.yaml`](manufacturing.native.yaml) | Native YAML |
| [`manufacturing.owl.ttl`](manufacturing.owl.ttl) | Turtle / OWL |
| [`manufacturing.jsonld`](manufacturing.jsonld) | JSON-LD |
| [`manufacturing.linkml.yaml`](manufacturing.linkml.yaml) | LinkML |
| [`manufacturing.obo`](manufacturing.obo) | OBO |

Graph model, properties, and seed narrative: [docs/end-to-end-neo4j.md](../docs/end-to-end-neo4j.md)

## Neo4j

| Path | Purpose |
|------|---------|
| [`neo4j/seed.cypher`](neo4j/seed.cypher) | Cypher 25 seed graph (load via [`../scripts/load_neo4j_seed.sh`](../scripts/load_neo4j_seed.sh)) |
| [`neo4j/constraints.cypher`](neo4j/constraints.cypher) | UNIQUE constraints (generated from ontology) |
| [`neo4j/schema.json`](neo4j/schema.json) | Expected graph catalog for app/ETL validation |
| [`neo4j/catalog.snapshot.json`](neo4j/catalog.snapshot.json) | Offline Neo4j label/rel-type snapshot for drift checks |

## Runnable demos

| Script | Purpose |
|--------|---------|
| [`run_neo4j_demo.py`](run_neo4j_demo.py) | Intent → Cypher → optional Neo4j execute |
| [`run_llm_e2e.py`](run_llm_e2e.py) | **Local only** — LLM Intent extraction → Cypher → Neo4j |
| [`intent_to_cypher.rs`](intent_to_cypher.rs) | Rust example: `cargo run -p ontographia-adapters --example intent_to_cypher -- …` |

## LLM layer (`examples/llm/`)

Provider-agnostic Intent extraction for local E2E (not used in CI). Wired by `run_llm_e2e.py`.

| Module | Role |
|--------|------|
| [`llm/extractors.py`](llm/extractors.py) | `mock` / OpenAI-compatible backends |
| [`llm/pipeline.py`](llm/pipeline.py) | Validate + retry loop |
| [`llm/repair.py`](llm/repair.py) | Deterministic Intent fixes |
| [`llm/fixtures.py`](llm/fixtures.py) | Mock LLM fixtures (also used by CI integration test) |

LiteLLM proxy setup: [docs/litellm-local.md](../docs/litellm-local.md)  
Graph schema alignment: [docs/ontology-graph-alignment.md](../docs/ontology-graph-alignment.md)  
Intent JSON rules for agents: [skills/ontographia-cypher-builder/SKILL.md](../skills/ontographia-cypher-builder/SKILL.md)
