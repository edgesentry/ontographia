"""Shim — use ``ontographia.llm.subset``."""

from ontographia.llm.subset import *  # noqa: F403
from ontographia.llm.subset import (  # noqa: F401
    OntologySubset,
    exact_name_matches,
    filter_intent_schema,
    prompt_views_for_question,
    subset_ontology,
    tokenize_question,
)
