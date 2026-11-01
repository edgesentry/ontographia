"""Experimental MCP server for Ontographia (``pip install "ontographia[mcp]"``).

Stability: **0.x / experimental**. Exposes ontology-backed tools so MCP clients
can obtain Intent schemas, build validated Cypher 25, and optionally execute
read-only queries. The server never accepts raw Cypher from the client and
never calls an LLM.

Requiring the optional ``mcp`` extra happens when the server API is used
(``OntographiaMcp``, ``create_mcp_server``, or :mod:`ontographia.mcp.server`).
:mod:`ontographia.mcp.safety`, :mod:`ontographia.mcp.read_only`, and
:mod:`ontographia.mcp.execute` are shared with the ``otg`` CLI.
``execute`` needs the ``neo4j`` driver (``ontographia[cli]`` or ``ontographia[mcp]``).
"""

from __future__ import annotations

import importlib
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "McpConfig": ("ontographia.mcp.config", "McpConfig"),
    "load_config_from_env": ("ontographia.mcp.config", "load_config_from_env"),
    "WriteQueryRejected": ("ontographia.mcp.safety", "WriteQueryRejected"),
    "assert_read_only_cypher": ("ontographia.mcp.safety", "assert_read_only_cypher"),
    "OntographiaMcp": ("ontographia.mcp.server", "OntographiaMcp"),
    "create_mcp_server": ("ontographia.mcp.server", "create_mcp_server"),
}

_SERVER_NAMES = frozenset({"OntographiaMcp", "create_mcp_server"})


def _require_mcp_extra() -> None:
    try:
        import mcp as _mcp  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            'ontographia.mcp requires the optional "mcp" extra. '
            'Install with: pip install "ontographia[mcp]"'
        ) from exc
    try:
        import neo4j as _neo4j  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            'ontographia.mcp requires the optional "mcp" extra (neo4j). '
            'Install with: pip install "ontographia[mcp]"'
        ) from exc


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name in _SERVER_NAMES:
        _require_mcp_extra()
    module_name, attr = _EXPORTS[name]
    module = importlib.import_module(module_name)
    value = getattr(module, attr)
    globals()[name] = value
    return value


__all__ = list(_EXPORTS)
