# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.6] - 2026-10-21

Pre-1.0 patch release. Ships the Phase 1 optional Python extras (`ontographia[llm]` and `ontographia[mcp]`). Issues [#84](https://github.com/edgesentry/ontographia/issues/84) and [#85](https://github.com/edgesentry/ontographia/issues/85) remain open until this release is cut; they are expected to close after publish.

### Added

- **Intent layer** (`ontographia[llm]`): package former `examples/llm/` helpers as an optional extra (`openai` + `pyyaml`) with a pluggable OpenAI-compatible `LLMBackend`, `ImportError` guidance when the extra is missing, and CI unit tests under `tests/python/llm/`. Docs: [docs/llm.md](docs/llm.md). Epic [#84](https://github.com/edgesentry/ontographia/issues/84) ([#93](https://github.com/edgesentry/ontographia/pull/93)).
- **MCP server** (`ontographia[mcp]`): optional extra with FastMCP-style tools `list_ontology`, `intent_schema`, `build_cypher`, and read-only `execute`; console entry point `ontographia-mcp` (stdio); Neo4j via CLI/env; write-query rejection (Intent-only execution, `READ_ACCESS` / `execute_read`, Cypher deny list). Docs: [docs/mcp.md](docs/mcp.md). Epic [#85](https://github.com/edgesentry/ontographia/issues/85) ([#94](https://github.com/edgesentry/ontographia/pull/94)).

### Dependencies

- `mcp` 1.29.1 → 1.30.0 (and related uv lockfile updates: `aiohttp`, `multidict`, `pyjwt`, `urllib3`) ([#95](https://github.com/edgesentry/ontographia/pull/95))
- `certifi` 2026.7.22 → 2026.10.19 in the uv lockfile ([#97](https://github.com/edgesentry/ontographia/pull/97))

## [0.1.5] - 2026-10-18

Pre-1.0 patch release. Intent JSON and dialect handling below are **breaking**. A patch bump is used because the project is still before 1.0.

### Changed

- **Breaking:** Intent JSON rejects unknown keys. `Intent`, `NodeRef`, `TraverseStep`, `FilterExpr`, `ReturnItem`, and `OrderBy` use `deny_unknown_fields`, and the generated JSON Schema sets `additionalProperties: false` on those objects. A typo such as `filters` is a validation error that names the field. Fixes #81 (#90).
- **Breaking:** An unknown dialect is an error. Python raises `ValueError`. The FFI and Go bindings return an error. They no longer fall back silently to `cypher25`. The CLI, Python, and FFI share one `Dialect` parser (#90).
- Prompt-token estimates in the eval baselines rise by about 54 tokens at p50/p95 (for example 1359 to 1414) because the schema now includes `additionalProperties: false`. Metric values are unchanged. Committed baseline files were left as recorded in #90.

### Added

- Public roadmap page (`docs/roadmap.md`): Phases 0–5 and epics #82–#89, linked from the README and the docs nav (#91).
- Related-work page comparing Ontographia with Text2Cypher schema filtering, iterative refinement, and difficulty-adaptive decoding (#44).
- Ontology subset prompts with full-schema fallback (`schema_policy=auto`) (#66, closes #45).
- Track A Intent eval stress harness: distractor ontologies, gold Intents, and silent-wrong near-duplicates (#58).
- Track A H1 comparison of full vs subset vs subset-fallback (#67, closes #51).
- Intent refinement from Neo4j execution feedback (`--execute --refine-on-exec`). Empty results or driver errors correct Intent JSON, then `Engine.build` runs again (#69, closes #46).
- Track A H2 eval of that refine loop on Empty@Valid (#70, #55).
- Difficulty-adaptive Intent spend (`initial_retries` / `escalated_retries`) and Track A H3 eval (#71, closes #47 and #54).
- Track A live-LLM H1 arm, Track B execution-match harness, and mapping-driven `repair` / `semantic_validate` (#72, #68, #53, #48).
- Track B schema-conversion eval from Hugging Face Text2Cypher `Node properties` schema text to native YAML (#59).

### Dependencies

- `serde_json` 1.0.151 → 1.0.154 (#80)
- `schemars` 1.2.2 → 1.2.3 (#79)
- `pyo3` 0.29.2 → 0.29.3 (#78)
- `thiserror` 2.0.20 → 2.0.21 (#77)
- `clap` 4.6.6 → 4.6.7 (#75)
- `indexmap` 2.14.1 → 2.14.2 (#74)
- `oauthlib` 3.3.1 → 4.0.0 in the uv lockfile (#76)
- `actions/setup-python` 5 → 7 (#65)
- `actions/upload-artifact` 4 → 7 (#64)
- `actions/deploy-pages` 4 → 5 (#63)
- `actions/download-artifact` 4 → 8 (#62)
- `actions/upload-pages-artifact` 4 → 5 (#61)
- `softprops/action-gh-release` 2 → 3 (#60)

[Unreleased]: https://github.com/edgesentry/ontographia/compare/v0.1.6...HEAD
[0.1.6]: https://github.com/edgesentry/ontographia/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/edgesentry/ontographia/compare/v0.1.4...v0.1.5
