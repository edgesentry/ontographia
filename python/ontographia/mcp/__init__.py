"""Experimental MCP server for Ontographia (``pip install "ontographia[mcp]"``).

Stability: **0.x / experimental**. Exposes ontology-backed tools so MCP clients
can obtain Intent schemas, build validated Cypher 25, and optionally execute
read-only queries. The server never accepts raw Cypher from the client and
never calls an LLM.

Requires the optional ``mcp`` extra (``mcp`` + ``neo4j``). Importing this
package without that extra raises :class:`ImportError` with install guidance.
"""

from __future__ import annotations

try:
    import mcp as _mcp  # noqa: F401
except ImportError as _exc:  # pragma: no cover - exercised without the extra
    raise ImportError(
        'ontographia.mcp requires the optional "mcp" extra. '
        'Install with: pip install "ontographia[mcp]"'
    ) from _exc

try:
    import neo4j as _neo4j  # noqa: F401
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        'ontographia.mcp requires the optional "mcp" extra (neo4j). '
        'Install with: pip install "ontographia[mcp]"'
    ) from _exc

from ontographia.mcp.config import McpConfig, load_config_from_env
from ontographia.mcp.safety import WriteQueryRejected, assert_read_only_cypher
from ontographia.mcp.server import OntographiaMcp, create_mcp_server

__all__ = [
    "McpConfig",
    "OntographiaMcp",
    "WriteQueryRejected",
    "assert_read_only_cypher",
    "create_mcp_server",
    "load_config_from_env",
]
