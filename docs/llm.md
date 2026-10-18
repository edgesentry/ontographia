# Intent layer (`ontographia[llm]`)

**Status: experimental / 0.x.** The Intent extraction helpers live in the optional
Python extra `ontographia[llm]`. They are **not** part of the Rust core: Cypher
always comes from `Engine.build()` after Intent validation.

```bash
pip install "ontographia[llm]"
```

Importing `ontographia` without the extra still works. Importing `ontographia.llm`
without the extra raises `ImportError` with install guidance.

A future optional `ontographia[litellm]` extra may wrap LiteLLM as an
`LLMBackend`; it is **not implemented**. Point `OpenAICompatibleBackend` at any
OpenAI-compatible endpoint (including a local [LiteLLM proxy](litellm-local.md)).

## Public API (`ontographia.llm`)

| Name | Role |
|------|------|
| `LLMBackend` | `typing.Protocol` — `complete(messages, *, json_schema=None) -> str \| dict` |
| `OpenAICompatibleBackend` | Default backend via the official `openai` SDK (`base_url` + `api_key` + `model`) |
| `IntentExtractor` / `IntentExtractorClient` / `MockIntentExtractor` | Prompt + extract Intent JSON |
| `create_extractor` | Factory (`mock` / `openai` / custom `LLMBackend`) |
| `extract_validated_intent` | Subset / full-schema fallback + adaptive retries (#45 / #47) |
| `refine_intent_after_execution` | Execution feedback → Intent correction (#46; never edits Cypher) |
| `subset_ontology` / `prompt_views_for_question` | Exact-match ontology subset for prompts |
| `repair_intent` / `semantic_validate_intent` | Mapping-driven repair / checks |
| `assess_execution` / `format_execution_feedback` | Empty-result / driver-error feedback |

Defaults (unchanged from the former `examples/llm/` helpers):

- `schema_policy="auto"` — subset first; escalate to full on any extract/validate/repair failure
- `initial_retries=1`, `escalated_retries=5`
- `max_exec_refines=2` (triggers: `neo4j_error`, `empty_result`; always uses full schema for corrections)

Intent JSON is validated by the Rust core (`deny_unknown_fields`, ontology enums, …).
Structured LLM output prefers `response_format.json_schema` when the provider
supports it, with fallback to JSON mode / parse.

## Minimal examples

### OpenAI

```python
import ontographia
from ontographia.llm import OpenAICompatibleBackend, IntentExtractorClient, extract_validated_intent

engine = ontographia.Engine.load("examples/manufacturing.native.yaml")
backend = OpenAICompatibleBackend(api_key="sk-...", model="gpt-4o-mini")
extractor = IntentExtractorClient(backend)

outcome = extract_validated_intent(
    engine,
    extractor,
    "Which plant hosts production Line-1?",
    engine.intent_json_schema(),
    ontology=engine.ontology_json(),
)
print(outcome.result["query"])
```

### Local OpenAI-compatible server (Ollama / vLLM)

```python
from ontographia.llm import OpenAICompatibleBackend, IntentExtractorClient

backend = OpenAICompatibleBackend(
    api_key="ollama",  # many local servers ignore the key but require a non-empty value
    base_url="http://localhost:11434/v1",
    model="llama3.1",
)
extractor = IntentExtractorClient(backend)
```

Environment variables used by `create_extractor("openai")`:
`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`.

### Custom backend

Implement `LLMBackend.complete` (or pass any object with that method) to
`create_extractor(backend)` / `IntentExtractorClient(backend)`.

## Neo4j execution feedback

`refine_intent_after_execution` takes an `execute_fn` callback — the **neo4j**
driver is not part of `ontographia[llm]`. Install `neo4j` separately when you
want live execution (see [Neo4j walkthrough](end-to-end-neo4j.md)).

## Examples & evaluation

| Path | Role |
|------|------|
| [`examples/run_llm_e2e.py`](https://github.com/edgesentry/ontographia/blob/main/examples/run_llm_e2e.py) | CLI on top of `ontographia.llm` |
| [`examples/llm/eval/`](https://github.com/edgesentry/ontographia/tree/main/examples/llm/eval) | Eval harnesses (import the packaged module) |
| [`tests/python/llm/`](https://github.com/edgesentry/ontographia/tree/main/tests/python/llm) | CI unit tests with fake backends |

## Related

- [Architecture — outside the core](architecture.md#what-is-intentionally-outside-the-core)
- [Evaluation](evaluation.md)
- [LiteLLM (local)](litellm-local.md)
