# scripts/

Operational scripts for local development and CI. Tutorials live in `docs/`, not here.

## Neo4j

| Script | Purpose |
|--------|---------|
| [`start_neo4j.sh`](start_neo4j.sh) | Start/create `ontographia-neo4j` container (Neo4j 2025.06+) |
| [`load_neo4j_seed.sh`](load_neo4j_seed.sh) | Load [`examples/neo4j/seed.cypher`](../examples/neo4j/seed.cypher) |

Walkthrough: [docs/end-to-end-neo4j.md](../docs/end-to-end-neo4j.md)

## Tests (invoked by CI or locally)

| Script | Purpose |
|--------|---------|
| [`python_smoke_test.py`](python_smoke_test.py) | Python binding smoke test |
| [`test-version-sync.sh`](test-version-sync.sh) | Bump, sync, and verify the five version files on a temp copy; asserts idempotency and stale-lockfile failures (CI) |
| [`docs_check.sh`](docs_check.sh) | MkDocs lint, strict build, and HTML assertions (CI) |
| [`neo4j_integration_test.py`](neo4j_integration_test.py) | Mock LLM Intent → Cypher → Neo4j (CI) |
| [`remeasure/run_all.sh`](remeasure/run_all.sh) | Verify every evaluation arm (offline by default; `--live` adds H1 live + Track B Exec Match); see [`remeasure/README.md`](remeasure/README.md) |
| [`remeasure/dry_run.py`](remeasure/dry_run.py) | Offline Intent fixture → expected Cypher dry-run (no LLM / Neo4j); see [`remeasure/README.md`](remeasure/README.md) |

## LiteLLM (`scripts/litellm/`)

Local-only LLM proxy for OpenAI / Gemini / Anthropic. **Not run in CI.**

| Script | Purpose |
|--------|---------|
| [`litellm/start.sh`](litellm/start.sh) | Start LiteLLM proxy |
| [`litellm/run-e2e.sh`](litellm/run-e2e.sh) | One-shot LLM E2E via proxy |
| [`litellm/use-provider.sh`](litellm/use-provider.sh) | `source` to set provider env |
| [`litellm/healthcheck.sh`](litellm/healthcheck.sh) | Proxy liveness check |
| [`litellm/env.example`](litellm/env.example) | Env template (copy to `.env`) |

Full setup: [docs/litellm-local.md](../docs/litellm-local.md)

## Release

| Script | Purpose |
|--------|---------|
| [`workspace-version.sh`](workspace-version.sh) | Print `[workspace.package] version` from `Cargo.toml` |
| [`sync-version.sh`](sync-version.sh) | Copy the workspace version into Cargo.toml internal dependencies, both npm manifests, `Cargo.lock` workspace packages, and the TypeScript lockfile |
| [`bump-version.sh`](bump-version.sh) | Set `[workspace.package] version` and run `sync-version.sh`; optional commit (release via Release workflow, not git tag push) |
| [`preflight-release.sh`](preflight-release.sh) | Version, tag, workflow, registry, npm package presence, npm pack dry-runs (Node-native and browser wasm), then `release-check.sh` |
| [`trigger-release.sh`](trigger-release.sh) | Read `Cargo.toml` version, preflight, then `gh workflow run Release` |
| [`release-check.sh`](release-check.sh) | Tests, `cargo publish --dry-run` (core only), wheel build (called by preflight) |
| [`check-release-workflow.mjs`](check-release-workflow.mjs) | Assert `release.yml` name Release, job id `publish-npm`, and `upload-assets` checkout + `GH_REPO` |
| [`check-npm-trusted-publishers.mjs`](check-npm-trusted-publishers.mjs) | Confirm the five npm packages exist. Does not publish. Actions skips the trust API. Local `NPM_TRUST_TOKEN` opts into `evaluatePublishers`. Operators use `npm trust list` |
| [`check-registry-reachability.sh`](check-registry-reachability.sh) | Read-only ping of npm, crates.io, and PyPI |
| [`package-npm-dry-run.mjs`](package-npm-dry-run.mjs) | `npm pack` metadata check with stub FFI archives. Does not publish |
| [`package-wasm-npm-dry-run.mjs`](package-wasm-npm-dry-run.mjs) | Build and `npm pack` the browser WASM tarball; assert wasm + JS + types. Does not publish |
| [`verify-release-version.sh`](verify-release-version.sh) | Ensure `vX.Y.Z` matches `Cargo.toml`, both npm manifests, `Cargo.lock` workspace packages, and the TypeScript lockfile |
| [`package-npm.mjs`](package-npm.mjs) | Pack `@edgesentry/ontographia` plus prebuilt FFI platform tarballs |
| [`publish-npm.sh`](publish-npm.sh) | Upload those tarballs. **Release workflow only** (`PUBLISH_TO_REGISTRIES`, npm Trusted Publishing / OIDC). Skips versions already on npm, keeps going after one package fails, then exits non-zero with the failed names. Refuses laptops, agents, and `NPM_TOKEN` |
| [`publish-wasm-npm.sh`](publish-wasm-npm.sh) | Upload the browser WASM tarball from Release job `publish-wasm-npm`. Same OIDC / no-token rules |
| [`refuse-npm-publish.mjs`](refuse-npm-publish.mjs) | Block `npm publish` of the unpackaged TypeScript directory |
| [`refuse-wasm-npm-publish.mjs`](refuse-wasm-npm-publish.mjs) | Block `npm publish` of the unpackaged browser WASM directory |
| [`verify-tag-not-exists.sh`](verify-tag-not-exists.sh) | Fail if `vX.Y.Z` (or related sentinels) already exists on origin |
| [`verify-release-not-processed.sh`](verify-release-not-processed.sh) | Fail if a release version was already claimed or has assets |
| [`claim-release-processed.sh`](claim-release-processed.sh) | Push `release-processed/vX.Y.Z` sentinel at release start |

See [docs/release.md](../docs/release.md).
