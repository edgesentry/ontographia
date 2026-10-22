# E2E example — v0.1.6 (PyPI) + Gemini 3.7 Flash via LiteLLM + local Neo4j

One question from the [Neo4j walkthrough](../../../docs/end-to-end-neo4j.md), run end-to-end with a **real LLM** and a **real Neo4j**, using the published `ontographia` **0.1.6** wheel from PyPI (no local build).

> List suppliers for parts in product SKU SPX-100

Every attempt is recorded, including failures ([`runs.json`](runs.json)). No re-runs were dropped.

## Results (2026-10-22, UTC)

| run | path | started | Cypher built | executed | rows |
|-----|------|---------|:------------:|:--------:|-----:|
| `cli_run1` | `examples/run_llm_e2e.py --execute` | 02:42:54Z | yes | yes | 2 |
| `cli_run2` | `examples/run_llm_e2e.py --execute` | 02:56:43Z | no (garbled property rejected by validation) | no | — |
| `mcp_llm` | `mcp_client.py` → `ontographia-mcp` (LLM in the loop) | 03:00:30Z | no (`build_cypher` ok=false after 1 correction) | no | — |
| `mcp_replay` | `mcp_client.py --intent-file intent.json` (no LLM) | 03:10:10Z | yes | yes (MCP `execute`, read-only) | 2 |

In the failed runs, the model output was malformed (for example `"property": "name激as_name"` and `"name Chad - wait, fix to name: supplier_name"`). Ontographia rejected those Intents, and no Cypher was emitted or executed. This is the intended safety behaviour; the LLM never writes Cypher.

### Successful run (`cli_run1`)

- Intent JSON: [`intent.json`](intent.json)
- Generated Cypher: [`query.cypher`](query.cypher)
- Bound parameters: [`params.json`](params.json)
- Result rows: [`rows.json`](rows.json) — `MikroMotors`, `FormTech` (matches the walkthrough's expected result)
- Raw console output: [`cli_run1_output.txt`](cli_run1_output.txt) (schema policy `auto`: subset first, escalated to full, 2 LLM calls)

```cypher
CYPHER 25
MATCH (product:Product)-[:has_part]->(part:Part)-[:supplied_by]->(supplier:Supplier)
FILTER product.sku = $param_0
RETURN supplier.name AS supplier_name
LIMIT 20
```

### MCP transcripts

- [`mcp_transcript_llm.json`](mcp_transcript_llm.json): `tools/list` → `list_ontology` → `intent_schema` → LLM Intent → `build_cypher` (ok=false) → LLM correction → `build_cypher` (ok=false). `execute` was not reached.
- [`mcp_transcript_replay.json`](mcp_transcript_replay.json): the same server with the `cli_run1` Intent replayed (no LLM call). `build_cypher` → `execute` returned the same 2 rows.

## Environment

- `ontographia[llm,mcp]==0.1.6` from PyPI (wheel `cp312-cp312-macosx_11_0_arm64`), plus `mcp 2.3.0`, `neo4j 6.4.1`, `openai 3.36.0`
- LiteLLM proxy `1.98.0` with [`scripts/litellm/config.yaml`](../../../scripts/litellm/config.yaml); alias `ontographia-gemini` → `gemini/gemini-3.7-flash`; `temperature=0`
- Neo4j `neo4j:2025.06` (Docker via colima), seeded with [`examples/neo4j/seed.cypher`](../../neo4j/seed.cypher)

## Reproduce

```bash
# 1. Released package in a clean venv (no Rust / maturin)
uv venv --python 3.12 .venv-0.1.6
uv pip install --python .venv-0.1.6/bin/python "ontographia[llm,mcp]==0.1.6"
export PATH="$PWD/.venv-0.1.6/bin:$PATH"

# 2. Neo4j + seed
./scripts/start_neo4j.sh --seed

# 3. LiteLLM proxy (see docs/litellm-local.md; needs GEMINI_API_KEY in scripts/litellm/.env)
#    e.g. a separate venv with "litellm[proxy]==1.98.0", started with scripts/litellm/config.yaml
source scripts/litellm/use-provider.sh gemini
export NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=ontographia

# 4a. CLI pipeline
python examples/run_llm_e2e.py --backend openai --execute --password "$NEO4J_PASSWORD" \
  --question "List suppliers for parts in product SKU SPX-100"

# 4b. MCP server over stdio (LLM emits Intent; server validates / builds / executes)
python examples/e2e/v0.1.6-gemini/mcp_client.py \
  --question "List suppliers for parts in product SKU SPX-100" \
  --out examples/e2e/v0.1.6-gemini/mcp_transcript_llm.json

# 4c. MCP replay of a saved Intent (no LLM)
python examples/e2e/v0.1.6-gemini/mcp_client.py \
  --question "List suppliers for parts in product SKU SPX-100" \
  --intent-file examples/e2e/v0.1.6-gemini/intent.json \
  --out examples/e2e/v0.1.6-gemini/mcp_transcript_replay.json
```

LLM output varies between runs even at `temperature=0`, so your results may differ.
