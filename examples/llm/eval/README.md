# Intent-layer evaluation harness

Offline experiments under `examples/llm/eval/`. Published summaries: [docs/evaluation.md](../../../docs/evaluation.md).

## Track A — distractor ontology stress test (Issues #49 / #50)

Reproduces silent wrong-field selection on large schemas **without a live LLM**.
Also reports exact-match **subset** prompt size (`tok_sub`, issue [#45](https://github.com/edgesentry/ontographia/issues/45)).

```bash
uv run python examples/llm/eval/run_track_a.py --record
uv run python examples/llm/eval/test_subset.py
```

Details: baselines in [`baselines/track_a_full_schema.md`](baselines/track_a_full_schema.md). Subset helper: [`../subset.py`](../subset.py).

## Track A H1 — full vs subset vs fallback (Issue #51)

Mechanical prompt-vocab comparison + H1 verdict (support / partial / reject).

```bash
uv run python examples/llm/eval/run_track_a_h1.py --record
```

Baselines: [`baselines/track_a_h1.md`](baselines/track_a_h1.md). Summary: [docs/evaluation.md](../../../docs/evaluation.md).

### Live LLM arm (Issue #68)

```bash
source scripts/litellm/use-provider.sh gemini   # or any OpenAI-compatible backend
uv run python examples/llm/eval/run_track_a_h1_live.py --profiles mid,large --record
```

Baselines: [`baselines/track_a_h1_live.md`](baselines/track_a_h1_live.md).

## H2 — execution feedback Intent refine (Issue #55)

Mechanical Empty@Valid recovery: corrupt filter values, mock executor, compare `no_refine` vs `with_refine` ([#46](https://github.com/edgesentry/ontographia/issues/46) loop).

```bash
uv run python examples/llm/eval/run_track_a_h2.py --record
uv run python examples/llm/eval/test_exec_feedback.py
```

Baselines: [`baselines/track_a_h2.md`](baselines/track_a_h2.md). Summary: [docs/evaluation.md](../../../docs/evaluation.md#h2-study-execution-feedback-intent-refine).

## H3 — difficulty-adaptive spend (Issue #54)

Mechanical cost/quality comparison: `always_full_fixed` vs subset-first adaptive escalate ([#47](https://github.com/edgesentry/ontographia/issues/47)).

```bash
uv run python examples/llm/eval/run_track_a_h3.py --record
uv run python examples/llm/eval/test_subset.py
```

Baselines: [`baselines/track_a_h3.md`](baselines/track_a_h3.md). Summary: [docs/evaluation.md](../../../docs/evaluation.md#h3-study-difficulty-adaptive-spend).

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

### Exec Match spot (Issue #53 remainder)

```bash
source scripts/litellm/use-provider.sh gemini
uv run --with datasets --with neo4j python examples/llm/eval/run_track_b_exec.py --record
```

Runs Intent → emit → `demo.neo4jlabs.com` vs gold Cypher row Jaccard on movies (+ recommendations). Baseline: [`baselines/track_b_exec_spot.md`](baselines/track_b_exec_spot.md).

## Repair mapping (Issue #48)

```bash
uv run python examples/llm/eval/test_repair_mapping.py
```

Manufacturing heuristics live in [`../mappings/manufacturing.repair.yaml`](../mappings/manufacturing.repair.yaml); a minimal movies mapping proves the non-demo path.

## Artifacts

| Path | Purpose |
|------|---------|
| `baselines/*.md` / `*.json` | Commit-friendly latest results |
| `out/` | Scratch (gitignored) |

## Related issues

- Track A: [#49](https://github.com/edgesentry/ontographia/issues/49), [#50](https://github.com/edgesentry/ontographia/issues/50), [#51](https://github.com/edgesentry/ontographia/issues/51), [#68](https://github.com/edgesentry/ontographia/issues/68)
- Subset prompts: [#45](https://github.com/edgesentry/ontographia/issues/45)
- H2 exec feedback: [#46](https://github.com/edgesentry/ontographia/issues/46), [#55](https://github.com/edgesentry/ontographia/issues/55)
- H3 adaptive spend: [#47](https://github.com/edgesentry/ontographia/issues/47), [#54](https://github.com/edgesentry/ontographia/issues/54)
- Track B: [#52](https://github.com/edgesentry/ontographia/issues/52), [#53](https://github.com/edgesentry/ontographia/issues/53)
- Repair mapping: [#48](https://github.com/edgesentry/ontographia/issues/48)
