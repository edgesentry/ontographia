"""Gold Intent field-match scoring for the Track A gold set (issue #96, steps 1-2).

Offline and deterministic: no live LLM, no Neo4j. Scores arms over the 40
Track A gold Intents (``examples/llm/eval/gold.py``), optionally restricted to
a frozen split partition (``examples/llm/eval/splits.py``, step 2):

- ``gold_self``:    gold vs gold — scorer self-check, expect exact match everywhere.
- ``silent_wrong``: near-duplicate distractor variant vs gold — expect degraded
                    ``filters``/``projections`` while ``entities``/``relations``
                    stay at 1.0 (validation cannot see semantic wrongness).
- ``predictions``:  externally produced Intents (JSONL: ``{"id", "intent"}``)
                    vs gold — the arm real LLM pipelines plug into.

JSON score shape (step 2): top-level ``schema_version``, ``git_rev``,
``split`` (id / version / gold hash, when ``--split`` is given), optional
``model`` / ``provider``; each entry under ``results`` carries ``arm``,
``partition``, ``aggregate``, per-fold aggregates for ``--partition cv``,
and per-item scores only with ``--per-item``.

Usage (from repo root):
  uv run python examples/llm/eval/run_gold_field_match.py
  uv run python examples/llm/eval/run_gold_field_match.py --split track_a_v1 --partition test
  uv run python examples/llm/eval/run_gold_field_match.py \
      --arms predictions --predictions preds.jsonl --split track_a_v1 --partition fold:0
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
EVAL_DIR = Path(__file__).resolve().parent
BASELINES_DIR = EVAL_DIR / "baselines"
sys.path.insert(0, str(EXAMPLES))

from llm.eval import splits as splits_mod  # noqa: E402
from llm.eval.field_match import aggregate_scores, intent_field_match  # noqa: E402
from llm.eval.gold import GoldCase, build_gold_cases, make_silent_wrong_intent  # noqa: E402

ARMS = ("gold_self", "silent_wrong", "predictions")
SCHEMA_VERSION = "2.0"


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


def load_predictions(path: Path) -> dict[str, dict[str, Any]]:
    """JSONL of ``{"id": <case id>, "intent": <predicted Intent>}``."""
    preds: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "id" not in row or "intent" not in row:
                raise ValueError(f"{path}:{lineno}: expected keys 'id' and 'intent'")
            preds[str(row["id"])] = row["intent"]
    return preds


def _select_cases(
    split: dict[str, Any] | None, partition: str
) -> list[GoldCase]:
    cases = build_gold_cases()
    if split is None:
        return cases
    wanted = set(splits_mod.partition_ids(split, partition))
    return [c for c in cases if c.id in wanted]


def _predict(
    arm: str, case: GoldCase, predictions: dict[str, dict[str, Any]] | None
) -> dict[str, Any] | None:
    if arm == "gold_self":
        return case.intent
    if arm == "silent_wrong":
        if not case.corrupt_target:
            return None
        return make_silent_wrong_intent(case.intent, case.corrupt_target)
    # predictions
    assert predictions is not None
    return predictions.get(case.id)


def score_cases(
    arm: str,
    cases: list[GoldCase],
    predictions: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    skipped: list[str] = []
    for case in cases:
        pred = _predict(arm, case, predictions)
        if pred is None:
            skipped.append(case.id)
            continue
        score = intent_field_match(pred, case.intent)
        items.append({"id": case.id, "score": _round_scores(score)})
    return {
        "aggregate": _round_aggregate(aggregate_scores(items)),
        "skipped": skipped,
        "items": items,
    }


def run_arm(
    arm: str,
    split: dict[str, Any] | None,
    partition: str,
    predictions: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """Score one arm over one partition; ``cv`` adds per-fold aggregates."""
    if partition == "cv":
        if split is None:
            raise ValueError("--partition cv requires --split")
        fold_results = []
        all_items: list[dict[str, Any]] = []
        all_skipped: list[str] = []
        for entry in split["partitions"]["folds"]:
            fold = entry["fold"]
            scored = score_cases(arm, _select_cases(split, f"fold:{fold}"), predictions)
            fold_results.append(
                {"fold": fold, "ids": entry["ids"], "aggregate": scored["aggregate"]}
            )
            all_items.extend(scored["items"])
            all_skipped.extend(scored["skipped"])
        return {
            "arm": arm,
            "partition": partition,
            "aggregate": _round_aggregate(aggregate_scores(all_items)),
            "folds": fold_results,
            "skipped": sorted(all_skipped),
            "items": all_items,
        }

    scored = score_cases(arm, _select_cases(split, partition), predictions)
    return {
        "arm": arm,
        "partition": partition,
        "aggregate": scored["aggregate"],
        "skipped": scored["skipped"],
        "items": scored["items"],
    }


def _record_path(split_id: str | None, partition: str) -> Path:
    if split_id is None:
        return BASELINES_DIR / "field_match.json"
    safe_partition = partition.replace(":", "_")
    return BASELINES_DIR / f"field_match_{split_id}_{safe_partition}.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gold Intent field-match scoring over the Track A gold set (issue #96 steps 1-2)"
    )
    parser.add_argument(
        "--arms",
        default="gold_self,silent_wrong",
        help=f"Comma-separated subset of: {','.join(ARMS)} (default: gold_self,silent_wrong)",
    )
    parser.add_argument(
        "--split",
        default=None,
        metavar="SPLIT_ID",
        help="Frozen split id from examples/llm/eval/splits/ (e.g. track_a_v1). "
        "The gold hash is verified before scoring; a mismatch fails the run.",
    )
    parser.add_argument(
        "--partition",
        default="all",
        help="all | dev | test | cv | fold:N (default: all; cv reports per-fold aggregates)",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=None,
        help="JSONL of {'id', 'intent'} predictions (required for the predictions arm)",
    )
    parser.add_argument("--model", default=None, help="Model label recorded in the JSON meta")
    parser.add_argument("--provider", default=None, help="Provider label recorded in the JSON meta")
    parser.add_argument(
        "--per-item",
        action="store_true",
        help="Include per-item scores (default: aggregate only; pass --per-item for full detail)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Also write the full JSON payload to this path (scratch; prefer --record for git)",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Write the JSON payload under examples/llm/eval/baselines/ (committed baselines)",
    )
    args = parser.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = set(arms) - set(ARMS)
    if unknown:
        print(f"unknown arms: {sorted(unknown)} (choose from {ARMS})", file=sys.stderr)
        return 2

    predictions: dict[str, dict[str, Any]] | None = None
    if "predictions" in arms:
        if args.predictions is None:
            print("the predictions arm needs --predictions <jsonl>", file=sys.stderr)
            return 2
        try:
            predictions = load_predictions(args.predictions)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"cannot load predictions: {exc}", file=sys.stderr)
            return 2

    split: dict[str, Any] | None = None
    if args.split is not None:
        try:
            split = splits_mod.load_split(args.split)
            # Validate the partition selector before scoring anything.
            splits_mod.partition_ids(split, args.partition)
        except (FileNotFoundError, ValueError) as exc:
            print(f"split error: {exc}", file=sys.stderr)
            return 2
        gold_ids = {c.id for c in build_gold_cases()}
        if predictions is not None:
            extra = sorted(set(predictions) - gold_ids)
            if extra:
                print(f"warning: predictions for unknown case ids ignored: {extra}", file=sys.stderr)

    try:
        results = [run_arm(arm, split, args.partition, predictions) for arm in arms]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not args.per_item:
        for r in results:
            del r["items"]

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "git_rev": _git_rev(),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "harness": "examples/llm/eval/run_gold_field_match.py",
        "issue": "https://github.com/edgesentry/ontographia/issues/96 (steps 1-2)",
        "scorer": "examples/llm/eval/field_match.py",
        "n_gold": len(build_gold_cases()),
        "split": (
            {
                "id": split["split_id"],
                "version": split["version"],
                "gold_hash": split["gold_hash"],
            }
            if split is not None
            else None
        ),
        "results": results,
    }
    if args.model:
        payload["model"] = args.model
    if args.provider:
        payload["provider"] = args.provider

    text = json.dumps(payload, indent=2) + "\n"
    print(text, end="")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
        print(f"wrote {args.json_out}", file=sys.stderr)
    if args.record:
        path = _record_path(args.split, args.partition)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"recorded {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
