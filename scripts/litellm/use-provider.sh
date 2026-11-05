#!/usr/bin/env bash
# Export Ontographia + LiteLLM environment for a chosen provider alias.
#
# Usage (source, do not execute):
#   source scripts/litellm/use-provider.sh openai
#   source scripts/litellm/use-provider.sh gemini-3.7
#   source scripts/litellm/use-provider.sh gemini-3.8
#   source scripts/litellm/use-provider.sh cursor
#
# Resolves scripts/litellm/.env.op via `op run` (1Password CLI, signed in),
# then sets OPENAI_MODEL to the LiteLLM alias.

use_provider() {
  local provider="${1:-}"
  local dir port master_key

  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  # shellcheck disable=SC1091
  source "$dir/_lib.sh"

  # Inject resolved env into this shell (sourced script; not a child process).
  local exports
  exports="$(litellm_op_eval_export)" || return 1
  # shellcheck disable=SC1090
  eval "$exports"

  port="${LITELLM_PORT:-4000}"
  master_key="${LITELLM_MASTER_KEY:-}"
  if [[ -z "$master_key" ]]; then
    echo "error: LITELLM_MASTER_KEY is empty; check item litellm-upstream in vault ontographia-dev" >&2
    return 1
  fi

  export ONTOGRAPHIA_LLM_BACKEND=openai
  export OPENAI_BASE_URL="http://127.0.0.1:${port}/v1"
  export OPENAI_API_KEY="$master_key"

  case "$provider" in
    openai)
      export OPENAI_MODEL=ontographia-openai
      ;;
    gemini)
      echo "provider 'gemini' was removed in #106; use gemini-3.7 or gemini-3.8" >&2
      return 1
      ;;
    gemini-3.7)
      export OPENAI_MODEL=ontographia-gemini-3.7
      ;;
    gemini-3.8)
      export OPENAI_MODEL=ontographia-gemini-3.8
      ;;
    cursor)
      export OPENAI_MODEL=ontographia-cursor
      ;;
    *)
      echo "usage: source scripts/litellm/use-provider.sh {openai|gemini-3.7|gemini-3.8|cursor}" >&2
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
