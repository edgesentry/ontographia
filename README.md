# Ontographia

**Any ontology in, Cypher 25 out — deterministically.**

Ontographia turns **ontology definitions** + **Intent JSON** into **parameter-bound Cypher** for Neo4j. The LLM (or a human) produces Intent; the Rust core validates it against the ontology and emits the query. It does not ask models to write Cypher.

```
Ontology → COM → validate(Intent) → AST → Cypher 25 + $params
```

## Start here

| Audience | Go to |
|----------|--------|
| **Humans (install, guides, Neo4j)** | Published docs: [edgesentry.github.io/ontographia](https://edgesentry.github.io/ontographia/) |
| **Overview & golden rules** | [docs/index.md](docs/index.md) |
| **How the pipeline works** | [docs/architecture.md](docs/architecture.md) |
| **AI coding agents** | [AGENTS.md](AGENTS.md) (routes to `docs/`; do not treat this README as the manual) |

## Docs map (short)

| Need | Doc |
|------|-----|
| Install (CLI / Rust / Python / Go) | [docs/index.md](docs/index.md#install-released-versions) · [Rust](docs/rust.md) · [Python](docs/python.md) · [Go](docs/go.md) |
| End-to-end with Neo4j | [docs/end-to-end-neo4j.md](docs/end-to-end-neo4j.md) |
| LLM / Intent layer (examples only) | [docs/architecture.md](docs/architecture.md#what-is-intentionally-outside-the-core) · [`examples/llm/`](examples/llm/) |
| Evaluation baselines | [docs/evaluation.md](docs/evaluation.md) |
| Related Text2Cypher work | [docs/related-work.md](docs/related-work.md) |
| Repo layout | [docs/repository-layout.md](docs/repository-layout.md) |
| Release | [docs/release.md](docs/release.md) |

Tutorials and tables live under [`docs/`](docs/) — this file is an index only.

## Quick taste

```bash
# After install (see docs/index.md)
ontographia build --ontology examples/manufacturing.native.yaml \
  --intent examples/sample_intent.json --json
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
