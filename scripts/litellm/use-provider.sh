#!/usr/bin/env bash
# Export Ontographia + LiteLLM environment for a chosen provider alias.
#
# Usage (source, do not execute):
#   source scripts/litellm/use-provider.sh openai
#   source scripts/litellm/use-provider.sh gemini
#   source scripts/litellm/use-provider.sh cursor
#
# Loads scripts/litellm/.env when present, then sets OPENAI_MODEL to the LiteLLM alias.

use_provider() {
  local provider="${1:-}"
  local dir root env_file port master_key

  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  root="$(cd "$dir/../.." && pwd)"
  env_file="${LITELLM_ENV_FILE:-$dir/.env}"

  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi

  port="${LITELLM_PORT:-4000}"
  master_key="${LITELLM_MASTER_KEY:-sk-litellm-local-dev}"

  export ONTOGRAPHIA_LLM_BACKEND=openai
  export OPENAI_BASE_URL="http://127.0.0.1:${port}/v1"
  export OPENAI_API_KEY="$master_key"

  case "$provider" in
    openai)
      export OPENAI_MODEL=ontographia-openai
      ;;
    gemini)
      export OPENAI_MODEL=ontographia-gemini
      ;;
    cursor)
      export OPENAI_MODEL=ontographia-cursor
      ;;
    *)
      echo "usage: source scripts/litellm/use-provider.sh {openai|gemini|cursor}" >&2
      return 1
      ;;
  esac

  echo "LiteLLM provider: $provider"
  echo "  OPENAI_BASE_URL=$OPENAI_BASE_URL"
  echo "  OPENAI_MODEL=$OPENAI_MODEL"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "source this script instead of executing it:" >&2
  echo "  source scripts/litellm/use-provider.sh openai" >&2
  exit 1
fi

use_provider "$@"
