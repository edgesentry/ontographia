"""Shim — use ``ontographia.llm.prompt``."""

from ontographia.llm.prompt import *  # noqa: F403
from ontographia.llm.prompt import (  # noqa: F401
    SYSTEM_PROMPT,
    build_correction_message,
    build_initial_user_message,
    example_label,
    pick_example_intent,
    properties_from_ontology,
    vocabulary_from_schema,
)
