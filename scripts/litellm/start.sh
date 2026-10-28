#!/usr/bin/env bash
# Start the LiteLLM proxy for local Ontographia LLM E2E.
#
# Usage:
#   ./scripts/litellm/start.sh              # uv (recommended)
#   ./scripts/litellm/start.sh --docker     # Docker image
#
# Prerequisites (dotenvx):
#   - Install dotenvx: curl -sfS https://dotenvx.sh | sh
#   - Encrypted env: scripts/litellm/.env.encrypted (committed ciphertext)
#   - Private key: ~/.config/ontographia/dotenv.keys (never commit)
#   See docs/litellm-local.md
#
# Then in another terminal:
#   source scripts/litellm/use-provider.sh openai   # or gemini-3.7 | gemini-3.8 | cursor
#   uv run python examples/run_llm_e2e.py --question "..." --execute --password ontographia

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$DIR/config.yaml"
PORT="${LITELLM_PORT:-4000}"

# shellcheck disable=SC1091
source "$DIR/_lib.sh"

litellm_require_dotenvx
litellm_require_env_file
litellm_require_keys_file

export LITELLM_PORT="$PORT"

if [[ "${1:-}" == "--docker" ]]; then
  # Pin v1.106.5 by digest. Do not use main-stable/latest: those tags pointed at
  # the compromised v1.107.0 image on 2026-10-21. Match the uv litellm floor.
  # dotenvx injects provider keys into this process env; docker run -e forwards them.
  exec dotenvx run --strict \
    -f "$(litellm_env_file)" \
    -fk "$(litellm_keys_file)" \
    -- docker run --rm \
      -p "${PORT}:${PORT}" \
      -v "$CONFIG:/app/config.yaml:ro" \
      -e OPENAI_API_KEY \
      -e GEMINI_API_KEY \
      -e ANTHROPIC_API_KEY \
      -e CURSOR_API_KEY \
      -e LITELLM_MASTER_KEY \
      ghcr.io/berriai/litellm:v1.106.5@sha256:7d6ae6c8d73d1b6aea4cb75d07c4a8a953f0809b0764522b8eab693734c5e905 \
      --config /app/config.yaml --port "$PORT" --host 0.0.0.0
fi

cd "$ROOT"
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install from https://docs.astral.sh/uv/" >&2
  exit 1
fi

echo "Starting LiteLLM on http://127.0.0.1:${PORT} (config: ${CONFIG#"$ROOT/"})"
echo "  env: $(litellm_env_file)"
echo "  keys: $(litellm_keys_file)"
exec dotenvx run --strict \
  -f "$(litellm_env_file)" \
  -fk "$(litellm_keys_file)" \
  -- uv run --group litellm litellm --config "$CONFIG" --port "$PORT" --host 127.0.0.1
