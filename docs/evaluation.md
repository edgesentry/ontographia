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

## Related

- [Related work](related-work.md)
- [Architecture](architecture.md)
- Issues [#49](https://github.com/edgesentry/ontographia/issues/49), [#50](https://github.com/edgesentry/ontographia/issues/50)
