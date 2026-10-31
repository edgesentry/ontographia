"""Shared Intent → read-only Cypher execution used by MCP and the ``otg`` CLI.

No MCP SDK and no Neo4j driver import. The driver lives in
:mod:`ontographia.mcp.execute`; write detection lives in
:mod:`ontographia.mcp.safety`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ontographia.mcp.safety import WriteQueryRejected, assert_read_only_cypher

NEO4J_NOT_CONFIGURED = (
    "Neo4j is not configured. Set NEO4J_URI, "
    "NEO4J_USERNAME (or NEO4J_USER), and NEO4J_PASSWORD "
    "(optional NEO4J_DATABASE), or pass matching CLI flags."
)


def parse_intent(intent: dict[str, Any] | str) -> dict[str, Any]:
    """Accept an Intent object or a JSON object string."""
    if isinstance(intent, str):
        try:
            parsed = json.loads(intent)
        except json.JSONDecodeError as exc:
            raise ValueError(f"intent must be a JSON object string: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("intent JSON must be an object")
        return parsed
    if not isinstance(intent, dict):
        raise ValueError("intent must be a JSON object (dict) or JSON object string")
    return intent


def clamp_row_limit(row_limit: int | None, configured: int) -> int:
    """Client-supplied limit cannot exceed the configured maximum."""
    requested = configured if row_limit is None else int(row_limit)
    if requested < 0:
        requested = 0
    return min(requested, configured)


def intent_with_server_limit(
    intent: dict[str, Any] | str,
    *,
    server_limit: int,
) -> dict[str, Any]:
    """Ensure emitted Cypher carries a LIMIT ≤ ``server_limit``.

    An Intent without ``limit`` must not become an unbounded Neo4j fetch that
    is only truncated client-side.
    """
    intent_obj = dict(parse_intent(intent))
    intent_limit = intent_obj.get("limit")
    if intent_limit is None:
        cypher_limit = server_limit
    else:
        try:
            cypher_limit = min(int(intent_limit), server_limit)
        except (TypeError, ValueError):
            cypher_limit = server_limit
    intent_obj["limit"] = cypher_limit
    return intent_obj


def build_read_only(
    engine: Any,
    intent: dict[str, Any] | str,
    *,
    dialect: str,
) -> dict[str, Any]:
    """Validate Intent JSON and emit Cypher. Writes are flagged, not returned as ok.

    On success::

        {"ok": True, "query": "...", "params": {...}, "dialect": "cypher25"}

    On validation / emission / write-detection failure::

        {"ok": False, "errors": [{"message": "..."}]}
    """
    try:
        intent_obj = parse_intent(intent)
        result = engine.build(intent_obj, dialect=dialect)
        query = result["query"]
        params = dict(result["params"])
        try:
            assert_read_only_cypher(query)
        except WriteQueryRejected as exc:
            return {
                "ok": False,
                "errors": [{"message": str(exc), "code": "write_rejected"}],
                "query": query,
                "params": params,
            }
        return {
            "ok": True,
            "query": query,
            "params": params,
            "dialect": dialect,
        }
    except Exception as exc:
        return {"ok": False, "errors": [{"message": str(exc)}]}


def execute_read_only(
    *,
    build_cypher: Callable[..., dict[str, Any]],
    runner: Any | None,
    intent: dict[str, Any] | str,
    dialect: str | None,
    database: str | None,
    row_limit: int | None,
    configured_limit: int,
) -> dict[str, Any]:
    """Build Cypher from Intent and run it on ``runner`` (read-only).

    ``build_cypher`` is called so callers (and tests) can intercept generation.
    Only that function's Cypher is executed — never a client-supplied query.
    """
    if runner is None:
        return {
            "ok": False,
            "errors": [{"message": NEO4J_NOT_CONFIGURED, "code": "neo4j_not_configured"}],
        }

    limit = clamp_row_limit(row_limit, configured_limit)
    try:
        bounded_intent = intent_with_server_limit(intent, server_limit=limit)
    except ValueError as exc:
        return {"ok": False, "errors": [{"message": str(exc)}]}

    built = build_cypher(bounded_intent, dialect=dialect)
    if not built.get("ok"):
        return built

    query = built["query"]
    params = built["params"]
    try:
        assert_read_only_cypher(query)
        rows = runner.run_read(
            query,
            params,
            database=database,
            row_limit=limit,
        )
        return {
            "ok": True,
            "query": query,
            "params": params,
            "rows": rows,
            "row_count": len(rows),
            "row_limit": limit,
            "truncated": len(rows) >= limit,
        }
    except WriteQueryRejected as exc:
        return {
            "ok": False,
            "errors": [{"message": str(exc), "code": "write_rejected"}],
            "query": query,
            "params": params,
        }
    except Exception as exc:
        return {
            "ok": False,
            "errors": [{"message": str(exc), "code": "neo4j_error"}],
            "query": query,
            "params": params,
        }
