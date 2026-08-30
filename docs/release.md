# Release workflow

Ontographia ships **Rust crates + CLI**, a **Python wheel** (PyPI), and **Go bindings** (cgo + FFI). Releases are cut from `main` only.

## Flow

```mermaid
flowchart LR
  A[PR merge to main] --> B[CI green on main]
  B --> C[Bump version in Cargo.toml]
  C --> D[Release check optional]
  D --> E[Release workflow]
  E --> E1[Preflight same as Release check]
  E1 --> E2[Create tag + GitHub Release]
  E2 --> F[Build and upload artifacts]
  F --> G1[GitHub Release assets]
  F --> G2[cargo publish optional]
  F --> G3[PyPI upload optional]
```

1. Merge feature work to `main` and confirm [CI](https://github.com/edgesentry/ontographia/actions/workflows/ci.yml) passes.
2. Bump the workspace version on `main` (see [Version bumps](#version-bumps)) — **no local git tag**.
3. **(Recommended)** Run **[Release check](https://github.com/edgesentry/ontographia/actions/workflows/release-check.yml)** — dry-run only; no tag or release is created.
4. Run **[Release](https://github.com/edgesentry/ontographia/actions/workflows/release.yml)** — runs the **same preflight** again, then creates `vX.Y.Z`, the GitHub Release, and uploads artifacts.

Both workflows call the shared [`preflight-release.yml`](https://github.com/edgesentry/ontographia/blob/main/.github/workflows/preflight-release.yml) reusable workflow (backed by `scripts/preflight-release.sh`).

**Immutable tags:** preflight fails if `vX.Y.Z`, `release-processed/vX.Y.Z`, or `bindings/go/vX.Y.Z` already exists on the remote. After a successful Release start, `release-processed/vX.Y.Z` is claimed; the same version cannot be re-released — bump the version in `Cargo.toml`.

## Option A — GitHub Actions

### Release check (dry-run)

1. Open **Actions → Release check**.
2. Click **Run workflow** (branch `main`).
3. Enter **version** without the `v` prefix (e.g. `0.1.1`).
4. Confirm the run passes (tests, `cargo publish --dry-run`, wheel build).

No tag or GitHub Release is created.

### Release (publish)

1. Open **Actions → Release**.
2. Click **Run workflow** (branch `main`).
3. Enter the same **version** (e.g. `0.1.1`) — must match `Cargo.toml`.
4. Click **Run workflow**.

Preflight runs again on the runner, then the workflow creates the tag, GitHub Release, and uploads assets.

## Option B — CLI

Requires [GitHub CLI](https://cli.github.com/) (`gh`) authenticated with `repo` scope.

### Release check only

```bash
bash scripts/preflight-release.sh 0.1.1
# or trigger the Release check workflow:
gh workflow run "Release check" --ref main -f version=0.1.1
```

### Full release

```bash
# 1. Bump version on main (via PR or locally)
scripts/bump-version.sh 0.1.1 --commit
git push origin main

# 2. (Recommended) dry-run
bash scripts/preflight-release.sh 0.1.1
# or: gh workflow run "Release check" --ref main -f version=0.1.1

# 3. Preflight locally + trigger Release workflow
scripts/trigger-release.sh 0.1.1

# 4. Watch the run
gh run watch --workflow Release
```

`trigger-release.sh` runs `preflight-release.sh` locally, then `gh workflow run Release`. The Release workflow still runs preflight on the runner.

### Preflight steps (shared by Release check and Release)

```bash
bash scripts/verify-release-version.sh v0.1.1
bash scripts/verify-tag-not-exists.sh v0.1.1
bash scripts/release-check.sh
```

(`preflight-release.sh` runs all three.)

### Trigger Release only (skip local preflight)

```bash
gh workflow run Release --ref main -f version=0.1.1
```

## Version bumps

**Single source of truth:** root `Cargo.toml` → `[workspace.package] version`.

| Component | Where version lives |
|-----------|---------------------|
| Rust (all crates) | `version.workspace = true` → workspace version |
| Python wheel | `pyproject.toml` `dynamic = ["version"]` → `bindings/python/Cargo.toml` via maturin |
| Go | No file; `bindings/go/vX.Y.Z` tag created by the release workflow |

```bash
scripts/bump-version.sh 0.1.1 --commit
```

The release workflow rejects versions that do not match `Cargo.toml` (`scripts/verify-release-version.sh`).

## GitHub secrets (optional registry publish)

| Secret | Purpose |
|--------|---------|
| `CARGO_REGISTRY_TOKEN` | `cargo publish` for `ontographia-core`, `-adapters`, `-schema`, `-cli` |
| `PYPI_API_TOKEN` | `maturin upload` to PyPI |

| Variable | Purpose |
|----------|---------|
| `PUBLISH_TO_REGISTRIES` | Set to `true` to enable crates.io / PyPI publish jobs |

Without registry settings, the workflow still uploads **GitHub Release assets**.

## Install after release

### CLI (GitHub Release or crates.io)

```bash
cargo install ontographia-cli
```

```bash
ontographia build --ontology manufacturing.native.yaml --intent intent.json --json
ontographia schema manufacturing.native.yaml --out constraints.cypher --json-out schema.json
```

### Rust libraries

```toml
ontographia-core = "0.1"
ontographia-adapters = "0.1"
ontographia-schema = "0.1"
```

### Python

Supported: **3.11, 3.12, 3.13** (`requires-python = ">=3.11"`). CI runs Python smoke and Neo4j integration on all three; releases ship Linux wheels for each.

```bash
pip install ontographia
```

### Go

```bash
go get github.com/edgesentry/ontographia/bindings/go@v0.1.1
```

Download the matching `libontographia_ffi-*` archive from GitHub Releases for cgo linking.

The release workflow creates `bindings/go/vX.Y.Z` automatically.

## Artifacts

| Artifact | Contents |
|----------|----------|
| `ontographia-{version}-{target}.tar.gz` | `ontographia` CLI binary |
| `libontographia_ffi-{version}-{target}.tar.gz` | Shared library for Go/cgo |
| `ontographia-{version}-*.whl` | Python package |

## Related

- [architecture.md](architecture.md)
- [AGENTS.md](https://github.com/edgesentry/ontographia/blob/main/AGENTS.md)
