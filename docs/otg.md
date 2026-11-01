# `otg` CLI

**Status: experimental / 0.x.** `otg` loads an ontology, compiles **Intent JSON** with the Rust `Engine`, and can run the query **read-only** against Neo4j.

The model never writes Cypher. `otg` does not call an LLM. Execution on the Python entry point reuses the MCP read-only path (`python/ontographia/mcp/read_only.py`, `safety.py`, `execute.py`): Intent-only input, `READ_ACCESS` / `execute_read`, and the write-clause deny list.

Packaging decision: [#121](https://github.com/edgesentry/ontographia/issues/121).

## Packaging

Homebrew is the front door for the CLI. Language package managers are the front door for libraries and for the MCP server.

| Channel | Install | What you get |
|---------|---------|----------------|
| Homebrew (primary CLI) | `brew tap edgesentry/tap` then `brew install ontographia` | Rust binary. The command is **`otg`**. Read-only Neo4j execute belongs in this binary. Formula: [`Formula/ontographia.rb`](https://github.com/edgesentry/homebrew-tap/blob/main/Formula/ontographia.rb) |
| Python | `uvx --from "ontographia[cli]" otg` or `pip install "ontographia[cli]"` | Library extra and the same `otg` entry point. This is how you call Ontographia from Python. It is the library install, not the Homebrew install |
| Rust crates | [crates.io](https://crates.io): `cargo install ontographia-cli`, `cargo add ontographia-core` (and `-adapters`, `-schema`) | Libraries and the CLI crate |
| Go | `go get` the module; matching `libontographia_ffi-*` archive from [GitHub Releases](https://github.com/edgesentry/ontographia/releases) | cgo bindings. See [Go](go.md) |
| MCP | `uvx --from "ontographia[mcp]" ontographia-mcp` or `pip install "ontographia[mcp]"` | MCP server. See [MCP server](mcp.md) |

The PyPI wheel is the pip / uvx artifact. Homebrew installs the Rust binary from the GitHub Release archive. This repository does not ship a Homebrew formula for that wheel. The formula lives in the tap under the name `ontographia`. The command it installs is `otg`.

### Published tap (v0.1.8)

[`Formula/ontographia.rb`](https://github.com/edgesentry/homebrew-tap/blob/main/Formula/ontographia.rb) points at the **v0.1.8** archives (macOS arm64 and Linux x86_64) and installs the binary as `otg` (`build` and `schema`).

Read-only `execute` is the Python console script from `ontographia[cli]`.

```bash
brew tap edgesentry/tap
brew install ontographia
otg build --help
otg schema --help
```

### Release archive and the next tap bump

`ontographia-cli` builds one binary, named `otg`. `cargo install ontographia-cli` (crates.io 0.1.8) installs that command.

The release tarball `ontographia-{version}-{target}.tar.gz` contains `otg` and a copy of the same file named `ontographia`. `--version` prints `otg` for both files. The formula prefers `otg`. An older archive that only contains `ontographia` is installed as `otg`.

The release workflow does not edit the tap. After a new GitHub Release, a follow-up pull request to [`edgesentry/homebrew-tap`](https://github.com/edgesentry/homebrew-tap) points `Formula/ontographia.rb` at the new archive. The tap does not gain a second formula named `otg`. Before that Release, run the [pre-release checks](release.md#pre-release-checks) (GitHub Actions Release check, then the Mac smoke).

`build` and `schema` are in the Rust binary. Read-only Neo4j `execute` in that binary is the remaining CLI work in [#121](https://github.com/edgesentry/ontographia/issues/121): Intent-only input, write queries rejected, same behavior as `python/ontographia/cli.py`. Until that subcommand ships, `otg execute` means the Python script below.

```bash
cargo install --path crates/ontographia-cli
otg build --help
otg schema --help
```

`uv run otg` in a checkout (after `maturin develop`) is the Python script, which has `execute`. The Cargo install is `build` and `schema`. When both are on `PATH`, the one earlier in `PATH` is the `otg` you run.

## Python entry point

Wheels: Linux x86_64 and arm64, macOS Apple Silicon, Windows x86_64, Python 3.11–3.13. Intel macOS has no wheel; build from a checkout. Matrix: [Python](python.md).

```bash
pip install "ontographia[cli]"
otg --help
```

```bash
uvx --from "ontographia[cli]" otg --help
```

From a git checkout (compiles the extension; needs Rust):

```bash
uv sync --group dev --extra cli
uv run maturin develop --release
uv run otg --help
```

## Movies quickstart

These commands use the **Python** entry point. `execute` is not a Rust subcommand yet.

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

Manufacturing walkthrough (local Neo4j, seed data): [End-to-end Neo4j](end-to-end-neo4j.md). Same flags: `--ontology` and `--intent`. The walkthrough's released-CLI samples use `otg`, the command the published tap installs.

## Commands

| Command | Python `ontographia[cli]` | Rust binary (`otg`) |
|---------|---------------------------|---------------------|
| `--help` | Subcommands and flags | Subcommands and flags. `--version` prints `otg` |
| `build --ontology PATH --intent PATH` | Compile only. `--intent -` or a pipe reads stdin | Compile only |
| `execute …` | Compile and run read-only | Follow-up in [#121](https://github.com/edgesentry/ontographia/issues/121) |
| `schema PATH` | — | Constraints and `schema.json` |

Python `execute` needs `NEO4J_URI`, `NEO4J_USERNAME` or `NEO4J_USER`, and `NEO4J_PASSWORD` (or the matching flags). `--row-limit` (default 100, or `ONTOGRAPHIA_MCP_ROW_LIMIT`) caps both the driver fetch and the Cypher `LIMIT`. Each traverse step must be a single hop: omit `min_hops` and `max_hops`, or set both to `1`. Any wider range is rejected with `hop_range_rejected` and is not sent to Neo4j (same rule as the MCP `execute` tool). Exit `2` means usage or missing Neo4j settings. Exit `1` means the Intent failed validation, the hop range was rejected, the generated Cypher was rejected as a write, or Neo4j returned an error.

## Write queries

The Python entry point never accepts raw Cypher. A file shaped like `{"query": "CREATE …"}` is an invalid Intent and is not sent to Neo4j. If compilation ever produced a write clause (`CREATE`, `MERGE`, `DELETE`, `SET`, …), execution stops with a read-only error and the driver is not asked to run it. The same deny list is covered by the MCP tests in CI.

The Rust subcommand will use that same rule when it lands: Intent in, generated Cypher only, writes rejected before any driver call.

## Related

- [Python bindings](python.md)
- [Rust](rust.md)
- [MCP server](mcp.md) — same execute/safety code on the Python side; install with `uvx` or `pip install "ontographia[mcp]"`
- [Release](release.md#pre-release-checks) — Actions vs Mac checks before Release, archive layout, and the tap bump after a release
- Issue [#117](https://github.com/edgesentry/ontographia/issues/117) (Python `otg`), [#121](https://github.com/edgesentry/ontographia/issues/121) (this packaging decision)
