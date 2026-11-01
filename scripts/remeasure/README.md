# Remeasure harnesses (Part 3 reproduction)

Scripts that reproduce the evaluation numbers published in
[docs/evaluation.md](../../docs/evaluation.md). Two modes:

| Script | Live LLM? | Purpose |
|--------|-----------|---------|
| [`dry_run.py`](dry_run.py) | No | Offline fixture check: a saved Intent still agrees with its expected Cypher. |
| [`run_h1_live_repeats.sh`](run_h1_live_repeats.sh) | Yes (LiteLLM / OpenAI-compatible) | N repeats of Track A H1 live (`examples/llm/eval/run_track_a_h1_live.py`) with health check, `meta.txt`, `logs/`, aggregate. |
| [`aggregate_h1_live.py`](aggregate_h1_live.py) | No | Summarize already-written `run*.json` files (Property Hit / tokens / compile across repeats). Stdlib only. |

The full command list for every Part 3 arm (mechanical, live, Track B) is in
[docs/evaluation.md — Reproduce Part 3](../../docs/evaluation.md#reproduce-part-3).

## Offline dry run

```bash
python3 scripts/remeasure/dry_run.py
```

Loads each `fixtures/*.intent.json`, checks it against the sibling
`*.expected.cypher`, prints the expected Cypher, and exits `0` on a match. No
LLM, API key, network, or Neo4j. Use `--fixtures DIR` for another fixture set.

## Live H1 remeasure (repeats)

Prerequisites:

```bash
uv sync --group dev && uv run maturin develop --release   # ontographia[llm]
scripts/litellm/start.sh
source scripts/litellm/use-provider.sh gemini-3.8          # sets OPENAI_* vars
```

Then run the repeats (this reproduces the Part 3 stem: n=3 over `mid,large`):

```bash
scripts/remeasure/run_h1_live_repeats.sh --profiles mid,large --n 3 \
  --out-dir examples/llm/eval/out/part3-$(date -u +%Y%m%d-%H%M)
```

and the large-only extension toward n=5 (separate stem, same model):

```bash
scripts/remeasure/run_h1_live_repeats.sh --profiles large --n 2 \
  --out-dir examples/llm/eval/out/part3-ext-$(date -u +%Y%m%d-%H%M)
```

The wrapper only calls `run_track_a_h1_live.py --json-out ...`; it never passes
`--record`, so checked-in baselines under `examples/llm/eval/baselines/` are not
modified. Nothing under `out/` is committed.

### Options and environment

Flags override the environment. Run `--help` for the authoritative list.

| Flag | Env | Default |
|------|-----|---------|
| `--n` | `N` | `3` |
| `--profiles` | `PROFILES` | `mid,large` |
| `--out-dir` | `OUT_DIR` | `examples/llm/eval/out/remeasure-h1-live-<UTC>` |
| `--model` | `MODEL_ALIAS` | `ontographia-gemini-3.8` |
| `--base-url` | `OPENAI_BASE_URL` | `http://127.0.0.1:4000/v1` |
| `--python` | `PYTHON` | `.venv-remeasure/bin/python`, else `uv run python`, else `python3` |
| `--limit` | `LIMIT` | `0` (all 40 gold cases) |
| `--max-retries` | `MAX_RETRIES` | `1` |
| `--skip-health-check` | — | off (requires `GET <base-url>/models` → `200`) |
| `--force` | — | off (refuses to reuse a stem that already has `run*.json`) |

`OPENAI_API_KEY` is read from the environment (LiteLLM master key). Only the
local development placeholder is used as a fallback default; never commit real
keys. `ONTOGRAPHIA_LLM_BACKEND` defaults to `openai`.

### Output layout

```text
<out-dir>/
├── meta.txt              # repo rev, dirty flag, python/pkg, model, base URL, n, timings
├── logs/run1.log …       # full harness stdout/stderr per repeat
├── json/run1.json …      # payload from run_track_a_h1_live.py --json-out
├── aggregate.json        # per profile/condition means and ranges across runs
├── aggregate_index.json  # files + per-run meta (recorded_at, git_rev, model, verdict)
└── aggregate.md          # markdown table for pasting next to the published tables
```

The wrapper exits `2` when LiteLLM is unhealthy or arguments are invalid, `3`
when a repeat fails, and `4` when aggregation fails. Partial stems keep their
`json/` and `logs/` for diagnosis.

### Aggregating a stem by hand

```bash
python3 scripts/remeasure/aggregate_h1_live.py \
  --out-dir examples/llm/eval/out/part3-20261101-1200
```

Reads `<out-dir>/json/run*.json` in natural (`run2` before `run10`) order and
reports, per profile and condition: repeat count, Property Hit mean and
min–max, compile OK over total cases, fallback rate, ≈tokens p95 mean, and mean
LLM calls. Missing profiles/conditions (for example a `large`-only extension)
are counted only for the runs that contain them. `--no-write` prints the table
without writing files.

## Scope

- These are remeasure drivers, not new studies: they report the same metrics as
  the harness they wrap, and this directory stores no baseline numbers.
- No CI job runs live LLM evals; `dry_run.py` is the offline check.
- Feature changes to prompts, schema exposure, subsetting, or Intent extraction
  should follow the [Context Rot feature-add checklist](../../docs/evaluation.md#feature-add-checklist-context-rot-lens).
