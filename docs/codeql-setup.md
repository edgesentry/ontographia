# CodeQL setup

Ontographia uses a **repo-managed** workflow: [`.github/workflows/codeql-analysis.yml`](../.github/workflows/codeql-analysis.yml).

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

Languages scanned by the workflow: `actions`, `python`, `rust` (autobuild), `go` (manual cgo build).

## Related

- [architecture.md](architecture.md) — project overview
- CI: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)
