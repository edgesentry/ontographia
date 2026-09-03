# Track A evaluation (Issue #49 / #50)

Reproducible stress test for the failure mode called out in colleague feedback and [related-work](../../../docs/related-work.md): on a **large ontology**, an Intent can use a **plausible but wrong** property, still pass ontology validation / `Engine::build`, and never look like a hard error.

This harness does **not** require a live LLM for the core demonstration. It:

1. Builds `small` / `mid` (~200 props) / `large` (~2000 props) ontologies from [`manufacturing.native.yaml`](../../manufacturing.native.yaml) plus near-duplicate + `CustomField_*` distractors
2. Runs ≥40 gold Intents (compile should succeed on all sizes)
3. Corrupts each gold Intent to a near-duplicate property (`name` → `PlantName`, `sku` → `SKU`, …)
4. Shows those **silent-wrong** Intents **fail** on `small` (distractor absent) but **compile on mid/large**
5. Estimates full-schema prompt size via `build_initial_user_message` (chars/4 ≈ tokens)

## Run

From repo root (needs `uv run maturin develop` / installed `ontographia`):

```bash
uv run python examples/llm/eval/run_track_a.py
uv run python examples/llm/eval/run_track_a.py --profiles large --json-out examples/llm/eval/out/track_a.json
uv run python examples/llm/eval/run_track_a.py --write-ontologies
```

## Reading the table

| Column | Meaning |
|--------|---------|
| `props` | Property count in ontology |
| `gold_ok` | Gold Intents that compile |
| `wrong_ok` | Silent-wrong Intents that still compile |
| `wrong_fail` | Silent-wrong rejected (expected on `small`) |
| `prop_hit` | Mean Property Hit of wrong vs gold (should be below 1.0) |
| `tok_p50` | Approx prompt tokens for full-schema user message |

## Relation to GitHub issues

- [#49](https://github.com/edgesentry/ontographia/issues/49) harness
- [#50](https://github.com/edgesentry/ontographia/issues/50) full-schema baseline (this run)
- [#51](https://github.com/edgesentry/ontographia/issues/51) later: add subset / fallback arms after [#45](https://github.com/edgesentry/ontographia/issues/45)
