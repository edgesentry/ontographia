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

**Caveat:** A live LLM could still invent near-duplicates without seeing them in the prompt. This arm measures *prompt-induced* distractibility, not model decoding. Follow-up: [issue #68](https://github.com/edgesentry/ontographia/issues/68).

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

**Caveat:** Mechanical arm proves the loop recovers Empty@Valid when Intent correction succeeds. It does **not** measure live-LLM correction quality or Exec Match on a real Neo4j database.

### Reproduce / refresh

```bash
uv run python examples/llm/eval/run_track_a.py --record
uv run python examples/llm/eval/run_track_a_h1.py --record
uv run python examples/llm/eval/run_track_a_h2.py --record
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

### Reproduce / refresh

```bash
uv run --with datasets python examples/llm/eval/run_track_b.py --record
```

Check the Hugging Face dataset card for license before redistributing samples.

## Related

- [Related work](related-work.md)
- [Architecture](architecture.md)
- Issues [#45](https://github.com/edgesentry/ontographia/issues/45), [#49](https://github.com/edgesentry/ontographia/issues/49), [#50](https://github.com/edgesentry/ontographia/issues/50), [#51](https://github.com/edgesentry/ontographia/issues/51), [#52](https://github.com/edgesentry/ontographia/issues/52), [#53](https://github.com/edgesentry/ontographia/issues/53), [#55](https://github.com/edgesentry/ontographia/issues/55), [#46](https://github.com/edgesentry/ontographia/issues/46)
