# Intent-layer evaluation harness

Offline experiments under `examples/llm/eval/`. Published summaries: [docs/evaluation.md](../../../docs/evaluation.md).

## Track A — distractor ontology stress test (Issues #49 / #50)

Reproduces silent wrong-field selection on large schemas **without a live LLM**.

```bash
uv run python examples/llm/eval/run_track_a.py --record
```

Details: baselines in [`baselines/track_a_full_schema.md`](baselines/track_a_full_schema.md).

## Track B — HF Text2Cypher schema → Ontographia (Issues #52 / #53)

External validity for **schema conversion** using [neo4j/text2cypher-2025v1](https://huggingface.co/datasets/neo4j/text2cypher-2025v1) demo-DB rows (`Node properties` format).

Measures convert/load success and whether gold Cypher labels/rels/properties appear in the converted ontology (not Intent generation quality; no Neo4j execution in this arm).

```bash
uv run --with datasets python examples/llm/eval/run_track_b.py --record
uv run --with datasets python examples/llm/eval/run_track_b.py --record --write-ontologies
```

Requires ephemeral `datasets` (not a core package dependency). Check the HF dataset card for license before redistributing rows.

Baselines: [`baselines/track_b_schema_convert.md`](baselines/track_b_schema_convert.md).

Converter module: [`schema_convert.py`](schema_convert.py) (also best-effort JSON introspect; unsupported formats raise).

## Artifacts

| Path | Purpose |
|------|---------|
| `baselines/*.md` / `*.json` | Commit-friendly latest results |
| `out/` | Scratch (gitignored) |

## Related issues

- Track A: [#49](https://github.com/edgesentry/ontographia/issues/49), [#50](https://github.com/edgesentry/ontographia/issues/50), later [#51](https://github.com/edgesentry/ontographia/issues/51)
- Track B: [#52](https://github.com/edgesentry/ontographia/issues/52), [#53](https://github.com/edgesentry/ontographia/issues/53)
