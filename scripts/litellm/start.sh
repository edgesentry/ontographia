#!/usr/bin/env bash
# Start the LiteLLM proxy for local Ontographia LLM E2E.
#
# Usage:
#   ./scripts/litellm/start.sh              # uv (recommended)
#   ./scripts/litellm/start.sh --docker     # Docker image
#
# Prerequisites:
#   cp scripts/litellm/env.example scripts/litellm/.env
#   # edit .env with provider API keys
#
# Then in another terminal:
#   source scripts/litellm/use-provider.sh openai   # or gemini | cursor
#   uv run python examples/run_llm_e2e.py --question "..." --execute --password ontographia

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${LITELLM_ENV_FILE:-$DIR/.env}"
CONFIG="$DIR/config.yaml"
PORT="${LITELLM_PORT:-4000}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "hint: copy $DIR/env.example to $DIR/.env and set provider API keys" >&2
fi

export LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY:-sk-litellm-local-dev}"
export LITELLM_PORT="$PORT"
export GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.7-flash}"
export GEMINI_LITELLM_MODEL="gemini/${GEMINI_MODEL}"

if [[ "${1:-}" == "--docker" ]]; then
  exec docker run --rm \
    -p "${PORT}:${PORT}" \
    -v "$CONFIG:/app/config.yaml:ro" \
    -e OPENAI_API_KEY \
    -e GEMINI_API_KEY \
    -e GEMINI_LITELLM_MODEL \
    -e ANTHROPIC_API_KEY \
    -e CURSOR_API_KEY \
    -e LITELLM_MASTER_KEY \
    ghcr.io/berriai/litellm:main-stable \
    --config /app/config.yaml --port "$PORT" --host 0.0.0.0
fi

cd "$ROOT"
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install from https://docs.astral.sh/uv/" >&2
  exit 1
fi

echo "Starting LiteLLM on http://127.0.0.1:${PORT} (config: ${CONFIG#"$ROOT/"}, gemini: ${GEMINI_LITELLM_MODEL})"
exec uv run --group llm litellm --config "$CONFIG" --port "$PORT" --host 127.0.0.1
