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
| [`neo4j_integration_test.py`](neo4j_integration_test.py) | Mock LLM Intent → Cypher → Neo4j (CI) |

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
| [`bump-version.sh`](bump-version.sh) | Bump workspace version; optional commit |
| [`preflight-release.sh`](preflight-release.sh) | Version + tag checks and full `release-check.sh` |
| [`trigger-release.sh`](trigger-release.sh) | Local preflight, then `gh workflow run Release` |
| [`release-check.sh`](release-check.sh) | Tests, publish dry-run, wheel build (called by preflight) |
| [`verify-release-version.sh`](verify-release-version.sh) | Ensure `vX.Y.Z` tag matches `Cargo.toml` |
| [`verify-tag-not-exists.sh`](verify-tag-not-exists.sh) | Fail if `vX.Y.Z` (or related sentinels) already exists on origin |
| [`verify-release-not-processed.sh`](verify-release-not-processed.sh) | Fail if a release version was already claimed or has assets |
| [`claim-release-processed.sh`](claim-release-processed.sh) | Push `release-processed/vX.Y.Z` sentinel at release start |

See [docs/release.md](../docs/release.md).
