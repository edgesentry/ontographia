# H2 — Intent refinement with execution feedback

- Recorded: `2026-09-08T13:12:20Z`
- Git: `4db68ce`
- Harness: `examples/llm/eval/run_track_a_h2.py`
- Issue: #55

## Verdict

**support** — on empty-inducing set: final execution_ok ≥ +20pt with refine, ≥80% recovered to gold Intent+rows, Cypher always from Engine.build (mechanical arm)

Caveat: Mechanical arm: mock executor + gold-returning corrector. Measures that the #46 loop recovers Empty@Valid when Intent correction succeeds; not live-LLM correction quality or real Neo4j Exec Match.

```json
{
  "final_ok_gain_pt": 100.0,
  "final_ok_gain_threshold_pt": 20.0,
  "intent_exact_match_gain_pt": 100.0,
  "cypher_always_from_engine_build": true,
  "gold_control_no_spurious_refine": true,
  "no_refine_final_ok_rate": 0.0,
  "with_refine_final_ok_rate": 1.0,
  "with_refine_recovered_rate": 1.0,
  "empty_at_valid_rate": 1.0
}
```

## Results

```
H2 (exec feedback Intent refine)
arm              cond          empty@v final_ok    exact recovered cypherOK   corr
empty_inducing   no_refine        1.00     0.00     0.00      0.00     1.00   0.00
empty_inducing   with_refine      1.00     1.00     1.00      1.00     1.00   1.00
gold_control     no_refine        0.00     1.00     1.00      0.00     1.00   0.00
gold_control     with_refine      0.00     1.00     1.00      0.00     1.00   0.00
```

## Method

Corrupt gold filter *values* → Empty@Valid (compile OK, mock exec empty). `no_refine` stops there; `with_refine` feeds Neo4j feedback into `extract_correction`, which mechanically returns gold Intent; Cypher is always recompiled via `Engine.build`. Gold control uses uncorrupted Intents.

Machine-readable: [`track_a_h2.json`](track_a_h2.json).

```bash
uv run python examples/llm/eval/run_track_a_h2.py --record
```
