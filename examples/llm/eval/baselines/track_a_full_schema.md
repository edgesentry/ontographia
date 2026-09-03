# Track A baseline — full-schema Intent stress test

- Recorded: `2026-09-03T11:20:01Z`
- Git: `bfe7336`
- Harness: `examples/llm/eval/run_track_a.py`
- Profiles: small, mid, large

## Results

```
Track A stress test (full-schema prompt + compile)
profile    props  gold_ok wrong_ok wrong_fail prop_hit  tok_p50
small         16       40        0         40     0.50     1359
mid          200       40       40          0     0.50     2460
large       2000       40       40          0     0.50    13710
```

## Interpretation

On mid/large, `silent_wrong_compile_ok ≈ gold_ok` means `Engine::build` accepts plausible wrong fields (Kervin failure mode). On small, `wrong_fail` should be high because distractors are absent.

Machine-readable copy: [`track_a_full_schema.json`](track_a_full_schema.json).

Regenerate:

```bash
uv run python examples/llm/eval/run_track_a.py --record
```
