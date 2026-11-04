# LiteLLM local setup (OpenAI, Gemini, Cursor)

Local-only guide for routing LLM calls through [LiteLLM](https://docs.litellm.ai/) before Ontographia Intent extraction. **Not run in CI.**

Ontographia still only accepts **Intent JSON** from the LLM layer; LiteLLM is a separate proxy that unifies provider credentials and model routing.

## Architecture

```
Natural language
    → LiteLLM proxy (OpenAI-compatible /v1/chat/completions)
        ├─ ontographia-openai  → OpenAI gpt-4o-mini
        ├─ ontographia-gemini-3.7 → Google Gemini 3.7 Flash
        ├─ ontographia-gemini-3.8 → Google Gemini 3.8 Flash
        └─ ontographia-cursor  → Anthropic Claude (typical Cursor IDE backend via LiteLLM)
    → Intent JSON
    → Ontographia Engine.build()
    → Cypher 25 + params
    → Neo4j
```

Cursor appears in three different roles — keep them separate:

| Role | Endpoint | Use case |
|------|----------|----------|
| **Ontographia E2E** | `http://127.0.0.1:4000/v1` | `run_llm_e2e.py` via model alias |
| **Cursor IDE** | `http://127.0.0.1:4000/cursor` | Route Ask/Plan/Agent through LiteLLM ([LiteLLM Cursor tutorial](https://docs.litellm.ai/docs/tutorials/cursor_integration)) |
| **Cursor Cloud Agents** | `http://127.0.0.1:4000/cursor/v0/*` | Pass-through to `api.cursor.com` with `CURSOR_API_KEY` ([docs](https://docs.litellm.ai/docs/pass_through/cursor)) |

Cursor does **not** expose a general chat-completions API for Intent extraction. The `ontographia-cursor` alias routes to **Anthropic** — the same class of models Cursor IDE often uses when pointed at LiteLLM.

## Secrets layout (1Password)

Secrets live in [1Password](https://developer.1password.com/docs/cli/), never in git. This repository is public: commit no plaintext secrets and no ciphertext.

The committed template [`scripts/litellm/.env.op`](https://github.com/edgesentry/ontographia/blob/main/scripts/litellm/.env.op) contains only `op://` references plus non-secret defaults. The scripts resolve it at run time:

```bash
op run --env-file scripts/litellm/.env.op -- <command>
```

### Vault layout (operator creates; not automated)

| Vault | Item | Fields |
|-------|------|--------|
| `ontographia-dev` | `litellm-upstream` | `LITELLM_MASTER_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `CURSOR_API_KEY` |
| `ontographia-dev` | `neo4j-local` | `password` |

Create the vault and items yourself in the 1Password app or CLI. Leave a field empty only for providers you do not route.

| Path | Role | Commit? |
|------|------|---------|
| `scripts/litellm/.env.op` | `op://` references + non-secret defaults | **Yes** |
| `scripts/litellm/.env*` (other) | Local scratch; scripts do **not** load it | **Never** (gitignored) |
| `*.keys` | Key files | **Never** (gitignored) |

Override the template path with `LITELLM_OP_ENV_FILE`.

There is **no** plaintext `.env` fallback in `start.sh` / `use-provider.sh` / `run-e2e.sh` / `healthcheck.sh`. A missing `op`, a signed-out session, or a missing template is a hard error.

### Install and sign in

Install the 1Password CLI ([docs](https://developer.1password.com/docs/cli/get-started/)), then sign in, for example with the desktop-app integration, or:

```bash
eval "$(op signin)"
op whoami   # must succeed before running the scripts
```

### Rotating a secret

Update the field in the 1Password item. Nothing in the repository changes. If a key was exposed, revoke it at the provider and store the new value in the item.

## 1. One-time setup

```bash
# Install and sign in to op, create vault ontographia-dev (see Secrets layout above)

uv sync --group dev --group litellm
uv run maturin develop --release
chmod +x scripts/litellm/*.sh
```

## 2. Start LiteLLM proxy

**Terminal A** — uv (recommended):

```bash
./scripts/litellm/start.sh
```

This runs `op run --env-file scripts/litellm/.env.op -- uv run --group litellm litellm ...`, so provider keys exist only in the proxy process environment.

**Or Docker:**

```bash
./scripts/litellm/start.sh --docker
```

`--docker` runs `docker run` under `op run` and forwards the keys with `-e`. It pins `ghcr.io/berriai/litellm:v1.106.5` (digest in `scripts/litellm/start.sh`). Leave the floating tags `main-stable` and `latest` unused: they pointed at the compromised `v1.107.0` image on 2026-10-21.

Verify:

```bash
./scripts/litellm/healthcheck.sh
```

Default URL: `http://127.0.0.1:4000`  
Clients use `LITELLM_MASTER_KEY` from the `litellm-upstream` item as the virtual key.

## 3. Run Ontographia LLM E2E

**Terminal B** — pick a provider alias:

```bash
./scripts/start_neo4j.sh --seed

# OpenAI via LiteLLM
./scripts/litellm/run-e2e.sh openai \
  "List suppliers for parts in product SKU SPX-100" \
  --execute --password "$NEO4J_PASSWORD"

# Gemini 3.7 Flash via LiteLLM
./scripts/litellm/run-e2e.sh gemini-3.7 \
  "Which plant hosts production Line-1?" \
  --execute --password "$NEO4J_PASSWORD"

# Gemini 3.8 Flash via LiteLLM
./scripts/litellm/run-e2e.sh gemini-3.8 \
  "Which plant hosts production Line-1?" \
  --execute --password "$NEO4J_PASSWORD"

# Anthropic (Cursor-style stack) via LiteLLM
./scripts/litellm/run-e2e.sh cursor \
  "Which defect codes affect quarantined lots?" \
  --execute --password "$NEO4J_PASSWORD"
```

`NEO4J_PASSWORD` is resolved from `neo4j-local` by `use-provider.sh`, which `run-e2e.sh` sources before expanding it. If you run a command by hand, `source` the script first.

Manual env export (same as the helper scripts):

```bash
source scripts/litellm/use-provider.sh gemini-3.7
uv run python examples/run_llm_e2e.py \
  --question "Which plant hosts production Line-1?" \
  --execute --password "$NEO4J_PASSWORD"
```

## 4. Connect Cursor IDE to LiteLLM (optional)

Use this when you want Cursor itself to call models through the same proxy (logging, key management, model switching).

1. Start LiteLLM (`./scripts/litellm/start.sh`).
2. In Cursor → **Settings → Models**:
   - Enable **Override OpenAI Base URL**: `http://127.0.0.1:4000/cursor`
   - **OpenAI API Key**: your `LITELLM_MASTER_KEY` from the `litellm-upstream` 1Password item
3. **Add Custom Model**: `litellm-claude-sonnet` (defined in `scripts/litellm/config.yaml` — distinct from built-in names).
4. Select that model in Ask/Agent mode.

If **Override OpenAI Base URL** is missing in your Cursor build, use the Azure OpenAI fallback described in the [LiteLLM Cursor integration guide](https://docs.litellm.ai/docs/tutorials/cursor_integration).

> Cursor sends requests from its backend for cloud features. For remote access, expose the proxy with HTTPS or a tunnel — local `127.0.0.1` works for on-machine development only.

## 5. Cursor Cloud Agents (optional)

For the Cursor Cloud Agents API (`/v0/agents`), set `CURSOR_API_KEY` in the `litellm-upstream` item. LiteLLM forwards `/cursor/*` to `api.cursor.com`. This is **not** used by `run_llm_e2e.py`; see [Cursor Cloud Agents pass-through](https://docs.litellm.ai/docs/pass_through/cursor).

## Configuration reference

| File | Purpose |
|------|---------|
| [`scripts/litellm/config.yaml`](https://github.com/edgesentry/ontographia/blob/main/scripts/litellm/config.yaml) | Model aliases and upstream routing |
| [`scripts/litellm/.env.op`](https://github.com/edgesentry/ontographia/blob/main/scripts/litellm/.env.op) | Committed `op://` template (no secret values) |
| [`scripts/litellm/env.example`](https://github.com/edgesentry/ontographia/blob/main/scripts/litellm/env.example) | Annotated copy of the template for reference |
| [`scripts/litellm/_lib.sh`](https://github.com/edgesentry/ontographia/blob/main/scripts/litellm/_lib.sh) | Shared `op` helpers |
| [`scripts/litellm/start.sh`](https://github.com/edgesentry/ontographia/blob/main/scripts/litellm/start.sh) | Start proxy via `op run` (uv or `--docker`) |
| [`scripts/litellm/use-provider.sh`](https://github.com/edgesentry/ontographia/blob/main/scripts/litellm/use-provider.sh) | `source` to set `OPENAI_*` for a provider |
| [`scripts/litellm/run-e2e.sh`](https://github.com/edgesentry/ontographia/blob/main/scripts/litellm/run-e2e.sh) | One-shot E2E through LiteLLM |
| [`scripts/litellm/healthcheck.sh`](https://github.com/edgesentry/ontographia/blob/main/scripts/litellm/healthcheck.sh) | Proxy liveness + model list |

### Model aliases (`config.yaml`)

| Alias | Upstream | Required env |
|-------|----------|--------------|
| `ontographia-openai` | `openai/gpt-4o-mini` | `OPENAI_API_KEY` |
| `ontographia-gemini-3.7` | `gemini/gemini-3.7-flash` | `GEMINI_API_KEY` |
| `ontographia-gemini-3.8` | `gemini/gemini-3.8-flash` | `GEMINI_API_KEY` |
| `ontographia-cursor` | `anthropic/claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| `litellm-claude-sonnet` | same Anthropic model | `ANTHROPIC_API_KEY` (for Cursor IDE custom model name) |

Edit `config.yaml` to change models or add aliases. Restart the proxy after changes.

### Running several Gemini versions side by side

Gemini aliases are always versioned, so several Gemini versions can be used side by side (much like testing against several Python versions) without editing the 1Password items or restarting the proxy:

```bash
source scripts/litellm/use-provider.sh gemini-3.7   # OPENAI_MODEL=ontographia-gemini-3.7
source scripts/litellm/use-provider.sh gemini-3.8   # OPENAI_MODEL=ontographia-gemini-3.8
```

Both aliases share `GEMINI_API_KEY`. Add a new `ontographia-gemini-<version>` entry to `config.yaml` when a new Gemini version is evaluated.

> **Breaking change (#106):** the unversioned `ontographia-gemini` alias, the `gemini` provider in `use-provider.sh` / `run-e2e.sh`, and the `GEMINI_MODEL` env variable were removed. Use `ontographia-gemini-3.7` (the previous default upstream) or `ontographia-gemini-3.8`. Baselines recorded before #106 still show `ontographia-gemini` in their `meta`; that alias pointed to `gemini/gemini-3.7-flash`. Live eval baselines record the alias and upstream model id in their `meta` (see [Evaluation](evaluation.md)).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `1Password CLI (op) not found` | Install the CLI and ensure it is on `PATH` |
| `op is not signed in` | Sign in (desktop-app integration or `eval "$(op signin)"`); check `op whoami` |
| `1Password env template not found` | Restore `scripts/litellm/.env.op` or set `LITELLM_OP_ENV_FILE` |
| `isn't a vault in this account` / item errors | Create vault `ontographia-dev` and the items listed under Vault layout |
| `Connection refused` on port 4000 | Start `./scripts/litellm/start.sh` first |
| `401` from proxy | `OPENAI_API_KEY` in E2E must match `LITELLM_MASTER_KEY` (`use-provider.sh` sets this) |
| `no healthy deployments` / model error | Provider API key missing in `litellm-upstream` for that alias |
| Gemini / Anthropic errors | Confirm key is set; check LiteLLM logs in Terminal A |
| Cursor IDE model collision | Use `litellm-claude-sonnet`, not built-in model names |
| Older local model rejects `json_schema` | Add `--no-json-schema` to `run_llm_e2e.py` |

## See also

- [end-to-end-neo4j.md §7](end-to-end-neo4j.md#7-local-llm-e2e-not-run-in-ci) — generic LLM E2E without LiteLLM
- [skills/ontographia-cypher-builder/SKILL.md](https://github.com/edgesentry/ontographia/blob/main/skills/ontographia-cypher-builder/SKILL.md) — Intent JSON rules for agents
