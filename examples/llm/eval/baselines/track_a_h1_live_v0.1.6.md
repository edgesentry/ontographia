# Track A H1 live — v0.1.6 (PyPI) re-run vs 2026-09-08 baseline

- Recorded (harness `recorded_at`, end of run): `2026-10-22T03:09:33Z` (2026-10-22 11:09:33 SGT); run started `2026-10-22T02:43:57Z` (10:43:57 SGT)
- Package: `ontographia[llm]==0.1.6` installed from the PyPI wheel into a clean venv (`uv venv` + `uv pip install`), **not** an editable / maturin build. The harness was run with that venv's `python`, so `examples/llm/eval/*` helpers come from the repo tree while `ontographia` / `ontographia.llm` resolve to `site-packages` (verified via `ontographia.__file__`).
- Repo tree (harness + gold set): `1624a2d` (origin/main at run time)
- Model: LiteLLM alias `ontographia-gemini` → upstream **Gemini 3.7 Flash** (`gemini-3.7-flash`), LiteLLM `1.98.0`, `temperature=0`, `max_retries=1`
- Cases: 40 gold × profiles mid, large × conditions full, subset, subset_fallback
- Machine-readable: [`track_a_h1_live_v0.1.6.json`](track_a_h1_live_v0.1.6.json) (metrics unmodified; meta annotated with package / upstream model after the run). Baseline [`track_a_h1_live.json`](track_a_h1_live.json) (`2026-09-08T14:42:52Z`, git `c8d8a05`) is unchanged.

## Results (v0.1.6 run, baseline 2026-09-08 in parentheses)

| profile | condition | Property Hit | compile OK | near-dup picks | invent-without-seeing | fallback | mean LLM calls | ≈tok p95 |
|---------|-----------|-------------:|-----------:|---------------:|----------------------:|---------:|---------------:|---------:|
| mid | full | 0.75 (0.89) | 33/40 (36/40) | 0 (0) | 0 (0) | 0.00 (0.00) | 0.825 (0.9) | 2,515 (2,460) |
| mid | subset | 0.50 (0.74) | 21/40 (30/40) | 0 (0) | 0 (0) | 0.00 (0.00) | 0.525 (0.75) | 1,301 (1,247) |
| mid | subset_fallback | 0.95 (0.95) | 40/40 (40/40) | 0 (0) | 0 (0) | 0.10 (0.15) | 1.1 (1.15) | 1,301 (1,247) |
| large | full | 0.65 (0.82) | 27/40 (33/40) | 0 (0) | 0 (0) | 0.00 (0.00) | 0.675 (0.825) | 13,765 (13,710) |
| large | subset | 0.61 (0.78) | 25/40 (32/40) | 0 (0) | 0 (0) | 0.00 (0.00) | 0.625 (0.8) | 1,301 (1,247) |
| large | subset_fallback | 0.95 (0.95) | 40/40 (40/40) | 0 (0) | 0 (0) | 0.23 (0.17) | 1.225 (1.175) | 1,301 (1,247) |

## Verdict (harness output)

**support** — live large subset_fallback (recommended policy): Property Hit ≥ +10pt vs full, tokens p95 ≤ −30%, compile not worse; subset-only alone was hit -3.8pt / compile_ok 25/27

```json
{
  "property_hit_gain_threshold_pt": 10.0,
  "token_p95_reduction_threshold": -0.3,
  "full_compile_ok": 27,
  "full_property_hit": 0.65,
  "full_near_dup_picked": 0,
  "subset_only": {
    "property_hit_gain_pt": -3.75,
    "token_p95_rel_change": -0.9055,
    "compile_not_worse": false,
    "arm_compile_ok": 25,
    "arm_property_hit": 0.6125,
    "arm_fallback_rate": 0.0,
    "invent_without_seeing_rate": 0.0,
    "near_dup_picked": 0
  },
  "subset_fallback": {
    "property_hit_gain_pt": 30.0,
    "token_p95_rel_change": -0.9055,
    "compile_not_worse": true,
    "arm_compile_ok": 40,
    "arm_property_hit": 0.95,
    "arm_fallback_rate": 0.225,
    "invent_without_seeing_rate": 0.0,
    "near_dup_picked": 0
  }
}
```

## Reading

- The recommended policy (`subset_fallback` / `schema_policy=auto`) reproduces the baseline on both profiles: Property Hit 0.95 and compile 40/40, with ≈tok p95 ~1.3k vs ~13.8k for `large` / `full`.
- Single-mode arms (`full`, `subset`) were clearly worse than on 2026-09-08 (for example `large` / `full` 0.82 → 0.65 Property Hit, 33 → 27 compile). The cause is not isolated (same alias, same upstream model id, `temperature=0`). During the same session, the E2E runs saw garbled model output (for example the property `"name激as_name"`; see [`examples/e2e/v0.1.6-gemini/`](../../../e2e/v0.1.6-gemini/)), so upstream decoding variance on this day is a plausible contributor. No re-runs or cherry-picking were done; this is the single recorded run.
- Near-duplicate picks and invent-without-seeing stayed at 0 in every arm.
- Prompt token estimates are ~+55 tokens higher than the baseline across the board. The estimate comes from `build_initial_user_message` in the installed 0.1.6 package, so prompt-template changes since `c8d8a05` are included.
- `mean_llm_calls` only counts calls for cases that compiled (the harness records 0 on exceptions), so it is below 1.0 for arms with compile failures.

## Reproduce

```bash
uv venv --python 3.12 /path/to/venv-0.1.6
uv pip install --python /path/to/venv-0.1.6/bin/python "ontographia[llm]==0.1.6"
# LiteLLM proxy per docs/litellm-local.md (alias ontographia-gemini-3.7 → gemini/gemini-3.7-flash; recorded as ontographia-gemini before #106)
source scripts/litellm/use-provider.sh gemini-3.7
/path/to/venv-0.1.6/bin/python examples/llm/eval/run_track_a_h1_live.py \
  --profiles mid,large --json-out examples/llm/eval/baselines/track_a_h1_live_v0.1.6.json
```

`--json-out` (not `--record`) is used so the 2026-09-08 `track_a_h1_live.json` / `.md` baseline is not overwritten.
