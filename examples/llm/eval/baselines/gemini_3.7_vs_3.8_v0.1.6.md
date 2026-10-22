# Gemini 3.7 vs 3.8 — Ontographia v0.1.6 live evals (issue #106)

Neutral comparison of three recorded live runs. All numbers are taken from the committed JSON baselines; metrics were not re-run or edited here.

| run | recorded_at | package | LiteLLM alias (as recorded) | upstream | JSON |
|-----|-------------|---------|-----------------------------|----------|------|
| Part 3 (2026-09-08) | `2026-09-08T14:42:52Z` / `2026-09-08T15:10:33Z` | (Part 3 tree `c8d8a05`) | `ontographia-gemini` | `gemini-3.7-flash` | [`track_a_h1_live.json`](track_a_h1_live.json), [`track_b_exec_spot.json`](track_b_exec_spot.json) |
| v0.1.6 Gemini 3.7 | `2026-10-22T03:09:33Z` / `2026-10-22T05:05:32Z` | `ontographia[llm]==0.1.6` (PyPI) | `ontographia-gemini` | `gemini-3.7-flash` | [`track_a_h1_live_v0.1.6.json`](track_a_h1_live_v0.1.6.json), [`track_b_exec_spot_v0.1.6.json`](track_b_exec_spot_v0.1.6.json) |
| v0.1.6 Gemini 3.8 | `2026-10-22T05:43:55Z` / `2026-10-22T07:57:21Z` | `ontographia[llm]==0.1.6` (PyPI) | `ontographia-gemini-3.8` | `gemini-3.8-flash` | [`track_a_h1_live_v0.1.6_gemini-3.8.json`](track_a_h1_live_v0.1.6_gemini-3.8.json), [`track_b_exec_spot_v0.1.6_gemini-3.8.json`](track_b_exec_spot_v0.1.6_gemini-3.8.json) |

Shared settings for the v0.1.6 arms: `temperature=0`, Track A `n_cases=40` / `max_retries=1`, Track B `n=60` / `seed=53` / `schema_policy=auto` / `neo4j+s://demo.neo4jlabs.com`. LiteLLM proxy `1.98.0`. After #106, Gemini aliases in `scripts/litellm/config.yaml` are versioned only (`ontographia-gemini-3.7`, `ontographia-gemini-3.8`); historical JSON `model` fields are left as recorded.

Human-readable companions: [`track_a_h1_live_v0.1.6.md`](track_a_h1_live_v0.1.6.md), [`track_a_h1_live_v0.1.6_gemini-3.8.md`](track_a_h1_live_v0.1.6_gemini-3.8.md), [`track_b_exec_spot_v0.1.6.md`](track_b_exec_spot_v0.1.6.md), [`track_b_exec_spot_v0.1.6_gemini-3.8.md`](track_b_exec_spot_v0.1.6_gemini-3.8.md).

## Track A H1 live — per profile × condition

Columns: Property Hit, compile_ok, near-dup picks, invent-without-seeing, fallback rate, mean LLM calls, ≈tok p95.

| profile | condition | Part 3 (3.7, 2026-09-08) | v0.1.6 Gemini 3.7 | v0.1.6 Gemini 3.8 |
|---------|-----------|--------------------------|-------------------|-------------------|
| mid | full | 0.8875 · 36/40 · 0 · 0 · 0.0 · 0.9 · 2460 | 0.75 · 33/40 · 0 · 0 · 0.0 · 0.825 · 2515 | 0.7625 · 32/40 · 0 · 0 · 0.0 · 0.8 · 2515 |
| mid | subset | 0.7375 · 30/40 · 0 · 0 · 0.0 · 0.75 · 1247 | 0.5 · 21/40 · 0 · 0 · 0.0 · 0.525 · 1301 | 0.725 · 29/40 · 0 · 0 · 0.0 · 0.725 · 1301 |
| mid | subset_fallback | 0.95 · 40/40 · 0 · 0 · 0.15 · 1.15 · 1247 | 0.95 · 40/40 · 0 · 0 · 0.1 · 1.1 · 1301 | 0.9 · 38/40 · 0 · 0 · 0.1 · 1.05 · 1301 |
| large | full | 0.825 · 33/40 · 0 · 0 · 0.0 · 0.825 · 13710 | 0.65 · 27/40 · 0 · 0 · 0.0 · 0.675 · 13765 | 0.725 · 30/40 · 0 · 0 · 0.0 · 0.75 · 13765 |
| large | subset | 0.775 · 32/40 · 0 · 0 · 0.0 · 0.8 · 1247 | 0.6125 · 25/40 · 0 · 0 · 0.0 · 0.625 · 1301 | 0.75 · 31/40 · 0 · 0 · 0.0 · 0.775 · 1301 |
| large | subset_fallback | 0.95 · 40/40 · 0 · 0 · 0.175 · 1.175 · 1247 | 0.95 · 40/40 · 0 · 0 · 0.225 · 1.225 · 1301 | 0.8875 · 37/40 · 0 · 0 · 0.1 · 1.025 · 1301 |

