"""Shim — use ``ontographia.llm.extractors``."""

from ontographia.llm.extractors import *  # noqa: F403
from ontographia.llm.extractors import (  # noqa: F401
    IntentExtractor,
    IntentExtractorClient,
    MockIntentExtractor,
    create_extractor,
)
