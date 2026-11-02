"""Gold Intent field-match scoring for the Track A gold set (issue #96, step 1).

Offline and deterministic: no live LLM, no Neo4j. Scores two arms over the 40
Track A gold Intents (``examples/llm/eval/gold.py``):

- ``gold_self``:    gold vs gold — scorer self-check, expect exact match everywhere.
- ``silent_wrong``: near-duplicate distractor variant vs gold — expect degraded
                    ``filters``/``projections`` while ``entities``/``relations``
                    stay at 1.0 (validation cannot see semantic wrongness).

Usage (from repo root):
  uv run python examples/llm/eval/run_gold_field_match.py
  uv run python examples/llm/eval/run_gold_field_match.py --arms gold_self --json-out examples/llm/eval/out/field_match.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(EXAMPLES))

from llm.eval.field_match import aggregate_scores, intent_field_match  # noqa: E402
from llm.eval.gold import build_gold_cases, make_silent_wrong_intent  # noqa: E402

ARMS = ("gold_self", "silent_wrong")


def _git_rev() -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=ROOT,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            or None
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def _round_scores(score: dict[str, Any]) -> dict[str, Any]:
    return {
        **score,
        "fields": {
            k: {m: round(v, 4) for m, v in field.items()}
            for k, field in score["fields"].items()
        },
        "field_f1": {k: round(v, 4) for k, v in score["field_f1"].items()},
        "macro_f1": round(score["macro_f1"], 4),
    }


def _round_aggregate(agg: dict[str, Any]) -> dict[str, Any]:
    return {
        **agg,
        "exact_match_rate": round(agg["exact_match_rate"], 4),
        "macro_f1_mean": round(agg["macro_f1_mean"], 4),
        "field_f1_mean": {k: round(v, 4) for k, v in agg["field_f1_mean"].items()},
    }


def run_arm(arm: str) -> dict[str, Any]:
    cases = build_gold_cases()
    items: list[dict[str, Any]] = []
    skipped: list[str] = []
    for case in cases:
        if arm == "gold_self":
            pred = case.intent
        else:
            pred = make_silent_wrong_intent(case.intent, case.corrupt_target) if case.corrupt_target else None
            if pred is None:
                skipped.append(case.id)
                continue
        score = intent_field_match(pred, case.intent)
        items.append({"id": case.id, "score": _round_scores(score)})

    return {
        "arm": arm,
        "aggregate": _round_aggregate(aggregate_scores(items)),
        "skipped": skipped,
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gold Intent field-match scoring over the Track A gold set (issue #96 step 1)"
    )
    parser.add_argument(
        "--arms",
        default=",".join(ARMS),
        help=f"Comma-separated subset of: {','.join(ARMS)}",
    )
    parser.add_argument(
        "--per-item",
        action="store_true",
        help="Include per-item scores (default: aggregate only; pass --per-item for full detail)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Also write the full JSON payload to this path",
    )
    args = parser.parse_args()
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = set(arms) - set(ARMS)
    if unknown:
        print(f"unknown arms: {sorted(unknown)} (choose from {ARMS})", file=sys.stderr)
        return 2

    results = [run_arm(arm) for arm in arms]
    if not args.per_item:
        for r in results:
            del r["items"]
    payload = {
        "meta": {
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_rev": _git_rev(),
            "harness": "examples/llm/eval/run_gold_field_match.py",
            "issue": "https://github.com/edgesentry/ontographia/issues/96 (step 1)",
            "scorer": "examples/llm/eval/field_match.py",
            "n_gold": len(build_gold_cases()),
        },
        "results": results,
    }
    text = json.dumps(payload, indent=2) + "\n"
    print(text, end="")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
        print(f"wrote {args.json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
