"""Thin demos / eval harnesses on top of ``ontographia.llm``.

Prefer ``from ontographia.llm import ...`` in application code.
Install: ``pip install "ontographia[llm]"``.

Docs: https://edgesentry.github.io/ontographia/llm/
"""

from ontographia.llm import (  # noqa: F401
    MOCK_LLM_INTENTS,
    IntentExtractor,
    create_extractor,
)

__all__ = ["IntentExtractor", "MOCK_LLM_INTENTS", "create_extractor"]
