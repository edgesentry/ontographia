# CodeQL setup

Ontographia uses a **repo-managed** workflow: [`.github/workflows/codeql-analysis.yml`](https://github.com/edgesentry/ontographia/blob/main/github/workflows/codeql-analysis.yml).

## Disable GitHub Default setup (required)

You cannot run **both** Default setup and the workflow file. If Default setup stays enabled, uploads fail with:

```text
CodeQL analyses from advanced configurations cannot be processed when the default setup is enabled
```

**One-time (repo admin):**

1. Open **Settings → Code security and analysis**
2. Under **Code scanning**, open **CodeQL analysis**
3. For **Default setup**, click **Disable**
4. Re-run the failed CodeQL workflow on the PR

Languages scanned by the workflow: `actions`, `python`, `rust` (`build-mode: none`, no compile), `go` (manual cgo build).

## "Advanced setup requested but no analysis uploaded for default branch"

This appears when **Default setup is disabled** but `main` has not yet received a successful run from [`.github/workflows/codeql-analysis.yml`](https://github.com/edgesentry/ontographia/blob/main/github/workflows/codeql-analysis.yml).

1. Merge the CodeQL workflow PR (or ensure the file exists on `main`).
2. Push to `main` or run **Actions → CodeQL → Run workflow** on `main`.
3. Confirm all matrix jobs succeed (especially `Analyze (rust)`).

Until step 2 completes, the Code scanning settings page will show that warning even if PR runs pass.

## Related

- [architecture.md](architecture.md) — project overview
- CI: [`.github/workflows/ci.yml`](https://github.com/edgesentry/ontographia/blob/main/github/workflows/ci.yml)
