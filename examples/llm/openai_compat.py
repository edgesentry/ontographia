"""Shim — use ``ontographia.llm.backend.OpenAICompatibleBackend``.

Historical name kept so older scripts that imported ``OpenAICompatibleExtractor``
still resolve via :class:`~ontographia.llm.extractors.IntentExtractorClient`.
"""

from ontographia.llm.backend import OpenAICompatibleBackend
from ontographia.llm.extractors import IntentExtractorClient, create_extractor

# Back-compat alias: previous class combined transport + prompting.
OpenAICompatibleExtractor = IntentExtractorClient

__all__ = [
    "OpenAICompatibleBackend",
    "OpenAICompatibleExtractor",
    "IntentExtractorClient",
    "create_extractor",
]
