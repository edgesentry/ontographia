#!/usr/bin/env bash
# N-repeat Track A H1 live remeasure (issue #142).
#
# Runs examples/llm/eval/run_track_a_h1_live.py N times against a local
# LiteLLM (or any OpenAI-compatible) endpoint, writing one JSON per repeat plus
# meta.txt, logs/, aggregate.json, and aggregate_index.json under OUT_DIR.
#
# Usage:
#   scripts/remeasure/run_h1_live_repeats.sh --profiles mid,large --n 3
#   scripts/remeasure/run_h1_live_repeats.sh --profiles large --n 2 \
#     --out-dir examples/llm/eval/out/remeasure-h1-live-ext
#   scripts/remeasure/run_h1_live_repeats.sh --skip-health-check --limit 4
#
# See scripts/remeasure/README.md for the live-repeat recipe and environment vars.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

usage() {
  cat <<EOF
N-repeat Track A H1 live remeasure.

Usage: scripts/remeasure/run_h1_live_repeats.sh [options]

Options:
  --n N                 repeats (default: $N)
  --profiles LIST       harness profiles (default: $PROFILES)
  --out-dir DIR         output stem dir (default: examples/llm/eval/out/remeasure-h1-live-<UTC>)
  --model ALIAS         OPENAI_MODEL / LiteLLM alias (default: $MODEL_ALIAS)
  --base-url URL        OpenAI-compatible base URL (default: $OPENAI_BASE_URL)
  --python CMD          interpreter command, may contain args (default: uv run python)
  --limit N             pass --limit N to the harness (0 = all gold cases)
  --max-retries N       pass --max-retries N to the harness (default: $MAX_RETRIES)
  --skip-health-check   do not require GET <base-url>/models to return 200
  --force               allow writing into an OUT_DIR that already has run*.json
  -h, --help            show this help

Environment (flag wins): N, PROFILES, OUT_DIR, MODEL_ALIAS, OPENAI_BASE_URL,
OPENAI_API_KEY, PYTHON, LIMIT, MAX_RETRIES. Secrets are never written to the
repository; export them in the shell (see scripts/litellm/use-provider.sh).
EOF
}

N="${N:-3}"
PROFILES="${PROFILES:-mid,large}"
OUT_DIR="${OUT_DIR:-}"
MODEL_ALIAS="${MODEL_ALIAS:-ontographia-gemini-3.8}"
OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://127.0.0.1:4000/v1}"
OPENAI_API_KEY="${OPENAI_API_KEY:-sk-litellm-local-dev}"
PYTHON="${PYTHON:-}"
LIMIT="${LIMIT:-0}"
MAX_RETRIES="${MAX_RETRIES:-1}"
HEALTH_CHECK=1
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --n) N="${2:?--n needs a value}"; shift 2 ;;
    --n=*) N="${1#*=}"; shift ;;
    --profiles) PROFILES="${2:?--profiles needs a value}"; shift 2 ;;
    --profiles=*) PROFILES="${1#*=}"; shift ;;
    --out-dir) OUT_DIR="${2:?--out-dir needs a value}"; shift 2 ;;
    --out-dir=*) OUT_DIR="${1#*=}"; shift ;;
    --model) MODEL_ALIAS="${2:?--model needs a value}"; shift 2 ;;
    --model=*) MODEL_ALIAS="${1#*=}"; shift ;;
    --base-url) OPENAI_BASE_URL="${2:?--base-url needs a value}"; shift 2 ;;
    --base-url=*) OPENAI_BASE_URL="${1#*=}"; shift ;;
    --python) PYTHON="${2:?--python needs a value}"; shift 2 ;;
    --python=*) PYTHON="${1#*=}"; shift ;;
    --limit) LIMIT="${2:?--limit needs a value}"; shift 2 ;;
    --limit=*) LIMIT="${1#*=}"; shift ;;
    --max-retries) MAX_RETRIES="${2:?--max-retries needs a value}"; shift 2 ;;
    --max-retries=*) MAX_RETRIES="${1#*=}"; shift ;;
    --skip-health-check) HEALTH_CHECK=0; shift ;;
    --force) FORCE=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "$N" =~ ^[1-9][0-9]*$ ]]; then
  echo "error: --n must be a positive integer (got '$N')" >&2
  exit 2
