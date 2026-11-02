#!/usr/bin/env bash
# Verify every evaluation arm in this repository, offline by default.
#
# Default arms (no LLM spend):
#   track-a   Track A full-schema distractor baseline
#   h1        H1 mechanical (full / subset / subset_fallback)
#   h2        H2 execution-feedback Intent refine
#   h3        H3 difficulty-adaptive spend
#   track-b   Track B public-schema conversion
#   dry-run   offline Intent fixture -> expected Cypher check
#
# --live adds the two arms that spend tokens or hit a database:
#   h1-live       repeated Track A H1 live runs (repeat wrapper)
#   track-b-exec  Track B Exec Match against demo.neo4jlabs.com
#
# Usage:
#   scripts/remeasure/run_all.sh
#   scripts/remeasure/run_all.sh --only h1,h2 --out-dir DIR
#   scripts/remeasure/run_all.sh --live --h1-live-n 3
#   scripts/remeasure/run_all.sh --only track-b-exec --live
#
# `--record` is never implied: without it, no checked-in baseline is touched.
# See scripts/remeasure/README.md for prerequisites, environment, and layout.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

OFFLINE_ARMS=(track-a h1 h2 h3 track-b dry-run)
LIVE_ARMS=(h1-live track-b-exec)

OUT_DIR=""
ONLY=""
LIVE=0
RECORD=0
FORCE=0
FAIL_FAST=0
HEALTH_CHECK=1
LIST_ARMS=0
PROFILES="${PROFILES:-}"
H1_LIVE_N="${H1_LIVE_N:-1}"
H1_LIVE_PROFILES="${H1_LIVE_PROFILES:-mid,large}"
LIMIT="${LIMIT:-0}"
MODEL_ALIAS="${MODEL_ALIAS:-ontographia-gemini-3.8}"
OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://127.0.0.1:4000/v1}"
OPENAI_API_KEY="${OPENAI_API_KEY:-sk-litellm-local-dev}"
PYTHON="${PYTHON:-}"
# Arms that need ephemeral extras (track-b, track-b-exec) run against the
# PUBLISHED wheel via `uv run --no-project`, never the project tree, so a stale
# or corrupt in-tree Maturin .so cannot break them (issue #144).
ONTOGRAPHIA_WHEEL_SPEC="${ONTOGRAPHIA_WHEEL_SPEC:-ontographia[llm]==0.1.8}"

