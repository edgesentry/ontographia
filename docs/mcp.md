# MCP server (`ontographia[mcp]`)

**Status: experimental / 0.x.** The Model Context Protocol (MCP) server lets
Claude Desktop, Cursor, and other MCP clients turn questions into
**ontology-validated Intent JSON** and **parameter-bound Cypher 25** through
Ontographia — without the model writing Cypher.

```bash
pip install "ontographia[mcp]"
# or launch without a local venv:
uvx --from "ontographia[mcp]" ontographia-mcp --ontology /path/to/ontology.native.yaml
```

Importing `ontographia` without the extra still works. Importing
`ontographia.mcp` without the extra raises `ImportError` with install guidance.

The server **does not call an LLM**. The MCP *client* (host app) is responsible
for producing Intent JSON; Ontographia only validates, emits, and optionally
executes.

## Tools

| Tool | Input | Output |
|------|--------|--------|
| `list_ontology` | _(none)_ | Summary: `classes`, `relationships`, `properties`, plus name lists |
| `intent_schema` | _(none)_ | Intent JSON Schema constrained to the loaded ontology (what the LLM must emit) |
| `build_cypher` | `intent` (object), optional `dialect` | `{ok, query, params, dialect}` or `{ok: false, errors: [{message}]}` |
| `execute` | `intent` (object), optional `dialect`, `row_limit` | Same as build, plus `rows` / `row_count` / `truncated` — or a clear Neo4j/config error |

**Key safety property:** the server never accepts raw Cypher from the client.
`execute` only runs Cypher that Ontographia generated from validated Intent.

Align tool usage with the Agent Skill
[`skills/ontographia-cypher-builder/SKILL.md`](https://github.com/edgesentry/ontographia/blob/main/skills/ontographia-cypher-builder/SKILL.md):
call `intent_schema` → emit Intent → `build_cypher` or `execute`.

## Configuration

| Source | Keys |
|--------|------|
| CLI | `--ontology PATH` (required unless env set), `--neo4j-uri`, `--neo4j-user`, `--neo4j-password`, `--neo4j-database`, `--row-limit`, `--dialect` |
| Env | `ONTOGRAPHIA_ONTOLOGY`, `NEO4J_URI`, `NEO4J_USERNAME` or `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `ONTOGRAPHIA_MCP_ROW_LIMIT`, `ONTOGRAPHIA_DIALECT` |

If Neo4j is not configured, `list_ontology` / `intent_schema` / `build_cypher`
still work; `execute` returns `{ok: false, errors: [{code: "neo4j_not_configured", ...}]}`.

Transport: **stdio** (default). Suitable for Desktop / Cursor MCP configs.

## Claude Desktop

Add to Claude Desktop MCP settings (paths are examples):

```json
{
  "mcpServers": {
    "ontographia": {
      "command": "uvx",
      "args": [
        "--from",
        "ontographia[mcp]",
        "ontographia-mcp",
        "--ontology",
        "/absolute/path/to/manufacturing.native.yaml"
      ],
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "changeme",
        "NEO4J_DATABASE": "neo4j"
      }
    }
  }
}
```

Omit the `env` block (or leave Neo4j vars unset) if you only need schema / build
tools without live execution.

## Cursor (`mcp.json`)

```json
{
  "mcpServers": {
    "ontographia": {
      "command": "uvx",
      "args": [
        "--from",
        "ontographia[mcp]",
        "ontographia-mcp",
        "--ontology",
        "/absolute/path/to/manufacturing.native.yaml"
      ],
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "changeme"
      }
    }
  }
}
```

From a local checkout (editable wheel via maturin):

```bash
uv sync --group dev
uv run maturin develop --release
uv run ontographia-mcp --ontology examples/manufacturing.native.yaml
```

The console script `ontographia-mcp` is declared in `pyproject.toml` and ships
in the maturin-built wheel.

## Safety model (write rejection)

Defense in depth — all three layers are covered by CI tests:

1. **Intent only** — clients cannot submit Cypher; only Ontographia-generated
   queries are executed.
2. **Neo4j read mode** — sessions use `READ_ACCESS` and `execute_read`.
3. **Deny list** — generated Cypher is scanned for write clauses / procedures
   (`CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `LOAD CSV`,
   `IN TRANSACTIONS`, APOC write procs, …) and rejected with an explicit error.

## Related

- [Intent layer (`ontographia[llm]`)](llm.md) — optional helpers for extracting Intent (not used by the MCP server itself)
- [Python bindings](python.md)
- [Neo4j walkthrough](end-to-end-neo4j.md)
- Epic [#85](https://github.com/edgesentry/ontographia/issues/85)
