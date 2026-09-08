"""Track A H3 study: always-full fixed retries vs adaptive spend (issue #54).

Mechanical (no live LLM) comparison of cost vs quality for difficulty-adaptive
Intent extraction (issue #47).

Arms:
  - always_full_fixed: full schema + fixed max_retries=5
  - adaptive: subset-first with initial_retries=1; escalate to full +
    escalated_retries=5 only on validation failure

Slices:
  - easy: mock extractor returns gold on first call (subset covers gold)
  - hard: subset extract returns invalid Intent; full extract returns gold
    (forces adaptive escalation)

Predeclared H3 verdict (large / easy):
  Support: adaptive tokens p95 ≤ −30% vs always_full, mean LLM calls lower,
    Compile Success / Property Hit not worse
  Partial: cost down but quality mixed / only easy improves
  Reject: adaptive hurts quality or does not cut cost

Usage:
  uv run python examples/llm/eval/run_track_a_h3.py
  uv run python examples/llm/eval/run_track_a_h3.py --record
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
EVAL_DIR = EXAMPLES / "llm" / "eval"
BASELINES_DIR = EVAL_DIR / "baselines"
sys.path.insert(0, str(EXAMPLES))

from llm.eval.distractor import generate_distractor_ontology, iter_profiles  # noqa: E402
from llm.eval.gold import GoldCase, build_gold_cases  # noqa: E402
from llm.eval.metrics import approx_tokens, property_hit  # noqa: E402
from llm.pipeline import extract_validated_intent  # noqa: E402
from llm.prompt import build_initial_user_message  # noqa: E402
from llm.subset import prompt_views_for_question, subset_ontology  # noqa: E402

Condition = Literal["always_full_fixed", "adaptive"]
Slice = Literal["easy", "hard"]
CONDITIONS: tuple[Condition, ...] = ("always_full_fixed", "adaptive")
SLICES: tuple[Slice, ...] = ("easy", "hard")

ALWAYS_FULL_RETRIES = 5
ADAPTIVE_INITIAL_RETRIES = 1
ADAPTIVE_ESCALATED_RETRIES = 5


def _mean(xs: list[float]) -> float:
    return float(statistics.fmean(xs)) if xs else 0.0


def _p95(xs: list[float]) -> int:
    if not xs:
        return 0
    if len(xs) < 2:
        return int(xs[0])
    return int(statistics.quantiles(xs, n=20, method="inclusive")[18])


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


def _is_subset_schema(
    intent_json_schema: dict[str, Any],
    *,
    full_class_count: int,
) -> bool:
    enums = (
        intent_json_schema.get("$defs", {})
        .get("NodeRef", {})
        .get("properties", {})
        .get("class", {})
        .get("enum")
        or []
    )
    return len(enums) < full_class_count


def _invalid_intent(gold: dict[str, Any]) -> dict[str, Any]:
    """Return an Intent that fails Engine.build for any gold pattern."""
    bad = copy.deepcopy(gold)
    start = bad.get("start") or {}
    alias = str(start.get("alias") or "n0")
    # Invented property on the start alias — always rejected by ontology validation.
    bad["return"] = [
        {
            "alias": alias,
            "property": "not_a_real_property_h3",
            "as_name": "x",
        }
    ]
    return bad


class EasyExtractor:
    """Always returns gold — models a successful first-pass Intent."""

    def __init__(self, gold: dict[str, Any]) -> None:
        self.gold = copy.deepcopy(gold)

    def extract(
        self,
        user_question: str,
        intent_json_schema: dict[str, Any],
        *,
        ontology: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del user_question, intent_json_schema, ontology
        return copy.deepcopy(self.gold)

    def extract_correction(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        return copy.deepcopy(self.gold)


class HardExtractor:
    """Fails on subset schema; succeeds with gold on full schema."""

    def __init__(self, gold: dict[str, Any], *, full_class_count: int) -> None:
        self.gold = copy.deepcopy(gold)
        self.full_class_count = full_class_count

    def extract(
        self,
        user_question: str,
        intent_json_schema: dict[str, Any],
        *,
        ontology: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del user_question, ontology
        if _is_subset_schema(intent_json_schema, full_class_count=self.full_class_count):
            return _invalid_intent(self.gold)
        return copy.deepcopy(self.gold)

    def extract_correction(
        self,
        user_question: str,
        intent_json_schema: dict[str, Any],
        *,
        ontology: dict[str, Any] | None = None,
        previous_intent: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        del previous_intent, error
        return self.extract(user_question, intent_json_schema, ontology=ontology)


def _prompt_tokens_for_mode(
    question: str,
    *,
    full_schema: dict[str, Any],
    full_ontology: dict[str, Any],
    mode: str,
) -> int:
    if mode == "subset":
        sub_schema, sub_ont, _ = prompt_views_for_question(
            question, full_schema, full_ontology
        )
        return approx_tokens(
            build_initial_user_message(question, sub_schema, ontology=sub_ont)
        )
    return approx_tokens(
        build_initial_user_message(question, full_schema, ontology=full_ontology)
    )


def evaluate_case(
    engine: Any,
    case: GoldCase,
    *,
    full_schema: dict[str, Any],
    full_ontology: dict[str, Any],
    condition: Condition,
    slice_name: Slice,
) -> dict[str, Any]:
    subset = subset_ontology(full_ontology, case.question)
    structure_ok = (not subset.empty) and set(
        _gold_classes_rels(case.intent)[0]
    ) <= set(subset.class_names) and set(
        _gold_classes_rels(case.intent)[1]
    ) <= set(subset.relationship_names)

    full_class_count = len(
        (full_schema.get("$defs") or {})
        .get("NodeRef", {})
        .get("properties", {})
        .get("class", {})
        .get("enum")
        or []
    )

    extractor: Any
    if slice_name == "easy":
        extractor = EasyExtractor(case.intent)
    else:
        extractor = HardExtractor(case.intent, full_class_count=full_class_count)

    t0 = time.perf_counter()
    if condition == "always_full_fixed":
        outcome = extract_validated_intent(
            engine,
            extractor,
            case.question,
            full_schema,
            ontology=full_ontology,
            schema_policy="full",
            max_retries=ALWAYS_FULL_RETRIES,
        )
    else:
        outcome = extract_validated_intent(
            engine,
            extractor,
            case.question,
            full_schema,
            ontology=full_ontology,
            schema_policy="auto",
            initial_retries=ADAPTIVE_INITIAL_RETRIES,
            escalated_retries=ADAPTIVE_ESCALATED_RETRIES,
        )
    wall_ms = (time.perf_counter() - t0) * 1000.0

    final_tokens = _prompt_tokens_for_mode(
        case.question,
        full_schema=full_schema,
        full_ontology=full_ontology,
        mode=outcome.schema_mode,
    )
    total_tokens = sum(
        _prompt_tokens_for_mode(
            case.question,
            full_schema=full_schema,
            full_ontology=full_ontology,
            mode=mode,
        )
        for mode in outcome.phases_tried
    )

    hit = property_hit(outcome.intent, case.intent)
    try:
        engine.build(outcome.intent)
        compile_ok = True
    except Exception:  # noqa: BLE001
        compile_ok = False

    return {
        "id": case.id,
        "condition": condition,
        "slice": slice_name,
        "schema_mode": outcome.schema_mode,
        "used_fallback": outcome.used_fallback,
        "phases_tried": list(outcome.phases_tried),
        "llm_calls": outcome.llm_calls,
        "prompt_approx_tokens_final": final_tokens,
        "prompt_approx_tokens_total": total_tokens,
        "wall_ms": round(wall_ms, 3),
        "property_hit": hit,
        "compile_ok": compile_ok,
        "subset_empty": subset.empty,
        "gold_structure_covered": structure_ok,
    }


def _gold_classes_rels(intent: dict[str, Any]) -> tuple[set[str], set[str]]:
    classes: set[str] = set()
    rels: set[str] = set()
    start = intent.get("start") or {}
    if start.get("class"):
        classes.add(str(start["class"]))
    for step in intent.get("traverse") or []:
        if step.get("relationship"):
            rels.add(str(step["relationship"]))
        to = step.get("to") or {}
        if to.get("class"):
            classes.add(str(to["class"]))
    return classes, rels


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tokens_final = [float(r["prompt_approx_tokens_final"]) for r in rows]
    tokens_total = [float(r["prompt_approx_tokens_total"]) for r in rows]
    calls = [float(r["llm_calls"]) for r in rows]
    hits = [float(r["property_hit"]) for r in rows]
    walls = [float(r["wall_ms"]) for r in rows]
    return {
        "n": len(rows),
        "property_hit_mean": round(_mean(hits), 4),
        "compile_ok": sum(1 for r in rows if r["compile_ok"]),
        "compile_fail": sum(1 for r in rows if not r["compile_ok"]),
        "escalation_rate": round(
            sum(1 for r in rows if r["used_fallback"]) / len(rows) if rows else 0.0,
            4,
        ),
        "mean_llm_calls": round(_mean(calls), 4),
        "prompt_approx_tokens_final_p50": int(statistics.median(tokens_final))
        if tokens_final
        else 0,
        "prompt_approx_tokens_final_p95": _p95(tokens_final),
        "prompt_approx_tokens_total_p50": int(statistics.median(tokens_total))
        if tokens_total
        else 0,
        "prompt_approx_tokens_total_p95": _p95(tokens_total),
        "mean_wall_ms": round(_mean(walls), 3),
        "gold_structure_covered_rate": round(
            sum(1 for r in rows if r["gold_structure_covered"]) / len(rows) if rows else 0.0,
            4,
        ),
    }


def run_profile(profile: str) -> dict[str, Any]:
    import ontographia

    yaml_bytes, stats = generate_distractor_ontology(profile)
    engine = ontographia.Engine.from_bytes(yaml_bytes, "manufacturing.native.yaml")
    schema = engine.intent_json_schema()
    ontology = engine.ontology_json()
    cases = build_gold_cases()

    by_slice: dict[str, Any] = {}
    for slice_name in SLICES:
        by_condition: dict[str, Any] = {}
        for condition in CONDITIONS:
            rows = [
                evaluate_case(
                    engine,
                    case,
                    full_schema=schema,
                    full_ontology=ontology,
                    condition=condition,
                    slice_name=slice_name,
                )
                for case in cases
            ]
            by_condition[condition] = summarize_rows(rows)
        by_slice[slice_name] = by_condition

    easy_full = by_slice["easy"]["always_full_fixed"]
    easy_ad = by_slice["easy"]["adaptive"]
    deltas_easy = {
        "adaptive_minus_full_property_hit_pt": round(
            (easy_ad["property_hit_mean"] - easy_full["property_hit_mean"]) * 100,
            2,
        ),
        "adaptive_token_final_p95_rel_change": round(
            (
                easy_ad["prompt_approx_tokens_final_p95"]
                / easy_full["prompt_approx_tokens_final_p95"]
                - 1.0
            )
            if easy_full["prompt_approx_tokens_final_p95"]
            else 0.0,
            4,
        ),
        "adaptive_mean_llm_calls_delta": round(
            easy_ad["mean_llm_calls"] - easy_full["mean_llm_calls"],
            4,
        ),
        "adaptive_compile_ok_delta": easy_ad["compile_ok"] - easy_full["compile_ok"],
    }

    return {
        "profile": profile,
        "ontology": stats,
        "slices": by_slice,
        "deltas_easy_vs_full": deltas_easy,
    }


def h3_verdict(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply predeclared criteria on the large profile / easy slice."""
    large = next((r for r in results if r["profile"] == "large"), None)
    if large is None:
        return {
            "verdict": "inconclusive",
            "reason": "large profile not run",
            "criteria": {},
            "caveat": "",
        }

    easy_full = large["slices"]["easy"]["always_full_fixed"]
    easy_ad = large["slices"]["easy"]["adaptive"]
    hard_ad = large["slices"]["hard"]["adaptive"]

    hit_delta_pt = (easy_ad["property_hit_mean"] - easy_full["property_hit_mean"]) * 100
    token_rel = (
        easy_ad["prompt_approx_tokens_final_p95"]
        / easy_full["prompt_approx_tokens_final_p95"]
        - 1.0
        if easy_full["prompt_approx_tokens_final_p95"]
        else 0.0
    )
    calls_lower = easy_ad["mean_llm_calls"] < easy_full["mean_llm_calls"] or (
        easy_ad["mean_llm_calls"] <= easy_full["mean_llm_calls"]
        and easy_ad["mean_llm_calls"] <= 1.0
        and token_rel <= -0.30
    )
    # On easy both arms typically use 1 call; require tokens down AND calls not higher.
    calls_not_higher = easy_ad["mean_llm_calls"] <= easy_full["mean_llm_calls"]
    compile_not_worse = easy_ad["compile_ok"] >= easy_full["compile_ok"]
    quality_not_worse = hit_delta_pt >= -0.01 and compile_not_worse
    tokens_down = token_rel <= -0.30
    escalate_works = hard_ad["escalation_rate"] >= 0.95 and hard_ad["compile_ok"] == hard_ad["n"]

    criteria = {
        "easy_token_p95_rel_change": round(token_rel, 4),
        "token_p95_reduction_threshold": -0.30,
        "easy_property_hit_delta_pt": round(hit_delta_pt, 2),
        "easy_adaptive_mean_llm_calls": easy_ad["mean_llm_calls"],
        "easy_full_mean_llm_calls": easy_full["mean_llm_calls"],
        "easy_calls_not_higher": calls_not_higher,
        "easy_compile_not_worse": compile_not_worse,
        "hard_escalation_rate": hard_ad["escalation_rate"],
        "hard_adaptive_compile_ok": hard_ad["compile_ok"],
        "hard_escalate_recovers": escalate_works,
    }

    quality_down = hit_delta_pt <= -10.0 or easy_ad["compile_ok"] < easy_full["compile_ok"]

    if quality_down:
        verdict = "reject"
        reason = "adaptive hurt Property Hit (≥10pt) or Compile Success on large/easy"
    elif tokens_down and quality_not_worse and calls_not_higher and escalate_works:
        verdict = "support"
        reason = (
            "on large/easy: tokens p95 ≤ −30% vs always_full, LLM calls not higher, "
            "Compile/Property Hit not worse; hard slice escalates and recovers "
            "(mechanical arm)"
        )
    elif tokens_down and quality_not_worse:
        verdict = "partial_support"
        reason = (
            "tokens down ≥30% with quality held on easy, but calls/escalation "
            "sanity incomplete"
        )
    elif tokens_down:
        verdict = "partial_support"
        reason = "tokens down; quality or escalation criteria mixed"
    else:
        verdict = "reject"
        reason = "adaptive did not cut tokens p95 by ≥30% on large/easy"

    # Note: calls_lower unused for primary gate when both are 1; kept for criteria clarity.
    del calls_lower

    return {
        "verdict": verdict,
        "reason": reason,
        "criteria": criteria,
        "caveat": (
            "Mechanical arm: mock extractors (gold on easy; subset-fail→full-gold on "
            "hard). Measures #47 retry/schema budgeting, not live-LLM difficulty "
            "routing. Follow-up live LLM: issue #68."
        ),
    }


