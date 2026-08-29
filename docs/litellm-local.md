# LiteLLM local setup (OpenAI, Gemini, Cursor)

Local-only guide for routing LLM calls through [LiteLLM](https://docs.litellm.ai/) before Ontographia Intent extraction. **Not run in CI.**

Ontographia still only accepts **Intent JSON** from the LLM layer; LiteLLM is a separate proxy that unifies provider credentials and model routing.

## Architecture

```
Natural language
    → LiteLLM proxy (OpenAI-compatible /v1/chat/completions)
        ├─ ontographia-openai  → OpenAI gpt-4o-mini
        ├─ ontographia-gemini  → Google Gemini
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

## 1. One-time setup

```bash
cp scripts/litellm/env.example scripts/litellm/.env
# Edit scripts/litellm/.env — set keys for providers you use:
#   OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY, CURSOR_API_KEY (optional)

uv sync --group dev --group llm
uv run maturin develop --release
chmod +x scripts/litellm/*.sh
```

## 2. Start LiteLLM proxy

**Terminal A** — uv (recommended):

```bash
./scripts/litellm/start.sh
```

**Or Docker:**

```bash
./scripts/litellm/start.sh --docker
```

Verify:

```bash
./scripts/litellm/healthcheck.sh
```

Default URL: `http://127.0.0.1:4000`  
Default virtual key: `sk-litellm-local-dev` (set `LITELLM_MASTER_KEY` in `.env`).

## 3. Run Ontographia LLM E2E

**Terminal B** — pick a provider alias:

```bash
./scripts/start_neo4j.sh --seed

# OpenAI via LiteLLM
./scripts/litellm/run-e2e.sh openai \
  "List suppliers for parts in product SKU SPX-100" \
  --execute --password ontographia

# Gemini via LiteLLM
./scripts/litellm/run-e2e.sh gemini \
  "Which plant hosts production Line-1?" \
  --execute --password ontographia

# Anthropic (Cursor-style stack) via LiteLLM
./scripts/litellm/run-e2e.sh cursor \
  "Which defect codes affect quarantined lots?" \
  --execute --password ontographia
```

Manual env export (same as the helper scripts):

```bash
source scripts/litellm/use-provider.sh gemini
uv run python examples/run_llm_e2e.py \
  --question "Which plant hosts production Line-1?" \
  --execute --password ontographia
```

## 4. Connect Cursor IDE to LiteLLM (optional)

Use this when you want Cursor itself to call models through the same proxy (logging, key management, model switching).

1. Start LiteLLM (`./scripts/litellm/start.sh`).
2. In Cursor → **Settings → Models**:
   - Enable **Override OpenAI Base URL**: `http://127.0.0.1:4000/cursor`
   - **OpenAI API Key**: your `LITELLM_MASTER_KEY` from `.env`
3. **Add Custom Model**: `litellm-claude-sonnet` (defined in `scripts/litellm/config.yaml` — distinct from built-in names).
4. Select that model in Ask/Agent mode.

If **Override OpenAI Base URL** is missing in your Cursor build, use the Azure OpenAI fallback described in the [LiteLLM Cursor integration guide](https://docs.litellm.ai/docs/tutorials/cursor_integration).

> Cursor sends requests from its backend for cloud features. For remote access, expose the proxy with HTTPS or a tunnel — local `127.0.0.1` works for on-machine development only.

## 5. Cursor Cloud Agents (optional)

For the Cursor Cloud Agents API (`/v0/agents`), set `CURSOR_API_KEY` in `.env`. LiteLLM forwards `/cursor/*` to `api.cursor.com`. This is **not** used by `run_llm_e2e.py`; see [Cursor Cloud Agents pass-through](https://docs.litellm.ai/docs/pass_through/cursor).

## Configuration reference

| File | Purpose |
|------|---------|
| [`scripts/litellm/config.yaml`](../scripts/litellm/config.yaml) | Model aliases and upstream routing |
| [`scripts/litellm/env.example`](../scripts/litellm/env.example) | Environment template (copy to `.env`) |
| [`scripts/litellm/start.sh`](../scripts/litellm/start.sh) | Start proxy (uv or `--docker`) |
| [`scripts/litellm/use-provider.sh`](../scripts/litellm/use-provider.sh) | `source` to set `OPENAI_*` for a provider |
| [`scripts/litellm/run-e2e.sh`](../scripts/litellm/run-e2e.sh) | One-shot E2E through LiteLLM |
| [`scripts/litellm/healthcheck.sh`](../scripts/litellm/healthcheck.sh) | Proxy liveness + model list |

### Model aliases (`config.yaml`)

| Alias | Upstream | Required env |
|-------|----------|--------------|
| `ontographia-openai` | `openai/gpt-4o-mini` | `OPENAI_API_KEY` |
| `ontographia-gemini` | `gemini/${GEMINI_MODEL}` (default `gemini-3.7-flash`) | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| `ontographia-cursor` | `anthropic/claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| `litellm-claude-sonnet` | same Anthropic model | `ANTHROPIC_API_KEY` (for Cursor IDE custom model name) |

Edit `config.yaml` to change models or add aliases. Restart the proxy after changes.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Connection refused` on port 4000 | Start `./scripts/litellm/start.sh` first |
| `401` from proxy | `OPENAI_API_KEY` in E2E must match `LITELLM_MASTER_KEY` |
| `no healthy deployments` / model error | Provider API key missing in `.env` for that alias |
| Gemini / Anthropic errors | Confirm key is set; check LiteLLM logs in Terminal A |
| Cursor IDE model collision | Use `litellm-claude-sonnet`, not built-in model names |
| Older local model rejects `json_schema` | Add `--no-json-schema` to `run_llm_e2e.py` |

## See also

- [end-to-end-neo4j.md §7](end-to-end-neo4j.md#7-local-llm-e2e-not-run-in-ci) — generic LLM E2E without LiteLLM
- [skills/ontographia-cypher-builder/SKILL.md](../skills/ontographia-cypher-builder/SKILL.md) — Intent JSON rules for agents
