# bindings/

Language bindings over the Rust engine. **Do not reimplement query logic here** — call `Engine.build()` from core.

| Binding | Path | API surface |
|---------|------|-------------|
| Python (PyO3) | [`python/`](python/) | `ontographia.Engine` — load ontology, `intent_json_schema()`, `build()` |
| Go (cgo) | [`go/`](go/) | `ontographia.BuildCypherFromFiles()` via [`ontographia-ffi`](../crates/ontographia-ffi/) |

## Quick start

See root [README.md](../README.md):

- **Python** — `uv sync --group dev && uv run maturin develop --release`
- **Go** — `cargo build --release -p ontographia-ffi` then `go test ./...` in `bindings/go/`

Demo: [`go/cmd/demo/main.go`](go/cmd/demo/main.go)

## Canonical docs

- Python/Go usage in Neo4j tutorial: [docs/end-to-end-neo4j.md](../docs/end-to-end-neo4j.md)
- Local LLM E2E (Python only): [examples/run_llm_e2e.py](../examples/run_llm_e2e.py), [docs/litellm-local.md](../docs/litellm-local.md)
- Agent rules: [AGENTS.md](../AGENTS.md)