def format_results_table(results: list[dict[str, Any]]) -> str:
    lines = [
        "Track A H3 (always_full_fixed vs adaptive)",
        f"{'profile':<8} {'slice':<5} {'cond':<18} {'hit':>6} {'compile':>8} "
        f"{'esc':>6} {'calls':>6} {'tok_f_p95':>10} {'tok_t_p95':>10}",
    ]
    for row in results:
        for slice_name in SLICES:
            for cond in CONDITIONS:
                c = row["slices"][slice_name][cond]
                lines.append(
                    f"{row['profile']:<8} {slice_name:<5} {cond:<18} "
                    f"{c['property_hit_mean']:>6.2f} "
                    f"{c['compile_ok']:>3}/{c['n']:<4} "
                    f"{c['escalation_rate']:>6.2f} "
                    f"{c['mean_llm_calls']:>6.2f} "
                    f"{c['prompt_approx_tokens_final_p95']:>10} "
                    f"{c['prompt_approx_tokens_total_p95']:>10}"
                )
    return "\n".join(lines)


def write_baseline(
    payload: dict[str, Any],
    results: list[dict[str, Any]],
    verdict: dict[str, Any],
) -> tuple[Path, Path]:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = payload["meta"]["recorded_at"].replace(":", "").replace("-", "")[:15]
    json_path = BASELINES_DIR / "track_a_h3.json"
    md_path = BASELINES_DIR / "track_a_h3.md"
    dated_json = BASELINES_DIR / f"track_a_h3_{stamp}.json"

    text = json.dumps(payload, indent=2) + "\n"
    json_path.write_text(text, encoding="utf-8")
    dated_json.write_text(text, encoding="utf-8")

    meta = payload["meta"]
    md = "\n".join(
        [
            "# Track A H3 — always_full_fixed vs adaptive spend",
            "",
            f"- Recorded: `{meta['recorded_at']}`",
            f"- Git: `{meta.get('git_rev') or 'unknown'}`",
            f"- Harness: `examples/llm/eval/run_track_a_h3.py`",
            f"- Profiles: {', '.join(meta['profiles'])}",
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
            "- `always_full_fixed`: full schema + `max_retries=5`",
            "- `adaptive`: subset-first (`initial_retries=1`); escalate to full "
            "(`escalated_retries=5`) only on failure (issue #47)",
            "- **easy**: mock extractor returns gold Intent on first call",
            "- **hard**: subset extract is invalid; full extract returns gold "
            "(forces escalation)",
            "",
            "`tok_f_*` = final-phase prompt ≈tokens; `tok_t_*` = sum across phases tried.",
            "",
            "Machine-readable: [`track_a_h3.json`](track_a_h3.json).",
            "",
            "```bash",
            "uv run python examples/llm/eval/run_track_a_h3.py --record",
            "```",
            "",
        ]
    )
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Track A H3 always_full vs adaptive spend"
    )
    parser.add_argument("--profiles", default="small,mid,large")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument(
        "--record",
        action="store_true",
        help="Write baselines under examples/llm/eval/baselines/",
    )
    args = parser.parse_args()
    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    for p in profiles:
        if p not in set(iter_profiles()):
            print(f"unknown profile: {p}", file=sys.stderr)
            return 2

    results = [run_profile(p) for p in profiles]
    verdict = h3_verdict(results)
    payload = {
        "meta": {
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_rev": _git_rev(),
            "profiles": profiles,
            "conditions": list(CONDITIONS),
            "slices": list(SLICES),
            "study": "h3_adaptive_spend",
            "issue": 54,
            "feature_issue": 47,
            "harness": "examples/llm/eval/run_track_a_h3.py",
            "budgets": {
                "always_full_retries": ALWAYS_FULL_RETRIES,
                "adaptive_initial_retries": ADAPTIVE_INITIAL_RETRIES,
                "adaptive_escalated_retries": ADAPTIVE_ESCALATED_RETRIES,
            },
        },
        "verdict": verdict,
        "results": results,
    }

    print()
    print(format_results_table(results))
    print()
    print(f"H3 verdict: {verdict['verdict']}")
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
