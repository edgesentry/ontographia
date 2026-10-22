#!/usr/bin/env bash
# Quick health check for the local LiteLLM proxy.
#
# Usage:
#   ./scripts/litellm/healthcheck.sh
#
# Loads LITELLM_MASTER_KEY from scripts/litellm/.env.encrypted via dotenvx
# when available; otherwise falls back to the local-dev default virtual key.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck disable=SC1091
source "$DIR/_lib.sh"

if command -v dotenvx >/dev/null 2>&1 \
  && [[ -f "$(litellm_env_file)" ]] \
  && [[ -f "$(litellm_keys_file)" ]]; then
  # shellcheck disable=SC1090
  eval "$(litellm_dotenvx_eval_export)"
fi

PORT="${LITELLM_PORT:-4000}"
MASTER_KEY="${LITELLM_MASTER_KEY:-sk-litellm-local-dev}"
BASE="http://127.0.0.1:${PORT}"

echo "GET ${BASE}/health/liveliness"
curl -fsS "${BASE}/health/liveliness"
echo

echo "GET ${BASE}/v1/models"
curl -fsS "${BASE}/v1/models" \
  -H "Authorization: Bearer ${MASTER_KEY}" | python3 -m json.tool
