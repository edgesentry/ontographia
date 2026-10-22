# Track B Exec Match spot — v0.1.6 (PyPI) re-run

- Recorded (harness `recorded_at`, end of run): `2026-10-22T05:05:32Z` (2026-10-22 13:05:32 SGT); run started `2026-10-22T03:09:33Z` (11:09:33 SGT)
- Package: `ontographia[llm]==0.1.6` from the PyPI wheel (same venv as [`track_a_h1_live_v0.1.6.md`](track_a_h1_live_v0.1.6.md))
- Repo tree (harness): `1624a2d`
- Model: LiteLLM alias `ontographia-gemini` → upstream **Gemini 3.7 Flash** (`gemini-3.7-flash`), LiteLLM `1.98.0`
- Refs: neo4jlabs_demo_db_movies, neo4jlabs_demo_db_recommendations; N: 60 (seed=53); schema_policy `auto`
- URI: `neo4j+s://demo.neo4jlabs.com`
- Machine-readable: [`track_b_exec_spot_v0.1.6.json`](track_b_exec_spot_v0.1.6.json). Baseline [`track_b_exec_spot.json`](track_b_exec_spot.json) (`2026-09-08T15:10:33Z`) is unchanged.

## Summary (v0.1.6 run vs 2026-09-08 baseline)

| metric | v0.1.6 (2026-10-22) | baseline (2026-09-08) |
|--------|--------------------:|----------------------:|
| n | 60 | 60 |
| compile_ok | 39 | 41 |
| compile_rate | 0.65 | 0.6833 |
| exec_scored | 36 | 38 |
| exec_match | 1 | 1 |
| exec_match_rate | 0.0278 | 0.0263 |
| jaccard_mean | 0.0278 | 0.0263 |
| structure_label_f1_mean | 0.81 | 0.8229 |
| structure_rel_f1_mean | 0.7009 | 0.6667 |
| structure_prop_f1_mean | 0.5607 | 0.613 |

| ref | n | compile OK | exec match rate |
|-----|--:|-----------:|----------------:|
| movies | 30 | 22 (23) | 0.0526 (0.0476) |
| recommendations | 30 | 17 (18) | 0.0 (0.0) |

(baseline in parentheses)

## Reading

Close to the baseline: compile 39/60 vs 41/60, Exec Match 1/36 vs 1/38. Exact Exec Match against HF gold Cypher remains rare. This is a single run with no re-runs. The run took ~2 h wall-clock (slow LLM / demo DB round-trips; the local machine was also briefly unreachable during the run).

```bash
source scripts/litellm/use-provider.sh gemini
/path/to/venv-0.1.6/bin/python examples/llm/eval/run_track_b_exec.py --n 60 --seed 53 \
  --json-out examples/llm/eval/baselines/track_b_exec_spot_v0.1.6.json
# (datasets + neo4j installed in the same venv)
```
