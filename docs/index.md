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
| CLI (Homebrew, primary) | `brew tap edgesentry/tap` then `brew install ontographia` ([tap](https://github.com/edgesentry/homebrew-tap) `Formula/ontographia.rb`). Rust binary; the command is `otg`. The published tap still installs `ontographia` (`build` and `schema`) until the next CLI release and a tap update. Read-only execute joins that binary in the follow-up tracked by [#121](https://github.com/edgesentry/ontographia/issues/121). Guide: [otg](otg.md) |
| CLI (Python entry point) | `uvx --from "ontographia[cli]" otg` or `pip install "ontographia[cli]"`. Same command name on the library extra, including read-only `execute` today. This is the Python install, not the Homebrew install. [otg](otg.md) |
| Rust libs | `ontographia-core`, `ontographia-adapters`, `ontographia-schema` on [crates.io](https://crates.io). `cargo install ontographia-cli` installs the CLI crate |
| Python | `pip install ontographia` (wheels for 3.11–3.13 on Linux, macOS arm64, Windows); optional Intent layer: `pip install "ontographia[llm]"` ([docs](llm.md)); optional MCP server: `pip install "ontographia[mcp]"` ([docs](mcp.md)) |
| Go | `go get github.com/edgesentry/ontographia/bindings/go@v0.1.7` (+ FFI lib from Releases) |
| TypeScript / JavaScript | `npm install @edgesentry/ontographia` (Node.js 22+). Installs a prebuilt `libontographia_ffi` for Linux x64, Linux arm64, macOS arm64, and Windows x64. Not on npm until a Release run publishes it; until then use a checkout (`bindings/typescript`). User guide deferred. |

Release process: [Release](release.md).

```bash
# Released tap today: the command is still `ontographia`.
# After the next CLI release and tap update, the same formula's command is `otg`.
ontographia build --ontology examples/manufacturing.native.yaml \
  --intent examples/sample_intent.json --json
ontographia schema examples/manufacturing.native.yaml --json-out schema.json
```

**Quickstart:** language guides ([Rust](rust.md) / [Python](python.md) / [Go](go.md)) → [Neo4j walkthrough](end-to-end-neo4j.md).

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
| Quickstart (install → Neo4j demo) | [Rust](rust.md) / [Python](python.md) / [Go](go.md) → [Neo4j walkthrough](end-to-end-neo4j.md) |
| Rust library & CLI | [Rust](rust.md) |
| `otg` CLI and packaging | [otg CLI](otg.md) |
| Python bindings (PyO3) | [Python](python.md) |
| Go bindings (cgo / FFI) | [Go](go.md) |
| TypeScript / JavaScript bindings | `bindings/typescript` (registry upload is the Release workflow only; user guide deferred) |
| Pipeline, COM, validation, emitters | [Architecture](architecture.md) |
| Related Text2Cypher / adaptive-decoding work | [Related work](related-work.md) |
| Intent layer (`ontographia[llm]`, experimental) | [Intent layer (LLM)](llm.md) |
| MCP server (`ontographia[mcp]`, experimental) | [MCP server](mcp.md) |
| Intent-layer evaluation (Track A baselines) | [Evaluation](evaluation.md) |
| Neo4j seed data + execute queries | [Neo4j walkthrough](end-to-end-neo4j.md) |
| Ontology ↔ Neo4j schema alignment | [Ontology & graph alignment](ontology-graph-alignment.md) |
| Local LLM via LiteLLM proxy | [LiteLLM (local)](litellm-local.md) |
| Release tagging & CI artifacts | [Release](release.md) |
| Repository directories | [Repository layout](repository-layout.md) |

## License

Apache-2.0
