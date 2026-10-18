"""Experimental Intent layer for Ontographia (``pip install "ontographia[llm]"``).

Stability: **0.x / experimental**. Public names listed in ``__all__`` may gain
additive APIs; breaking changes will be called out in release notes.

Requires the optional ``llm`` extra (``openai`` + ``pyyaml``). Importing this
package without that extra raises :class:`ImportError` with install guidance.

A future optional ``ontographia[litellm]`` extra may wrap LiteLLM as an
:class:`~ontographia.llm.backend.LLMBackend`; it is not implemented yet —
use any OpenAI-compatible endpoint via :class:`OpenAICompatibleBackend`.
"""

from __future__ import annotations

try:
    import openai as _openai  # noqa: F401
except ImportError as _exc:  # pragma: no cover - exercised without the extra
    raise ImportError(
        'ontographia.llm requires the optional "llm" extra. '
        'Install with: pip install "ontographia[llm]"'
    ) from _exc

try:
    import yaml as _yaml  # noqa: F401
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        'ontographia.llm requires the optional "llm" extra (pyyaml). '
        'Install with: pip install "ontographia[llm]"'
    ) from _exc

from ontographia.llm.backend import LLMBackend, OpenAICompatibleBackend
from ontographia.llm.exec_feedback import (
    ExecutionAssessment,
    assess_execution,
    build_execution_correction_message,
    format_execution_feedback,
)
from ontographia.llm.extractors import (
    IntentExtractor,
    IntentExtractorClient,
    MockIntentExtractor,
    create_extractor,
)
from ontographia.llm.fixtures import MOCK_LLM_INTENTS
from ontographia.llm.mapping_loader import (
    DEFAULT_MAPPING_PATH,
    MAPPINGS_DIR,
    default_manufacturing_mapping,
    load_repair_mapping,
)
from ontographia.llm.pipeline import (
    DEFAULT_ESCALATED_RETRIES,
    DEFAULT_INITIAL_RETRIES,
    DEFAULT_MAX_EXEC_REFINES,
    DEFAULT_MAX_RETRIES,
    ExtractOutcome,
    SchemaPolicy,
    extract_validated_intent,
    refine_intent_after_execution,
)
from ontographia.llm.prompt import (
    SYSTEM_PROMPT,
    build_correction_message,
    build_initial_user_message,
)
from ontographia.llm.repair import repair_intent
from ontographia.llm.semantic_validate import semantic_validate_intent
from ontographia.llm.subset import (
    OntologySubset,
    filter_intent_schema,
    prompt_views_for_question,
    subset_ontology,
    tokenize_question,
)

__all__ = [
    # Backend
    "LLMBackend",
    "OpenAICompatibleBackend",
    # Extractors
    "IntentExtractor",
    "IntentExtractorClient",
    "MockIntentExtractor",
    "create_extractor",
    "MOCK_LLM_INTENTS",
    # Pipeline
    "ExtractOutcome",
    "SchemaPolicy",
    "extract_validated_intent",
    "refine_intent_after_execution",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_INITIAL_RETRIES",
    "DEFAULT_ESCALATED_RETRIES",
    "DEFAULT_MAX_EXEC_REFINES",
    # Subset
    "OntologySubset",
    "tokenize_question",
    "subset_ontology",
    "filter_intent_schema",
    "prompt_views_for_question",
    # Exec feedback
    "ExecutionAssessment",
    "assess_execution",
    "format_execution_feedback",
    "build_execution_correction_message",
    # Repair / validate
    "repair_intent",
    "semantic_validate_intent",
    "load_repair_mapping",
    "default_manufacturing_mapping",
    "MAPPINGS_DIR",
    "DEFAULT_MAPPING_PATH",
    # Prompt helpers
    "SYSTEM_PROMPT",
    "build_initial_user_message",
    "build_correction_message",
]
