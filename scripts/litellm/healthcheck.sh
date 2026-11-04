#!/usr/bin/env bash
# Quick health check for the local LiteLLM proxy.
#
# Usage:
#   ./scripts/litellm/healthcheck.sh
#
# Resolves LITELLM_MASTER_KEY from scripts/litellm/.env.op via `op run`
# (1Password CLI, signed in). Hard-fails otherwise; no plaintext fallback.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck disable=SC1091
source "$DIR/_lib.sh"

# shellcheck disable=SC1090
eval "$(litellm_op_eval_export)"

PORT="${LITELLM_PORT:-4000}"
MASTER_KEY="${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY is empty; check vault ontographia-dev}"
BASE="http://127.0.0.1:${PORT}"

echo "GET ${BASE}/health/liveliness"
curl -fsS "${BASE}/health/liveliness"
echo

echo "GET ${BASE}/v1/models"
curl -fsS "${BASE}/v1/models" \
  -H "Authorization: Bearer ${MASTER_KEY}" | python3 -m json.tool
