# Release workflow

Ontographia ships **Rust crates + CLI**, a **Python wheel** (PyPI), **Go bindings** (cgo + FFI), and **TypeScript bindings** (npm, with a prebuilt `libontographia_ffi`). Releases are cut from `main` only.

**Changelog:** [GitHub Releases](https://github.com/edgesentry/ontographia/releases) are the source of truth. The Release workflow creates each release with `gh release create … --generate-notes`.

**Trigger policy:** [Release check](https://github.com/edgesentry/ontographia/actions/workflows/release-check.yml) and [Release](https://github.com/edgesentry/ontographia/actions/workflows/release.yml) run **only** via **Run workflow** (`workflow_dispatch`). They **never** start on push to `main`, tag push, or GitHub Release publish events.

## Flow

```mermaid
flowchart LR
  A[PR merge to main] --> B[CI green on main]
  B --> C[Bump version in Cargo.toml]
  C --> D[Release check]
  C --> E[Release]
  D -. optional .-> E
  E --> F[GitHub Release + artifacts]
  F --> G1[Release assets]
  F --> G2[crates.io optional]
  F --> G3[PyPI optional]
  F --> G4[npm optional]
```

1. Merge feature work to `main` and confirm [CI](https://github.com/edgesentry/ontographia/actions/workflows/ci.yml) passes.
2. Bump the workspace version on `main` (see [Version bumps](#version-bumps)) — **no local git tag**.
3. **(Recommended)** Run **[Release check](https://github.com/edgesentry/ontographia/actions/workflows/release-check.yml)** — dry-run only; no tag or release is created.
4. Run **[Release](https://github.com/edgesentry/ontographia/actions/workflows/release.yml)** — reads `Cargo.toml`, creates `vX.Y.Z`, uploads artifacts.

Both workflows share the same internal validation (`scripts/preflight-release.sh`). **No version input** — bump `Cargo.toml` on `main` first.

**Immutable tags:** preflight fails if `vX.Y.Z`, `release-processed/vX.Y.Z`, or `bindings/go/vX.Y.Z` already exists on the remote. After a successful Release start, `release-processed/vX.Y.Z` is claimed; the same version cannot be re-released — bump the version in `Cargo.toml`.

## Option A — GitHub Actions

### Release check (dry-run)

1. Open **Actions → Release check**.
2. Click **Run workflow** (branch `main`).
3. Confirm the run passes. Preflight prints these lines, in order:

   - `release version ok`
   - `release workflow ok: .github/workflows/release.yml name=Release job=publish-npm`
   - `registry reachability ok` (read-only npm, crates.io, and PyPI)
   - each of `@edgesentry/ontographia` and the four platform packages `is on the registry`, then `npm packages on registry; trusted publisher settings were not read`
   - `npm pack dry-run ok` (stub FFI archives; four platform `optionalDependencies`; no publish)
   - `tag vX.Y.Z is available`
   - `release check ok` (tests, `cargo publish --dry-run` for `ontographia-core`, wheels)
   - `preflight ok for vX.Y.Z`

No tag or GitHub Release is created. Nothing is published.

The npm package check runs **before** the immutable-tag check. A version whose tag already exists still confirms the five packages are on the registry and packs the npm tarballs, then stops with `tag already exists` and does not build wheels. A green run waits until `Cargo.toml` is a version whose tag is free.

Release check confirms those five packages from the **public** registry document. It does not call `GET /-/package/{package}/trust` and it does not read `NPM_TRUST_TOKEN`. That GET needs a granular token with write access and, when the account has 2FA, an `npm-otp` header. npm warns against Bypass-2fa and publish-and-stage tokens and prefers Trusted Publishing. Do not add `NPM_TRUST_TOKEN`, a Bypass-2fa token, or `NPM_TOKEN` to GitHub Actions. `publish-npm` stays on Trusted Publishing (OIDC) only.

Confirm the publishers yourself after `npm login`:

```bash
npm trust list @edgesentry/ontographia --json
npm trust list @edgesentry/ontographia-linux-x64 --json
npm trust list @edgesentry/ontographia-linux-arm64 --json
npm trust list @edgesentry/ontographia-darwin-arm64 --json
npm trust list @edgesentry/ontographia-win32-x64 --json
```

Each record should be GitHub Actions on `edgesentry/ontographia`, workflow filename `release.yml`, an empty environment, and `createPackage` (**Allow npm publish** on). Do this before the next Release if win32 or the main package might still be missing that publisher. Release check prints the same commands as a warning. A missing trust token does not fail the job.

An optional local read of the same API, outside Actions, is `NPM_TRUST_TOKEN=... node scripts/check-npm-trusted-publishers.mjs`. If npm asks for a one-time code, use `npm trust list`, or set `NPM_TRUST_OTP` for that local process only. GitHub Actions ignores `NPM_TRUST_TOKEN`.

### Release (publish)

1. Bump `[workspace.package] version` in `Cargo.toml` on `main` (see [Version bumps](#version-bumps)).
2. Open **Actions → Release**.
3. Click **Run workflow** (branch `main`) — no version field; the workflow reads `Cargo.toml`.

Preflight runs internally, then the workflow creates `vX.Y.Z`, the GitHub Release, and uploads assets.

## Option B — CLI

Requires [GitHub CLI](https://cli.github.com/) (`gh`) authenticated with `repo` scope.

### Release check only

```bash
bash scripts/preflight-release.sh
# or trigger the Release check workflow:
gh workflow run "Release check" --ref main
```

### Full release

```bash
# 1. Bump version on main (via PR or locally)
scripts/bump-version.sh 0.1.8 --commit
git push origin main

# 2. (Recommended) dry-run
bash scripts/preflight-release.sh
# or: gh workflow run "Release check" --ref main

# 3. Preflight locally + trigger Release workflow
scripts/trigger-release.sh

# 4. Watch the run
gh run watch --workflow Release
```

`trigger-release.sh` reads `Cargo.toml`, runs `preflight-release.sh`, then `gh workflow run Release`. The Release workflow still runs preflight on the runner.

### Preflight steps (shared by Release check and Release)

```bash
VERSION="$(bash scripts/workspace-version.sh)"
bash scripts/verify-release-version.sh "v${VERSION}"
node scripts/check-release-workflow.mjs
bash scripts/check-registry-reachability.sh
node scripts/check-npm-trusted-publishers.mjs
node scripts/package-npm-dry-run.mjs
bash scripts/verify-tag-not-exists.sh "v${VERSION}"
bash scripts/release-check.sh
```

(`preflight-release.sh` runs these using the workspace version. In GitHub Actions, `check-npm-trusted-publishers.mjs` only checks that the five packages exist. It reads publisher settings only when `NPM_TRUST_TOKEN` is set outside Actions.)

### Trigger Release only (skip local preflight)

```bash
gh workflow run Release --ref main
```

## Version bumps

**Single source of truth:** root `Cargo.toml` → `[workspace.package] version`.

| Component | Where version lives |
|-----------|---------------------|
| Rust (all crates) | `version.workspace = true` → workspace version |
| Python wheel | `pyproject.toml` `dynamic = ["version"]` → `bindings/python/Cargo.toml` via maturin |
| Go | No file; `bindings/go/vX.Y.Z` tag created by the release workflow |
| TypeScript / npm | `bindings/typescript/package.json` `version`, kept equal to the workspace version by `scripts/bump-version.sh`. Preflight fails if they differ. Platform-package versions are not stored in git; `scripts/package-npm.mjs` stamps the workspace version when it packs them |

```bash
scripts/bump-version.sh 0.1.8 --commit
```

The release workflow rejects versions that do not match `Cargo.toml` (`scripts/verify-release-version.sh`).

## GitHub secrets (optional registry publish)

| Secret | Purpose |
|--------|---------|
| `CARGO_REGISTRY_TOKEN` | `cargo publish` for `ontographia-core`, `-adapters`, `-schema`, `-cli` |
| `PYPI_API_TOKEN` | `maturin upload` to PyPI |

| Variable | Purpose |
|----------|---------|
| `PUBLISH_TO_REGISTRIES` | Set to `true` to enable crates.io / PyPI / npm publish jobs |

npm does not use an Actions secret. Job `publish-npm` authenticates with [npm Trusted Publishing](https://docs.npmjs.com/trusted-publishers/) (GitHub Actions OIDC). The Release workflow grants `id-token: write`, and the job sets that permission again because a job `permissions` block replaces workflow inheritance. `actions/setup-node` is configured with `registry-url: https://registry.npmjs.org`. The job runs `npm publish` (npm CLI **11.5.1+**). Provenance is attached automatically for this public repository; the command does not pass `--provenance`.

Delete the Actions secret `NPM_TOKEN` if it was added. `scripts/publish-npm.sh` exits when `NPM_TOKEN` or a real `NODE_AUTH_TOKEN` is present, so a granular access token (including one that bypasses MFA) cannot publish.

Without registry settings, the workflow still uploads **GitHub Release assets**, including the npm tarballs.

### npm Trusted Publishing (maintainer, once per package)

The scope `@edgesentry` is an npm organization. Creating the GitHub org does not create it. Package names are immutable after the first publish. Do this on npmjs.com as an owner of that org. Laptops and agents do not upload the Release tarballs.

1. Create the npm organization **`edgesentry`** at [npmjs.com/org/create](https://www.npmjs.com/org/create).
2. Create these five package names under that org. The Trusted Publisher form is on a package that already exists ([`npm trust` requires the package on the registry](https://docs.npmjs.com/cli/v11/commands/npm-trust/)). A placeholder version such as `0.0.0`, published by you with an interactive login, is enough for the settings page. Use a version other than the workspace version in `Cargo.toml`, so the Release job still publishes the real tarball. Do not upload the Release `.tgz` files and do not run `scripts/publish-npm.sh`.
   - `@edgesentry/ontographia`
   - `@edgesentry/ontographia-linux-x64`
   - `@edgesentry/ontographia-linux-arm64`
   - `@edgesentry/ontographia-darwin-arm64`
   - `@edgesentry/ontographia-win32-x64`
3. On each package, open **Packages → the package → Settings → Trusted publishing** ([docs](https://docs.npmjs.com/trusted-publishers/)). Choose **GitHub Actions** and save one connection with the fields below. The same screen is `https://www.npmjs.com/package/<name>/access`.
4. On each package, open **Settings → Publishing access**, choose **Require two-factor authentication and disallow tokens**, and save. Trusted Publishing still publishes. An npm token does not.
5. Set the repository variable `PUBLISH_TO_REGISTRIES` to `true`.

Trusted Publisher fields, same on all five packages:

| Field | Value |
|-------|--------|
| Organization or user | `edgesentry` |
| Repository | `ontographia` |
| Workflow filename | `release.yml` |
| Environment name | empty |
| Allow `npm publish` | on |

The file is `.github/workflows/release.yml`. Its workflow `name:` is **Release**. npm matches the filename `release.yml`, including `.yml`. **Run workflow** starts that file directly, so the filename is `release.yml` and the environment stays empty (the job does not set a GitHub environment).

A trusted publisher created after 2026-09-03 allows `npm stage publish` until you also allow direct `npm publish`. The Release job runs `npm publish`. Turn **Allow npm publish** on.

`os` and `cpu` on a platform `package.json` (`scripts/package-npm.mjs`) choose which optional dependency npm installs. They do not decide whether `npm publish` is allowed. The v0.1.7 Release runner was Linux and still published `@edgesentry/ontographia-darwin-arm64@0.1.7` (`"os": ["darwin"]`) with provenance. Leave those fields in place, including on `@edgesentry/ontographia-win32-x64` (`"os": ["win32"]`, `"cpu": ["x64"]`, no `libc`).

**Win32 uses the same Trusted Publisher as the other four packages.** Release run [41265294898](https://github.com/edgesentry/ontographia/actions/runs/41265294898) published `@edgesentry/ontographia-darwin-arm64`, `@edgesentry/ontographia-linux-arm64`, and `@edgesentry/ontographia-linux-x64` at `0.1.7` via OIDC. `@edgesentry/ontographia-win32-x64@0.1.7` then returned `ENEEDAUTH` (`need auth`). The package already exists (`0.0.0` and `0.0.0-stage`); `0.1.7` was not published, and neither was `@edgesentry/ontographia@0.1.7`, because the script stopped at the first failure. That is a missing, expired, or publish-disallowed Trusted Publisher on the win32 package alone. Re-check [its access page](https://www.npmjs.com/package/@edgesentry/ontographia-win32-x64/access) against the table above before re-running Release. Do the same for [`@edgesentry/ontographia`](https://www.npmjs.com/package/@edgesentry/ontographia/access) if the main package has not been published at this version yet.

A new connection must complete its first successful publish within **2 days** or it expires. Save it when you are about to run Release, and run Release inside that window. An expired connection is deleted and created again; it cannot be edited.

**npm publish is allowed only in the Release job `publish-npm`.** `scripts/publish-npm.sh` exits before it talks to the registry unless `GITHUB_ACTIONS=true`, `GITHUB_WORKFLOW=Release`, and `GITHUB_JOB=publish-npm`, and unless the OIDC request variables from `id-token: write` are present. `bindings/typescript` sets `prepublishOnly` so `npm publish` in that directory fails. Packing (`scripts/package-npm.mjs` / `npm pack`, including `scripts/package-npm-dry-run.mjs` in preflight) does not upload. Preflight also refuses a `release.yml` whose name is not **Release**, whose publish job id is not `publish-npm`, or whose `upload-assets` job has no checkout and no `GH_REPO`. Those are the OIDC and `gh release upload` invariants. `scripts/check-npm-trusted-publishers.mjs` confirms the five packages exist before any publish job. In GitHub Actions it does not call the authenticated trust API and it does not publish. Confirm publishers locally with `npm trust list`.

### Re-running a failed Release

If a Release run fails partway through (for example after `ontographia-core` was already published, or after the Go module tag was pushed), fix the workflow or bump the version as needed, then **Run workflow** again on the same `Cargo.toml` version:

- **crates.io:** publish jobs skip crates that already exist at the workspace version.
- **Go:** the workflow fails fast if `bindings/go/vX.Y.Z` already exists — do not delete that tag; bump the version instead.
- **npm:** platform tarballs publish first (lexical filename order: `darwin-arm64`, `linux-arm64`, `linux-x64`, `win32-x64`), then `@edgesentry/ontographia`. Versions already on npm are skipped, so a re-run is safe when some packages are already at this version (for `0.1.7`, the three platform packages above). A missing trusted publisher, a workflow filename other than `release.yml`, or a publisher that does not allow `npm publish` makes that one package return `ENEEDAUTH`. The script still attempts the remaining tarballs, then exits non-zero and lists the names that are not on the registry. npm versions are immutable; replace a bad native by bumping `Cargo.toml` (and the TypeScript `package.json` via `scripts/bump-version.sh`). Do not delete tag `v0.1.7` to retry this publish.
- **GitHub Release assets:** `upload-assets` checks out the release tag and sets `GH_REPO`. `gh release upload` needs a git checkout or `GH_REPO`; without either it exits `fatal: not a git repository`. The upload overwrites files of the same name (`--clobber`).

**Re-run uses the workflow file from that run's commit**, not a later commit on `main`. For [run 41265294898](https://github.com/edgesentry/ontographia/actions/runs/41265294898) (`c6ca92a`, tag `v0.1.7`):

1. On npm, open [@edgesentry/ontographia-win32-x64 access](https://www.npmjs.com/package/@edgesentry/ontographia-win32-x64/access) and save the same Trusted Publisher as the other four packages (table above, **Allow npm publish** on). Also confirm [@edgesentry/ontographia access](https://www.npmjs.com/package/@edgesentry/ontographia/access) before the main package is published.
2. **Re-run failed jobs** on that run. `publish-npm` checks out tag `v0.1.7`. The script on that tag already skips `@edgesentry/ontographia-darwin-arm64@0.1.7`, `@edgesentry/ontographia-linux-arm64@0.1.7`, and `@edgesentry/ontographia-linux-x64@0.1.7`, then publishes win32 and `@edgesentry/ontographia`. Do this only after step 1. The continue-on-failure behavior in this document is on `main` after the fix is merged; the tag does not move.
3. Do not expect that same re-run to fix `upload-assets`. It still executes the workflow from `c6ca92a`, which does not check out the repo. Do not start a new Release for `0.1.7`: preflight refuses because `v0.1.7` and `release-processed/v0.1.7` already exist. Do not delete those tags. Attach the assets from the run with `gh release upload v0.1.7 <files> --clobber` (the run's artifacts are the CLI, FFI, wheel, and npm tarballs). The checkout fix applies to the next Release, which is a new `Cargo.toml` version.

## Install after release

| Channel | Role |
|---------|------|
| Homebrew `brew install ontographia` | Primary CLI. Rust binary. The command is **`otg`** once [`Formula/ontographia.rb`](https://github.com/edgesentry/homebrew-tap/blob/main/Formula/ontographia.rb) is pointed at that filename. That `otg` runs read-only Neo4j `execute` when Neo4j is available |
| `pip` / `uvx` extras (`ontographia[cli]`, `[llm]`, `[mcp]`) | Python library and the Python `otg` entry point |
| crates.io | Rust libraries and `cargo install ontographia-cli` |
| Go module + `libontographia_ffi-*` on the GitHub Release | cgo bindings |
| npm `@edgesentry/ontographia` | TypeScript / JavaScript. Prebuilt `libontographia_ffi` for Linux x64, Linux arm64, macOS arm64, and Windows x64 |
| `ontographia[mcp]` via `uvx` or pip | MCP server |

Guide: [otg CLI](otg.md). Decision: [#121](https://github.com/edgesentry/ontographia/issues/121).

### CLI (GitHub Release, Homebrew, or crates.io)

The published tap (assets from **v0.1.3**) installs a binary named `ontographia`:

```bash
brew tap edgesentry/tap
brew install ontographia
```

```bash
ontographia build --ontology manufacturing.native.yaml --intent intent.json --json
ontographia schema manufacturing.native.yaml --out constraints.cypher --json-out schema.json
```

crates.io matches the last published crate:

```bash
cargo install ontographia-cli
```

**Next CLI release.** Cargo builds `otg`. `ontographia-{version}-{target}.tar.gz` contains that binary and a copy named `ontographia`, so the current formula keeps installing. `--version` prints `otg` for both files. After that release is published, a follow-up pull request on `edgesentry/homebrew-tap` changes `Formula/ontographia.rb` to install `otg` and can drop the extra filename from the archive. The release workflow does not edit the tap. Open the tap pull request only after the `otg` binary is in the GitHub Release.

A checkout that already builds both filenames:

```bash
cargo install --path crates/ontographia-cli
otg build --help
```

Rust `otg` here has `build`, `schema`, and read-only `execute` ([#136](https://github.com/edgesentry/ontographia/issues/136)). `execute` runs when Neo4j is available. The Python entry point below is still how pip and uvx install `otg`.

**macOS smoke** for the `macos-arm64` archive (and for `otg` after the tap installs it). Neo4j has to be reachable; the binary does not start a database:

```bash
otg --version
otg execute --help
# exit 2 when NEO4J_URI / user / password are unset
otg execute --ontology examples/manufacturing.native.yaml --intent examples/sample_intent.json
# with Neo4j up (env or --neo4j-uri / --neo4j-user / --neo4j-password): prints Cypher and rows
```

The same checks apply to the copy of the binary named `ontographia` inside `ontographia-{version}-macos-arm64.tar.gz`. `--version` prints `otg` for both files.

### Rust libraries

```toml
ontographia-core = "0.1"
ontographia-adapters = "0.1"
ontographia-schema = "0.1"
```

### Python

Supported: **3.11, 3.12, 3.13** (`requires-python = ">=3.11"`). CI runs Python smoke and Neo4j integration on all three; releases ship wheels for **Linux x86_64**, **Linux arm64**, **macOS arm64**, and **Windows x86_64** (12 wheels per version).

```bash
pip install ontographia
pip install "ontographia[llm]"   # optional Intent layer
pip install "ontographia[mcp]"   # optional MCP server (ontographia-mcp)
pip install "ontographia[cli]"   # Python otg entry point (read-only execute)
uvx --from "ontographia[cli]" otg --help
```

### Go

```bash
go get github.com/edgesentry/ontographia/bindings/go@v0.1.8
```

Download the matching `libontographia_ffi-*` archive from GitHub Releases (`linux-x86_64`, `linux-arm64`, `macos-arm64`, `windows-x86_64`). Point `LIBRARY_PATH` and `CGO_LDFLAGS` at the extracted directory (`LD_LIBRARY_PATH` on Linux, `DYLD_LIBRARY_PATH` on macOS, `PATH` on Windows at run time). `ONTOGRAPHIA_FFI_LIB` is the library file or that directory; `bindings/go/scripts/ffi-env.sh` copies it into the linker variables. Exact exports: [Go](go.md).

`v0.1.8` of the module still passes `-L${SRCDIR}/../../../target/release`. The tree on `main` does not. That link line ships in the next `bindings/go` tag.

The release workflow creates `bindings/go/vX.Y.Z` on the same commit as `vX.Y.Z` (the `main` checkout that created the GitHub Release). The `release-processed/vX.Y.Z` claim uses that same checkout. Neither tag uses the commit that merely started the manual workflow, which can differ when `main` has moved or the run was dispatched from another ref.

### TypeScript / JavaScript

Node.js **22+**.

```bash
npm install @edgesentry/ontographia
```

That install also selects one platform package (`os` / `cpu` / `libc`) and downloads a single prebuilt library:

| Package | Host |
|---------|------|
| `@edgesentry/ontographia-linux-x64` | Linux x64, glibc |
| `@edgesentry/ontographia-linux-arm64` | Linux arm64, glibc |
| `@edgesentry/ontographia-darwin-arm64` | macOS Apple Silicon |
| `@edgesentry/ontographia-win32-x64` | Windows x64 |

musl/Alpine, macOS x64, and Windows arm64 are not built. Set `ONTOGRAPHIA_FFI_LIB` (or `ONTOGRAPHIA_FFI_DIR`) to load a custom shared library; those variables override the prebuild. A git checkout still uses `target/release` when no prebuild is installed (`cargo build --release -p ontographia-ffi`).

The same tarballs are attached to the GitHub Release (`edgesentry-ontographia-*.tgz`) for a registry-less install. Uploading them to npm happens only in the Release workflow when `PUBLISH_TO_REGISTRIES` is `true`. Local `npm publish` is forbidden; see [GitHub secrets](#github-secrets-optional-registry-publish).

User guide (`docs/typescript.md`) is still deferred. Package notes: [bindings/typescript](https://github.com/edgesentry/ontographia/tree/main/bindings/typescript).

## Artifacts

| Artifact | Contents |
|----------|----------|
| `ontographia-{version}-{target}.tar.gz` | CLI binary `otg`, plus a copy named `ontographia` so the current tap formula keeps installing. `--version` prints `otg`. Drop the copy after the tap installs `otg` |
| `libontographia_ffi-{version}-{target}.tar.gz` | Shared library for Go/cgo (`linux-x86_64`, `linux-arm64`, `macos-arm64`, `windows-x86_64`). The Windows archive also includes `ontographia_ffi.dll.lib` (MSVC import library) starting with the next release. The npm job consumes these same archives and copies the shared library only |
| `ontographia-{version}-*.whl` | Python package (Linux x86_64/arm64, macOS arm64, Windows x86_64 × Python 3.11–3.13) |
| `edgesentry-ontographia-{version}.tgz` | npm package `@edgesentry/ontographia` (loader + `optionalDependencies` on the platform packages) |
| `edgesentry-ontographia-<platform>-{version}.tgz` | Prebuilt `libontographia_ffi` for `linux-x64`, `linux-arm64`, `darwin-arm64`, `win32-x64` |

## Related

- [architecture.md](architecture.md)
- [AGENTS.md](https://github.com/edgesentry/ontographia/blob/main/AGENTS.md)
