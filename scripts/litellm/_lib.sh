#!/usr/bin/env bash
# Shared helpers for LiteLLM scripts (1Password `op run` load path).
# Sourced by start.sh / use-provider.sh / run-e2e.sh / healthcheck.sh.
#
# Committed template: scripts/litellm/.env.op (op:// references, no secrets)
# Override the template path with LITELLM_OP_ENV_FILE.
# There is no plaintext .env fallback.

_litellm_dir() {
  cd "$(dirname "${BASH_SOURCE[0]}")" && pwd
}

litellm_op_env_file() {
  echo "${LITELLM_OP_ENV_FILE:-$(_litellm_dir)/.env.op}"
}

litellm_require_op() {
  if ! command -v op >/dev/null 2>&1; then
    echo "error: 1Password CLI (op) not found on PATH" >&2
    echo "  install: https://developer.1password.com/docs/cli/get-started/" >&2
    echo "  see docs/litellm-local.md (1Password setup)" >&2
    return 1
  fi
  if ! op whoami >/dev/null 2>&1; then
    echo "error: op is not signed in" >&2
    echo "  sign in (e.g. enable desktop-app integration, or: eval \"\$(op signin)\")" >&2
    echo "  see docs/litellm-local.md (1Password setup)" >&2
    return 1
  fi
}

litellm_require_op_env_file() {
  local env_file
  env_file="$(litellm_op_env_file)"
  if [[ ! -f "$env_file" ]]; then
    echo "error: 1Password env template not found: $env_file" >&2
    echo "  expected scripts/litellm/.env.op or set LITELLM_OP_ENV_FILE" >&2
    return 1
  fi
}

litellm_require_op_ready() {
  litellm_require_op || return 1
  litellm_require_op_env_file || return 1
}

# Resolve op:// references into a child process environment and run the command.
litellm_op_run() {
  litellm_require_op_ready || return 1
  op run --env-file "$(litellm_op_env_file)" -- "$@"
}

# Print `export KEY='value'` lines for eval into the current shell (sourced scripts).
# Values are resolved via `op run` and shell-quoted with printf %q.
litellm_op_eval_export() {
  litellm_require_op_ready || return 1
  local keys key
  keys="$(sed -nE 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=.*/\1/p' "$(litellm_op_env_file)")"
  # shellcheck disable=SC2016
  op run --env-file "$(litellm_op_env_file)" -- bash -c '
    for key in "$@"; do
      printf "export %s=%q\n" "$key" "${!key-}"
    done
  ' _ $keys
}
