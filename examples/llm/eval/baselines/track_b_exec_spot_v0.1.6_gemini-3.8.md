# Track B Exec Match spot — v0.1.6 (PyPI) with Gemini 3.8 Flash

- Recorded (harness `recorded_at`, end of run): `2026-10-22T07:57:21Z`
- Package: `ontographia[llm]==0.1.6` from the PyPI wheel (same setup as [`track_a_h1_live_v0.1.6_gemini-3.8.md`](track_a_h1_live_v0.1.6_gemini-3.8.md))
- Repo tree (harness): `6bebd01`
- Model: LiteLLM alias `ontographia-gemini-3.8` → upstream **Gemini 3.8 Flash** (`gemini-3.8-flash`), LiteLLM `1.98.0`
- Refs: neo4jlabs_demo_db_movies, neo4jlabs_demo_db_recommendations; N: 60 (seed=53); schema_policy `auto`
- URI: `neo4j+s://demo.neo4jlabs.com`
- Repair mapping: [`examples/llm/mappings/movies.repair.yaml`](../../mappings/movies.repair.yaml) (repo-relative; absolute local path rewritten in meta after the run)
- Machine-readable: [`track_b_exec_spot_v0.1.6_gemini-3.8.json`](track_b_exec_spot_v0.1.6_gemini-3.8.json). Comparison: [`gemini_3.7_vs_3.8_v0.1.6.md`](gemini_3.7_vs_3.8_v0.1.6.md). Baseline [`track_b_exec_spot.json`](track_b_exec_spot.json) (`2026-09-08T15:10:33Z`) is unchanged.

## Summary (v0.1.6 Gemini 3.8 vs 2026-09-08 baseline)

| metric | v0.1.6 Gemini 3.8 (2026-10-22) | baseline (2026-09-08) |
|--------|-------------------------------:|----------------------:|
| n | 60 | 60 |
| compile_ok | 36 | 41 |
| compile_rate | 0.6 | 0.6833 |
| exec_scored | 33 | 38 |
| exec_match | 1 | 1 |
| exec_match_rate | 0.0303 | 0.0263 |
| jaccard_mean | 0.0303 | 0.0263 |
| structure_label_f1_mean | 0.8062 | 0.8229 |
| structure_rel_f1_mean | 0.713 | 0.6667 |
| structure_prop_f1_mean | 0.5944 | 0.613 |

| ref | n | compile OK | exec match rate |
|-----|--:|-----------:|----------------:|
| movies | 30 | 21 (23) | 0.0526 (0.0476) |
| recommendations | 30 | 15 (18) | 0.0 (0.0) |

(baseline in parentheses)

## Reading

Compile 36/60 vs baseline 41/60; Exec Match 1/33 vs 1/38. Exact Exec Match against HF gold Cypher remains rare. This is a single run with no re-runs. See [`gemini_3.7_vs_3.8_v0.1.6.md`](gemini_3.7_vs_3.8_v0.1.6.md) for the three-way comparison with the v0.1.6 Gemini 3.7 spot.

```bash
source scripts/litellm/use-provider.sh gemini-3.8
/path/to/venv-0.1.6/bin/python examples/llm/eval/run_track_b_exec.py --n 60 --seed 53 \
  --json-out examples/llm/eval/baselines/track_b_exec_spot_v0.1.6_gemini-3.8.json
# (datasets + neo4j installed in the same venv)
```
