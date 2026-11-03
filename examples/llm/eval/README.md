# Intent-layer evaluation harness

Offline experiments under `examples/llm/eval/`. Harnesses import the packaged module `ontographia.llm` (`pip install "ontographia[llm]"`). Published summaries: [docs/evaluation.md](../../../docs/evaluation.md). Unit tests for the Intent layer live in `tests/python/llm/` (CI).

The study map (Track A vs Track B, H1 mechanical / H1 live / H2 / H3) is in [docs/evaluation.md — Study map](../../../docs/evaluation.md#study-map); `scripts/remeasure/run_all.sh` verifies the whole map.

## Context Rot lens for feature adds

Changes to prompts, schema exposure, subsetting / `subset_fallback`, or Intent extraction should re-run the harnesses mapped in the [Context Rot feature-add checklist](../../../docs/evaluation.md#feature-add-checklist-context-rot-lens). `scripts/remeasure/dry_run.py` is an offline fixture consistency check; live repeats are driven by [`scripts/remeasure/run_h1_live_repeats.sh`](../../../scripts/remeasure/README.md). Every arm, offline and live, can be run through [`scripts/remeasure/run_all.sh`](../../../scripts/remeasure/README.md); arm-by-arm commands are listed under [Reproduce or refresh all arms](../../../docs/evaluation.md#reproduce-or-refresh-all-arms).

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
source scripts/litellm/use-provider.sh gemini-3.7   # or gemini-3.8 / any OpenAI-compatible backend
uv run python examples/llm/eval/run_track_a_h1_live.py --profiles mid,large --record
```

Baselines: [`baselines/track_a_h1_live.md`](baselines/track_a_h1_live.md) (`2026-09-08` live baseline). v0.1.6 re-runs: [`track_a_h1_live_v0.1.6.md`](baselines/track_a_h1_live_v0.1.6.md) (Gemini 3.7), [`track_a_h1_live_v0.1.6_gemini-3.8.md`](baselines/track_a_h1_live_v0.1.6_gemini-3.8.md) (Gemini 3.8). Comparison: [`gemini_3.7_vs_3.8_v0.1.6.md`](baselines/gemini_3.7_vs_3.8_v0.1.6.md) ([#106](https://github.com/edgesentry/ontographia/issues/106)).

The published live baseline used **repeated** runs. Reproduce them (LiteLLM health check, `meta.txt`, `logs/`, `aggregate.json`) with [`scripts/remeasure/run_h1_live_repeats.sh`](../../../scripts/remeasure/README.md), or include the arm in [`scripts/remeasure/run_all.sh --live`](../../../scripts/remeasure/README.md):

```bash
scripts/remeasure/run_h1_live_repeats.sh --profiles mid,large --n 3 --out-dir DIR
scripts/remeasure/run_h1_live_repeats.sh --profiles large --n 2 --out-dir DIR-EXT
```

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

These project-mode commands require a working local Maturin build. If a stale
in-tree `python/ontographia/*.so` breaks `import ontographia` (LINKEDIT
ImportError, issue [#144](https://github.com/edgesentry/ontographia/issues/144)),
run against the published wheel instead — this is what
`scripts/remeasure/run_all.sh` does for the `track-b` / `track-b-exec` arms
(see [scripts/remeasure/README.md](../../../scripts/remeasure/README.md#interpreter-modes-and-stale-native-builds)):

```bash
uv run --no-project --with 'ontographia[llm]==0.1.8' --with datasets \
  python examples/llm/eval/run_track_b.py --record
```

Requires ephemeral `datasets` (not a core package dependency). Check the HF dataset card for license before redistributing rows.

Baselines: [`baselines/track_b_schema_convert.md`](baselines/track_b_schema_convert.md).

Converter module: [`schema_convert.py`](schema_convert.py) (also best-effort JSON introspect; unsupported formats raise).

### Exec Match spot (Issue #53 remainder)

```bash
source scripts/litellm/use-provider.sh gemini-3.7   # or gemini-3.8
uv run --with datasets --with neo4j python examples/llm/eval/run_track_b_exec.py --record
```

Runs Intent → emit → `demo.neo4jlabs.com` vs gold Cypher row Jaccard on movies (+ recommendations). Also scores secondary Soft Exec Match (`soft_exec_match`, `soft_jaccard`, `soft_f1`, and optional `entity_jaccard` via [`soft_exec_match.py`](soft_exec_match.py), issue [#73](https://github.com/edgesentry/ontographia/issues/73)) by dropping column aliases and comparing normalized value multisets while keeping exact `exec_match` / `jaccard` unchanged. Baseline: [`baselines/track_b_exec_spot.md`](baselines/track_b_exec_spot.md). v0.1.6 re-runs: [`track_b_exec_spot_v0.1.6.md`](baselines/track_b_exec_spot_v0.1.6.md) (Gemini 3.7), [`track_b_exec_spot_v0.1.6_gemini-3.8.md`](baselines/track_b_exec_spot_v0.1.6_gemini-3.8.md) (Gemini 3.8). Comparison: [`gemini_3.7_vs_3.8_v0.1.6.md`](baselines/gemini_3.7_vs_3.8_v0.1.6.md).

## Gold Intent field match (Issue #96 steps 1–2)

Deterministic field-by-field scorer (entities / relations / filters / projections / limit) comparing a predicted Intent dict against a gold Intent dict; aliases are resolved to classes before comparison. No LLM, no Neo4j. Scorer: [`field_match.py`](field_match.py).

```bash
uv run python examples/llm/eval/run_gold_field_match.py            # aggregate JSON
uv run python examples/llm/eval/run_gold_field_match.py --per-item # + per-item scores
```

Arms over the 40 Track A golds: `gold_self` (gold vs gold self-check, expect 1.0 everywhere), `silent_wrong` (near-duplicate distractor variant vs gold, expect the corrupted field to drop while entities/relations stay 1.0), and `predictions` (external Intents from a JSONL of `{"id", "intent"}` vs gold — the arm real LLM pipelines plug into).

Step 2 freezes the gold set into stratified splits ([`splits.py`](splits.py), [`splits/track_a_v1.json`](splits/track_a_v1.json)): 4 strata (one per gold template) × 10 cases, 2 per stratum held out as `test` (8), the remaining 32 dealt into 4 folds (2 per stratum per fold) for `dev` / CV. Regeneration is deterministic (fixed seed); the loader verifies the frozen `gold_hash` and fails if the gold set changed.

```bash
uv run python examples/llm/eval/splits.py --write                  # regenerate the frozen split
uv run python examples/llm/eval/run_gold_field_match.py --split track_a_v1 --partition test
uv run python examples/llm/eval/run_gold_field_match.py --split track_a_v1 --partition cv   # per-fold aggregates
uv run python examples/llm/eval/run_gold_field_match.py --arms predictions \
    --predictions preds.jsonl --split track_a_v1 --partition fold:0 --model X --provider Y
```

The JSON payload carries `schema_version`, `git_rev`, the split id/version/gold hash, per-arm `partition` + `aggregate` (plus per-fold aggregates for `--partition cv`, plus per-item scores with `--per-item`), and optional `model`/`provider` labels. Default output is stdout / scratch (`--json-out`); `--record` is the only path that writes under `baselines/`. Unit tests: `tests/python/llm/test_field_match.py`, `tests/python/llm/test_splits.py` (CI). The execute-or-clarify gate and product hooks (steps 3b / 3c) are not in scope here.

## Failure-mode judges (Issue #96 step 3a)

Three independent yes/no judges — `wrong_relation`, `missing_filter`, `over_broad_scope` — over question + Intent + ontology subset ([`judges.py`](judges.py)). Evaluation only: no gate, threshold, F-beta, Brier score, or product wiring. Prompt build and parse are offline; live model calls require an explicit `--live` and reuse the LiteLLM / OpenAI-compatible backend.

```bash
# no network: replay committed fixture answers through prompt build + parse
uv run python examples/llm/eval/run_failure_mode_judges.py --dry-run \
    --split track_a_v1 --partition test

# live judges (LiteLLM or any OpenAI-compatible endpoint; same env as H1 live)
source scripts/litellm/use-provider.sh gemini-3.8
uv run python examples/llm/eval/run_failure_mode_judges.py --live \
    --split track_a_v1 --partition test

# reliability on externally produced Intents (JSONL: {"id", "intent"})
uv run python examples/llm/eval/run_failure_mode_judges.py --live \
    --predictions preds.jsonl --split track_a_v1 --partition fold:0
```

Labels are derived from [`field_match.py`](field_match.py), not from a model: `gold` and `silent_wrong` (near-duplicate property swap) are negatives for all three modes; `swap_relation`, `drop_filter`, and `drop_traverse` are positives for one mode each. `unknown` answers abstain and are excluded from precision/recall. JSON carries `schema_version`, `git_rev`, split meta, per-mode precision/recall/F1 with counts, and a per-variant breakdown. Dry-run aggregates are a plumbing check, not a reliability claim. This arm is intentionally **not** in `scripts/remeasure/run_all.sh` defaults. Tests: `tests/python/llm/test_failure_mode_judges.py`. Fixtures: [`fixtures/failure_mode_judges.json`](fixtures/failure_mode_judges.json).

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
- Track B: [#52](https://github.com/edgesentry/ontographia/issues/52), [#53](https://github.com/edgesentry/ontographia/issues/53), [#73](https://github.com/edgesentry/ontographia/issues/73)
- Gold Intent field match + failure-mode judges: [#96](https://github.com/edgesentry/ontographia/issues/96) (steps 1–2, 3a; gate / product hooks 3b–3c out of scope)
- Repair mapping: [#48](https://github.com/edgesentry/ontographia/issues/48)
- Gemini 3.7 vs 3.8 v0.1.6 live: [#106](https://github.com/edgesentry/ontographia/issues/106)