### Verdicts (harness)

| run | verdict | reason (harness text) |
|-----|---------|------------------------|
| Part 3 | **support** | live large subset_fallback (recommended policy): Property Hit ≥ +10pt vs full, tokens p95 ≤ −30%, compile not worse; subset-only alone was hit -5.0pt / compile_ok 32/33 |
| v0.1.6 Gemini 3.7 | **support** | live large subset_fallback (recommended policy): Property Hit ≥ +10pt vs full, tokens p95 ≤ −30%, compile not worse; subset-only alone was hit -3.8pt / compile_ok 25/27 |
| v0.1.6 Gemini 3.8 | **support** | live large subset_fallback (recommended policy): Property Hit ≥ +10pt vs full, tokens p95 ≤ −30%, compile not worse; subset-only alone was hit +2.5pt / compile_ok 31/30 |

On `large` / `subset_fallback` (production policy): Part 3 and v0.1.6 Gemini 3.7 both recorded Property Hit 0.95 and compile 40/40; Gemini 3.8 recorded 0.8875 and 37/40. Relative to `full` on the same run, Gemini 3.8 still cleared the predeclared +10pt / −30% token / compile-not-worse gates (+16.25pt Property Hit, token p95 rel change −0.9055, compile 37 ≥ full 30).

Near-dup picks and invent-without-seeing were 0 in every arm of every run.

## Track B Exec Match spot

| metric | Part 3 (3.7, 2026-09-08) | v0.1.6 Gemini 3.7 | v0.1.6 Gemini 3.8 |
|--------|-------------------------:|------------------:|------------------:|
| n | 60 | 60 | 60 |
| compile_ok | 41 | 39 | 36 |
| compile_rate | 0.6833 | 0.65 | 0.6 |
| exec_scored | 38 | 36 | 33 |
| exec_match | 1 | 1 | 1 |
| exec_match_rate | 0.0263 | 0.0278 | 0.0303 |
| jaccard_mean | 0.0263 | 0.0278 | 0.0303 |
| structure_label_f1_mean | 0.8229 | 0.81 | 0.8062 |
| structure_rel_f1_mean | 0.6667 | 0.7009 | 0.713 |
| structure_prop_f1_mean | 0.613 | 0.5607 | 0.5944 |

| ref | Part 3 compile / exec_match_rate | v0.1.6 3.7 | v0.1.6 3.8 |
|-----|--------------------------------:|-----------:|-----------:|
| movies (n=30) | 23 / 0.0476 | 22 / 0.0526 | 21 / 0.0526 |
| recommendations (n=30) | 18 / 0.0 | 17 / 0.0 | 15 / 0.0 |

Exact Exec Match against HF gold Cypher stayed at 1 scored match in each of the three runs.

## Notes / caveats

- Single run per cell; no re-runs, tuning, or cherry-picking.
- The v0.1.6 Gemini 3.7 session (same calendar day as the 3.8 runs) also recorded E2E malformed model output such as the property name `name激as_name` (see [`examples/e2e/v0.1.6-gemini/`](../../e2e/v0.1.6-gemini/)). That observation is **not verified** as a cause of the Track A single-mode drops on the 3.7 re-run.
- Prompt ≈tok p95 for v0.1.6 arms is ~+55 vs Part 3 on matching conditions; estimates come from the installed 0.1.6 `build_initial_user_message`.
- Track B `repair_mapping_path` in the 3.8 JSON was rewritten to the repo-relative `examples/llm/mappings/movies.repair.yaml` after the run (same annotation pattern as the 3.7 v0.1.6 JSON).
- Breaking change (#106): the unversioned LiteLLM alias `ontographia-gemini` was removed. Use `ontographia-gemini-3.7` or `ontographia-gemini-3.8` (see [`docs/litellm-local.md`](../../../docs/litellm-local.md)).
