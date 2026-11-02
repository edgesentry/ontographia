# Remeasure harnesses

Scripts that re-run the evaluation arms published in
[docs/evaluation.md](../../docs/evaluation.md). The default path is offline;
only the explicitly live arms call a model or a database.

| Script | Live? | Purpose |
|--------|-------|---------|
| [`run_all.sh`](run_all.sh) | Opt-in | Top-level runner for every arm: Track A, H1 mechanical, H2, H3, Track B schema convert, `dry_run`, plus H1 live and Track B Exec Match under `--live`. |
| [`dry_run.py`](dry_run.py) | No | Offline fixture check: a saved Intent still agrees with its expected Cypher. |
| [`run_h1_live_repeats.sh`](run_h1_live_repeats.sh) | Yes (LiteLLM / OpenAI-compatible) | N repeats of Track A H1 live (`examples/llm/eval/run_track_a_h1_live.py`) with health check, `meta.txt`, `logs/`, aggregate. |
| [`aggregate_h1_live.py`](aggregate_h1_live.py) | No | Summarize already-written `run*.json` files (Property Hit / tokens / compile across repeats). Stdlib only. |

The arm-by-arm command list is in
[docs/evaluation.md — Reproduce or refresh all arms](../../docs/evaluation.md#reproduce-or-refresh-all-arms).

## Run every arm

Default run — no LLM spend, no database:

```bash
scripts/remeasure/run_all.sh
```

This runs `track-a`, `h1` (mechanical), `h2`, `h3`, `track-b` (schema
conversion; downloads the public HF dataset), and `dry-run`. Outputs go under
`examples/llm/eval/out/run-all-<UTC>/` (gitignored).

Live arms — H1 live repeats and Track B Exec Match:

```bash
scripts/litellm/start.sh
source scripts/litellm/use-provider.sh gemini-3.8
scripts/remeasure/run_all.sh --live --h1-live-n 3
```

`--live` first probes `GET <base-url>/models` and aborts before spending tokens
if LiteLLM is unhealthy. Track B Exec Match additionally needs network access to
`neo4j+s://demo.neo4jlabs.com` and the `datasets` / `neo4j` extras (injected via
`uv run --with` when uv is available).

Select arms explicitly (useful for a quick check or a single table):

```bash
scripts/remeasure/run_all.sh --only dry-run
scripts/remeasure/run_all.sh --only h1,h2 --out-dir examples/llm/eval/out/check
scripts/remeasure/run_all.sh --only track-b-exec --live
```

Arm IDs: `track-a`, `h1`, `h1-live`, `h2`, `h3`, `track-b`, `track-b-exec`,
`dry-run`. Live IDs require `--live`; they are never selected implicitly.

### Interpreter modes and stale native builds

`run_all.sh` picks the local interpreter in this order (override with
`--python`): `.venv-remeasure/bin/python`, else `uv run python` (project mode),
else `python3`. That interpreter must be able to `import ontographia` for the
`track-a` / `h1` / `h2` / `h3` / `h1-live` arms; the runner probes the import
up front and exits `2` with guidance instead of dying per-arm when it fails.

The `track-b` and `track-b-exec` arms are different: they run against the
**published wheel** via `uv run --no-project --with "$ONTOGRAPHIA_WHEEL_SPEC"`
(default `ontographia[llm]==0.1.8`, overridable via the environment). The
harness scripts still come from this checkout; only the `ontographia` package
resolves to PyPI. This is the recommended mode for Track B remeasurement —
it cannot be broken by the state of your local Rust build (issue
[#144](https://github.com/edgesentry/ontographia/issues/144)).

The classic local-build failure is a stale or half-built Maturin extension
left in the source tree (`python/ontographia/*.so`, gitignored via `*.so`),
which makes project-mode imports die with
`ImportError: ... mis-aligned LINKEDIT ...`. Any one of these fixes it:

```bash
rm -f python/ontographia/*.so                                  # drop stale extensions
uv sync --group dev && uv run maturin develop --release        # or rebuild in place
scripts/remeasure/run_all.sh --python .venv-remeasure/bin/python  # or use a clean venv
```

### Options and output

| Flag | Default | Meaning |
|------|---------|---------|
| `--only ARMS` | offline set | Comma-separated arm IDs; replaces the default selection. |
| `--live` | off | Add `h1-live` + `track-b-exec` to the default set (or permit them under `--only`). |
| `--out-dir DIR` | `examples/llm/eval/out/run-all-<UTC>` | Output root. |
| `--record` | off | Pass `--record` through so harnesses rewrite checked-in baselines. Never implied. |
| `--profiles LIST` | harness default | Profiles for `track-a` / `h1` / `h3`. |
| `--h1-live-n N` | `1` | Repeats for `h1-live` (the published protocol used 3). |
| `--h1-live-profiles LIST` | `mid,large` | Profiles for `h1-live`. |
| `--limit N` | `0` (all) | Pass `--limit` to the H1 live harness. |
| `--model ALIAS` | `ontographia-gemini-3.8` | `OPENAI_MODEL` / LiteLLM alias for live arms. |
| `--base-url URL` | `http://127.0.0.1:4000/v1` | OpenAI-compatible endpoint. |
| `--python CMD` | `.venv-remeasure/bin/python`, else `uv run python`, else `python3` | Interpreter command. |
| `--skip-health-check` | off | Do not require `GET <base-url>/models` → `200`. |
| `--force` | off | Reuse an `--out-dir` that already has `status.tsv`. |
| `--fail-fast` | off | Stop after the first failing arm (default: run every selected arm). |
| `--list-arms` | off | Print the selected arm IDs and exit. |

`OPENAI_API_KEY` is read from the environment (LiteLLM master key). Only the
local development placeholder is used as a fallback default; never commit real
keys. `ONTOGRAPHIA_LLM_BACKEND` defaults to `openai`.

The runner writes:

```text
<out-dir>/
├── meta.txt            # repo rev, dirty flag, python/pkg, arms, model, timings
├── status.tsv          # arm, pass/fail, exit code, duration, log path
├── summary.md          # same status table for humans
├── logs/<arm>.log      # full harness stdout/stderr
├── logs/<arm>.exit     # exit code
├── logs/<arm>.command  # exact command, for reproduction
├── json/<arm>.json     # harness --json-out payload (arms that support it)
└── h1-live/            # repeat wrapper layout when h1-live is selected
```

The runner records process status only. It never parses or invents metrics and
never edits `docs/evaluation.md` or the checked-in baselines; compare logs or
`json/` payloads with the published tables by hand. Exit codes: `0` all selected
arms passed, `1` at least one arm failed, `2` invalid arguments / existing
output directory / unhealthy LiteLLM.

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

Then run the repeats (n=3 over `mid,large`, the published live protocol):

```bash
scripts/remeasure/run_h1_live_repeats.sh --profiles mid,large --n 3 \
  --out-dir examples/llm/eval/out/remeasure-h1-live-$(date -u +%Y%m%d-%H%M)
```

and the large-only extension toward n=5 (separate stem, same model):

```bash
scripts/remeasure/run_h1_live_repeats.sh --profiles large --n 2 \
  --out-dir examples/llm/eval/out/remeasure-h1-live-ext-$(date -u +%Y%m%d-%H%M)
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
  --out-dir examples/llm/eval/out/remeasure-h1-live-20261101-1200
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
