#!/usr/bin/env node
// bindings/typescript prepublishOnly. The publishable manifest is produced by
// scripts/package-npm.mjs (optionalDependencies for the prebuilt FFI packages).
// Publishing this directory would ship a package that does not install natives.

console.error(
  "npm publish is forbidden from this directory, from a laptop, and from an agent.\n" +
    "Only the GitHub Actions Release workflow may publish, and only when\n" +
    "PUBLISH_TO_REGISTRIES=true. That job uses npm Trusted Publishing (GitHub Actions OIDC),\n" +
    "not an NPM_TOKEN secret.\n" +
    "The workflow runs scripts/package-npm.mjs (stamps optionalDependencies for the\n" +
    "prebuilt platform packages) and then scripts/publish-npm.sh.\n" +
    "See docs/release.md.",
);
process.exit(1);
