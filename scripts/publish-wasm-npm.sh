#!/usr/bin/env bash
# Publish @edgesentry/ontographia-wasm tarballs produced by
# bindings/wasm/scripts/build-package.sh.
#
# Forbidden on laptops, agent sandboxes, and every workflow except Release.
# Auth is npm Trusted Publishing (GitHub Actions OIDC). No NPM_TOKEN.
# npm attaches provenance automatically for this public repo. See docs/release.md.
set -euo pipefail

DIR="${1:-}"
if [[ -z "$DIR" || ! -d "$DIR" ]]; then
  echo "usage: scripts/publish-wasm-npm.sh <tarball-dir>" >&2
  exit 1
fi

# GITHUB_JOB is the workflow job id (`publish-wasm-npm`), not the display name.
if [[ "${GITHUB_ACTIONS:-}" != "true" || "${GITHUB_WORKFLOW:-}" != "Release" || "${GITHUB_JOB:-}" != "publish-wasm-npm" ]]; then
  echo "error: npm publish is forbidden outside the GitHub Actions Release job publish-wasm-npm." >&2
  echo "Do not publish from a laptop, a cloud agent, or any other workflow." >&2
  echo "Configure npm Trusted Publishing for release.yml, set PUBLISH_TO_REGISTRIES=true, then run Release." >&2
  exit 1
fi

# actions/setup-node with registry-url exports this when no token was passed.
# It is not an npm credential. A real token would publish without the trusted publisher.
SETUP_NODE_DUMMY_TOKEN="XXXXX-XXXXX-XXXXX-XXXXX"
if [[ -n "${NPM_TOKEN:-}" ]]; then
  echo "error: NPM_TOKEN is set." >&2
  echo "npm Trusted Publishing uses the GitHub Actions OIDC token. Remove the npm token from this job." >&2
  exit 1
fi
if [[ -n "${NODE_AUTH_TOKEN:-}" && "${NODE_AUTH_TOKEN}" != "${SETUP_NODE_DUMMY_TOKEN}" ]]; then
  echo "error: NODE_AUTH_TOKEN is set." >&2
  echo "npm Trusted Publishing uses the GitHub Actions OIDC token. Remove the npm token from this job." >&2
  exit 1
fi
unset NODE_AUTH_TOKEN

# Drop the auth line setup-node writes (//registry.npmjs.org/:_authToken=${NODE_AUTH_TOKEN})
# so npm publish exchanges the OIDC token instead of sending a placeholder.
if [[ -n "${NPM_CONFIG_USERCONFIG:-}" && -f "${NPM_CONFIG_USERCONFIG}" ]]; then
  npmrc_tmp="$(mktemp)"
  grep -v -E '_authToken=|^always-auth=' "${NPM_CONFIG_USERCONFIG}" > "$npmrc_tmp" || true
  if ! grep -q '^registry=' "$npmrc_tmp"; then
    printf 'registry=https://registry.npmjs.org/\n' >> "$npmrc_tmp"
  fi
  mv "$npmrc_tmp" "${NPM_CONFIG_USERCONFIG}"
fi

if [[ -z "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" || -z "${ACTIONS_ID_TOKEN_REQUEST_TOKEN:-}" ]]; then
  echo "error: GitHub Actions OIDC is unavailable." >&2
  echo "The publish-wasm-npm job needs permissions id-token: write so npm can use Trusted Publishing." >&2
  exit 1
fi

npm_version="$(npm --version)"
node --input-type=module -e '
  const raw = process.argv[1].trim();
  const parts = raw.split(".").map((part) => Number.parseInt(part, 10));
  const ok =
    parts.length >= 3 &&
    (parts[0] > 11 ||
      (parts[0] === 11 && (parts[1] > 5 || (parts[1] === 5 && parts[2] >= 1))));
  if (!ok) {
    console.error(
      `error: npm ${raw} cannot use Trusted Publishing. Need npm >= 11.5.1 on Node >= 22.14.`,
    );
    process.exit(1);
  }
' "$npm_version"

shopt -s nullglob
tarballs=("$DIR"/*.tgz)
if [[ ${#tarballs[@]} -ne 1 ]]; then
  echo "error: expected exactly one .tgz in ${DIR}, found ${#tarballs[@]}" >&2
  exit 1
fi

tgz="${tarballs[0]}"
meta="$(tar -xOzf "$tgz" package/package.json | node --input-type=module -e '
  import { readFileSync } from "node:fs";
  const pkg = JSON.parse(readFileSync(0, "utf8"));
  if (pkg.name !== "@edgesentry/ontographia-wasm") {
    console.error(`unexpected package ${pkg.name}`);
    process.exit(1);
  }
  if (typeof pkg.version !== "string") {
    console.error("tarball package.json is missing version");
    process.exit(1);
  }
  process.stdout.write(pkg.version);
')"
name="@edgesentry/ontographia-wasm"

if npm view "${name}@${meta}" version >/dev/null 2>&1; then
  echo "${name}@${meta} already on npm. Skipping."
  exit 0
fi

echo "Publishing ${name}@${meta}"
# OIDC auth. Provenance is generated for a public package from a public repo.
npm publish "$tgz" --access public
echo "npm publish ok: ${name}@${meta}"
