"""Shim — use ``ontographia.llm.mapping_loader``.

Example YAML copies under ``examples/llm/mappings/`` remain for demos; the
wheel ships the same defaults from ``ontographia.llm.mappings``.
"""

from ontographia.llm.mapping_loader import *  # noqa: F403
from ontographia.llm.mapping_loader import (  # noqa: F401
    DEFAULT_MAPPING_PATH,
    MAPPINGS_DIR,
    default_manufacturing_mapping,
    load_repair_mapping,
)
