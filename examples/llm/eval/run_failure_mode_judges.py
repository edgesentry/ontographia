"""Failure-mode judge reliability for the Track A gold set (issue #96, step 3a).

Offline by default. Builds one prompt per failure mode over a prompt-scoped
ontology subset, then either replays the committed fixture answers
(``--dry-run``) or calls an OpenAI-compatible / LiteLLM backend (``--live``).
Live calls are never implicit.

Labels come from the deterministic field-match scorer, not from a model:

- ``gold``: the gold Intent (all modes negative);
- ``silent_wrong``: near-duplicate property swap (all modes negative — the
  negative control that catches judges firing on any imperfection);
- ``swap_relation``: swapped relationship (``wrong_relation`` positive);
- ``drop_filter``: removed filters (``missing_filter`` positive);
- ``drop_traverse``: removed last traverse step (``over_broad_scope`` positive).

``--predictions`` adds an arm for externally produced Intents (JSONL of
``{"id", "intent"}``), labelled by the same field-match rules.

JSON shape: top-level ``schema_version``, ``git_rev``, ``split`` meta,
per-mode ``judges`` (precision / recall / F1 + counts, ``unknown`` reported
separately), a ``by_variant`` breakdown, and per-item rows with ``--per-item``.

Usage (from repo root):
  uv run python examples/llm/eval/run_failure_mode_judges.py --dry-run \\
      --split track_a_v1 --partition test
  uv run python examples/llm/eval/run_failure_mode_judges.py --live \\
      --split track_a_v1 --partition test
  uv run python examples/llm/eval/run_failure_mode_judges.py --live \\
      --predictions preds.jsonl --split track_a_v1 --partition fold:0

Evaluation only: no execute-or-clarify gate, threshold, F-beta, Brier score, or
product hook (steps 3b / 3c are out of scope).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(EXAMPLES))

from llm.eval import splits as splits_mod  # noqa: E402
from llm.eval.distractor import generate_distractor_ontology  # noqa: E402
from llm.eval.gold import GoldCase, build_gold_cases  # noqa: E402
from llm.eval.judges import (  # noqa: E402
    MODES,
    FixtureResponder,
    build_variants,
    derive_mode_labels,
    fixture_path,
    load_fixture_answers,
    run_judge,
    score_judge_items,
)

SCHEMA_VERSION = "1.0"
# Extra variants that are not synthetic field swaps / drops.
PREDICTIONS_VARIANT = "predictions"


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


def select_cases(
    split: dict[str, Any] | None, partition: str
) -> list[GoldCase]:
    cases = build_gold_cases()
    if split is None:
        return cases
    wanted = set(splits_mod.partition_ids(split, partition))
    return [c for c in cases if c.id in wanted]


def prompt_ontology(full_ontology: dict[str, Any], question: str) -> dict[str, Any]:
    """Exact-match subset for the prompt, falling back to the full ontology."""
    from ontographia.llm.subset import subset_ontology

    subset = subset_ontology(full_ontology, question)
    return full_ontology if subset.empty else subset.ontology


def _live_responder_and_meta(
    backend: str | None, model: str | None, base_url: str | None
) -> tuple[Any, dict[str, Any]]:
    resolved = (backend or os.environ.get("ONTOGRAPHIA_LLM_BACKEND", "openai")).lower()
    if resolved not in {"openai", "openai_compat", "openai-compatible"}:
        raise ValueError(
            f"unsupported judge backend: {resolved!r} "
            "(supported: openai / openai_compat; reuse the LiteLLM wiring)"
        )
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is required for --live (point it at LiteLLM or any "
            "OpenAI-compatible endpoint; see scripts/remeasure/README.md)"
        )

    from ontographia.llm.backend import OpenAICompatibleBackend

    resolved_base = base_url or os.environ.get(
        "OPENAI_BASE_URL", "https://api.openai.com/v1"
    )
    resolved_model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAICompatibleBackend(
        api_key=api_key,
        base_url=resolved_base,
        model=resolved_model,
    )

    def responder(mode: str, messages: list[dict[str, str]]) -> Any:
        del mode
        return client.complete(messages)

    return responder, {
        "backend": resolved,
        "model": resolved_model,
        "base_url": resolved_base,
    }


def _add_items(
    items: list[dict[str, Any]],
    *,
    case: GoldCase,
    variant: str,
    intent: dict[str, Any],
    ontology_subset: dict[str, Any],
    responder: Any,
) -> None:
    labels = derive_mode_labels(case.intent, intent)
    for mode in MODES:
        result = run_judge(mode, case.question, intent, ontology_subset, responder)
        item: dict[str, Any] = {
            "id": case.id,
            "variant": variant,
            "mode": mode,
            "expected": "yes" if labels[mode] else "no",
            "answer": result["answer"],
        }
        if result.get("rationale"):
            item["rationale"] = result["rationale"]
        items.append(item)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Failure-mode judge reliability over the Track A gold set "
            "(issue #96 step 3a; evaluation only)"
        )
    )
    parser.add_argument(
        "--split",
        default=None,
        metavar="SPLIT_ID",
        help="Frozen split id from examples/llm/eval/splits/ (e.g. track_a_v1). "
        "The gold hash is verified before scoring.",
    )
    parser.add_argument(
        "--partition",
        default="all",
        help="all | dev | test | cv | fold:N (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No network: replay committed fixture answers through prompt build + parse",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly call the configured OpenAI-compatible / LiteLLM backend",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=None,
        help="Fixture answers for --dry-run (default: examples/llm/eval/fixtures/failure_mode_judges.json)",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=None,
        help="Optional JSONL of {'id', 'intent'} Intents to label and judge",
    )
    parser.add_argument(
        "--profile",
        default="small",
        help="Ontology size profile for the prompt view (default: small = base)",
    )
    parser.add_argument(
        "--backend",
        default=None,
        help="Live backend name (default: $ONTOGRAPHIA_LLM_BACKEND or openai)",
    )
    parser.add_argument("--model", default=None, help="Live model label / override")
    parser.add_argument("--base-url", default=None, help="Live endpoint override")
    parser.add_argument(
        "--per-item",
        action="store_true",
        help="Include per-item judge rows (default: aggregates only)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Also write the full JSON payload to this scratch path",
    )
    args = parser.parse_args()

    if args.dry_run and args.live:
        print("--dry-run and --live are mutually exclusive", file=sys.stderr)
        return 2
    if not args.dry_run and not args.live:
        print(
            "pass --dry-run (offline fixture replay) or --live (explicit model calls)",
            file=sys.stderr,
        )
        return 2
    if args.partition != "all" and args.split is None:
        print("--partition requires --split", file=sys.stderr)
        return 2

    split: dict[str, Any] | None = None
    if args.split is not None:
        try:
            split = splits_mod.load_split(args.split)
            splits_mod.partition_ids(split, args.partition)
        except (FileNotFoundError, ValueError) as exc:
            print(f"split error: {exc}", file=sys.stderr)
            return 2

    fixture_responder: FixtureResponder | None = None
    live_meta: dict[str, Any] | None = None
    live_responder: Any = None
    if args.dry_run:
        source = args.fixtures or fixture_path()
        try:
            fixture_responder = FixtureResponder(load_fixture_answers(source))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"cannot load judge fixtures: {exc}", file=sys.stderr)
            return 2
    else:
        try:
            live_responder, live_meta = _live_responder_and_meta(
                args.backend,
                args.model,
                args.base_url,
            )
        except (ValueError, ImportError) as exc:
            print(f"live judge setup failed: {exc}", file=sys.stderr)
            return 2

    try:
        yaml_bytes, ontology_stats = generate_distractor_ontology(args.profile)
    except ValueError as exc:
        print(f"ontology profile error: {exc}", file=sys.stderr)
        return 2
    import ontographia

    engine = ontographia.Engine.from_bytes(yaml_bytes, "manufacturing.native.yaml")
    ontology = engine.ontology_json()

    cases = select_cases(split, args.partition)
    predictions: dict[str, dict[str, Any]] | None = None
    skipped: list[str] = []
    if args.predictions is not None:
        try:
            predictions = load_predictions(args.predictions)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"cannot load predictions: {exc}", file=sys.stderr)
            return 2
        gold_ids = {c.id for c in build_gold_cases()}
        extra = sorted(set(predictions) - gold_ids)
        if extra:
            print(
                f"warning: predictions for unknown case ids ignored: {extra}",
                file=sys.stderr,
            )

    items: list[dict[str, Any]] = []
    for case in cases:
        subset = prompt_ontology(ontology, case.question)
        for variant, intent in build_variants(case, ontology):
            responder = (
                fixture_responder.for_variant(variant)
                if fixture_responder is not None
                else live_responder
            )
            _add_items(
                items,
                case=case,
                variant=variant,
                intent=intent,
                ontology_subset=subset,
                responder=responder,
            )

        if predictions is not None:
            predicted = predictions.get(case.id)
            if predicted is None:
                skipped.append(case.id)
                continue
            responder = (
                fixture_responder.for_variant(PREDICTIONS_VARIANT)
                if fixture_responder is not None
                else live_responder
            )
            _add_items(
                items,
                case=case,
                variant=PREDICTIONS_VARIANT,
                intent=predicted,
                ontology_subset=subset,
                responder=responder,
            )

    judges = score_judge_items(items)
    variants = sorted({str(item["variant"]) for item in items})
    by_variant = {
        variant: score_judge_items(
            [item for item in items if item["variant"] == variant]
        )
        for variant in variants
    }

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "git_rev": _git_rev(),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "harness": "examples/llm/eval/run_failure_mode_judges.py",
        "issue": "https://github.com/edgesentry/ontographia/issues/96 (step 3a)",
        "judges_module": "examples/llm/eval/judges.py",
        "selection": "dry_run_fixture" if args.dry_run else "live",
        "ontology": ontology_stats,
        "split": (
            {
                "id": split["split_id"],
                "version": split["version"],
                "gold_hash": split["gold_hash"],
            }
            if split is not None
            else None
        ),
        "partition": args.partition,
        "n_cases": len(cases),
        "n_items": len(items),
        "judges": judges,
        "by_variant": by_variant,
        "skipped": sorted(skipped),
    }
    if args.dry_run:
        payload["fixtures"] = str(args.fixtures or fixture_path())
        payload["note"] = (
            "Dry run replays fixture answers; judge metrics verify prompt build / "
            "parse / split wiring, not model reliability. Use --live for that."
        )
    if live_meta is not None:
        payload.update(live_meta)
    if args.per_item:
        payload["items"] = items

    text = json.dumps(payload, indent=2) + "\n"
    print(text, end="")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
        print(f"wrote {args.json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
