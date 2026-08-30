# Python

Python bindings expose `ontographia.Engine` via PyO3. They call the same Rust `Engine::build()` as the CLI — no duplicated validation or emission logic.

## Requirements

- Python **3.11, 3.12, or 3.13**
- [uv](https://docs.astral.sh/uv/) recommended for local development
- Rust toolchain (for `maturin develop` from source)

## Install

**Released wheel** (after publish to PyPI):

```bash
pip install ontographia
```

**From source** (git checkout):

```bash
uv sync --group dev
uv run maturin develop --release
```

Pin the interpreter uv uses:

```bash
uv python pin 3.12   # or 3.11 / 3.13
```

## Basic usage

```python
import ontographia

engine = ontographia.Engine.load("examples/manufacturing.native.yaml")

# JSON Schema for LLM tool / constrained decoding
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

## API surface

| Method | Description |
|--------|-------------|
| `Engine.load(path)` | Load ontology from file (format auto-detected) |
| `Engine.from_bytes(data, path_hint=None)` | Load from bytes with optional path hint |
| `intent_json_schema()` | JSON Schema for Intent, enriched with ontology enums |
| `build(intent, dialect="cypher25")` | Validate Intent and return `{"query", "params"}` |
| `ontology_json()` | Serialized COM for debugging |

Dialects: `"cypher25"` (default), `"cypher5"`, `"gql"`.

## Neo4j execution

With the `neo4j` driver installed (`uv sync --group dev`):

```bash
./scripts/start_neo4j.sh --seed
uv run python examples/run_neo4j_demo.py --ontology examples/manufacturing.native.yaml --execute
```

Step-by-step tutorial: [Neo4j walkthrough](end-to-end-neo4j.md).

## LLM end-to-end (local)

For Intent extraction via a real LLM on your machine:

```bash
uv sync --group dev --group llm
uv run python examples/run_llm_e2e.py --ontology examples/manufacturing.native.yaml
```

LiteLLM proxy setup (OpenAI, Gemini, Cursor): [LiteLLM (local)](litellm-local.md).

## Tests

```bash
uv run python scripts/python_smoke_test.py
# Neo4j integration (requires running Neo4j)
NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=ontographia \
  uv run python scripts/neo4j_integration_test.py
```
