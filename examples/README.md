# examples/

Sample ontologies, Neo4j artifacts, and runnable demos. Manufacturing files share the **same semantics** in different syntaxes.

**Walkthrough:** [docs/end-to-end-neo4j.md](../docs/end-to-end-neo4j.md) · **Graph alignment:** [docs/ontology-graph-alignment.md](../docs/ontology-graph-alignment.md)

## Ontology files

| File | Format |
|------|--------|
| [`manufacturing.native.yaml`](manufacturing.native.yaml) | Native YAML |
| [`manufacturing.owl.ttl`](manufacturing.owl.ttl) | Turtle / OWL |
| [`manufacturing.jsonld`](manufacturing.jsonld) | JSON-LD |
| [`manufacturing.linkml.yaml`](manufacturing.linkml.yaml) | LinkML |
| [`manufacturing.obo`](manufacturing.obo) | OBO |

## Neo4j

| Path | Purpose |
|------|---------|
| [`neo4j/seed.cypher`](neo4j/seed.cypher) | Seed graph (`../scripts/load_neo4j_seed.sh`) |
| [`neo4j/constraints.cypher`](neo4j/constraints.cypher) | UNIQUE constraints from ontology |
| [`neo4j/schema.json`](neo4j/schema.json) | Expected graph catalog |
| [`neo4j/catalog.snapshot.json`](neo4j/catalog.snapshot.json) | Offline label/rel-type snapshot |

## Demos

| Script | Purpose |
|--------|---------|
| [`run_neo4j_demo.py`](run_neo4j_demo.py) | Intent → Cypher → optional execute |
| [`run_llm_e2e.py`](run_llm_e2e.py) | Local-only LLM E2E |
| [`intent_to_cypher.rs`](intent_to_cypher.rs) | Rust example via `ontographia-adapters` |

## LLM layer (`llm/`)

Used by `run_llm_e2e.py` only (not CI). LiteLLM setup: [docs/litellm-local.md](../docs/litellm-local.md). Intent rules: [skills/ontographia-cypher-builder/SKILL.md](../skills/ontographia-cypher-builder/SKILL.md).
