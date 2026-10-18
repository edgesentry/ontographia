"""Neo4j READ access mode / execute_read wiring (mocked driver)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ontographia.mcp.execute import Neo4jDriverRunner
from ontographia.mcp.safety import WriteQueryRejected


def test_driver_session_uses_read_access_and_execute_read() -> None:
    """Layer 2: session opened with READ_ACCESS and execute_read."""
    from neo4j import READ_ACCESS

    fake_driver = MagicMock()
    fake_session = MagicMock()
    fake_driver.session.return_value.__enter__.return_value = fake_session
    fake_session.execute_read.side_effect = lambda fn: fn(MagicMock())

    with patch("ontographia.mcp.execute.GraphDatabase") as gd:
        gd.driver.return_value = fake_driver
        runner = Neo4jDriverRunner("bolt://localhost:7687", "neo4j", "secret")

        # Make tx.run return no records.
        def _run_work(tx: Any) -> list[dict[str, Any]]:
            # The real run_read defines _work; we let execute_read invoke it.
            return []

        # Replace execute_read to capture and invoke the work function.
        captured: dict[str, Any] = {}

        def _execute_read(work):
            captured["work"] = work
            tx = MagicMock()
            tx.run.return_value = iter([])
            return work(tx)

        fake_session.execute_read.side_effect = _execute_read

        rows = runner.run_read(
            "MATCH (n) RETURN n LIMIT 1",
            {},
            database="neo4j",
            row_limit=10,
        )
        assert rows == []
        fake_driver.session.assert_called_once()
        kwargs = fake_driver.session.call_args.kwargs
        assert kwargs["default_access_mode"] == READ_ACCESS
        assert kwargs["database"] == "neo4j"
        assert "work" in captured
        runner.close()
        fake_driver.close.assert_called_once()


def test_driver_runner_rejects_write_before_session() -> None:
    """Layer 3 before layer 2: write Cypher never opens a useful session run."""
    fake_driver = MagicMock()
    with patch("ontographia.mcp.execute.GraphDatabase") as gd:
        gd.driver.return_value = fake_driver
        runner = Neo4jDriverRunner("bolt://localhost:7687", "neo4j", "secret")
        with pytest.raises(WriteQueryRejected):
            runner.run_read(
                "CREATE (n:X) RETURN n",
                {},
                database=None,
                row_limit=10,
            )
        fake_driver.session.assert_not_called()
