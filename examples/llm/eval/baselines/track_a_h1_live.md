# Track A H1 live — full vs subset vs subset+fallback

- Recorded: `2026-09-08T14:42:52Z`
- Git: `c8d8a05`
- Model: `ontographia-gemini` → upstream **Gemini 3.7 Flash** (`gemini-3.7-flash`)
- Base URL: `http://127.0.0.1:4000/v1`
- Harness: `examples/llm/eval/run_track_a_h1_live.py`
- Profiles: mid, large
- Cases per condition: 40

## Verdict

**support** — live large subset_fallback (recommended policy): Property Hit ≥ +10pt vs full, tokens p95 ≤ −30%, compile not worse; subset-only alone was hit -5.0pt / compile_ok 32/33

Caveat: Live OpenAI-compatible extractor (temperature=0). Primary verdict is on subset_fallback (schema_policy=auto), the production path from #45. subset-only is reported for ablation. invent_without_seeing counts near-duplicate picks absent from the final prompt property vocabulary. Mechanical H1 remains the prompt-vocab control experiment.

```json
{
  "property_hit_gain_threshold_pt": 10.0,
  "token_p95_reduction_threshold": -0.3,
  "full_compile_ok": 33,
  "full_property_hit": 0.825,
  "full_near_dup_picked": 0,
  "subset_only": {
    "property_hit_gain_pt": -5.0,
    "token_p95_rel_change": -0.909,
    "compile_not_worse": false,
    "arm_compile_ok": 32,
    "arm_property_hit": 0.775,
    "arm_fallback_rate": 0.0,
    "invent_without_seeing_rate": 0.0,
    "near_dup_picked": 0
  },
  "subset_fallback": {
    "property_hit_gain_pt": 12.5,
    "token_p95_rel_change": -0.909,
    "compile_not_worse": true,
    "arm_compile_ok": 40,
    "arm_property_hit": 0.95,
    "arm_fallback_rate": 0.175,
    "invent_without_seeing_rate": 0.0,
    "near_dup_picked": 0
  }
}
```

## Results

```
Track A H1 live LLM
profile  cond                hit  compile  ndup invent     fb  calls  tok_p95
mid      full               0.89  36/40       0      0   0.00   0.90     2460
mid      subset             0.74  30/40       0      0   0.00   0.75     1247
mid      subset_fallback    0.95  40/40       0      0   0.15   1.15     1247
large    full               0.82  33/40       0      0   0.00   0.82    13710
large    subset             0.78  32/40       0      0   0.00   0.80     1247
large    subset_fallback    0.95  40/40       0      0   0.17   1.18     1247
```

## Qualitative (large / full errors)

- (none)

## Method

Live OpenAI-compatible Intent extraction via `extract_validated_intent` with `schema_policy` mapped from H1 conditions. Tokens approximate the first-phase prompt. `invent_without_seeing` = preferred near-duplicate chosen while absent from the final prompt property list.

Machine-readable: [`track_a_h1_live.json`](track_a_h1_live.json).

```bash
uv run python examples/llm/eval/run_track_a_h1_live.py --profiles mid,large --record
```
