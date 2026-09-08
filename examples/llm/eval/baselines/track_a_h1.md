# Track A H1 — full vs subset vs subset+fallback

- Recorded: `2026-09-08T09:20:56Z`
- Git: `b7045ae`
- Harness: `examples/llm/eval/run_track_a_h1.py`
- Profiles: small, mid, large

## Verdict

**support** — on large: Property Hit ≥ +10pt vs full, tokens p95 ≤ −30%, compile success not worse (mechanical prompt-vocab arm)

Caveat: Mechanical arm: induced silent-wrong only when the distractor name appears in the prompt property list. A live LLM could still invent near-duplicates without seeing them.

```json
{
  "property_hit_gain_pt": 50.0,
  "property_hit_gain_threshold_pt": 10.0,
  "token_p95_rel_change": -0.909,
  "token_p95_reduction_threshold": -0.3,
  "compile_not_worse": true,
  "subset_compile_ok": 40,
  "full_compile_ok": 40
}
```

## Results

```
Track A H1 (prompt-vocab induced Intent)
profile  cond                hit  compile  vis_d  wrong     fb  tok_p50  tok_p95
small    full               1.00  40/40        0      0   0.00     1317     1359
small    subset             1.00  40/40        0      0   0.00     1172     1246
small    subset_fallback    1.00  40/40        0      0   0.00     1172     1246
mid      full               0.50  40/40       40     40   0.00     2417     2460
mid      subset             1.00  40/40        0      0   0.00     1174     1247
mid      subset_fallback    1.00  40/40        0      0   0.00     1174     1247
large    full               0.50  40/40       40     40   0.00    13667    13710
large    subset             1.00  40/40        0      0   0.00     1174     1247
large    subset_fallback    1.00  40/40        0      0   0.00     1174     1247
```

## Qualitative (large / full)

- `bom_suppliers_00`: full prompt surfaces `SupplierName` (property_hit=0.5); subset hides it
- `bom_suppliers_01`: full prompt surfaces `SupplierName` (property_hit=0.5); subset hides it
- `bom_suppliers_02`: full prompt surfaces `SupplierName` (property_hit=0.5); subset hides it
- `bom_suppliers_03`: full prompt surfaces `SupplierName` (property_hit=0.5); subset hides it
- `bom_suppliers_04`: full prompt surfaces `SupplierName` (property_hit=0.5); subset hides it

## Method

Induced Intent = silent-wrong near-duplicate **only if** that property name appears in the prompt's property vocabulary; else gold. `subset_fallback` uses full when the subset is empty or gold classes/relationships are missing from subset schema enums.

Machine-readable: [`track_a_h1.json`](track_a_h1.json).

```bash
uv run python examples/llm/eval/run_track_a_h1.py --record
```
