#!/usr/bin/env bash
# Publish tarballs from scripts/package-npm.mjs.
# Platform packages first, then @edgesentry/ontographia.
# Versions already on the registry are skipped so a Release re-run is safe.
#
# Forbidden on laptops, agent sandboxes, and every workflow except Release.
# The Release job is also gated by PUBLISH_TO_REGISTRIES and NPM_TOKEN.
# See docs/release.md.
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
  echo "Set repository variable PUBLISH_TO_REGISTRIES=true and secret NPM_TOKEN, then run Release." >&2
  exit 1
fi

if [[ -z "${NODE_AUTH_TOKEN:-}" ]]; then
  echo "error: NODE_AUTH_TOKEN is empty. Add the NPM_TOKEN Actions secret." >&2
  echo "The Release workflow maps secrets.NPM_TOKEN to NODE_AUTH_TOKEN." >&2
  exit 1
fi

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

publish_one() {
  local tgz="$1"
  local name="$2"
  local version="$3"
  if npm view "${name}@${version}" version >/dev/null 2>&1; then
    echo "${name}@${version} already on npm. Skipping."
    return 0
  fi
  echo "Publishing ${name}@${version}"
  npm publish "$tgz" --access public
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

echo "npm publish ok"
