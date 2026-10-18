# Intent layer examples

The Intent extraction pipeline (subset / fallback / refine / adaptive spend) lives
in the optional Python extra:

```bash
pip install "ontographia[llm]"
```

Public API: [docs/llm.md](../../docs/llm.md) · package `ontographia.llm`.

This directory keeps:

| Path | Role |
|------|------|
| `../run_llm_e2e.py` | CLI demo (mock or OpenAI-compatible) |
| `eval/` | Evaluation harnesses (import `ontographia.llm`) |

Repair mapping YAML defaults ship inside the wheel (`ontographia.llm.mappings`).
