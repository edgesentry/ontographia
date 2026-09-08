"""Neo4j execution feedback for Intent-level refinement (issue #46).

Judges empty results / driver errors and formats correction prompts.
Never asks the model to edit Cypher — only Intent JSON, then recompile.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionAssessment:
    """Outcome of running a compiled query against Neo4j."""

    ok: bool
    reason: str
    row_count: int = 0
    error: str | None = None
    sample_rows: list[dict[str, Any]] | None = None

    @property
    def needs_refine(self) -> bool:
        return not self.ok


def assess_execution(
    *,
    rows: list[dict[str, Any]] | None = None,
    error: BaseException | str | None = None,
    sample_limit: int = 3,
) -> ExecutionAssessment:
    """Decide whether execution feedback should trigger Intent correction.

    Triggers refine on:
    - driver / runtime errors
    - empty result sets (compiled OK but no rows)
    """
    if error is not None:
        msg = str(error).strip() or error.__class__.__name__
        return ExecutionAssessment(
            ok=False,
            reason="neo4j_error",
            row_count=0,
            error=msg,
        )

    assert rows is not None
    n = len(rows)
    if n == 0:
        return ExecutionAssessment(
            ok=False,
            reason="empty_result",
            row_count=0,
            sample_rows=[],
        )

    sample = rows[:sample_limit]
    return ExecutionAssessment(
        ok=True,
        reason="ok",
        row_count=n,
        sample_rows=sample,
    )


def format_execution_feedback(
    assessment: ExecutionAssessment,
    *,
    user_question: str,
) -> str:
    """Short feedback string for ``extract_correction`` (not Cypher)."""
    parts = [
        "Neo4j execution feedback (fix the Intent JSON, not Cypher).",
        f"User question: {user_question}",
        f"Outcome: {assessment.reason}",
    ]
    if assessment.error:
        parts.append(f"Driver/error: {assessment.error}")
    if assessment.reason == "empty_result":
        parts.append(
            "The compiled query returned 0 rows. Likely causes: wrong filter "
            "value, missing traverse, or wrong class/relationship. Adjust the "
            "Intent so it matches the question and ontology vocabulary."
        )
    parts.append(
        "Return corrected Intent JSON only. Do not output Cypher."
    )
    return "\n".join(parts)


def build_execution_correction_message(
    user_question: str,
    previous_intent: dict[str, Any],
    assessment: ExecutionAssessment,
) -> str:
    """User message for an execution-driven Intent correction turn."""
    feedback = format_execution_feedback(assessment, user_question=user_question)
    return (
        f"{feedback}\n\n"
        f"Previous Intent JSON:\n{json.dumps(previous_intent, indent=2)}\n\n"
        "Return a corrected Intent JSON only."
    )
