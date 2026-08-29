#!/usr/bin/env bash
# Quick health check for the local LiteLLM proxy.
#
# Usage:
#   ./scripts/litellm/healthcheck.sh

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${LITELLM_ENV_FILE:-$DIR/.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
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
