# Evaluation

Offline experiments for the **app / agent Intent layer** (not the Rust Cypher emitters). Design context: [Related work](related-work.md). Why this stays outside the core: [Architecture — outside the core](architecture.md#what-is-intentionally-outside-the-core).

## Study map

The evaluation has two tracks. **Track A** is an internal stress test on manufacturing ontologies where the gold answers are known: it asks whether the Intent layer selects the right fields, whether it recovers when execution returns nothing, and whether schema subsetting / retry budget can cut spend. **Track B** is external validity: it converts public Text2Cypher schema text into Ontographia ontologies and, in the live arm, checks whether generated queries return the same rows as the public gold Cypher.

| Track | Arm ID | Purpose | Harness | Needs |
|-------|--------|---------|---------|-------|
| A | `track-a` | On a large ontology, can a plausible-but-wrong property Intent still pass `Engine.build`? | [`run_track_a.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_a.py) | — |
| A | `h1` — H1 mechanical | Does exact-match subsetting (+ fallback) improve field selection and cut tokens vs the full schema? | [`run_track_a_h1.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_a_h1.py) | — |
| A | `h1-live` — H1 live | Do the H1 gains hold with a real OpenAI-compatible LLM? | [`run_track_a_h1_live.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_a_h1_live.py) + [`run_h1_live_repeats.sh`](https://github.com/edgesentry/ontographia/blob/main/scripts/remeasure/run_h1_live_repeats.sh) | LiteLLM |
| A | `h2` — H2 | When an Intent compiles but returns no rows (Empty@Valid), does execution-feedback Intent refine recover rows? | [`run_track_a_h2.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_a_h2.py) | — |
| A | `h3` — H3 | Does difficulty-adaptive spend (subset-first, escalate on hard questions) cut tokens without hurting Compile / Property Hit? | [`run_track_a_h3.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_a_h3.py) | — |
| B | `track-b` | Can public Text2Cypher schema text become a loadable ontology, and does it cover the tokens used in gold Cypher? | [`run_track_b.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_b.py) | HF `datasets` |
| B | `track-b-exec` | Does Question → Intent → `Engine.build` → Neo4j return the same rows as the gold Cypher? | [`run_track_b_exec.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_b_exec.py) | LiteLLM + Neo4j |
| — | `dry-run` | Offline consistency check: a saved Intent still agrees with its expected Cypher. | [`scripts/remeasure/dry_run.py`](https://github.com/edgesentry/ontographia/blob/main/scripts/remeasure/dry_run.py) | — |

**How the arms relate.** H1 is one hypothesis with two arms, not two studies: the mechanical arm (`h1`) induces silent-wrong Intents from the prompt vocabulary and establishes the mechanism, while the live arm (`h1-live`) repeats the same full / subset / `subset_fallback` comparison against a real model. Read the mechanical result as the controlled version and the live result as the production-relevant one. H2 and H3 ask different questions (execution-feedback recovery and spend budgeting); they are not variants of H1. Track B does not reuse Track A's manufacturing fixture — it measures external validity on public demo databases and makes no Track A-level field-selection claim. The [Context Rot checklist](#feature-add-checklist-context-rot-lens) is a lens for deciding which of these arms to re-run after a feature change, not a standalone study. [`scripts/remeasure/run_all.sh`](https://github.com/edgesentry/ontographia/blob/main/scripts/remeasure/run_all.sh) runs the whole map (see [Reproduce or refresh all arms](#reproduce-or-refresh-all-arms)).

## Track A — distractor ontology stress test

Track A asks whether ontology validation can see that a field is the wrong *semantic* choice when it is still a valid property. It contains the `track-a`, `h1` / `h1-live`, `h2`, and `h3` arms above.

**Question:** On a large ontology, can an Intent use a *plausible but wrong* property and still pass `Engine::build`?

**Harness:** [`examples/llm/eval/`](https://github.com/edgesentry/ontographia/tree/main/examples/llm/eval) (no live LLM required for this baseline).

Manufacturing gold Intents (40) are compiled as-is, then each is corrupted to a near-duplicate distractor property (for example `Plant.name` → `PlantName`). Ontologies: `small` (base), `mid` (~200 properties), `large` (~2000 properties).

### Full-schema baseline (+ subset prompt size)

Recorded `2026-09-08T09:11:27Z` (git `0563c07`). Machine-readable copy: [`examples/llm/eval/baselines/track_a_full_schema.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_a_full_schema.json).

| profile | properties | gold compile OK | silent-wrong OK | silent-wrong fail | mean prop hit (wrong vs gold) | prompt ≈tokens full | prompt ≈tokens subset |
|---------|------------:|----------------:|----------------:|------------------:|------------------------------:|--------------------:|----------------------:|
| small | 16 | 40 | 0 | 40 | 0.50 | 1,359 | 1,246 |
| mid | 200 | 40 | 40 | 0 | 0.50 | 2,460 | 1,247 |
| large | 2,000 | 40 | 40 | 0 | 0.50 | 13,710 | 1,247 |

**Reading:** On `mid` / `large`, silent-wrong Intents compile as often as gold — ontology validation cannot see that the field is the wrong *semantic* choice. On `small`, distractors are absent, so the same wrong Intents fail. Full-schema prompt size grows with the vocabulary dump in `build_initial_user_message`; **exact-match subset prompts** ([issue #45](https://github.com/edgesentry/ontographia/issues/45), `ontographia.llm.subset` — [Intent layer](llm.md)) stay ~1.2k tokens even at 2k properties.

### H1 study — full vs subset vs subset+fallback

**Question:** Does exact-match subsetting improve Intent field selection *and* cut tokens vs full schema?

**Harness:** [`examples/llm/eval/run_track_a_h1.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_a_h1.py) (mechanical; no live LLM).

This is the **mechanical arm** of H1 (`h1`). It establishes the prompt-vocabulary mechanism; the **live arm** (`h1-live`) below asks the same question with a real model and is the production-relevant evidence.

**Method:** Induce a silent-wrong near-duplicate Intent **only when** that distractor property name appears in the prompt’s property vocabulary; otherwise use gold. `subset_fallback` uses the full schema when the subset is empty or gold classes/relationships are missing from subset enums (mirrors [#45](https://github.com/edgesentry/ontographia/issues/45) pipeline policy).

Recorded in [`examples/llm/eval/baselines/track_a_h1.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_a_h1.json). Regenerate: `uv run python examples/llm/eval/run_track_a_h1.py --record`.

| profile | condition | Property Hit | compile OK | distractor visible | induced wrong | fallback rate | ≈tok p50 | ≈tok p95 |
|---------|-----------|-------------:|-----------:|-------------------:|--------------:|--------------:|---------:|---------:|
| small | full | 1.00 | 40/40 | 0 | 0 | 0.00 | 1,317 | 1,359 |
| small | subset | 1.00 | 40/40 | 0 | 0 | 0.00 | 1,172 | 1,246 |
| small | subset_fallback | 1.00 | 40/40 | 0 | 0 | 0.00 | 1,172 | 1,246 |
| mid | full | 0.50 | 40/40 | 40 | 40 | 0.00 | 2,417 | 2,460 |
| mid | subset | 1.00 | 40/40 | 0 | 0 | 0.00 | 1,174 | 1,247 |
| mid | subset_fallback | 1.00 | 40/40 | 0 | 0 | 0.00 | 1,174 | 1,247 |
| large | full | 0.50 | 40/40 | 40 | 40 | 0.00 | 13,667 | 13,710 |
| large | subset | 1.00 | 40/40 | 0 | 0 | 0.00 | 1,174 | 1,247 |
| large | subset_fallback | 1.00 | 40/40 | 0 | 0 | 0.00 | 1,174 | 1,247 |

**H1 verdict: support** (predeclared criteria on `large`): Property Hit +50pt vs full, tokens p95 ≈ −91%, compile success not worse.

**Qualitative:** Under `full` / `large`, prompts surface near-duplicates such as `PlantName`, `supplier_name`, `DefectCode`. Under `subset`, none of those names appear in the property list for the 40 gold questions, so the mechanical arm never induces silent-wrong. Fallback rate is **0** on this fixture because gold class/relationship structure is always covered by the exact-match subset.

**Caveat (mechanical):** This arm measures *prompt-induced* distractibility, not model decoding. Live follow-up: [issue #68](https://github.com/edgesentry/ontographia/issues/68) below.

### H1 live arm (issue #68) — H1 with a real model

**Question:** Do the H1 gains hold with a real OpenAI-compatible LLM (not a mechanical inducer)? This is the **live arm of H1** (`h1-live`), not a separate hypothesis.

**Harness:** [`examples/llm/eval/run_track_a_h1_live.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_a_h1_live.py). Recorded `2026-09-08T14:42:52Z` via LiteLLM alias `ontographia-gemini-3.7` (recorded as `ontographia-gemini` before #106) → upstream **Gemini 3.7 Flash** (`gemini-3.7-flash`), `temperature=0`, 40 gold × mid/large × three policies. Machine-readable: [`examples/llm/eval/baselines/track_a_h1_live.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_a_h1_live.json).

| profile | condition | Property Hit | compile OK | near-dup picks | invent-without-seeing | fallback | ≈tok p95 |
|---------|-----------|-------------:|-----------:|---------------:|----------------------:|---------:|---------:|
| mid | full | 0.89 | 36/40 | 0 | 0 | 0.00 | 2,460 |
| mid | subset | 0.74 | 30/40 | 0 | 0 | 0.00 | 1,247 |
| mid | subset_fallback | **0.95** | **40/40** | 0 | 0 | 0.15 | **1,247** |
| large | full | 0.82 | 33/40 | 0 | 0 | 0.00 | 13,710 |
| large | subset | 0.78 | 32/40 | 0 | 0 | 0.00 | 1,247 |
| large | subset_fallback | **0.95** | **40/40** | 0 | 0 | 0.17 | **1,247** |

**H1 live verdict: support** on the **recommended production policy** (`subset_fallback` / `schema_policy=auto`): on `large`, Property Hit +12.5pt vs full (0.82 → 0.95), tokens p95 ≈ −91%, compile 40/40 (better than full). Ablation: **subset-only** can under-cover vocabulary (−5pt hit, slightly worse compile) — exact-match pruning needs the full-schema fallback. Invent-without-seeing rate was **0** on this run; preferred near-duplicates were not selected even under `full`.

```bash
source scripts/litellm/use-provider.sh gemini-3.7   # or gemini-3.8 / any OpenAI-compatible backend
uv run python examples/llm/eval/run_track_a_h1_live.py --profiles mid,large --record
```

#### v0.1.6 live re-runs (Gemini 3.7 / 3.8, issue #106)

Published-package re-runs (`ontographia[llm]==0.1.6` from PyPI, LiteLLM `1.98.0`, `temperature=0`). The `2026-09-08` baselines above are unchanged (`--json-out`).

| artifact | model | recorded_at | notes |
|----------|-------|-------------|-------|
| [`track_a_h1_live_v0.1.6.md`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_a_h1_live_v0.1.6.md) / [`.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_a_h1_live_v0.1.6.json) | alias recorded as `ontographia-gemini` → `gemini-3.7-flash` | `2026-10-22T03:09:33Z` | harness verdict **support**; see file for per-arm table |
| [`track_a_h1_live_v0.1.6_gemini-3.8.md`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_a_h1_live_v0.1.6_gemini-3.8.md) / [`.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_a_h1_live_v0.1.6_gemini-3.8.json) | `ontographia-gemini-3.8` → `gemini-3.8-flash` | `2026-10-22T05:43:55Z` | harness verdict **support** |
| [`gemini_3.7_vs_3.8_v0.1.6.md`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/gemini_3.7_vs_3.8_v0.1.6.md) | — | — | `2026-09-08` baseline vs v0.1.6 3.7 vs v0.1.6 3.8 (Track A + Track B) |

### H2 study — execution feedback Intent refine

**Question:** When an Intent compiles but Neo4j returns empty (Empty@Valid), does feeding execution feedback into Intent correction (then `Engine::build` again) recover final rows vs stopping after the first empty result?

**Harness:** [`examples/llm/eval/run_track_a_h2.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_a_h2.py) (mechanical; mock executor + gold-returning corrector; no live LLM / Neo4j).

**Method:** Corrupt each gold Intent’s first filter *value* so build still succeeds but the mock executor returns `[]`. Compare `no_refine` (`max_exec_refines=0`) vs `with_refine` (`max_exec_refines=2`). Gold (uncorrupted) control checks that refine does not fire spuriously. Every emitted `{query, params}` is checked against a fresh `Engine.build`.

Recorded in [`examples/llm/eval/baselines/track_a_h2.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_a_h2.json). Regenerate: `uv run python examples/llm/eval/run_track_a_h2.py --record`.

| arm | condition | Empty@Valid | final exec OK | Intent exact | recovered | Cypher = Engine.build | mean corrections |
|-----|-----------|------------:|--------------:|-------------:|----------:|----------------------:|-----------------:|
| empty-inducing | no_refine | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| empty-inducing | with_refine | 1.00 | **1.00** | **1.00** | **1.00** | 1.00 | 1.00 |
| gold control | no_refine | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 |
| gold control | with_refine | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 | 0.00 |

**H2 verdict: support** (predeclared): on the empty-inducing set, final execution_ok +100pt with refine, ≥80% recovered to gold Intent + rows, Cypher always from `Engine.build`. Feature: [issue #46](https://github.com/edgesentry/ontographia/issues/46) / `--refine-on-exec`.

**Caveat:** Mechanical arm proves the loop recovers Empty@Valid when Intent correction succeeds. It does **not** measure live-LLM correction quality on a real Neo4j database. Live field-selection evidence for the Intent layer is covered by the H1 live arm (#68); H2’s contribution remains the deterministic refine loop.

### H3 study — difficulty-adaptive spend

**Question:** On easy questions, can subset-first extraction with a small retry budget cut prompt tokens vs always-full + fixed retries **without** hurting Compile Success / Property Hit? On hard questions, does escalation to full schema recover?

**Harness:** [`examples/llm/eval/run_track_a_h3.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_a_h3.py) (mechanical; mock extractors; no live LLM).

**Method:** Compare `always_full_fixed` (full schema, `max_retries=5`) vs `adaptive` (subset-first, `initial_retries=1`, escalate to full with `escalated_retries=5` — [issue #47](https://github.com/edgesentry/ontographia/issues/47)).

- **easy:** mock extractor returns gold Intent on the first call.
- **hard:** subset extract is invalid; full extract returns gold (forces escalation).

Recorded in [`examples/llm/eval/baselines/track_a_h3.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_a_h3.json). Regenerate: `uv run python examples/llm/eval/run_track_a_h3.py --record`.

| profile | slice | condition | Property Hit | compile OK | escalation | mean LLM calls | ≈tok final p95 | ≈tok total p95 |
|---------|-------|-----------|-------------:|-----------:|-----------:|---------------:|---------------:|---------------:|
| large | easy | always_full_fixed | 1.00 | 40/40 | 0.00 | 1.00 | 13,710 | 13,710 |
| large | easy | adaptive | 1.00 | 40/40 | 0.00 | 1.00 | **1,247** | **1,247** |
| large | hard | always_full_fixed | 1.00 | 40/40 | 0.00 | 1.00 | 13,710 | 13,710 |
| large | hard | adaptive | 1.00 | 40/40 | **1.00** | 2.00 | 13,710 | 14,957 |

**H3 verdict: support** (predeclared on `large` / easy): tokens p95 ≈ −91% vs always_full, LLM calls not higher, Compile / Property Hit not worse; hard slice escalates (rate 1.00) and recovers compile.

**Caveat:** Mechanical arm measures #47 schema/retry budgeting with mock extractors. Live Intent extraction under `schema_policy=auto` (subset-first + escalate) is exercised in the H1 live arm (#68); this study isolates the spend state machine.

### Reproduce / refresh

```bash
uv run python examples/llm/eval/run_track_a.py --record
uv run python examples/llm/eval/run_track_a_h1.py --record
uv run python examples/llm/eval/run_track_a_h1_live.py --profiles mid,large --record
uv run python examples/llm/eval/run_track_a_h2.py --record
uv run python examples/llm/eval/run_track_a_h3.py --record
```

Updates [`examples/llm/eval/baselines/`](https://github.com/edgesentry/ontographia/tree/main/examples/llm/eval/baselines). After regenerating, sync the tables above if numbers change. For a scratch run that leaves baselines untouched, use [`scripts/remeasure/run_all.sh`](https://github.com/edgesentry/ontographia/blob/main/scripts/remeasure/run_all.sh) (see [Reproduce or refresh all arms](#reproduce-or-refresh-all-arms)).

## Track B — public Text2Cypher schemas

Track B contains two arms: schema conversion (`track-b`, offline apart from the public dataset download) and the live Exec Match spot (`track-b-exec`). Neither reuses Track A's manufacturing fixture.

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

### Exec Match spot (issue #53)

**Question:** On public demo DBs, can Question → LLM Intent → `Engine.build` → Neo4j rows match gold Cypher execution?

**Harness:** [`examples/llm/eval/run_track_b_exec.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_b_exec.py). Recorded `2026-09-08T15:10:33Z` (LiteLLM `ontographia-gemini-3.7`, recorded as `ontographia-gemini` before #106 → **Gemini 3.7 Flash** / `gemini-3.7-flash`), n=60 (seed=53) on `movies` + `recommendations` via `neo4j+s://demo.neo4jlabs.com`. HF gold Cypher literal `\n` sequences are normalized; write golds are skipped. Baseline: [`track_b_exec_spot.md`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_b_exec_spot.md).

| metric | value |
|--------|------:|
| Compile OK | 41 / 60 (0.68) |
| Exec scored (read golds that ran) | 38 |
| Exec Match (exact row-set) | **1 / 38 (0.03)** |
| Jaccard mean | 0.03 |
| Structure F1 label / rel / prop | 0.82 / 0.67 / 0.61 |

**Reading:** Schema ingest remains strong; live Intent→emit often compiles (~68%) and structure overlap is moderate, but **exact Exec Match against gold Cypher is rare**. HF gold is Cypher (not Intent), so mismatches mix Intent extraction error, ontology conversion gaps, and legitimate Cypher paraphrases. This spot closes external-validity measurement; it does **not** claim Text2Cypher SOTA or Track A H1-level field-selection proof.

```bash
source scripts/litellm/use-provider.sh gemini-3.7   # or gemini-3.8
uv run --with datasets --with neo4j python examples/llm/eval/run_track_b_exec.py --record
```

#### v0.1.6 Exec Match re-runs (Gemini 3.7 / 3.8, issue #106)

Same package / LiteLLM / seed / refs as above; the `2026-09-08` [`track_b_exec_spot.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_b_exec_spot.json) is unchanged.

| artifact | model | recorded_at | compile_ok | exec_match |
|----------|-------|-------------|------------:|-----------:|
| [`track_b_exec_spot_v0.1.6.md`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_b_exec_spot_v0.1.6.md) / [`.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_b_exec_spot_v0.1.6.json) | `ontographia-gemini` → `gemini-3.7-flash` | `2026-10-22T05:05:32Z` | 39/60 | 1/36 |
| [`track_b_exec_spot_v0.1.6_gemini-3.8.md`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_b_exec_spot_v0.1.6_gemini-3.8.md) / [`.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_b_exec_spot_v0.1.6_gemini-3.8.json) | `ontographia-gemini-3.8` → `gemini-3.8-flash` | `2026-10-22T07:57:21Z` | 36/60 | 1/33 |

Three-way table (incl. structure F1): [`gemini_3.7_vs_3.8_v0.1.6.md`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/gemini_3.7_vs_3.8_v0.1.6.md).

### Reproduce / refresh

```bash
uv run --with datasets python examples/llm/eval/run_track_b.py --record
```

Check the Hugging Face dataset card for license before redistributing samples.

## Reproduce or refresh all arms

Every table on this page is produced by a script in this repository. `--record` rewrites the checked-in files under [`examples/llm/eval/baselines/`](https://github.com/edgesentry/ontographia/tree/main/examples/llm/eval/baselines); `--json-out` (and the repeat wrapper below) write a scratch copy instead, which is what remeasure runs use so published numbers stay put. The top-level runner defaults to the scratch path and **never** passes `--record` unless you ask for it.

### All arms at once

```bash
# offline: Track A, H1 mechanical, H2, H3, Track B schema convert, dry-run
scripts/remeasure/run_all.sh

# also H1 live repeats and Track B Exec Match (health-checked before spend)
scripts/remeasure/run_all.sh --live --h1-live-n 3

# a subset of arms
scripts/remeasure/run_all.sh --only h1,h2
```

The runner writes `meta.txt`, `status.tsv`, `summary.md`, `logs/<arm>.log`, `logs/<arm>.exit`, `logs/<arm>.command`, and `json/<arm>.json` under `--out-dir` (default `examples/llm/eval/out/run-all-<UTC>`, gitignored). It records process status and harness output only — no metrics are parsed or invented, and no baseline is rewritten unless `--record` is passed explicitly. Live arms require `--live`, and the default set excludes them so an accidental run cannot spend tokens. Prerequisites, flags, and exit codes: [`scripts/remeasure/README.md`](https://github.com/edgesentry/ontographia/blob/main/scripts/remeasure/README.md).

### Arm-by-arm commands

| Arm | Command | Needs |
|-----|---------|-------|
| All offline arms | `scripts/remeasure/run_all.sh` | — (Track B needs HF `datasets`) |
| All arms, live included | `scripts/remeasure/run_all.sh --live` | LiteLLM (+ Neo4j for Track B Exec) |
| Track A full schema | `uv run python examples/llm/eval/run_track_a.py --record` | — |
| H1 mechanical | `uv run python examples/llm/eval/run_track_a_h1.py --record` | — |
| H1 live, one run | `uv run python examples/llm/eval/run_track_a_h1_live.py --profiles mid,large --record` | LiteLLM |
| H1 live, repeats | `scripts/remeasure/run_h1_live_repeats.sh --profiles mid,large --n 3 --out-dir DIR` | LiteLLM |
| H2 exec feedback | `uv run python examples/llm/eval/run_track_a_h2.py --record` | — |
| H3 adaptive spend | `uv run python examples/llm/eval/run_track_a_h3.py --record` | — |
| Gold Intent field match (#96 step 1) | `uv run python examples/llm/eval/run_gold_field_match.py --per-item` | — |
| Track B schema convert | `uv run --with datasets python examples/llm/eval/run_track_b.py --record` | HF `datasets` |
| Track B Exec Match | `uv run --with datasets --with neo4j python examples/llm/eval/run_track_b_exec.py --record` | LiteLLM + `demo.neo4jlabs.com` |
| Offline fixture check | `python3 scripts/remeasure/dry_run.py` | — |

### Live repeats (variance)

The published live H1 numbers came from **repeated** runs, not from a single `--record` invocation. Reproduce the main stem with n=3 over `mid,large`, then extend the high-variance `large` arm toward n=5:

```bash
# once
uv sync --group dev && uv run maturin develop --release
scripts/litellm/start.sh
source scripts/litellm/use-provider.sh gemini-3.8

# n=3 over mid + large
scripts/remeasure/run_h1_live_repeats.sh --profiles mid,large --n 3 \
  --out-dir examples/llm/eval/out/remeasure-h1-live-$(date -u +%Y%m%d-%H%M)

# +2 large-only repeats (cumulative n=5 on large)
scripts/remeasure/run_h1_live_repeats.sh --profiles large --n 2 \
  --out-dir examples/llm/eval/out/remeasure-h1-live-ext-$(date -u +%Y%m%d-%H%M)
```

Each stem holds `meta.txt` (git revision, package version, model alias, base URL, timings), `logs/`, the per-repeat `json/run<N>.json` written by the harness, and `aggregate.json` / `aggregate_index.json` / `aggregate.md`. Options, environment variables, and exit codes: [`scripts/remeasure/README.md`](https://github.com/edgesentry/ontographia/blob/main/scripts/remeasure/README.md). The wrapper never passes `--record`, so baselines are untouched — compare the aggregate by hand before editing any table or JSON above.

`scripts/remeasure/aggregate_h1_live.py --out-dir DIR` re-summarizes an existing stem (repeat count, Property Hit mean and min–max, compile OK, fallback, ≈tokens p95, LLM calls) without calling a model.

## Feature-add checklist: Context Rot lens

[Context Rot (Chroma, July 2025)](https://www.trychroma.com/research/context-rot) reports that model accuracy degrades as input grows, as distractors accumulate, and when the full context is supplied instead of a focused subset. Ontographia has **not** replicated that study (18 models, LongMemEval-style long inputs) and makes no comparable claim. The Track A results above are fixture measurements on Ontographia's own prompts and tasks; this checklist only records which of them to re-run when a feature changes the context the LLM sees.

**When to use:** any roadmap feature that changes prompts (`build_initial_user_message`), schema exposure, subsetting / `subset_fallback` (`schema_policy`), or Intent extraction / repair. Re-run the mapped harnesses below, then refresh the tables and baselines above if numbers move.

| Context Rot dimension | What to re-check | Existing harness (scripted today) |
|-----------------------|------------------|-----------------------------------|
| Input length / prompt tokens | full vs subset ≈tokens per profile; p50 / p95 | `run_track_a.py`, `run_track_a_h1.py` (mechanical), `run_track_a_h1_live.py` (live, p95), `run_track_a_h3.py` (total p95) |
| Distractors / near-duplicates | whether a near-duplicate property is visible in the prompt and gets selected | `run_track_a.py` (silent-wrong), `run_track_a_h1.py` (mechanical induce), `run_track_a_h1_live.py` (near-dup picks, invent-without-seeing) |
| Full schema vs focused subset (and `subset_fallback`) | Property Hit / compile / fallback rate under `full`, `subset`, `subset_fallback`; escalation spend | `run_track_a_h1.py`, `run_track_a_h1_live.py`, `run_track_a_h3.py` |
| Intent extraction / repair | Empty@Valid recovery after execution feedback (changes the prompt sequence rather than context length) | `run_track_a_h2.py` |

The whole checklist can be run scratch-only with [`scripts/remeasure/run_all.sh`](https://github.com/edgesentry/ontographia/blob/main/scripts/remeasure/run_all.sh) (add `--live` for the live arms); the per-arm commands below use `--record` only because they refresh the published baselines.

```bash
# mechanical: prompt length, distractors, full / subset / subset_fallback, refine loop
uv run python examples/llm/eval/run_track_a.py --record
uv run python examples/llm/eval/run_track_a_h1.py --record
uv run python examples/llm/eval/run_track_a_h3.py --record
uv run python examples/llm/eval/run_track_a_h2.py --record

# live Intent extraction (needs an OpenAI-compatible backend via LiteLLM)
source scripts/litellm/use-provider.sh gemini-3.7
uv run python examples/llm/eval/run_track_a_h1_live.py --profiles mid,large --record

# live repeat driver for variance (the published protocol used n=3)
scripts/remeasure/run_h1_live_repeats.sh --profiles mid,large --n 3 --out-dir DIR
```

**Coverage and limits today:**

- Live evidence is the H1 live arm only: 40 gold × `mid`/`large`, one provider alias per run (Gemini 3.7 / 3.8 in the v0.1.6 re-runs), `temperature=0`. There is no long-input sweep, no many-model replication, and no LongMemEval-style study.
- Track A mechanical, H2, and H3 measure prompt vocabulary and the spend/refine state machines with mock extractors — they do not measure live model accuracy.
- [`scripts/remeasure/dry_run.py`](https://github.com/edgesentry/ontographia/blob/main/scripts/remeasure/dry_run.py) loads a saved Intent and checks its expected Cypher offline. It is a fixture consistency check only, **not** a live Context Rot / remeasure harness; use [`scripts/remeasure/run_h1_live_repeats.sh`](https://github.com/edgesentry/ontographia/blob/main/scripts/remeasure/run_h1_live_repeats.sh) for live repeats, or [`scripts/remeasure/run_all.sh`](https://github.com/edgesentry/ontographia/blob/main/scripts/remeasure/run_all.sh) to verify every arm.

## Related

- [Related work](related-work.md)
- [Architecture](architecture.md)
- Issues [#45](https://github.com/edgesentry/ontographia/issues/45), [#46](https://github.com/edgesentry/ontographia/issues/46), [#47](https://github.com/edgesentry/ontographia/issues/47), [#48](https://github.com/edgesentry/ontographia/issues/48), [#49](https://github.com/edgesentry/ontographia/issues/49), [#50](https://github.com/edgesentry/ontographia/issues/50), [#51](https://github.com/edgesentry/ontographia/issues/51), [#52](https://github.com/edgesentry/ontographia/issues/52), [#53](https://github.com/edgesentry/ontographia/issues/53), [#54](https://github.com/edgesentry/ontographia/issues/54), [#55](https://github.com/edgesentry/ontographia/issues/55), [#68](https://github.com/edgesentry/ontographia/issues/68), [#106](https://github.com/edgesentry/ontographia/issues/106)
