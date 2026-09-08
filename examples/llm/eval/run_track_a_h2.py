"""H2 study: Intent refinement with vs without execution feedback (issue #55).

Mechanical (no live LLM / no Neo4j) comparison on manufacturing gold Intents.

Method — empty-inducing filter corruption:
  Start from gold Intent (compiles). Corrupt a filter *value* to a wrong but
  still-schema-valid literal so Engine.build succeeds (Empty@Valid when "run").
  A mock executor returns rows only when filter values match gold; otherwise [].

  - no_refine (max_exec_refines=0): empty stays empty
  - with_refine (max_exec_refines=2): mechanical corrector returns gold Intent
    on Neo4j execution feedback, then Engine.build again

Also runs a gold control arm (uncorrupted) to ensure refine does not fire
unnecessarily.

Predeclared H2 verdict:
  Support: on empty-inducing set, final execution_ok rate ≥ +20pt with refine,
    Intent Exact Match recovers, and every emitted query equals Engine.build
  Partial: recovery helps but below +20pt
  Reject: refine does not improve final_ok (or worsens it)

Usage:
  uv run python examples/llm/eval/run_track_a_h2.py
  uv run python examples/llm/eval/run_track_a_h2.py --record
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
EVAL_DIR = EXAMPLES / "llm" / "eval"
BASELINES_DIR = EVAL_DIR / "baselines"
sys.path.insert(0, str(EXAMPLES))

from llm.eval.gold import GoldCase, build_gold_cases  # noqa: E402
from llm.pipeline import ExtractOutcome, refine_intent_after_execution  # noqa: E402

Condition = Literal["no_refine", "with_refine"]
CONDITIONS: tuple[Condition, ...] = ("no_refine", "with_refine")
WRONG_VALUE_SUFFIX = "-WRONG"


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


def make_empty_inducing_intent(intent: dict[str, Any]) -> dict[str, Any] | None:
    """Corrupt the first filter value so compile still works but exec is empty."""
    filters = intent.get("filter") or []
    if not filters:
        return None
    wrong = copy.deepcopy(intent)
    entry = wrong["filter"][0]
    if "value" not in entry:
        return None
    entry["value"] = f"{entry['value']}{WRONG_VALUE_SUFFIX}"
    return wrong


def _filter_values(intent: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(
        entry.get("value") for entry in (intent.get("filter") or []) if "value" in entry
    )


def _intent_exact_match(pred: dict[str, Any], gold: dict[str, Any]) -> bool:
    return json.dumps(pred, sort_keys=True) == json.dumps(gold, sort_keys=True)


def _cypher_from_engine(engine: Any, intent: dict[str, Any], built: dict[str, Any]) -> bool:
    """Emitted query/params must match a fresh Engine.build (never LLM-edited)."""
    rebuilt = engine.build(intent)
    return rebuilt.get("query") == built.get("query") and rebuilt.get("params") == built.get(
        "params"
    )


class MechanicalExtractor:
    """Initial Intent is fixed; corrections return gold on exec feedback."""

    def __init__(self, initial: dict[str, Any], gold: dict[str, Any]) -> None:
        self.initial = copy.deepcopy(initial)
        self.gold = copy.deepcopy(gold)
        self.correction_calls = 0

    def extract(
        self,
        user_question: str,
        intent_json_schema: dict[str, Any],
        *,
        ontology: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del user_question, intent_json_schema, ontology
        return copy.deepcopy(self.initial)

    def extract_correction(
        self,
        user_question: str,
        intent_json_schema: dict[str, Any],
        *,
        ontology: dict[str, Any] | None,
        previous_intent: dict[str, Any],
        error: str,
    ) -> dict[str, Any]:
        del user_question, intent_json_schema, ontology, previous_intent
        self.correction_calls += 1
        if not error.startswith("Neo4j execution feedback"):
            raise AssertionError(f"expected Neo4j execution feedback, got: {error[:80]!r}")
        if "Cypher" not in error:
            raise AssertionError("feedback must tell the model not to edit Cypher")
        return copy.deepcopy(self.gold)


def _mock_execute_fn(gold_intent: dict[str, Any]):
    gold_values = _filter_values(gold_intent)

    def execute_fn(built: dict[str, Any]) -> list[dict[str, Any]]:
        params = built.get("params") or {}
        # Params are bound in filter order as param_0, param_1, ...
        ordered = tuple(
            params[k] for k in sorted(params.keys(), key=lambda s: int(s.split("_")[1]))
        )
        if ordered == gold_values:
            return [{"ok": True, "n": 1}]
        return []

    return execute_fn


def run_case(
    engine: Any,
    case: GoldCase,
    *,
    initial_intent: dict[str, Any],
    condition: Condition,
) -> dict[str, Any]:
    schema = engine.intent_json_schema()
    ontology = engine.ontology_json()
    extractor = MechanicalExtractor(initial_intent, case.intent)
    built = engine.build(initial_intent)
    outcome = ExtractOutcome(
        intent=copy.deepcopy(initial_intent),
        result=built,
        schema_mode="full",
        used_fallback=False,
    )
    max_refines = 0 if condition == "no_refine" else 2
    refined = refine_intent_after_execution(
        engine,
        extractor,
        case.question,
        schema,
        outcome,
        execute_fn=_mock_execute_fn(case.intent),
        ontology=ontology,
        max_exec_refines=max_refines,
    )

    first_empty = _filter_values(initial_intent) != _filter_values(case.intent)
    compile_ok = True
    cypher_ok = _cypher_from_engine(engine, refined.intent, refined.result)
    exact = _intent_exact_match(refined.intent, case.intent)
    final_ok = bool(refined.execution_ok)
    empty_at_valid = first_empty and compile_ok
    # Recovered from Empty@Valid when refine restored gold and exec succeeded
    recovered = empty_at_valid and final_ok and exact

    return {
        "id": case.id,
        "condition": condition,
        "compile_ok": compile_ok,
        "empty_at_valid": empty_at_valid,
        "final_execution_ok": final_ok,
        "intent_exact_match": exact,
        "recovered": recovered,
        "cypher_from_engine_build": cypher_ok,
        "exec_refine_attempts": refined.exec_refine_attempts,
        "correction_calls": extractor.correction_calls,
        "execution_row_count": refined.execution_row_count,
    }


def summarize(rows: list[dict[str, Any]], *, n: int) -> dict[str, Any]:
    def rate(key: str) -> float:
        return sum(1 for r in rows if r[key]) / n if n else 0.0

    return {
        "n": n,
        "compile_ok": sum(1 for r in rows if r["compile_ok"]),
        "empty_at_valid": sum(1 for r in rows if r["empty_at_valid"]),
        "empty_at_valid_rate": rate("empty_at_valid"),
        "final_execution_ok": sum(1 for r in rows if r["final_execution_ok"]),
        "final_execution_ok_rate": rate("final_execution_ok"),
        "intent_exact_match": sum(1 for r in rows if r["intent_exact_match"]),
        "intent_exact_match_rate": rate("intent_exact_match"),
        "recovered": sum(1 for r in rows if r["recovered"]),
        "recovered_rate": rate("recovered"),
        "cypher_from_engine_build": sum(1 for r in rows if r["cypher_from_engine_build"]),
        "cypher_from_engine_build_rate": rate("cypher_from_engine_build"),
        "mean_exec_refine_attempts": (
            sum(r["exec_refine_attempts"] for r in rows) / n if n else 0.0
        ),
        "mean_correction_calls": (
            sum(r["correction_calls"] for r in rows) / n if n else 0.0
        ),
    }


def run_study() -> dict[str, Any]:
    import ontographia

    engine = ontographia.Engine.load(str(EXAMPLES / "manufacturing.native.yaml"))
    cases = build_gold_cases()

    empty_inducing: dict[Condition, list[dict[str, Any]]] = {c: [] for c in CONDITIONS}
    gold_control: dict[Condition, list[dict[str, Any]]] = {c: [] for c in CONDITIONS}
    skipped = 0

    for case in cases:
        wrong = make_empty_inducing_intent(case.intent)
        if wrong is None:
            skipped += 1
            continue
        # Sanity: wrong still compiles
        engine.build(wrong)
        for cond in CONDITIONS:
            empty_inducing[cond].append(
                run_case(engine, case, initial_intent=wrong, condition=cond)
            )
            gold_control[cond].append(
                run_case(engine, case, initial_intent=case.intent, condition=cond)
            )

    n_empty = len(empty_inducing["no_refine"])
    n_gold = len(gold_control["no_refine"])
    return {
        "empty_inducing": {c: summarize(empty_inducing[c], n=n_empty) for c in CONDITIONS},
        "gold_control": {c: summarize(gold_control[c], n=n_gold) for c in CONDITIONS},
        "skipped_no_filter": skipped,
        "n_cases": len(cases),
        "n_empty_inducing": n_empty,
    }


def h2_verdict(results: dict[str, Any]) -> dict[str, Any]:
    no_r = results["empty_inducing"]["no_refine"]
    with_r = results["empty_inducing"]["with_refine"]
    gold = results["gold_control"]["with_refine"]

    final_ok_gain_pt = (
        with_r["final_execution_ok_rate"] - no_r["final_execution_ok_rate"]
    ) * 100
    exact_gain_pt = (
        with_r["intent_exact_match_rate"] - no_r["intent_exact_match_rate"]
    ) * 100
    cypher_always = (
        with_r["cypher_from_engine_build_rate"] == 1.0
        and no_r["cypher_from_engine_build_rate"] == 1.0
        and gold["cypher_from_engine_build_rate"] == 1.0
    )
    gold_stays_ok = gold["final_execution_ok_rate"] == 1.0 and gold["mean_correction_calls"] == 0.0

    criteria = {
        "final_ok_gain_pt": round(final_ok_gain_pt, 2),
        "final_ok_gain_threshold_pt": 20.0,
        "intent_exact_match_gain_pt": round(exact_gain_pt, 2),
        "cypher_always_from_engine_build": cypher_always,
        "gold_control_no_spurious_refine": gold_stays_ok,
        "no_refine_final_ok_rate": round(no_r["final_execution_ok_rate"], 4),
        "with_refine_final_ok_rate": round(with_r["final_execution_ok_rate"], 4),
        "with_refine_recovered_rate": round(with_r["recovered_rate"], 4),
        "empty_at_valid_rate": round(no_r["empty_at_valid_rate"], 4),
    }

    if not cypher_always:
        verdict = "reject"
        reason = "emitted Cypher did not always match Engine.build (H2 safety invariant)"
    elif not gold_stays_ok:
        verdict = "inconclusive"
        reason = "gold control failed or spuriously refined"
    elif final_ok_gain_pt >= 20.0 and with_r["recovered_rate"] >= 0.8:
        verdict = "support"
        reason = (
            "on empty-inducing set: final execution_ok ≥ +20pt with refine, "
            "≥80% recovered to gold Intent+rows, Cypher always from Engine.build "
            "(mechanical arm)"
        )
    elif final_ok_gain_pt > 0:
        verdict = "partial_support"
        reason = "refine improves final_ok but below +20pt / 80% recovery thresholds"
    else:
        verdict = "reject"
        reason = "refine did not improve final execution_ok on empty-inducing set"

    return {
        "verdict": verdict,
        "reason": reason,
        "criteria": criteria,
        "caveat": (
            "Mechanical arm: mock executor + gold-returning corrector. Measures that "
            "the #46 loop recovers Empty@Valid when Intent correction succeeds; not "
            "live-LLM correction quality or real Neo4j Exec Match."
        ),
    }


def format_results_table(results: dict[str, Any]) -> str:
    lines = [
        "H2 (exec feedback Intent refine)",
        f"{'arm':<16} {'cond':<12} {'empty@v':>8} {'final_ok':>8} {'exact':>8} "
        f"{'recovered':>9} {'cypherOK':>8} {'corr':>6}",
    ]
    for arm in ("empty_inducing", "gold_control"):
        for cond in CONDITIONS:
            c = results[arm][cond]
            lines.append(
                f"{arm:<16} {cond:<12} {c['empty_at_valid_rate']:>8.2f} "
                f"{c['final_execution_ok_rate']:>8.2f} {c['intent_exact_match_rate']:>8.2f} "
                f"{c['recovered_rate']:>9.2f} {c['cypher_from_engine_build_rate']:>8.2f} "
                f"{c['mean_correction_calls']:>6.2f}"
            )
    return "\n".join(lines)


def write_baseline(
    payload: dict[str, Any],
    results: dict[str, Any],
    verdict: dict[str, Any],
) -> tuple[Path, Path]:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = payload["meta"]["recorded_at"].replace(":", "").replace("-", "")[:15]
    json_path = BASELINES_DIR / "track_a_h2.json"
    md_path = BASELINES_DIR / "track_a_h2.md"
    dated_json = BASELINES_DIR / f"track_a_h2_{stamp}.json"

    text = json.dumps(payload, indent=2) + "\n"
    json_path.write_text(text, encoding="utf-8")
    dated_json.write_text(text, encoding="utf-8")

    meta = payload["meta"]
    md = "\n".join(
        [
            "# H2 — Intent refinement with execution feedback",
            "",
            f"- Recorded: `{meta['recorded_at']}`",
            f"- Git: `{meta.get('git_rev') or 'unknown'}`",
            f"- Harness: `examples/llm/eval/run_track_a_h2.py`",
            f"- Issue: #{meta['issue']}",
            "",
            "## Verdict",
            "",
            f"**{verdict['verdict']}** — {verdict['reason']}",
            "",
            f"Caveat: {verdict['caveat']}",
            "",
            "```json",
            json.dumps(verdict["criteria"], indent=2),
            "```",
            "",
            "## Results",
            "",
            "```",
            format_results_table(results),
            "```",
            "",
            "## Method",
            "",
            "Corrupt gold filter *values* → Empty@Valid (compile OK, mock exec empty). "
            "`no_refine` stops there; `with_refine` feeds Neo4j feedback into "
            "`extract_correction`, which mechanically returns gold Intent; Cypher is "
            "always recompiled via `Engine.build`. Gold control uses uncorrupted Intents.",
            "",
            "Machine-readable: [`track_a_h2.json`](track_a_h2.json).",
            "",
            "```bash",
            "uv run python examples/llm/eval/run_track_a_h2.py --record",
            "```",
            "",
        ]
    )
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="H2 exec-feedback Intent refine study")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument(
        "--record",
        action="store_true",
        help="Write baselines under examples/llm/eval/baselines/",
    )
    args = parser.parse_args()

    results = run_study()
    verdict = h2_verdict(results)
    payload = {
        "meta": {
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_rev": _git_rev(),
            "conditions": list(CONDITIONS),
            "study": "h2_exec_feedback_mechanical",
            "issue": 55,
            "feature_issue": 46,
            "harness": "examples/llm/eval/run_track_a_h2.py",
        },
        "verdict": verdict,
        "results": results,
    }

    print()
    print(format_results_table(results))
    print()
    print(f"H2 verdict: {verdict['verdict']}")
    print(verdict["reason"])
    print(f"Caveat: {verdict['caveat']}")

    if args.record:
        json_path, md_path = write_baseline(payload, results, verdict)
        print(f"recorded {json_path}")
        print(f"recorded {md_path}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json_out}")
    elif not args.record:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
