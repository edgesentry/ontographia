# Track A H3 — always_full_fixed vs adaptive spend

- Recorded: `2026-09-08T13:28:37Z`
- Git: `cbcde8f`
- Harness: `examples/llm/eval/run_track_a_h3.py`
- Profiles: small, mid, large

## Verdict

**support** — on large/easy: tokens p95 ≤ −30% vs always_full, LLM calls not higher, Compile/Property Hit not worse; hard slice escalates and recovers (mechanical arm)

Caveat: Mechanical arm: mock extractors (gold on easy; subset-fail→full-gold on hard). Measures #47 retry/schema budgeting, not live-LLM difficulty routing. Follow-up live LLM: issue #68.

```json
{
  "easy_token_p95_rel_change": -0.909,
  "token_p95_reduction_threshold": -0.3,
  "easy_property_hit_delta_pt": 0.0,
  "easy_adaptive_mean_llm_calls": 1.0,
  "easy_full_mean_llm_calls": 1.0,
  "easy_calls_not_higher": true,
  "easy_compile_not_worse": true,
  "hard_escalation_rate": 1.0,
  "hard_adaptive_compile_ok": 40,
  "hard_escalate_recovers": true
}
```

## Results

```
Track A H3 (always_full_fixed vs adaptive)
profile  slice cond                  hit  compile    esc  calls  tok_f_p95  tok_t_p95
small    easy  always_full_fixed    1.00  40/40     0.00   1.00       1359       1359
small    easy  adaptive             1.00  40/40     0.00   1.00       1246       1246
small    hard  always_full_fixed    1.00  40/40     0.00   1.00       1359       1359
small    hard  adaptive             1.00  40/40     1.00   2.00       1359       2605
mid      easy  always_full_fixed    1.00  40/40     0.00   1.00       2460       2460
mid      easy  adaptive             1.00  40/40     0.00   1.00       1247       1247
mid      hard  always_full_fixed    1.00  40/40     0.00   1.00       2460       2460
mid      hard  adaptive             1.00  40/40     1.00   2.00       2460       3707
large    easy  always_full_fixed    1.00  40/40     0.00   1.00      13710      13710
large    easy  adaptive             1.00  40/40     0.00   1.00       1247       1247
large    hard  always_full_fixed    1.00  40/40     0.00   1.00      13710      13710
large    hard  adaptive             1.00  40/40     1.00   2.00      13710      14957
```

## Method

- `always_full_fixed`: full schema + `max_retries=5`
- `adaptive`: subset-first (`initial_retries=1`); escalate to full (`escalated_retries=5`) only on failure (issue #47)
- **easy**: mock extractor returns gold Intent on first call
- **hard**: subset extract is invalid; full extract returns gold (forces escalation)

`tok_f_*` = final-phase prompt ≈tokens; `tok_t_*` = sum across phases tried.

Machine-readable: [`track_a_h3.json`](track_a_h3.json).

```bash
uv run python examples/llm/eval/run_track_a_h3.py --record
```
