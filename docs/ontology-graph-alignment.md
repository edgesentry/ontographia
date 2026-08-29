# Ontology ↔ graph alignment and executable queries

Ontographia guarantees that **generated Cypher matches the ontology (COM)**. It does **not** by itself guarantee that a Neo4j instance contains matching labels, relationship types, or data. Executable queries require a **multi-layer contract** between the engine, schema tooling, data pipelines, and operations.

See also: [architecture.md](architecture.md) (pipeline overview), [end-to-end-neo4j.md](end-to-end-neo4j.md) (manufacturing walkthrough).

## What “executable” means

| Level | Guarantee | Example failure if missing |
|-------|-----------|----------------------------|
| **L1 — Query shape** | Cypher uses valid COM `class` / `relationship` / `property` names | Syntax or unknown identifier at parse time |
| **L2 — Graph catalog** | Neo4j has the expected **labels** and **relationship types** | Query runs but returns empty; pattern may not match any data |
| **L3 — Constraints** | Business keys are unique where the ontology says `unique: true` | Duplicate nodes; MERGE behaviour diverges |
| **L4 — Data** | Nodes and edges exist for the patterns the query traverses | Valid query, zero rows |
| **L5 — Pattern rules** | Only allowed domain/range (e.g. `Product-[:has_part]->Part`) | Wrong graph shape; Neo4j does not enforce this natively |

| Layer | Ontographia / repo | App / ETL | CI / ops | Neo4j |
|-------|-------------------|-----------|----------|-------|
| **L1** | **Owns** (`validate_intent`, emitters) | Calls `Engine.build()` | Tests Intent → Cypher | Executes query |
| **L2** | **Artifacts** (`schema.json`, `diff`) | May validate writes | **Runs `diff`**, blocks deploy on drift | Stores labels / rel types implicitly |
| **L3** | **Generates** `constraints.cypher` | — | Applies DDL on deploy | Enforces UNIQUE |
| **L4** | **Example** `seed.cypher` | **Owns** production ETL / APIs | Smoke / integration tests | Stores data |
| **L5** | COM domain/range in **Intent validation only** | **Owns** write-path validation | Optional contract tests | No native GRAPH TYPE |

**Bottom line:** query generation is the engine’s job; **alignment and executability in production are shared** — not “app layer only,” but the app and data teams own everything from L2 onward that the engine does not enforce in the database.

## End-to-end flow

```
Ontology file (.native.yaml, TTL, …)
        │
        ▼
   COM (adapters) ─────────────────────────────────────┐
        │                                              │
        ├─► ontographia-core                           │
        │      Intent → validate → Cypher  (L1)        │
        │                                              │
        └─► ontographia-schema                         │
               ├─ schema.json      (expected catalog)  │
               ├─ constraints.cypher (L3 DDL)          │
               └─ diff vs catalog.snapshot.json (L2)   │
                                                       │
        ┌──────────────────────────────────────────────┘
        ▼
   Deploy / runtime
        ├─ Apply constraints.cypher            (ops / CI)
        ├─ Load or sync graph data             (ETL / app)  → L4
        ├─ Validate writes against schema.json (app / ETL)  → L2–L5
        └─ Execute generated Cypher            (app)
```

## Artifacts

| Artifact | Produced by | Used for |
|----------|-------------|----------|
| Ontology source | Domain / data modeling | Source of truth; COM input |
| [`schema.json`](../examples/neo4j/schema.json) | `emit_schema_json` / `emit_constraints` `--json-out` | Expected labels, properties, rel types + domain/range |
| [`constraints.cypher`](../examples/neo4j/constraints.cypher) | `emit_cypher25_constraints` / `--out` | Neo4j UNIQUE constraints (`unique: true` in ontology) |
| [`catalog.snapshot.json`](../examples/neo4j/catalog.snapshot.json) | Manual export or future introspection | Observed Neo4j labels / relationship types |
| [`seed.cypher`](../examples/neo4j/seed.cypher) | Hand-authored (demo) | Sample L4 data |
| Intent JSON | LLM / app / user | Query generation input |
| Generated `{ query, params }` | `Engine.build()` | Neo4j driver execution |

Regenerate schema artifacts when the ontology changes:

```bash
cargo run -p ontographia-schema --example emit_constraints -- examples/manufacturing.native.yaml \
  --out examples/neo4j/constraints.cypher \
  --json-out examples/neo4j/schema.json
```

## Who does what

### Ontographia (engine + `ontographia-schema`)

- Parse ontology → COM
- Validate Intent against COM; emit parameter-bound Cypher (**L1**)
- Derive `GraphSchema` from COM → `schema.json`, `constraints.cypher`
- Offline `diff(expected, snapshot)` for label / relationship-type drift (**L2**)

Does **not**: run Neo4j, load data, enforce writes, or prove non-empty results.

### CI / platform

