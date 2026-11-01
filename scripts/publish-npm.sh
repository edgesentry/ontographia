#!/usr/bin/env bash
# Publish tarballs from scripts/package-npm.mjs.
# Platform packages first (lexical tarball order), then @edgesentry/ontographia.
# Versions already on the registry are skipped so a Release re-run is safe
# when some packages at this version are already published.
# One package failure does not stop the rest. The script then exits non-zero
# and names every package that was neither skipped nor published.
#
# Forbidden on laptops, agent sandboxes, and every workflow except Release.
# The Release job is also gated by PUBLISH_TO_REGISTRIES.
# Auth is npm Trusted Publishing (GitHub Actions OIDC). No NPM_TOKEN.
# npm attaches provenance automatically for this public repo. See docs/release.md.
set -euo pipefail

DIR="${1:-}"
if [[ -z "$DIR" || ! -d "$DIR" ]]; then
  echo "usage: scripts/publish-npm.sh <tarball-dir>" >&2
  exit 1
fi

# GITHUB_JOB is the workflow job id (`publish-npm`), not the display name.
if [[ "${GITHUB_ACTIONS:-}" != "true" || "${GITHUB_WORKFLOW:-}" != "Release" || "${GITHUB_JOB:-}" != "publish-npm" ]]; then
  echo "error: npm publish is forbidden outside the GitHub Actions Release job publish-npm." >&2
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
  echo "The publish-npm job needs permissions id-token: write so npm can use Trusted Publishing." >&2
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
if [[ ${#tarballs[@]} -eq 0 ]]; then
  echo "error: no .tgz files in ${DIR}" >&2
  exit 1
fi

# Prints "<name>\n<version>\n". Refuses the main package if platform deps are missing.
read_meta() {
  local tgz="$1"
  tar -xOzf "$tgz" package/package.json | node --input-type=module -e '
    import { readFileSync } from "node:fs";
    const pkg = JSON.parse(readFileSync(0, "utf8"));
    if (typeof pkg.name !== "string" || typeof pkg.version !== "string") {
      console.error("tarball package.json is missing name or version");
      process.exit(1);
    }
    if (pkg.name === "@edgesentry/ontographia") {
      const deps = pkg.optionalDependencies ?? {};
      const count = Object.keys(deps).filter((key) =>
        key.startsWith("@edgesentry/ontographia-"),
      ).length;
      if (count < 4) {
        console.error(
          "refusing to publish @edgesentry/ontographia without the four platform optionalDependencies",
        );
        process.exit(1);
      }
    }
    process.stdout.write(pkg.name + "\n" + pkg.version + "\n");
  '
}

# Names that were not already on npm and whose publish command failed.
failed=()

publish_one() {
  local tgz="$1"
  local name="$2"
  local version="$3"
  if npm view "${name}@${version}" version >/dev/null 2>&1; then
    echo "${name}@${version} already on npm. Skipping."
    return 0
  fi
  echo "Publishing ${name}@${version}"
  # OIDC auth. Provenance is generated for a public package from a public repo.
  # `if` so set -e does not abort the remaining packages.
  if npm publish "$tgz" --access public; then
    return 0
  fi
  echo "error: failed to publish ${name}@${version}" >&2
  failed+=("${name}@${version}")
}

main_name=""
main_version=""
main_tgz=""
platform_names=()
platform_versions=()
platform_tgz=()

for tgz in "${tarballs[@]}"; do
  mapfile -t meta < <(read_meta "$tgz")
  name="${meta[0]}"
  version="${meta[1]}"
  case "$name" in
    @edgesentry/ontographia)
      if [[ -n "$main_tgz" ]]; then
        echo "error: two tarballs for @edgesentry/ontographia" >&2
        exit 1
      fi
      main_tgz="$tgz"
      main_name="$name"
      main_version="$version"
      ;;
    @edgesentry/ontographia-*)
      platform_tgz+=("$tgz")
      platform_names+=("$name")
      platform_versions+=("$version")
      ;;
    *)
      echo "error: unexpected package ${name} in ${tgz}" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$main_tgz" ]]; then
  echo "error: missing @edgesentry/ontographia tarball in ${DIR}" >&2
  exit 1
fi
if [[ ${#platform_tgz[@]} -lt 4 ]]; then
  echo "error: expected 4 platform tarballs, found ${#platform_tgz[@]}" >&2
  exit 1
fi

for i in "${!platform_tgz[@]}"; do
  publish_one "${platform_tgz[$i]}" "${platform_names[$i]}" "${platform_versions[$i]}"
done
publish_one "$main_tgz" "$main_name" "$main_version"

if [[ ${#failed[@]} -gt 0 ]]; then
  echo "error: npm publish incomplete. These packages are not on the registry at this version:" >&2
  for item in "${failed[@]}"; do
    echo "  ${item}" >&2
  done
  cat >&2 <<'EOF'
Already-published versions were skipped. The other tarballs were still attempted.
ENEEDAUTH on one package means that package's Trusted Publisher is missing, expired, or does not allow npm publish. Each package needs its own connection, including @edgesentry/ontographia-win32-x64, with the same fields as the others (GitHub Actions, organization edgesentry, repository ontographia, workflow filename release.yml, empty environment, Allow npm publish on). os and cpu in the platform package.json are install filters; they are not why publish returned ENEEDAUTH.
Re-run the failed publish-npm job after fixing that publisher. A new Release for the same version is refused once the tag exists. Do not bump the version and do not delete the tag.
EOF
  exit 1
fi

echo "npm publish ok"
