"""Execute rejects variable-length hop ranges before Neo4j (and before build)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ontographia.mcp.read_only import HopRangeRejected, assert_execute_hop_policy, execute_read_only
from tests.python.mcp.conftest import SAMPLE_INTENT


def _step(**hops: object) -> dict[str, Any]:
    step: dict[str, Any] = {
        "relationship": "has_part",
        "direction": "out",
        "to": {"class": "Part", "alias": "part"},
    }
    step.update(hops)
    return step


def _intent(*steps: dict[str, Any]) -> dict[str, Any]:
    intent = {
        "start": {"class": "Product", "alias": "product"},
        "traverse": list(steps),
        "return": [{"alias": "part" if steps else "product"}],
    }
    return intent


class _Runner:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run_read(self, query: str, params: dict[str, Any], *, database: str | None, row_limit: int):
        self.calls.append(
            {"query": query, "params": params, "database": database, "row_limit": row_limit}
        )
        return []


def _execute(intent: dict[str, Any] | str, *, build: Any | None = None) -> tuple[dict[str, Any], _Runner, dict[str, Any]]:
    state = {"called": False, "intent": None}

    def build_cypher(bounded: dict[str, Any], dialect: str | None = None) -> dict[str, Any]:
        state["called"] = True
        state["intent"] = bounded
        if build is not None:
            return build(bounded, dialect)
        return {
            "ok": True,
            "query": "CYPHER 25\nMATCH (product:Product)-[:has_part]->(part:Part)\nRETURN part\nLIMIT 1",
            "params": {},
            "dialect": dialect or "cypher25",
        }

    runner = _Runner()
    result = execute_read_only(
        build_cypher=build_cypher,
        runner=runner,
        intent=intent,
        dialect="cypher25",
        database="neo4j",
        row_limit=1,
        configured_limit=50,
    )
    return result, runner, state


def _not_exists_intent(*entries: Any) -> dict[str, Any]:
    return {
        "start": {"class": "Product", "alias": "product"},
        "not_exists": list(entries),
        "return": [{"alias": "product"}],
    }


def _sub_pattern(*steps: dict[str, Any], start: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "start": start or {"class": "Part", "alias": "part"},
        "traverse": list(steps),
    }


def test_policy_allows_omitted_and_exact_one_hop() -> None:
    assert_execute_hop_policy(_intent(_step()))
    assert_execute_hop_policy(_intent(_step(min_hops=1, max_hops=1)))
    assert_execute_hop_policy(_intent(_step(min_hops=None, max_hops=None)))


def test_policy_rejects_wide_not_exists_step_and_names_its_location() -> None:
    intent = _not_exists_intent(_sub_pattern(_step(min_hops=1, max_hops=5)))
    with pytest.raises(HopRangeRejected) as excinfo:
        assert_execute_hop_policy(intent)
    message = str(excinfo.value)
    assert message.startswith(
        "not_exists[0] traverse step 0 hop range 1..5 is not allowed on execute."
    )
    assert "single hop" in message


def test_policy_rejects_one_sided_not_exists_step_bound() -> None:
    intent = _not_exists_intent(_sub_pattern(_step(max_hops=2)))
    with pytest.raises(HopRangeRejected, match="not_exists\\[0\\] traverse step 0"):
        assert_execute_hop_policy(intent)


def test_policy_reports_not_exists_entry_index() -> None:
    intent = _not_exists_intent(
        _sub_pattern(_step(min_hops=1, max_hops=1)),
        _sub_pattern(
            _step(min_hops=1, max_hops=3),
            start={"class": "Supplier", "alias": "supplier"},
        ),
    )
    with pytest.raises(HopRangeRejected, match="^not_exists\\[1\\] traverse step 0"):
        assert_execute_hop_policy(intent)


def test_policy_allows_single_hop_not_exists_steps() -> None:
    intent = _not_exists_intent(
        _sub_pattern(
            _step(min_hops=1, max_hops=1),
            _step(),
            _step(min_hops=None, max_hops=None),
        )
    )
    assert_execute_hop_policy(intent)


def test_policy_skips_malformed_not_exists_entries_and_steps() -> None:
    intent = _not_exists_intent(
        "not-an-object",
        {"start": {"class": "Part", "alias": "part"}, "traverse": "not-a-list"},
        {"start": {"class": "Part", "alias": "part"}, "traverse": [None, 7]},
    )
    assert_execute_hop_policy(intent)


@pytest.mark.parametrize(
    "hops",
    [
        {"min_hops": 1, "max_hops": 4},
        {"min_hops": 1, "max_hops": 2**32 - 1},
        {"min_hops": 0, "max_hops": 1},
        {"min_hops": 2, "max_hops": 2},
        {"min_hops": 1, "max_hops": 0},
        {"max_hops": 4},
        {"min_hops": 1},
        {"min_hops": True, "max_hops": True},
        {"min_hops": 1.0, "max_hops": 1.0},
    ],
)
def test_policy_rejects_ranges_other_than_one_hop(hops: dict[str, object]) -> None:
    with pytest.raises(HopRangeRejected, match="single hop"):
        assert_execute_hop_policy(_intent(_step(**hops)))


def test_execute_rejects_wide_range_before_build_and_driver() -> None:
    result, runner, state = _execute(_intent(_step(min_hops=1, max_hops=4)))
    assert result["ok"] is False
    assert result["errors"][0]["code"] == "hop_range_rejected"
    assert "hop range 1..4" in result["errors"][0]["message"]
    assert state["called"] is False
    assert runner.calls == []


def test_execute_rejects_u32_max_from_json_string() -> None:
    payload = _intent(_step(min_hops=1, max_hops=2**32 - 1))
    result, runner, state = _execute(json.dumps(payload))
    assert result["ok"] is False
    assert result["errors"][0]["code"] == "hop_range_rejected"
    assert state["called"] is False
    assert runner.calls == []


def test_execute_rejects_when_any_step_is_wider_than_one() -> None:
    intent = _intent(_step(min_hops=1, max_hops=1), _step(min_hops=1, max_hops=3))
    intent["return"] = [{"alias": "part"}]
    result, runner, state = _execute(intent)
    assert result["ok"] is False
    assert result["errors"][0]["code"] == "hop_range_rejected"
    assert state["called"] is False
    assert runner.calls == []


def test_execute_runs_exact_one_hop() -> None:
    result, runner, state = _execute(_intent(_step(min_hops=1, max_hops=1)))
    assert result["ok"] is True
    assert state["called"] is True
    assert len(runner.calls) == 1
    assert "*" not in runner.calls[0]["query"]


def test_execute_with_engine_blocks_not_exists_pattern_the_compiler_would_emit(mcp_tools) -> None:
    """A wide not_exists step must be rejected before build and driver."""
    wider_not_exists = {
        "start": {"class": "Product", "alias": "product"},
        "traverse": [
            {
                "relationship": "has_part",
                "direction": "out",
                "to": {"class": "Part", "alias": "part"},
            }
        ],
        "not_exists": [
            {
                "start": {"class": "Part", "alias": "part"},
                "traverse": [
                    {
                        "relationship": "has_sub_part",
                        "direction": "out",
                        "to": {"class": "Part", "alias": "sub"},
                        "min_hops": 1,
                        "max_hops": 4,
                    }
                ],
            }
        ],
        "return": [{"alias": "product", "property": "sku", "as_name": "sku"}],
    }
    built = mcp_tools.build_cypher(wider_not_exists)
    assert built["ok"] is True
    assert "*1..4" in built["query"]

    result = mcp_tools.execute(wider_not_exists)
    assert result["ok"] is False
    assert result["errors"][0]["code"] == "hop_range_rejected"
    assert "not_exists[0] traverse step 0" in result["errors"][0]["message"]
    assert mcp_tools._fake_runner.calls == []

    exact_not_exists = {
        **wider_not_exists,
        "not_exists": [
            {
                **wider_not_exists["not_exists"][0],
                "traverse": [
                    {
                        **wider_not_exists["not_exists"][0]["traverse"][0],
                        "min_hops": 1,
                        "max_hops": 1,
                    }
                ],
            }
        ],
    }
    ran = mcp_tools.execute(exact_not_exists)
    assert ran["ok"] is True
    assert "*1.." not in ran["query"]
    assert len(mcp_tools._fake_runner.calls) == 1


def test_execute_with_engine_blocks_pattern_the_compiler_would_emit(mcp_tools) -> None:
    """The Cypher emitter still prints ``*min..max``; execute must not run it."""
    wide = {
        **SAMPLE_INTENT,
        "traverse": [
            {**SAMPLE_INTENT["traverse"][0], "min_hops": 1, "max_hops": 4},
            SAMPLE_INTENT["traverse"][1],
        ],
    }
    built = mcp_tools.build_cypher(wide)
    assert built["ok"] is True
    assert "*1..4" in built["query"]

    result = mcp_tools.execute(wide)
    assert result["ok"] is False
    assert result["errors"][0]["code"] == "hop_range_rejected"
    assert mcp_tools._fake_runner.calls == []

    exact = {
        **SAMPLE_INTENT,
        "traverse": [
            {**SAMPLE_INTENT["traverse"][0], "min_hops": 1, "max_hops": 1},
            SAMPLE_INTENT["traverse"][1],
        ],
    }
    ran = mcp_tools.execute(exact)
    assert ran["ok"] is True
    assert "*1.." not in ran["query"]
    assert len(mcp_tools._fake_runner.calls) == 1
