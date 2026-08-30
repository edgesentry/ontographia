# Ontographia

**Any ontology in, Cypher 25 out — deterministically.**

Ontographia normalizes domain knowledge from RDF/OWL, LinkML, native YAML, and other formats into a **Canonical Ontology Model (COM)**, validates **Intent JSON** against that model, and builds **parameter-bound Cypher 25** queries via a GQL-aware AST.

```
Ontology → Adapter → COM → validate(Intent) → QueryAst → Emitter → CYPHER 25 + params
```

Intent JSON is produced outside the core (LLM or hand-authored), constrained by `intent_json_schema()`. Pipeline details: [Architecture](architecture.md).

## Why Ontographia

- LLM-generated Cypher suffers from schema hallucination and syntax errors
- Static query templates are expensive to maintain
- Ontologies live in many formats (W3C, LinkML, custom YAML) but graph queries need a single safe pipeline

## Golden rules

1. **LLMs emit Intent JSON, not Cypher** — the core validates and emits queries.
2. **Ontology is the source of truth** for class, relationship, and property names.
3. **Filter values are always bound** as `$param_N`; user input is never concatenated into query strings.
4. **Default dialect is `cypher25`** (Neo4j 2025.06+ with `FILTER` clause).

## Install (released versions)

| Target | Install |
|--------|---------|
| CLI | `cargo install ontographia-cli` or [GitHub Releases](https://github.com/edgesentry/ontographia/releases) |
| Rust libs | `ontographia-core`, `ontographia-adapters`, `ontographia-schema` on [crates.io](https://crates.io) |
| Python | `pip install ontographia` (wheels for 3.11–3.13) |
| Go | `go get github.com/edgesentry/ontographia/bindings/go@v0.1.1` (+ FFI lib from Releases) |

Release process: [Release](release.md).

```bash
# CLI example (after install)
ontographia build --ontology examples/manufacturing.native.yaml \
  --intent examples/sample_intent.json --json
ontographia schema examples/manufacturing.native.yaml --json-out schema.json
```

## Supported ontology formats

| Format | Extensions |
|--------|------------|
| Native YAML | `.native.yaml`, `.ontographia.yaml` |
| Turtle / OWL | `.ttl`, `.turtle`, `.owl` |
| JSON-LD | `.jsonld` |
| LinkML | `.linkml.yaml` |
| SHACL | `.shacl.ttl` |
| SKOS | `.skos.ttl` |
| OBO | `.obo` |

Detection and routing: `crates/ontographia-adapters/src/registry.rs`.

## Dialects

- **`cypher25`** (default) — Neo4j Cypher 25 with `CYPHER 25` prefix and `FILTER` clause
- **`cypher5`** — legacy fallback with `WHERE`
- **`gql`** — GQL-oriented prototype emitter

## Documentation map

| Topic | Page |
|-------|------|
| Rust library & CLI | [Rust](rust.md) |
| Python bindings (PyO3) | [Python](python.md) |
| Go bindings (cgo / FFI) | [Go](go.md) |
| Pipeline, COM, validation, emitters | [Architecture](architecture.md) |
| Neo4j seed data + execute queries | [Neo4j walkthrough](end-to-end-neo4j.md) |
| Ontology ↔ Neo4j schema alignment | [Ontology & graph alignment](ontology-graph-alignment.md) |
| Local LLM via LiteLLM proxy | [LiteLLM (local)](litellm-local.md) |
| Release tagging & CI artifacts | [Release](release.md) |
| Repository directories | [Repository layout](repository-layout.md) |

## License

Apache-2.0
