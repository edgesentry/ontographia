#!/usr/bin/env node
// bindings/wasm prepublishOnly. The publishable tarball is produced by
// bindings/wasm/scripts/build-package.sh (wasm + JS + types), and only the
// GitHub Actions Release job `publish-wasm-npm` may upload it.

console.error(
  "npm publish is forbidden from the wasm package directory, from a laptop, and from an agent.\n" +
    "Only the GitHub Actions Release workflow may publish, and only when\n" +
    "PUBLISH_TO_REGISTRIES=true. That job uses npm Trusted Publishing (GitHub Actions OIDC),\n" +
    "not an NPM_TOKEN secret.\n" +
    "Build and pack with bindings/wasm/scripts/build-package.sh, then let\n" +
    "scripts/publish-wasm-npm.sh run in Release job publish-wasm-npm.\n" +
    "See docs/wasm.md and docs/release.md.",
);
process.exit(1);