fi
if ! [[ "$LIMIT" =~ ^[0-9]+$ ]]; then
  echo "error: --limit must be a non-negative integer (got '$LIMIT')" >&2
  exit 2
fi
if ! [[ "$MAX_RETRIES" =~ ^[0-9]+$ ]]; then
  echo "error: --max-retries must be a non-negative integer (got '$MAX_RETRIES')" >&2
  exit 2
fi
if [[ -z "$PROFILES" ]]; then
  echo "error: --profiles must not be empty" >&2
  exit 2
fi

PY_CMD=()
if [[ -n "$PYTHON" ]]; then
  read -r -a PY_CMD <<<"$PYTHON"
elif [[ -x "$REPO_ROOT/.venv-remeasure/bin/python" ]]; then
  PY_CMD=("$REPO_ROOT/.venv-remeasure/bin/python")
elif command -v uv >/dev/null 2>&1; then
  PY_CMD=(uv run python)
else
  PY_CMD=(python3)
fi

if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR="examples/llm/eval/out/remeasure-h1-live-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$OUT_DIR/json" "$OUT_DIR/logs"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

if compgen -G "$OUT_DIR/json/run*.json" >/dev/null && [[ "$FORCE" -ne 1 ]]; then
  echo "error: $OUT_DIR/json already has run*.json (use --force or a new --out-dir)" >&2
  exit 2
fi

export ONTOGRAPHIA_LLM_BACKEND="${ONTOGRAPHIA_LLM_BACKEND:-openai}"
export OPENAI_BASE_URL
export OPENAI_API_KEY
export OPENAI_MODEL="$MODEL_ALIAS"

META="$OUT_DIR/meta.txt"
: >"$META"

meta() {
  printf '%s\n' "$*" | tee -a "$META"
}

pkg_info="$(
  "${PY_CMD[@]}" -c 'import importlib.metadata as m, ontographia; print(m.version("ontographia"), ontographia.__file__)' 2>/dev/null ||
    echo "ontographia not importable"
)"
dirty="no"
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]]; then
  dirty="yes"
fi

meta "stem=$(basename "$OUT_DIR")"
meta "issue=142"
meta "repo=$REPO_ROOT"
meta "rev=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
meta "dirty=$dirty"
meta "python=${PY_CMD[*]}"
meta "pkg=$pkg_info"
meta "backend=$ONTOGRAPHIA_LLM_BACKEND"
meta "model=$OPENAI_MODEL"
meta "base=$OPENAI_BASE_URL"
meta "n=$N profiles=$PROFILES limit=$LIMIT max_retries=$MAX_RETRIES"
meta "started=$(date -Iseconds)"

if [[ "$HEALTH_CHECK" -eq 1 ]]; then
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    "${OPENAI_BASE_URL%/}/models" || true)"
  meta "litellm_models_http=$code"
  if [[ "$code" != "200" ]]; then
    cat >&2 <<EOF
LiteLLM is not healthy at ${OPENAI_BASE_URL%/}/models (HTTP $code).
Start it and export a provider first, for example:
  scripts/litellm/start.sh
  source scripts/litellm/use-provider.sh gemini-3.8
Pass --skip-health-check to bypass this probe.
EOF
    exit 2
  fi
else
  meta "litellm_models_http=skipped"
fi

for i in $(seq 1 "$N"); do
  out="$OUT_DIR/json/run${i}.json"
  log="$OUT_DIR/logs/run${i}.log"
  meta "=== run $i/$N -> $out ==="
  args=(
    examples/llm/eval/run_track_a_h1_live.py
    --profiles "$PROFILES"
    --json-out "$out"
    --max-retries "$MAX_RETRIES"
  )
  if [[ "$LIMIT" -gt 0 ]]; then
    args+=(--limit "$LIMIT")
  fi
  if ! "${PY_CMD[@]}" "${args[@]}" >"$log" 2>&1; then
    meta "run $i failed; see $log"
    tail -n 20 "$log" >&2 || true
    exit 3
  fi
  meta "run $i ok $(date -Iseconds)"
done

meta "finished=$(date -Iseconds)"

if ! "${PY_CMD[@]}" scripts/remeasure/aggregate_h1_live.py --out-dir "$OUT_DIR"; then
  echo "error: aggregation failed (raw run*.json kept under $OUT_DIR/json)" >&2
  exit 4
fi

meta "aggregate=aggregate.json aggregate_index=aggregate_index.json"
echo "done: $OUT_DIR"
