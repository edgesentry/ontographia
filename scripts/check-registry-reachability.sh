#!/usr/bin/env bash
# Read-only reachability pings for the registries Release can publish to.
# A host that answers is reachable. HTTP 404 (package or path missing) still
# counts: the registry responded. Connection failure, 401/403, and 5xx fail
# the check. This does not publish and does not send a token.
# crates.io returns 403 when the client sends no User-Agent.
# See docs/release.md.
set -euo pipefail

UA="ontographia-release-check (+https://github.com/edgesentry/ontographia)"
CURL_BIN="${CURL_BIN:-curl}"

if ! command -v "$CURL_BIN" >/dev/null 2>&1 && [[ ! -x "$CURL_BIN" ]]; then
  echo "error: curl is required for registry reachability checks (${CURL_BIN})" >&2
  exit 1
fi

body="$(mktemp)"
trap 'rm -f "$body"' EXIT

# Prints the HTTP status. Returns non-zero when curl cannot get a status.
fetch_code() {
  local url="$1"
  "$CURL_BIN" -sS -A "$UA" --retry 2 --retry-delay 1 --max-time 20 \
    -o "$body" -w "%{http_code}" "$url"
}

ping() {
  local name="$1"
  local url="$2"
  local code=""
  if ! code="$(fetch_code "$url")"; then
    echo "error: ${name} did not respond: ${url}" >&2
    exit 1
  fi
  case "$code" in
    2*|3*|404)
      echo "${name} reachable (HTTP ${code}) ${url}"
      ;;
    *)
      echo "error: ${name} returned HTTP ${code}: ${url}" >&2
      echo "Reachability accepts 2xx, 3xx, and 404. This check does not publish." >&2
      exit 1
      ;;
  esac
}

ping npm "https://registry.npmjs.org/-/ping"
ping crates.io "https://crates.io/api/v1/crates/ontographia-core"
ping pypi "https://pypi.org/pypi/ontographia/json"

echo "registry reachability ok"
