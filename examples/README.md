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

## Runnable demos

| Script | Purpose |
|--------|---------|
| [`run_neo4j_demo.py`](run_neo4j_demo.py) | Intent → Cypher → optional Neo4j execute |
| [`intent_to_cypher.rs`](intent_to_cypher.rs) | Rust example: `cargo run -p ontographia-adapters --example intent_to_cypher -- …` |

Intent JSON rules for agents: [skills/ontographia-cypher-builder/SKILL.md](../skills/ontographia-cypher-builder/SKILL.md)
