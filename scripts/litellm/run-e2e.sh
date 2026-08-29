#!/usr/bin/env bash
# Run Ontographia LLM E2E through a local LiteLLM proxy.
#
# Usage:
#   ./scripts/litellm/run-e2e.sh openai "List suppliers for parts in product SKU SPX-100"
#   ./scripts/litellm/run-e2e.sh gemini "Which plant hosts production Line-1?"
#   ./scripts/litellm/run-e2e.sh cursor "Which defect codes affect quarantined lots?"
#
# Start the proxy first: ./scripts/litellm/start.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROVIDER="${1:-}"
QUESTION="${2:-}"
shift 2 || true
EXTRA_ARGS=("$@")

if [[ -z "$PROVIDER" || -z "$QUESTION" ]]; then
  echo "usage: $0 {openai|gemini|cursor} \"<question>\" [--execute] [--password ...]" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/scripts/litellm/use-provider.sh" "$PROVIDER"

cd "$ROOT"
exec uv run python examples/run_llm_e2e.py \
  --question "$QUESTION" \
  --backend openai \
  "${EXTRA_ARGS[@]}"
