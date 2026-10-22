#!/usr/bin/env bash
# Shared helpers for LiteLLM scripts (dotenvx load path).
# Sourced by start.sh / use-provider.sh / run-e2e.sh / healthcheck.sh.
#
# Committed ciphertext: scripts/litellm/.env.encrypted
# Private key (outside repo): ~/.config/ontographia/dotenv.keys
# Plaintext scripts/litellm/.env is gitignored and is NOT loaded by these scripts.

# shellcheck disable=SC2034  # exported for callers that want the paths

_litellm_dir() {
  cd "$(dirname "${BASH_SOURCE[0]}")" && pwd
}

litellm_env_file() {
  echo "${LITELLM_ENV_FILE:-$(_litellm_dir)/.env.encrypted}"
}

litellm_keys_file() {
  echo "${DOTENV_KEYS_FILE:-${LITELLM_DOTENV_KEYS:-${HOME}/.config/ontographia/dotenv.keys}}"
}

litellm_require_dotenvx() {
  if ! command -v dotenvx >/dev/null 2>&1; then
    echo "error: dotenvx not found on PATH" >&2
    echo "  install (OS-independent): curl -sfS https://dotenvx.sh | sh" >&2
    echo "  macOS (Homebrew): brew tap dotenvx/brew && brew trust dotenvx/brew && brew install dotenvx" >&2
    echo "  docs: https://dotenvx.com/docs/install/" >&2
    return 1
  fi
}

litellm_require_env_file() {
  local env_file
  env_file="$(litellm_env_file)"
  if [[ ! -f "$env_file" ]]; then
    echo "error: encrypted env file not found: $env_file" >&2
    echo "  create it from env.example, encrypt with dotenvx, and commit only the ciphertext" >&2
    echo "  see docs/litellm-local.md (dotenvx setup)" >&2
    return 1
  fi
}

litellm_require_keys_file() {
  local keys_file
  keys_file="$(litellm_keys_file)"
  if [[ ! -f "$keys_file" ]]; then
    echo "error: dotenvx private key file not found: $keys_file" >&2
    echo "  after encrypt, move the generated .env.keys there:" >&2
    echo "    mkdir -p ~/.config/ontographia" >&2
    echo "    mv scripts/litellm/.env.keys ~/.config/ontographia/dotenv.keys" >&2
    echo "    chmod 600 ~/.config/ontographia/dotenv.keys" >&2
    echo "  see docs/litellm-local.md (dotenvx setup)" >&2
    return 1
  fi
}

# Decrypt into a child process environment and run the given command.
litellm_dotenvx_run() {
  litellm_require_dotenvx || return 1
  litellm_require_env_file || return 1
  litellm_require_keys_file || return 1
  # Prefer --strict so missing/invalid keys fail loudly.
  dotenvx run --strict \
    -f "$(litellm_env_file)" \
    -fk "$(litellm_keys_file)" \
    -- "$@"
}

# Print `export KEY='value'` lines for eval into the current shell (sourced scripts).
litellm_dotenvx_eval_export() {
  litellm_require_dotenvx || return 1
  litellm_require_env_file || return 1
  litellm_require_keys_file || return 1
  dotenvx get \
    -f "$(litellm_env_file)" \
    -fk "$(litellm_keys_file)" \
    --format eval-export
}
