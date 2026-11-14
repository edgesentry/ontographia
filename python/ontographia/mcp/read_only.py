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

# Read-only execution submits only a single relationship hop. A variable-length
# quantifier (``*min..max``) is not capped by the row limit. Omitted bounds and
# exactly 1..1 both compile to one hop; every other pair is rejected.
EXECUTE_HOP_MIN = 1
EXECUTE_HOP_MAX = 1


class HopRangeRejected(ValueError):
    """Raised when execute Intent asks for anything other than a single hop."""


def assert_execute_hop_policy(intent: dict[str, Any]) -> None:
    """Reject hop ranges that read-only execute will not submit to Neo4j.

    Allowed on each traverse step:

    * ``min_hops`` and ``max_hops`` both omitted or null
    * both exactly the integer ``1``

    Rejected: one side set, ``0``, ``min != max``, ``max > 1``, booleans, and
    non-integers. The same rule applies to every step of every
    ``not_exists[i].traverse`` entry. ``build_cypher`` may still emit
    variable-length patterns for offline inspection; this policy applies only
    when a query would be run.
    """
    _assert_traverse_hop_policy(intent.get("traverse"), "")
    not_exists = intent.get("not_exists")
    if not isinstance(not_exists, list):
        return
    for entry_index, entry in enumerate(not_exists):
        if not isinstance(entry, dict):
            continue
        _assert_traverse_hop_policy(entry.get("traverse"), f"not_exists[{entry_index}] ")


def _assert_traverse_hop_policy(traverse: Any, location: str) -> None:
    """Apply the single-hop rule to one traverse list; ``location`` names it."""
    if not isinstance(traverse, list):
        return
    for index, step in enumerate(traverse):
        if not isinstance(step, dict):
            continue
        min_hops = step.get("min_hops")
        max_hops = step.get("max_hops")
        if min_hops is None and max_hops is None:
            continue
        if (
            type(min_hops) is int
            and type(max_hops) is int
            and min_hops == EXECUTE_HOP_MIN
            and max_hops == EXECUTE_HOP_MAX
        ):
            continue
        raise HopRangeRejected(
            f"{location}traverse step {index} hop range {min_hops!r}..{max_hops!r} is not "
            "allowed on execute. Only a single hop may be submitted to Neo4j: omit min_hops and "
            "max_hops, or set both to 1. Variable-length patterns are not executed "
            "(use build_cypher to inspect them offline)."
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
        assert_execute_hop_policy(bounded_intent)
    except HopRangeRejected as exc:
        return {
            "ok": False,
            "errors": [{"message": str(exc), "code": "hop_range_rejected"}],
        }
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
