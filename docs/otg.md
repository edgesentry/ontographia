# `otg` CLI

**Status: experimental / 0.x.** `otg` is a short command that loads an ontology, compiles **Intent JSON** with the Rust `Engine`, and can run the query **read-only** against Neo4j.

The model never writes Cypher. `otg` does not call an LLM. Execution reuses the MCP read-only path (`python/ontographia/mcp/read_only.py`, `safety.py`, `execute.py`): Intent-only input, `READ_ACCESS` / `execute_read`, and the write-clause deny list.

This is separate from the Rust binary `ontographia` (`build` / `schema`, no driver) and from the MCP server. **Homebrew does not package `ontographia-mcp`.** Keep MCP on `uvx` or `pip install "ontographia[mcp]"`. See [MCP server](mcp.md).

## Install

### pip / uv (any platform with a wheel)

```bash
pip install "ontographia[cli]"
otg --help
```

From a git checkout (compiles the extension; needs Rust):

```bash
uv sync --group dev --extra cli
uv run maturin develop --release
uv run otg --help
```

Wheels match the [Python](python.md) matrix: Linux x86_64 and arm64, macOS Apple Silicon, Windows x86_64, Python 3.11–3.13. Intel macOS has no wheel; build from the checkout.

### Homebrew

The formula lives in this repo at [`packaging/homebrew/otg.rb`](https://github.com/edgesentry/ontographia/blob/main/packaging/homebrew/otg.rb). It does **not** compile Rust and it is **not** bottled. `brew install` creates a virtualenv with `uv` and installs the PyPI wheel `ontographia[cli]` (the same artifact as the maturin release). Bottle CI would duplicate that and go stale; the tap stays a thin pointer.

After the release that contains `otg` is on PyPI, and the formula is in the [tap](https://github.com/edgesentry/homebrew-tap):

```bash
brew tap edgesentry/tap
brew install otg
otg --help
```

What the maintainer does on that release (same kind of manual step as `Formula/ontographia.rb`):

1. Publish the wheel (existing release workflow).
2. In `packaging/homebrew/otg.rb`, set `url` / `sha256` to that git tag and set `PYPI_SPEC` to `ontographia[cli]==X.Y.Z`.
3. Copy the file to `edgesentry/homebrew-tap` as `Formula/otg.rb`.
4. On a Mac: `brew update && brew install otg` (or `brew reinstall otg`), then the Movies commands below.

`brew install otg` fails closed until that PyPI release exists (`otg` script missing). The v0.1.6 tag in the formula is only a Homebrew source anchor; install does not build that tarball.

Platforms: macOS Apple Silicon and Linux x86_64/arm64, where wheels exist. Intel Mac: use the checkout commands above (no wheel, and this formula does not pull a Rust toolchain).

The Rust CLI stays `brew install ontographia`. Do not add an MCP formula.

## Movies quickstart

Public Neo4j Labs movies demo at `neo4j+s://demo.neo4jlabs.com` (read-only). The login is published by Neo4j (`movies` / `movies` on database `movies`). It is not an Ontographia secret; do not commit other passwords.

Ontology (a small subset, not the full sample-graph pack in roadmap [#86](https://github.com/edgesentry/ontographia/issues/86)): [`examples/movies.native.yaml`](https://github.com/edgesentry/ontographia/blob/main/examples/movies.native.yaml). Intent: people who acted in *The Matrix*.

```bash
otg build \
  --ontology examples/movies.native.yaml \
  --intent examples/movies_matrix.json

otg execute \
  --ontology examples/movies.native.yaml \
  --intent examples/movies_matrix.json \
  --neo4j-uri neo4j+s://demo.neo4jlabs.com \
  --neo4j-user movies \
  --neo4j-password movies \
  --neo4j-database movies
```

Prefer env vars over putting the password on the command line:

```bash
export NEO4J_URI=neo4j+s://demo.neo4jlabs.com
export NEO4J_USERNAME=movies
export NEO4J_PASSWORD=movies
export NEO4J_DATABASE=movies
otg execute --ontology examples/movies.native.yaml --intent examples/movies_matrix.json
```

`otg execute` prints the compiled Cypher (so you can see it came from the engine), the bound parameters, and a table. Against the demo database that Intent returns five actors, ordered by name:

| actor |
|-------|
| Carrie-Anne Moss |
| Emil Eifrem |
| Hugo Weaving |
| Keanu Reeves |
| Laurence Fishburne |

`--json` prints one object (`query`, `params`, `rows`, …) instead of the table. `--dialect cypher5` emits `WHERE` instead of Cypher 25 `FILTER` if you need it. The movies demo accepts the default `cypher25` dialect.

Manufacturing walkthrough (local Neo4j, seed data): [End-to-end Neo4j](end-to-end-neo4j.md). Same flags: `--ontology` and `--intent`.

## Commands

| Command | What it does |
|---------|----------------|
| `otg --help` | Subcommands and flags |
| `otg build --ontology PATH --intent PATH` | Compile only. `--intent -` or a pipe reads stdin |
| `otg execute …` | Compile and run read-only. Needs `NEO4J_URI`, `NEO4J_USERNAME` or `NEO4J_USER`, and `NEO4J_PASSWORD` (or the matching flags) |

`--row-limit` (default 100, or `ONTOGRAPHIA_MCP_ROW_LIMIT`) caps both the driver fetch and the Cypher `LIMIT`. Exit `2` means usage or missing Neo4j settings. Exit `1` means the Intent failed validation, the generated Cypher was rejected as a write, or Neo4j returned an error.

## Write queries

`otg` never accepts raw Cypher. A file shaped like `{"query": "CREATE …"}` is an invalid Intent and is not sent to Neo4j. If compilation ever produced a write clause (`CREATE`, `MERGE`, `DELETE`, `SET`, …), execution stops with a read-only error and the driver is not asked to run it. The same deny list is covered by the MCP tests in CI.

## Related

- [Python bindings](python.md)
- [MCP server](mcp.md) — same execute/safety code; not a Homebrew formula
- [Release](release.md) — tap update when publishing
- Issue [#117](https://github.com/edgesentry/ontographia/issues/117)