- `cargo test --workspace` (schema + query tests)
- On ontology or `schema.json` change: run `emit_constraints` and fail if artifacts are stale (optional check-in)
- Apply `constraints.cypher` to staging / production before or with releases
- Run `diff(schema.json-derived, catalog.snapshot)` — or live catalog export — and **block deploy** on mismatch
- Neo4j integration tests (e.g. `scripts/neo4j_integration_test.py`) for L1 + L4 on a seeded instance

### Data / ETL team

- Own **L4**: nodes, relationships, and property values in Neo4j
- Keep ingest mappings aligned with COM class names (→ labels) and relationship names (→ rel types)
- Use `schema.json` as the **contract** for batch validation (see below)
- Prefer idempotent `MERGE` on `unique_properties` keys from `schema.json`

### Application layer

- Obtain Intent (or call `Engine.build()`); never emit raw Cypher from LLMs
- **Write path:** validate creates/updates against `schema.json` (label, rel type, allowed properties)
- **Read path:** handle empty results; distinguish “no data” from misconfigured graph
- Optional: refuse to run queries if a pre-flight catalog check failed (platform feature)

### Neo4j operations

- Run Neo4j 2025.06+ for Cypher 25
- Apply and retain constraints from `constraints.cypher`
- Restrict ad-hoc write access in production so the graph cannot drift from COM

## Using `schema.json` in app and ETL

**Yes — `schema.json` is intended as a portable contract** for anything that mutates or inspects the graph outside the Rust engine.

Structure (from COM):

```json
{
  "labels": {
    "Product": {
      "properties": { "sku": "string", "name": "string" },
      "unique_properties": ["sku"]
    }
  },
  "relationship_types": {
    "has_part": { "from_class": "Product", "to_class": "Part" }
  }
}
```

### Recommended uses

| Use case | How |
|----------|-----|
| **ETL row validation** | Reject records whose entity type is not a key in `labels` |
| **Property allow-list** | Before `SET`, ensure property name exists under that label in `schema.json` |
| **MERGE keys** | Use `unique_properties` for merge keys (e.g. `Product.sku`) |
| **Edge creation** | Check rel type exists; optionally enforce `from_class` / `to_class` (COM domain/range — **L5**, not enforced by Neo4j) |
| **CI contract test** | Compare ETL output schema or Neo4j export to `schema.json` |
| **Catalog drift** | Build `GraphSnapshot` from `SHOW LABELS` / `SHOW REL TYPE` and call `diff` (Rust) or reimplement the same logic in Python |

### What `schema.json` does not provide

- Instance data or row counts
- Proof that constraints are applied (check Neo4j separately)
- Automatic validation — consumers must load the file and implement checks
- Full SHACL / OWL reasoning (use source ontology formats for that)

### Minimal ETL check (pseudocode)

```python
import json

schema = json.load(open("schema.json"))

def validate_node(label: str, props: dict) -> None:
    if label not in schema["labels"]:
        raise ValueError(f"unknown label: {label}")
    allowed = schema["labels"][label]["properties"]
    for key in props:
        if key not in allowed:
            raise ValueError(f"unknown property {label}.{key}")

def validate_edge(rel_type: str, from_label: str, to_label: str) -> None:
    rel = schema["relationship_types"].get(rel_type)
    if rel is None:
        raise ValueError(f"unknown relationship: {rel_type}")
    if rel["from_class"] and rel["from_class"] != from_label:
        raise ValueError(f"{rel_type} expects from {rel['from_class']}, got {from_label}")
    if rel["to_class"] and rel["to_class"] != to_label:
        raise ValueError(f"{rel_type} expects to {rel['to_class']}, got {to_label}")
```

For catalog-level checks (L2), use the lighter [`catalog.snapshot.json`](../examples/neo4j/catalog.snapshot.json) or `diff` in `ontographia-schema`.

## `schema.json` vs `catalog.snapshot.json`

| File | Contents | Best for |
|------|----------|----------|
| **`schema.json`** | Labels, all properties, datatypes, `unique_properties`, rel domain/range | ETL / app write validation, documentation |
| **`catalog.snapshot.json`** | Observed `labels` + `relationship_types` only | Quick drift check vs live or exported Neo4j |

Generate both from the same ontology; compare snapshot to reality, `schema.json` to your write paths.

## Checklist before running generated queries in production

1. Ontology version pinned; `schema.json` and `constraints.cypher` regenerated from it
2. `constraints.cypher` applied to the target Neo4j
3. Catalog `diff` passes (labels and relationship types)
4. ETL / seed loaded data for the patterns queries expect (**L4**)
5. App uses `Engine.build()` (or equivalent) for reads; writes validated against `schema.json`
6. Integration test suite green against staging

## Related

- [architecture.md](architecture.md) — § Graph schema governance
- [end-to-end-neo4j.md](end-to-end-neo4j.md) — demo seed and query execution
- [`crates/ontographia-schema/`](../crates/ontographia-schema/) — `from_com`, `emit`, `diff`
