# Ontographia

**Any ontology in, Cypher 25 out — deterministically.**

Ontographia is a multi-ontology deterministic Cypher query generation engine. It normalizes domain knowledge from RDF/OWL, LinkML, native YAML, and other formats into a Canonical Ontology Model (COM), validates LLM-extracted intent JSON against that model, and builds parameter-bound Cypher 25 queries via a GQL-aware AST.

> **AI agents:** start with [AGENTS.md](AGENTS.md) for rules, doc routing, and code entry points.

## Why

- LLM-generated Cypher suffers from schema hallucination and syntax errors
- Static query templates are expensive to maintain
- Ontologies live in many formats (W3C, LinkML, custom YAML) but graph queries need a single safe pipeline

## Architecture

```
Ontology (TTL/YAML/JSON-LD/LinkML/...)
    → Adapter → COM
    → Schema Generator → LLM Intent JSON
    → Validator → QueryAst Builder → Cypher25Emitter
    → CYPHER 25 query + params
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

## End-to-end tutorial (Neo4j)

See [docs/end-to-end-neo4j.md](docs/end-to-end-neo4j.md) for a full walkthrough:

1. Load the same manufacturing ontology in YAML / Turtle / JSON-LD / LinkML
2. Build schema and seed data in Neo4j (`examples/neo4j/seed.cypher`)
3. Generate Cypher 25 with Ontographia from Intent JSON
4. Execute the query against Neo4j (`examples/run_neo4j_demo.py`)

## Quick start (Rust)

```bash
cargo test --workspace
cargo run -p ontographia-adapters --example intent_to_cypher -- examples/manufacturing.native.yaml
```

## Quick start (Python)

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
uv sync --group dev
uv run maturin develop --release
```

```python
import ontographia

engine = ontographia.Engine.load("examples/manufacturing.native.yaml")
schema = engine.intent_json_schema()

result = engine.build({
    "start": {"class": "Product", "alias": "product"},
    "traverse": [
        {"relationship": "has_part", "direction": "out", "to": {"class": "Part", "alias": "part"}},
        {"relationship": "supplied_by", "direction": "out", "to": {"class": "Supplier", "alias": "supplier"}},
    ],
    "filter": [{"alias": "product", "property": "sku", "op": "eq", "value": "SPX-100"}],
    "return": [{"alias": "supplier", "property": "name", "as_name": "supplier_name"}],
    "limit": 20,
})

print(result["query"])
print(result["params"])
```

## Quick start (Go)

Requires Go 1.22+ and a built FFI library.

```bash
cargo build --release -p ontographia-ffi
cd bindings/go
# Linux: export LD_LIBRARY_PATH=../../target/release  # if the linker cannot find libontographia_ffi.so
go test ./...
go run ./cmd/demo
```

```go
package main

import (
	"fmt"
	"path/filepath"

	"github.com/yohei1126/ontographia/bindings/go/ontographia"
)

func main() {
	ontology := filepath.Join("examples", "manufacturing.native.yaml")
	intent := `{
		"start": {"class": "Product", "alias": "product"},
		"traverse": [
			{"relationship": "has_part", "direction": "out", "to": {"class": "Part", "alias": "part"}},
			{"relationship": "supplied_by", "direction": "out", "to": {"class": "Supplier", "alias": "supplier"}}
		],
		"filter": [{"alias": "product", "property": "sku", "op": "eq", "value": "SPX-100"}],
		"return": [{"alias": "supplier", "property": "name", "as_name": "supplier_name"}],
		"limit": 20
	}`

	result, err := ontographia.BuildCypherFromFiles(ontology, intent, "cypher25")
	if err != nil {
		panic(err)
	}
	fmt.Println(result.Query)
	fmt.Println(result.Params)
}
```

## Dialects

- `cypher25` (default) — Neo4j Cypher 25 with `FILTER` clause
- `cypher5` — legacy fallback with `WHERE`
- `gql` — GQL-oriented prototype emitter

## Project layout

| Directory | Contents |
|-----------|----------|
| [crates/](crates/README.md) | Rust engine: core, adapters, FFI |
| [bindings/](bindings/README.md) | Python and Go bindings |
| [examples/](examples/README.md) | Sample ontologies, Neo4j seed, demos |
| [schemas/](schemas/README.md) | COM and native ontology JSON Schemas |
| [scripts/](scripts/README.md) | Neo4j setup, CI tests |
| [skills/](skills/README.md) | Agent Skill templates |
| [docs/](docs/) | Tutorials ([Neo4j walkthrough](docs/end-to-end-neo4j.md)) |

## License

Apache-2.0
