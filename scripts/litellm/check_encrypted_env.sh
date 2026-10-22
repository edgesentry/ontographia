#!/usr/bin/env bash
# Fail if a tracked LiteLLM env file contains plaintext secret values.
#
# Committed ciphertext lives at scripts/litellm/.env.encrypted (or any other
# tracked scripts/litellm/.env* file except env.example). Every non-empty
# assignment (other than DOTENV_PUBLIC_KEY*) must use a dotenvx ciphertext
# value starting with "encrypted:".
#
# Plaintext scripts/litellm/.env must never be tracked.
#
# Usage (CI / pre-commit):
#   bash scripts/litellm/check_encrypted_env.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if ! command -v git >/dev/null 2>&1; then
  echo "error: git is required" >&2
  exit 1
fi

# Never allow the plaintext path to be tracked.
if git ls-files --error-unmatch scripts/litellm/.env >/dev/null 2>&1; then
  echo "error: scripts/litellm/.env is tracked; plaintext env must stay gitignored" >&2
  echo "  commit ciphertext as scripts/litellm/.env.encrypted instead" >&2
  exit 1
fi

# Bash 3.2-compatible (macOS /bin/bash); avoid mapfile.
FILES=()
while IFS= read -r _env_path; do
  [[ -n "$_env_path" ]] && FILES+=("$_env_path")
done < <(
  git ls-files 'scripts/litellm/.env' 'scripts/litellm/.env.*' 'scripts/litellm/*.env' \
    | grep -vE '(^|/)env\.example$' \
    || true
)

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "ok: no tracked LiteLLM env ciphertext files yet (maintainer adds .env.encrypted locally)"
  exit 0
fi

failures=0

check_file() {
  local path="$1"
  local line_no=0
  local line key value

  while IFS= read -r line || [[ -n "$line" ]]; do
    line_no=$((line_no + 1))
    # Strip CR
    line="${line%$'\r'}"
    # Skip blank / comment / dotenvx banner comments
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

    if [[ ! "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      echo "error: ${path}:${line_no}: expected KEY=VALUE, got: ${line}" >&2
      failures=$((failures + 1))
      continue
    fi
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    # Strip optional surrounding quotes
    if [[ "$value" =~ ^\"(.*)\"$ ]]; then
      value="${BASH_REMATCH[1]}"
    elif [[ "$value" =~ ^\'(.*)\'$ ]]; then
      value="${BASH_REMATCH[1]}"
    fi
    # Inline comments after unquoted values are uncommon in dotenvx output; keep raw.

    # Public key metadata is plaintext by design.
    if [[ "$key" == DOTENV_PUBLIC_KEY || "$key" == DOTENV_PUBLIC_KEY_* ]]; then
      continue
    fi

    if [[ -z "$value" ]]; then
      echo "error: ${path}:${line_no}: ${key} is empty; dotenvx values must be encrypted:" >&2
      failures=$((failures + 1))
      continue
    fi

    if [[ "$value" != encrypted:* ]]; then
      echo "error: ${path}:${line_no}: ${key} is not dotenvx ciphertext (must start with encrypted:)" >&2
      failures=$((failures + 1))
    fi
  done <"$path"
}

for path in "${FILES[@]}"; do
  echo "checking ${path}"
  check_file "$path"
done

if [[ "$failures" -ne 0 ]]; then
  echo "error: ${failures} unencrypted value(s) in tracked LiteLLM env file(s)" >&2
  exit 1
fi

echo "ok: all tracked LiteLLM env values are dotenvx ciphertext"
