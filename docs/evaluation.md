# Evaluation

Offline experiments for the **app / agent Intent layer** (not the Rust Cypher emitters). Design context: [Related work](related-work.md).

## Track A — distractor ontology stress test

**Question:** On a large ontology, can an Intent use a *plausible but wrong* property and still pass `Engine::build`?

**Harness:** [`examples/llm/eval/`](https://github.com/edgesentry/ontographia/tree/main/examples/llm/eval) (no live LLM required for this baseline).

Manufacturing gold Intents (40) are compiled as-is, then each is corrupted to a near-duplicate distractor property (for example `Plant.name` → `PlantName`). Ontologies: `small` (base), `mid` (~200 properties), `large` (~2000 properties).

### Full-schema baseline

Recorded `2026-09-03T11:20:01Z` (git `bfe7336`). Machine-readable copy: [`examples/llm/eval/baselines/track_a_full_schema.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_a_full_schema.json).

| profile | properties | gold compile OK | silent-wrong OK | silent-wrong fail | mean prop hit (wrong vs gold) | prompt ≈tokens p50 |
|---------|------------:|----------------:|----------------:|------------------:|------------------------------:|-------------------:|
| small | 16 | 40 | 0 | 40 | 0.50 | 1,359 |
| mid | 200 | 40 | 40 | 0 | 0.50 | 2,460 |
| large | 2,000 | 40 | 40 | 0 | 0.50 | 13,710 |

**Reading:** On `mid` / `large`, silent-wrong Intents compile as often as gold — ontology validation cannot see that the field is the wrong *semantic* choice. On `small`, distractors are absent, so the same wrong Intents fail. Prompt size grows with the full vocabulary dump in `build_initial_user_message`.

This is the failure mode motivating schema subsetting for Intent prompts ([issue #45](https://github.com/edgesentry/ontographia/issues/45)); comparative arms land in [issue #51](https://github.com/edgesentry/ontographia/issues/51).

### Reproduce / refresh

```bash
uv run python examples/llm/eval/run_track_a.py --record
```

Updates [`examples/llm/eval/baselines/`](https://github.com/edgesentry/ontographia/tree/main/examples/llm/eval/baselines). After regenerating, sync the table above if numbers change.

## Track B — public Text2Cypher schemas

**Question:** Can Neo4j Text2Cypher **schema text** from public demo databases be converted into a loadable Ontographia ontology, and does that ontology cover tokens used in gold Cypher?

**Harness:** [`examples/llm/eval/run_track_b.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_b.py) + [`schema_convert.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/schema_convert.py).

Dataset: [neo4j/text2cypher-2025v1](https://huggingface.co/datasets/neo4j/text2cypher-2025v1) `test` split, rows with a `database_reference_alias` and schema starting with `Node properties` (15 neo4jlabs demo DBs). This arm does **not** score Intent generation or execute Cypher against Neo4j.

### Schema-convert baseline

Recorded `2026-09-03T11:29:09Z` (git `9b3c7cf`). Machine-readable: [`examples/llm/eval/baselines/track_b_schema_convert.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_b_schema_convert.json).

| metric | value |
|--------|------:|
| demo DBs converted | 15 / 15 |
| Engine.load OK | 15 / 15 |
| questions scored (≤15 per DB) | 211 |
| mean label coverage (gold Cypher ∩ ontology) | 0.96 |
| mean relationship coverage | 1.00 |
| mean property coverage | 0.81 |

**Reading:** Conversion is reliable for the demo `Node properties` format. Relationship coverage is high because patterns are explicit in the schema text. Property gaps (~19%) often come from Cypher using properties omitted from the schema snippet, or from heuristic token extraction noise. JSON introspect / free-text schemas are unsupported or best-effort only.

### Reproduce / refresh

```bash
uv run --with datasets python examples/llm/eval/run_track_b.py --record
```

Check the Hugging Face dataset card for license before redistributing samples.

## Related

- [Related work](related-work.md)
- [Architecture](architecture.md)
- Issues [#49](https://github.com/edgesentry/ontographia/issues/49), [#50](https://github.com/edgesentry/ontographia/issues/50), [#52](https://github.com/edgesentry/ontographia/issues/52), [#53](https://github.com/edgesentry/ontographia/issues/53)