usage() {
  cat <<EOF
Verify all evaluation arms (offline by default).

Usage: scripts/remeasure/run_all.sh [options]

Selection:
  --only ARMS           comma-separated arm IDs; overrides the default set
                        IDs: track-a, h1, h1-live, h2, h3, track-b,
                             track-b-exec, dry-run
  --live                also run live arms (h1-live, track-b-exec) by default
  --list-arms           print the selected arm IDs and exit
  --skip-health-check   do not require GET <base-url>/models to return 200

Output and recording:
  --out-dir DIR         output root (default: examples/llm/eval/out/run-all-<UTC>)
  --record              pass --record through to the harnesses that support it
                        (default: off; committed baselines stay untouched)
  --force               allow writing into an OUT_DIR that already has status.tsv
  --fail-fast           stop after the first failing arm (default: keep going)

Parameters:
  --profiles LIST       profiles for track-a/h1/h3 (default: harness defaults)
  --h1-live-n N         repeats for h1-live (default: $H1_LIVE_N)
  --h1-live-profiles L  profiles for h1-live (default: $H1_LIVE_PROFILES)
  --limit N             pass --limit N to h1-live (0 = all gold cases)
  --model ALIAS         OPENAI_MODEL / LiteLLM alias (default: $MODEL_ALIAS)
  --base-url URL        OpenAI-compatible base URL (default: $OPENAI_BASE_URL)
  --python CMD          interpreter command; may contain args
                        (default: .venv-remeasure/bin/python, else uv run python,
                        else python3)
  -h, --help            show this help

Environment (flag wins): PROFILES, H1_LIVE_N, H1_LIVE_PROFILES, LIMIT,
MODEL_ALIAS, OPENAI_BASE_URL, OPENAI_API_KEY, PYTHON, ONTOGRAPHIA_WHEEL_SPEC
(published-package spec for the track-b arms; default: $ONTOGRAPHIA_WHEEL_SPEC).
Secrets are exported to child harnesses only; they are never written to the
output directory.

Interpreter note: track-b and track-b-exec run against the published
ontographia wheel via \`uv run --no-project\` so a stale or corrupt in-tree
Maturin .so (python/ontographia/*.so) cannot break them. The other arms use
the local interpreter chain above; if it cannot import ontographia the runner
fails fast with cleanup/rebuild guidance (issue #144).

Exit codes: 0 all selected arms passed; 1 one or more arms failed;
2 invalid arguments, an existing OUT_DIR without --force, or an unhealthy
LiteLLM endpoint.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --only) ONLY="${2:?--only needs a value}"; shift 2 ;;
    --only=*) ONLY="${1#*=}"; shift ;;
    --live) LIVE=1; shift ;;
    --list-arms) LIST_ARMS=1; shift ;;
    --out-dir) OUT_DIR="${2:?--out-dir needs a value}"; shift 2 ;;
    --out-dir=*) OUT_DIR="${1#*=}"; shift ;;
    --record) RECORD=1; shift ;;
    --force) FORCE=1; shift ;;
    --fail-fast) FAIL_FAST=1; shift ;;
    --skip-health-check) HEALTH_CHECK=0; shift ;;
    --profiles) PROFILES="${2:?--profiles needs a value}"; shift 2 ;;
    --profiles=*) PROFILES="${1#*=}"; shift ;;
    --h1-live-n) H1_LIVE_N="${2:?--h1-live-n needs a value}"; shift 2 ;;
    --h1-live-n=*) H1_LIVE_N="${1#*=}"; shift ;;
    --h1-live-profiles) H1_LIVE_PROFILES="${2:?--h1-live-profiles needs a value}"; shift 2 ;;
    --h1-live-profiles=*) H1_LIVE_PROFILES="${1#*=}"; shift ;;
    --limit) LIMIT="${2:?--limit needs a value}"; shift 2 ;;
    --limit=*) LIMIT="${1#*=}"; shift ;;
    --model) MODEL_ALIAS="${2:?--model needs a value}"; shift 2 ;;
    --model=*) MODEL_ALIAS="${1#*=}"; shift ;;
    --base-url) OPENAI_BASE_URL="${2:?--base-url needs a value}"; shift 2 ;;
    --base-url=*) OPENAI_BASE_URL="${1#*=}"; shift ;;
    --python) PYTHON="${2:?--python needs a value}"; shift 2 ;;
    --python=*) PYTHON="${1#*=}"; shift ;;
    -h | --help) usage; exit 0 ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "$H1_LIVE_N" =~ ^[1-9][0-9]*$ ]]; then
  echo "error: --h1-live-n must be a positive integer (got '$H1_LIVE_N')" >&2
  exit 2
fi
if ! [[ "$LIMIT" =~ ^[0-9]+$ ]]; then
  echo "error: --limit must be a non-negative integer (got '$LIMIT')" >&2
  exit 2
fi

normalize_arm() {
  case "$1" in
    track-a | track_a) echo "track-a" ;;
    h1 | h1-mechanical | h1_mechanical) echo "h1" ;;
    h1-live | h1_live) echo "h1-live" ;;
    h2) echo "h2" ;;
    h3) echo "h3" ;;
    track-b | track_b) echo "track-b" ;;
    track-b-exec | track_b_exec | track-b-exec-match) echo "track-b-exec" ;;
    dry-run | dry_run | dryrun) echo "dry-run" ;;
    *) echo "" ;;
  esac
}

is_live_arm() {
  case "$1" in
    h1-live | track-b-exec) return 0 ;;
    *) return 1 ;;
  esac
}

SELECTED=()
add_arm() {
  local candidate="$1" existing
  for existing in ${SELECTED[@]+"${SELECTED[@]}"}; do
    if [[ "$existing" == "$candidate" ]]; then
      return 0
    fi
  done
  SELECTED+=("$candidate")
}

if [[ -n "$ONLY" ]]; then
  IFS=',' read -r -a requested <<<"$ONLY"
  for raw in "${requested[@]}"; do
    raw="${raw//[[:space:]]/}"
    [[ -z "$raw" ]] && continue
    arm="$(normalize_arm "$raw")"
    if [[ -z "$arm" ]]; then
      echo "error: unknown arm '$raw' (see --help)" >&2
      exit 2
    fi
    if is_live_arm "$arm" && [[ "$LIVE" -ne 1 ]]; then
      echo "error: arm '$arm' spends tokens or hits a database; pass --live" >&2
      exit 2
    fi
    add_arm "$arm"
  done
else
  for arm in "${OFFLINE_ARMS[@]}"; do
    add_arm "$arm"
  done
  if [[ "$LIVE" -eq 1 ]]; then
    for arm in "${LIVE_ARMS[@]}"; do
      add_arm "$arm"
    done
  fi
fi

if [[ "${#SELECTED[@]}" -eq 0 ]]; then
  echo "error: no arms selected (use --only ARMS with at least one ID)" >&2
  exit 2
fi

NEEDS_LIVE=0
for arm in "${SELECTED[@]}"; do
  if is_live_arm "$arm"; then
    NEEDS_LIVE=1
  fi
done

if [[ "$LIST_ARMS" -eq 1 ]]; then
  printf '%s\n' "${SELECTED[@]}"
  exit 0
fi

if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR="examples/llm/eval/out/run-all-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$OUT_DIR/json" "$OUT_DIR/logs"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

if [[ -e "$OUT_DIR/status.tsv" && "$FORCE" -ne 1 ]]; then
  echo "error: $OUT_DIR already has status.tsv (use --force or a new --out-dir)" >&2
  exit 2
fi

PY_CMD=()
PY_MODE=""
if [[ -n "$PYTHON" ]]; then
  read -r -a PY_CMD <<<"$PYTHON"
  PY_MODE="explicit"
elif [[ -x "$REPO_ROOT/.venv-remeasure/bin/python" ]]; then
  PY_CMD=("$REPO_ROOT/.venv-remeasure/bin/python")
  PY_MODE="venv-remeasure"
elif command -v uv >/dev/null 2>&1; then
  PY_CMD=(uv run python)
  PY_MODE="uv"
else
  PY_CMD=(python3)
  PY_MODE="system"
fi

# Set ARM_PY to the interpreter for the current arm. Arms that need ephemeral
# extras (track-b: datasets; track-b-exec: datasets + neo4j) run against the
# PUBLISHED ontographia wheel via `uv run --no-project`, never the project
# tree: project mode would import the in-tree python/ontographia/ and can pick
# up a stale or corrupt Maturin .so (issue #144). The harness scripts still
# come from this checkout; only the `ontographia` package resolves to the
# wheel. Override the wheel with ONTOGRAPHIA_WHEEL_SPEC. An explicit --python
# is assumed to provide its own dependencies and is used as-is.
ARM_PY=()
set_arm_py() {
  ARM_PY=()
  if [[ "$PY_MODE" != "explicit" && "$#" -gt 0 ]] && command -v uv >/dev/null 2>&1; then
    ARM_PY=(uv run --no-project --with "$ONTOGRAPHIA_WHEEL_SPEC")
    local extra
    for extra in "$@"; do
      ARM_PY+=(--with "$extra")
    done
    ARM_PY+=(python)
  else
    ARM_PY=("${PY_CMD[@]}")
  fi
}

if [[ "$NEEDS_LIVE" -eq 1 ]]; then
  export ONTOGRAPHIA_LLM_BACKEND="${ONTOGRAPHIA_LLM_BACKEND:-openai}"
  export OPENAI_BASE_URL
  export OPENAI_API_KEY
  export OPENAI_MODEL="$MODEL_ALIAS"
fi

META="$OUT_DIR/meta.txt"
STATUS="$OUT_DIR/status.tsv"
SUMMARY_MD="$OUT_DIR/summary.md"
: >"$META"
printf 'arm\tstatus\texit\tslug\tduration_s\n' >"$STATUS"
{
  echo "# Remeasure arm status"
  echo
  echo "| arm | status | exit | duration (s) | log |"
  echo "|-----|--------|-----:|-------------:|-----|"
} >"$SUMMARY_MD"

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

meta "out_dir=$OUT_DIR"
meta "repo=$REPO_ROOT"
meta "rev=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
meta "dirty=$dirty"
meta "python=${PY_CMD[*]} (mode=$PY_MODE)"
meta "pkg=$pkg_info"
meta "arms=${SELECTED[*]}"
meta "live=$LIVE record=$RECORD"
meta "profiles=${PROFILES:-<harness defaults>}"
meta "h1_live_n=$H1_LIVE_N h1_live_profiles=$H1_LIVE_PROFILES limit=$LIMIT"
meta "wheel_spec=$ONTOGRAPHIA_WHEEL_SPEC"
meta "started=$(date -Iseconds)"

# Fail fast (issue #144): arms other than track-b/track-b-exec/dry-run import
# ontographia through the local interpreter. If that import is broken -- the
# classic cause is a stale or corrupt in-tree Maturin extension at
# python/ontographia/*.so -- stop here with the fix instead of dying per-arm
# with a LINKEDIT ImportError.
if [[ "$pkg_info" == "ontographia not importable" ]]; then
  NEEDS_LOCAL_IMPORT=0
  for arm in "${SELECTED[@]}"; do
    case "$arm" in
      track-a | h1 | h2 | h3 | h1-live) NEEDS_LOCAL_IMPORT=1 ;;
    esac
  done
  if [[ "$NEEDS_LOCAL_IMPORT" -eq 1 ]]; then
    cat >&2 <<EOF
error: ${PY_CMD[*]} (mode=$PY_MODE) cannot import ontographia.
A stale or corrupt in-tree Maturin extension (python/ontographia/*.so) is the
usual cause (issue #144). Pick one fix:
  1. Delete stale extensions (gitignored, safe to remove):
       rm -f python/ontographia/*.so
  2. Rebuild the native module:
       uv sync --group dev && uv run maturin develop --release
  3. Point the runner at a clean interpreter:
       scripts/remeasure/run_all.sh --python .venv-remeasure/bin/python ...
The track-b / track-b-exec arms are unaffected: they run against the published
wheel via 'uv run --no-project' (ONTOGRAPHIA_WHEEL_SPEC=$ONTOGRAPHIA_WHEEL_SPEC).
EOF
    exit 2
  fi
fi

if [[ "$NEEDS_LIVE" -eq 1 ]]; then
  if [[ "$HEALTH_CHECK" -eq 1 ]]; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
      -H "Authorization: Bearer $OPENAI_API_KEY" \
      "${OPENAI_BASE_URL%/}/models" || true)"
    meta "litellm_models_http=$code"
    if [[ "$code" != "200" ]]; then
      cat >&2 <<EOF
LiteLLM is not healthy at ${OPENAI_BASE_URL%/}/models (HTTP $code).
Start it and export a provider before spending tokens, for example:
  scripts/litellm/start.sh
  source scripts/litellm/use-provider.sh gemini-3.8
Pass --skip-health-check to bypass this probe.
EOF
      exit 2
    fi
  else
    meta "litellm_models_http=skipped"
  fi
  meta "backend=$ONTOGRAPHIA_LLM_BACKEND model=$OPENAI_MODEL base=$OPENAI_BASE_URL"
fi

FAILED=0
FAILED_ARMS=()

run_arm() {
  local arm="$1"
  shift
  local log="$OUT_DIR/logs/$arm.log"
  local start_ts end_ts rc duration status
  start_ts="$(date +%s)"

  printf '%q ' "$@" >"$OUT_DIR/logs/$arm.command"
  printf '\n' >>"$OUT_DIR/logs/$arm.command"
  meta "=== $arm -> $log"
  meta "cmd=$(cat "$OUT_DIR/logs/$arm.command")"

  if "$@" >"$log" 2>&1; then
    rc=0
  else
    rc=$?
  fi

  end_ts="$(date +%s)"
  duration=$((end_ts - start_ts))
  if [[ "$rc" -eq 0 ]]; then
    status="pass"
  else
    status="fail"
    FAILED=1
    FAILED_ARMS+=("$arm")
    meta "arm $arm failed (exit $rc); tail of $log:"
    tail -n 20 "$log" >>"$META" 2>/dev/null || true
  fi

  printf '%s\n' "$rc" >"$OUT_DIR/logs/$arm.exit"
  printf '%s\t%s\t%s\t%s\t%s\n' "$arm" "$status" "$rc" "$duration" "$log" >>"$STATUS"
  printf '| %s | %s | %s | %s | %s |\n' \
    "$arm" "$status" "$rc" "$duration" "logs/$arm.log" >>"$SUMMARY_MD"
  meta "arm $arm: $status (exit $rc, ${duration}s)"
}

for arm in "${SELECTED[@]}"; do
  cmd=()
  case "$arm" in
    track-a)
      set_arm_py
      cmd=("${ARM_PY[@]}" examples/llm/eval/run_track_a.py \
        --json-out "$OUT_DIR/json/track-a.json")
      if [[ -n "$PROFILES" ]]; then
        cmd+=(--profiles "$PROFILES")
      fi
      ;;
    h1)
      set_arm_py
      cmd=("${ARM_PY[@]}" examples/llm/eval/run_track_a_h1.py \
        --json-out "$OUT_DIR/json/h1.json")
      if [[ -n "$PROFILES" ]]; then
        cmd+=(--profiles "$PROFILES")
      fi
      ;;
    h2)
      set_arm_py
      cmd=("${ARM_PY[@]}" examples/llm/eval/run_track_a_h2.py \
        --json-out "$OUT_DIR/json/h2.json")
      ;;
    h3)
      set_arm_py
      cmd=("${ARM_PY[@]}" examples/llm/eval/run_track_a_h3.py \
        --json-out "$OUT_DIR/json/h3.json")
      if [[ -n "$PROFILES" ]]; then
        cmd+=(--profiles "$PROFILES")
      fi
      ;;
    track-b)
      set_arm_py datasets
      cmd=("${ARM_PY[@]}" examples/llm/eval/run_track_b.py \
        --json-out "$OUT_DIR/json/track-b.json")
      ;;
    dry-run)
      set_arm_py
      cmd=("${ARM_PY[@]}" scripts/remeasure/dry_run.py)
      ;;
    h1-live)
      cmd=(bash scripts/remeasure/run_h1_live_repeats.sh \
        --n "$H1_LIVE_N" \
        --profiles "$H1_LIVE_PROFILES" \
        --out-dir "$OUT_DIR/h1-live" \
        --model "$MODEL_ALIAS" \
        --base-url "$OPENAI_BASE_URL")
      if [[ -n "$PYTHON" ]]; then
        cmd+=(--python "$PYTHON")
      fi
      if [[ "$LIMIT" -gt 0 ]]; then
        cmd+=(--limit "$LIMIT")
      fi
      ;;
    track-b-exec)
      set_arm_py datasets neo4j
      cmd=("${ARM_PY[@]}" examples/llm/eval/run_track_b_exec.py \
        --json-out "$OUT_DIR/json/track-b-exec.json")
      ;;
    *)
      echo "error: no command defined for arm '$arm'" >&2
      exit 2
      ;;
  esac

  if [[ "$RECORD" -eq 1 && "$arm" != "dry-run" && "$arm" != "h1-live" ]]; then
    cmd+=(--record)
  elif [[ "$RECORD" -eq 1 && "$arm" == "h1-live" ]]; then
    meta "note: h1-live uses the repeat wrapper, which never writes --record baselines"
  fi

  run_arm "$arm" "${cmd[@]}"
  if [[ "$FAILED" -eq 1 && "$FAIL_FAST" -eq 1 ]]; then
    meta "stopping after first failure (--fail-fast)"
    break
  fi
done

meta "finished=$(date -Iseconds)"
meta "summary=$STATUS"

{
  echo
  echo "Per-arm logs, exit codes, and any JSON payloads are stored next to this"
  echo "file. No metrics are parsed or invented here; read the logs or compare"
  echo "them with the published tables in docs/evaluation.md."
} >>"$SUMMARY_MD"

if [[ "$FAILED" -eq 0 ]]; then
  echo "all selected arms passed: $OUT_DIR"
  exit 0
fi

echo "failed arms: ${FAILED_ARMS[*]-} (see $STATUS)" >&2
exit 1
