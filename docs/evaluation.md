# Evaluation

Offline experiments for the **app / agent Intent layer** (not the Rust Cypher emitters). Design context: [Related work](related-work.md). Why this stays outside the core: [Architecture — outside the core](architecture.md#what-is-intentionally-outside-the-core).

## Track A — distractor ontology stress test

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

**Reading:** On `mid` / `large`, silent-wrong Intents compile as often as gold — ontology validation cannot see that the field is the wrong *semantic* choice. On `small`, distractors are absent, so the same wrong Intents fail. Full-schema prompt size grows with the vocabulary dump in `build_initial_user_message`; **exact-match subset prompts** ([issue #45](https://github.com/edgesentry/ontographia/issues/45), [`examples/llm/subset.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/subset.py)) stay ~1.2k tokens even at 2k properties.

### H1 study — full vs subset vs subset+fallback

**Question:** Does exact-match subsetting improve Intent field selection *and* cut tokens vs full schema?

**Harness:** [`examples/llm/eval/run_track_a_h1.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_a_h1.py) (mechanical; no live LLM).

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

### H1 live LLM arm (issue #68)

**Question:** Do the H1 gains hold with a real OpenAI-compatible LLM (not a mechanical inducer)?

**Harness:** [`examples/llm/eval/run_track_a_h1_live.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_a_h1_live.py). Recorded `2026-09-08T14:42:52Z` via LiteLLM alias `ontographia-gemini` (Gemini 3.7 Flash), `temperature=0`, 40 gold × mid/large × three policies. Machine-readable: [`examples/llm/eval/baselines/track_a_h1_live.json`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_a_h1_live.json).

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
source scripts/litellm/use-provider.sh gemini   # or any OpenAI-compatible backend
uv run python examples/llm/eval/run_track_a_h1_live.py --profiles mid,large --record
```

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

Updates [`examples/llm/eval/baselines/`](https://github.com/edgesentry/ontographia/tree/main/examples/llm/eval/baselines). After regenerating, sync the tables above if numbers change.

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

### Exec Match spot (issue #53)

**Question:** On public demo DBs, can Question → LLM Intent → `Engine.build` → Neo4j rows match gold Cypher execution?

**Harness:** [`examples/llm/eval/run_track_b_exec.py`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/run_track_b_exec.py). Recorded `2026-09-08T15:10:33Z` (LiteLLM `ontographia-gemini`), n=60 (seed=53) on `movies` + `recommendations` via `neo4j+s://demo.neo4jlabs.com`. HF gold Cypher literal `\n` sequences are normalized; write golds are skipped. Baseline: [`track_b_exec_spot.md`](https://github.com/edgesentry/ontographia/blob/main/examples/llm/eval/baselines/track_b_exec_spot.md).

| metric | value |
|--------|------:|
| Compile OK | 41 / 60 (0.68) |
| Exec scored (read golds that ran) | 38 |
| Exec Match (exact row-set) | **1 / 38 (0.03)** |
| Jaccard mean | 0.03 |
| Structure F1 label / rel / prop | 0.82 / 0.67 / 0.61 |

**Reading:** Schema ingest remains strong; live Intent→emit often compiles (~68%) and structure overlap is moderate, but **exact Exec Match against gold Cypher is rare**. HF gold is Cypher (not Intent), so mismatches mix Intent extraction error, ontology conversion gaps, and legitimate Cypher paraphrases. This spot closes external-validity measurement; it does **not** claim Text2Cypher SOTA or Track A H1-level field-selection proof.

```bash
source scripts/litellm/use-provider.sh gemini
uv run --with datasets --with neo4j python examples/llm/eval/run_track_b_exec.py --record
```

### Reproduce / refresh

```bash
uv run --with datasets python examples/llm/eval/run_track_b.py --record
```

Check the Hugging Face dataset card for license before redistributing samples.

## Related

- [Related work](related-work.md)
- [Architecture](architecture.md)
- Issues [#45](https://github.com/edgesentry/ontographia/issues/45), [#46](https://github.com/edgesentry/ontographia/issues/46), [#47](https://github.com/edgesentry/ontographia/issues/47), [#48](https://github.com/edgesentry/ontographia/issues/48), [#49](https://github.com/edgesentry/ontographia/issues/49), [#50](https://github.com/edgesentry/ontographia/issues/50), [#51](https://github.com/edgesentry/ontographia/issues/51), [#52](https://github.com/edgesentry/ontographia/issues/52), [#53](https://github.com/edgesentry/ontographia/issues/53), [#54](https://github.com/edgesentry/ontographia/issues/54), [#55](https://github.com/edgesentry/ontographia/issues/55), [#68](https://github.com/edgesentry/ontographia/issues/68)
