# Track A H1 live — v0.1.6 (PyPI) with Gemini 3.8 Flash

- Recorded (harness `recorded_at`, end of run): `2026-10-22T05:43:55Z`
- Package: `ontographia[llm]==0.1.6` installed from the PyPI wheel into a clean venv (`uv venv` + `uv pip install`), **not** an editable / maturin build. The harness was run with that venv's `python`, so `examples/llm/eval/*` helpers come from the repo tree while `ontographia` / `ontographia.llm` resolve to `site-packages` (verified via `ontographia.__file__`).
- Repo tree (harness + gold set): `6bebd01` (origin/main at run time)
- Model: LiteLLM alias `ontographia-gemini-3.8` → upstream **Gemini 3.8 Flash** (`gemini-3.8-flash`), LiteLLM `1.98.0`, `temperature=0`, `max_retries=1`
- Cases: 40 gold × profiles mid, large × conditions full, subset, subset_fallback
- Machine-readable: [`track_a_h1_live_v0.1.6_gemini-3.8.json`](track_a_h1_live_v0.1.6_gemini-3.8.json) (metrics unmodified; meta annotated with package / upstream model after the run). Comparison across Part 3 / v0.1.6 Gemini 3.7 / v0.1.6 Gemini 3.8: [`gemini_3.7_vs_3.8_v0.1.6.md`](gemini_3.7_vs_3.8_v0.1.6.md). Baseline [`track_a_h1_live.json`](track_a_h1_live.json) (`2026-09-08T14:42:52Z`) is unchanged.

## Results (v0.1.6 Gemini 3.8 run, Part 3 baseline 2026-09-08 in parentheses)

| profile | condition | Property Hit | compile OK | near-dup picks | invent-without-seeing | fallback | mean LLM calls | ≈tok p95 |
|---------|-----------|-------------:|-----------:|---------------:|----------------------:|---------:|---------------:|---------:|
| mid | full | 0.76 (0.89) | 32/40 (36/40) | 0 (0) | 0 (0) | 0.00 (0.00) | 0.8 (0.9) | 2,515 (2,460) |
| mid | subset | 0.72 (0.74) | 29/40 (30/40) | 0 (0) | 0 (0) | 0.00 (0.00) | 0.725 (0.75) | 1,301 (1,247) |
| mid | subset_fallback | 0.90 (0.95) | 38/40 (40/40) | 0 (0) | 0 (0) | 0.10 (0.15) | 1.05 (1.15) | 1,301 (1,247) |
| large | full | 0.72 (0.82) | 30/40 (33/40) | 0 (0) | 0 (0) | 0.00 (0.00) | 0.75 (0.825) | 13,765 (13,710) |
| large | subset | 0.75 (0.78) | 31/40 (32/40) | 0 (0) | 0 (0) | 0.00 (0.00) | 0.775 (0.8) | 1,301 (1,247) |
| large | subset_fallback | 0.89 (0.95) | 37/40 (40/40) | 0 (0) | 0 (0) | 0.10 (0.17) | 1.025 (1.175) | 1,301 (1,247) |

## Verdict (harness output)

**support** — live large subset_fallback (recommended policy): Property Hit ≥ +10pt vs full, tokens p95 ≤ −30%, compile not worse; subset-only alone was hit +2.5pt / compile_ok 31/30

```json
{
  "property_hit_gain_threshold_pt": 10.0,
  "token_p95_reduction_threshold": -0.3,
  "full_compile_ok": 30,
  "full_property_hit": 0.725,
  "full_near_dup_picked": 0,
  "subset_only": {
    "property_hit_gain_pt": 2.5,
    "token_p95_rel_change": -0.9055,
    "compile_not_worse": true,
    "arm_compile_ok": 31,
    "arm_property_hit": 0.75,
    "arm_fallback_rate": 0.0,
    "invent_without_seeing_rate": 0.0,
    "near_dup_picked": 0
  },
  "subset_fallback": {
    "property_hit_gain_pt": 16.25,
    "token_p95_rel_change": -0.9055,
    "compile_not_worse": true,
    "arm_compile_ok": 37,
    "arm_property_hit": 0.8875,
    "arm_fallback_rate": 0.1,
    "invent_without_seeing_rate": 0.0,
    "near_dup_picked": 0
  }
}
```

## Reading

- The recommended policy (`subset_fallback` / `schema_policy=auto`) still meets the harness support criteria on `large`: Property Hit 0.89 vs full 0.72 (+16.25pt), ≈tok p95 1,301 vs 13,765, compile 37/40 (not worse than full 30/40). Absolute `subset_fallback` hit/compile are below the Part 3 and v0.1.6 Gemini 3.7 runs (both 0.95 / 40/40); see the comparison doc.
- Single-mode arms (`full`, `subset`) on this run sit between the weaker v0.1.6 Gemini 3.7 day and the Part 3 baseline on several cells (for example `large` / `full` Property Hit 0.725 vs 0.65 on 3.7 vs 0.825 on Part 3).
- Near-duplicate picks and invent-without-seeing stayed at 0 in every arm.
- Prompt token estimates match the v0.1.6 Gemini 3.7 re-run (~+55 vs Part 3), as expected from the same installed 0.1.6 `build_initial_user_message`.
- `mean_llm_calls` only counts calls for cases that compiled (the harness records 0 on exceptions), so it is below 1.0 for arms with compile failures.
- No re-runs or cherry-picking; this is the single recorded Gemini 3.8 run for issue #106.

## Reproduce

```bash
uv venv --python 3.12 /path/to/venv-0.1.6
uv pip install --python /path/to/venv-0.1.6/bin/python "ontographia[llm]==0.1.6"
# LiteLLM proxy per docs/litellm-local.md (alias ontographia-gemini-3.8 → gemini/gemini-3.8-flash)
source scripts/litellm/use-provider.sh gemini-3.8
/path/to/venv-0.1.6/bin/python examples/llm/eval/run_track_a_h1_live.py \
  --profiles mid,large --json-out examples/llm/eval/baselines/track_a_h1_live_v0.1.6_gemini-3.8.json
```

`--json-out` (not `--record`) is used so the 2026-09-08 `track_a_h1_live.json` / `.md` baseline is not overwritten.
