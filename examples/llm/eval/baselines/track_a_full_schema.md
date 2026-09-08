# Track A baseline — full-schema Intent stress test

- Recorded: `2026-09-08T09:11:27Z`
- Git: `0563c07`
- Harness: `examples/llm/eval/run_track_a.py`
- Profiles: small, mid, large

## Results

```
Track A stress test (full-schema compile + prompt size vs subset)
profile    props  gold_ok wrong_ok wrong_fail prop_hit tok_full  tok_sub
small         16       40        0         40     0.50     1359     1246
mid          200       40       40          0     0.50     2460     1247
large       2000       40       40          0     0.50    13710     1247
```

## Interpretation

On mid/large, `silent_wrong_compile_ok ≈ gold_ok` means `Engine::build` accepts plausible wrong fields (Kervin failure mode). On small, `wrong_fail` should be high because distractors are absent.

`tok_sub` is exact-match ontology subset prompts (issue #45); it should be much smaller than `tok_full` on mid/large.

Machine-readable copy: [`track_a_full_schema.json`](track_a_full_schema.json).

Regenerate:

```bash
uv run python examples/llm/eval/run_track_a.py --record
```
