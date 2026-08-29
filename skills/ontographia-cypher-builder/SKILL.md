---
name: ontographia-cypher-builder
description: Build deterministic Cypher 25 queries from ontology-backed intent JSON using Ontographia. Use when translating natural language graph exploration requests into safe, parameter-bound Neo4j queries without letting the LLM write Cypher directly.
---

# Ontographia Cypher Builder

## Workflow

Follow [AGENTS.md](../../AGENTS.md) for repository rules and [docs/end-to-end-neo4j.md](../../docs/end-to-end-neo4j.md) for Neo4j execution steps.

## Manufacturing domain (default examples)

Classes: `Product`, `Part`, `Supplier`, `Plant`, `Line`, `Lot`, `DefectType`  
Relationships: `has_part`, `has_sub_part`, `supplied_by`, `located_at`, `produced_on`, `contains_part`, `has_defect`

Ontology files: `examples/manufacturing.*`  
Seed graph: `examples/neo4j/seed.cypher`

## Intent JSON shape — suppliers for a product SKU

```json
{
  "start": { "class": "Product", "alias": "product" },
  "traverse": [
    { "relationship": "has_part", "direction": "out", "to": { "class": "Part", "alias": "part" } },
    { "relationship": "supplied_by", "direction": "out", "to": { "class": "Supplier", "alias": "supplier" } }
  ],
  "filter": [
    { "alias": "product", "property": "sku", "op": "eq", "value": "SPX-100" }
  ],
  "return": [{ "alias": "supplier", "property": "name", "as_name": "supplier_name" }],
  "limit": 20
}
```

## Rules for the LLM

- Only use `class`, `relationship`, and `property` values present in the ontology schema enums.
- Never output Cypher, SQL, or other query languages.
- Use abstract operators (`eq`, `gte`, `contains`, `in`) in filters.
- Literal values in filters are bound as parameters automatically.
- For multi-level BOM (sub-assemblies), insert a `has_sub_part` traverse step between `has_part` and `supplied_by`.

## Python example

```python
import ontographia

engine = ontographia.Engine.load("examples/manufacturing.native.yaml")
schema = engine.intent_json_schema()
# Provide `schema` to the LLM structured output API

intent = ...  # from LLM
result = engine.build(intent)
cypher, params = result["query"], result["params"]
```

## Ontology format hints

| File type | Loader |
|-----------|--------|
| `.native.yaml` | Native property-graph ontology |
| `.ttl` / `.owl` | RDF/OWL Turtle (IOF-inspired manufacturing) |
| `.jsonld` | JSON-LD |
| `.linkml.yaml` | LinkML schema (internal implementation style) |
| `.obo` | OBO Format |
