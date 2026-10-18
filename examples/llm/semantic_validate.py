"""Shim — use ``ontographia.llm.semantic_validate``."""

from ontographia.llm.semantic_validate import *  # noqa: F403
from ontographia.llm.semantic_validate import (  # noqa: F401
    default_manufacturing_mapping,
    load_repair_mapping,
    semantic_validate_intent,
)
