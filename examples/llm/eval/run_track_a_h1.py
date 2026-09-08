"""Track A H1 study: full vs subset vs subset→full fallback (issue #51).

Mechanical (no live LLM) comparison of prompt conditions on manufacturing
gold + distractor ontologies.

Method — prompt-vocab induced Intent:
  Assume a model that only selects near-duplicate distractor properties when
  those names appear in the property vocabulary of the prompt. Otherwise it
  emits the gold Intent.

  - full: mid/large prompts list near-duplicates → induced silent-wrong
  - subset: distractors almost never exact-match the question → induced gold
  - subset_fallback: use subset unless empty or gold classes/rels are missing
    from the subset schema enums; then fall back to full (same as pipeline #45)

Predeclared H1 verdict (from plan / issue #51):
  Support: on large, Property Hit ≥ +10pt vs full, tokens ≥ −30%, compile not worse
  Partial: tokens down, quality flat
  Reject: subset hurts quality materially

Usage:
  uv run python examples/llm/eval/run_track_a_h1.py
  uv run python examples/llm/eval/run_track_a_h1.py --record
"""

from __future__ import annotations

import argparse
import json
import statistics
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

from llm.eval.distractor import generate_distractor_ontology, iter_profiles  # noqa: E402
from llm.eval.gold import GoldCase, build_gold_cases, make_silent_wrong_intent  # noqa: E402
from llm.eval.metrics import approx_tokens, property_hit  # noqa: E402
from llm.prompt import build_initial_user_message  # noqa: E402
from llm.subset import prompt_views_for_question, subset_ontology  # noqa: E402

Condition = Literal["full", "subset", "subset_fallback"]
CONDITIONS: tuple[Condition, ...] = ("full", "subset", "subset_fallback")


def _mean(xs: list[float]) -> float:
    return float(statistics.fmean(xs)) if xs else 0.0


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


def _prop_names(ontology: dict[str, Any]) -> set[str]:
    return {str(p["name"]) for p in ontology.get("properties") or [] if p.get("name")}


def _gold_structure(intent: dict[str, Any]) -> tuple[set[str], set[str]]:
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


def _distractor_property(case: GoldCase, wrong: dict[str, Any]) -> str | None:
    if not case.corrupt_target:
        return None
    alias, gold_prop = case.corrupt_target
    for entry in list(wrong.get("return") or []) + list(wrong.get("filter") or []):
        if entry.get("alias") == alias and entry.get("property") and entry.get("property") != gold_prop:
            return str(entry["property"])
    return None


def _structure_covered(intent: dict[str, Any], class_names: set[str], rel_names: set[str]) -> bool:
    classes, rels = _gold_structure(intent)
    return classes <= class_names and rels <= rel_names


def evaluate_case(
    engine: Any,
    case: GoldCase,
    *,
    full_schema: dict[str, Any],
    full_ontology: dict[str, Any],
    condition: Condition,
) -> dict[str, Any]:
    subset = subset_ontology(full_ontology, case.question)
    sub_schema, sub_ont, _ = prompt_views_for_question(
        case.question, full_schema, full_ontology
    )

    used_fallback = False
    if condition == "full":
        schema, ontology = full_schema, full_ontology
        mode = "full"
    elif condition == "subset":
        if subset.empty:
            schema, ontology = full_schema, full_ontology
            mode = "full"
        else:
            schema, ontology = sub_schema, sub_ont
            mode = "subset"
    else:  # subset_fallback
        cover = (not subset.empty) and _structure_covered(
            case.intent, set(subset.class_names), set(subset.relationship_names)
        )
        if cover:
            schema, ontology = sub_schema, sub_ont
            mode = "subset"
        else:
            schema, ontology = full_schema, full_ontology
            mode = "full"
            used_fallback = True

    prompt = build_initial_user_message(case.question, schema, ontology=ontology)
    tokens = approx_tokens(prompt)
    visible_props = _prop_names(ontology)

    wrong = (
        make_silent_wrong_intent(case.intent, case.corrupt_target)
        if case.corrupt_target
        else None
    )
    distractor = _distractor_property(case, wrong) if wrong else None
    distractor_visible = bool(distractor and distractor in visible_props)

    if distractor_visible and wrong is not None:
        induced = wrong
        induced_kind = "silent_wrong"
    else:
        induced = case.intent
        induced_kind = "gold"

    hit = property_hit(induced, case.intent)
    try:
        engine.build(induced)
        compile_ok = True
        compile_error = None
    except Exception as exc:  # noqa: BLE001
        compile_ok = False
        compile_error = str(exc)

    return {
        "id": case.id,
        "condition": condition,
        "schema_mode": mode,
        "used_fallback": used_fallback,
        "approx_tokens": tokens,
        "distractor": distractor,
        "distractor_visible": distractor_visible,
        "induced_kind": induced_kind,
        "property_hit": hit,
        "compile_ok": compile_ok,
        "compile_error": compile_error,
        "subset_empty": subset.empty,
        "subset_stats": subset.stats,
        "gold_structure_covered": _structure_covered(
            case.intent, set(subset.class_names), set(subset.relationship_names)
        ),
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tokens = [float(r["approx_tokens"]) for r in rows]
    hits = [float(r["property_hit"]) for r in rows]
    return {
        "n": len(rows),
        "property_hit_mean": round(_mean(hits), 4),
        "compile_ok": sum(1 for r in rows if r["compile_ok"]),
        "compile_fail": sum(1 for r in rows if not r["compile_ok"]),
        "distractor_visible": sum(1 for r in rows if r["distractor_visible"]),
        "induced_silent_wrong": sum(1 for r in rows if r["induced_kind"] == "silent_wrong"),
        "fallback_rate": round(
            sum(1 for r in rows if r["used_fallback"]) / len(rows) if rows else 0.0,
            4,
        ),
        "gold_structure_covered_rate": round(
            sum(1 for r in rows if r["gold_structure_covered"]) / len(rows) if rows else 0.0,
            4,
        ),
        "prompt_approx_tokens_p50": int(statistics.median(tokens)) if tokens else 0,
        "prompt_approx_tokens_p95": int(
            statistics.quantiles(tokens, n=20, method="inclusive")[18]
        )
        if len(tokens) >= 2
        else (int(tokens[0]) if tokens else 0),
    }


def run_profile(profile: str) -> dict[str, Any]:
    import ontographia

    yaml_bytes, stats = generate_distractor_ontology(profile)
    engine = ontographia.Engine.from_bytes(yaml_bytes, "manufacturing.native.yaml")
    schema = engine.intent_json_schema()
    ontology = engine.ontology_json()
    cases = build_gold_cases()

    by_condition: dict[str, Any] = {}
    qualitative: list[dict[str, Any]] = []

    for condition in CONDITIONS:
        rows = [
            evaluate_case(
                engine,
                case,
                full_schema=schema,
                full_ontology=ontology,
                condition=condition,
            )
            for case in cases
        ]
        by_condition[condition] = summarize_rows(rows)

        # Keep a few qualitative examples (first silent-wrong under full).
        if condition == "full":
            for row in rows:
                if row["induced_kind"] == "silent_wrong" and len(qualitative) < 5:
                    qualitative.append(
                        {
                            "id": row["id"],
                            "distractor": row["distractor"],
                            "property_hit": row["property_hit"],
                            "note": "visible in full prompt property list",
                        }
                    )

    # Cross-condition deltas vs full (for verdict helpers).
    full = by_condition["full"]
    subset = by_condition["subset"]
    deltas = {
        "subset_minus_full_property_hit_pt": round(
            (subset["property_hit_mean"] - full["property_hit_mean"]) * 100,
            2,
        ),
        "subset_token_p95_rel_change": round(
            (subset["prompt_approx_tokens_p95"] / full["prompt_approx_tokens_p95"] - 1.0)
            if full["prompt_approx_tokens_p95"]
            else 0.0,
            4,
        ),
        "subset_compile_ok_delta": subset["compile_ok"] - full["compile_ok"],
    }

    return {
        "profile": profile,
        "ontology": stats,
        "conditions": by_condition,
        "deltas_vs_full": deltas,
        "qualitative_full_distractors": qualitative,
    }


def h1_verdict(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply predeclared criteria on the large profile."""
    large = next((r for r in results if r["profile"] == "large"), None)
    if large is None:
        return {
            "verdict": "inconclusive",
            "reason": "large profile not run",
            "criteria": {},
        }

    full = large["conditions"]["full"]
    subset = large["conditions"]["subset"]
    hit_gain_pt = (subset["property_hit_mean"] - full["property_hit_mean"]) * 100
    token_rel = (
        subset["prompt_approx_tokens_p95"] / full["prompt_approx_tokens_p95"] - 1.0
        if full["prompt_approx_tokens_p95"]
        else 0.0
    )
    compile_ok = subset["compile_ok"] >= full["compile_ok"]

    criteria = {
        "property_hit_gain_pt": round(hit_gain_pt, 2),
        "property_hit_gain_threshold_pt": 10.0,
        "token_p95_rel_change": round(token_rel, 4),
        "token_p95_reduction_threshold": -0.30,
        "compile_not_worse": compile_ok,
        "subset_compile_ok": subset["compile_ok"],
        "full_compile_ok": full["compile_ok"],
    }

    quality_up = hit_gain_pt >= 10.0
    tokens_down = token_rel <= -0.30
    quality_flat = abs(hit_gain_pt) < 10.0
    quality_down = hit_gain_pt <= -10.0

    if quality_down:
        verdict = "reject"
        reason = "subset Property Hit fell by ≥10pt vs full on large"
    elif quality_up and tokens_down and compile_ok:
        verdict = "support"
        reason = (
            "on large: Property Hit ≥ +10pt vs full, tokens p95 ≤ −30%, "
            "compile success not worse (mechanical prompt-vocab arm)"
        )
    elif tokens_down and quality_flat and compile_ok:
        verdict = "partial_support"
        reason = "tokens down ≥30% with flat Property Hit on large"
    elif tokens_down and compile_ok:
        verdict = "partial_support"
        reason = "tokens down; quality gain present but below +10pt threshold or mixed"
    else:
        verdict = "inconclusive"
        reason = "predeclared thresholds not met cleanly"

    return {
        "verdict": verdict,
        "reason": reason,
        "criteria": criteria,
        "caveat": (
            "Mechanical arm: induced silent-wrong only when the distractor name "
            "appears in the prompt property list. A live LLM could still invent "
            "near-duplicates without seeing them."
        ),
    }


def format_results_table(results: list[dict[str, Any]]) -> str:
    lines = [
        "Track A H1 (prompt-vocab induced Intent)",
        f"{'profile':<8} {'cond':<16} {'hit':>6} {'compile':>8} {'vis_d':>6} "
        f"{'wrong':>6} {'fb':>6} {'tok_p50':>8} {'tok_p95':>8}",
    ]
    for row in results:
        for cond in CONDITIONS:
            c = row["conditions"][cond]
            lines.append(
                f"{row['profile']:<8} {cond:<16} {c['property_hit_mean']:>6.2f} "
                f"{c['compile_ok']:>3}/{c['n']:<4} {c['distractor_visible']:>6} "
                f"{c['induced_silent_wrong']:>6} {c['fallback_rate']:>6.2f} "
                f"{c['prompt_approx_tokens_p50']:>8} {c['prompt_approx_tokens_p95']:>8}"
            )
    return "\n".join(lines)


def write_baseline(
    payload: dict[str, Any],
    results: list[dict[str, Any]],
    verdict: dict[str, Any],
) -> tuple[Path, Path]:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = payload["meta"]["recorded_at"].replace(":", "").replace("-", "")[:15]
    json_path = BASELINES_DIR / "track_a_h1.json"
    md_path = BASELINES_DIR / "track_a_h1.md"
    dated_json = BASELINES_DIR / f"track_a_h1_{stamp}.json"

    text = json.dumps(payload, indent=2) + "\n"
    json_path.write_text(text, encoding="utf-8")
    dated_json.write_text(text, encoding="utf-8")

    meta = payload["meta"]
    qual_lines: list[str] = []
    for row in results:
        if row["profile"] != "large":
            continue
        for q in row.get("qualitative_full_distractors") or []:
            qual_lines.append(
                f"- `{q['id']}`: full prompt surfaces `{q['distractor']}` "
                f"(property_hit={q['property_hit']}); subset hides it"
            )

    md = "\n".join(
        [
            "# Track A H1 — full vs subset vs subset+fallback",
            "",
            f"- Recorded: `{meta['recorded_at']}`",
            f"- Git: `{meta.get('git_rev') or 'unknown'}`",
            f"- Harness: `examples/llm/eval/run_track_a_h1.py`",
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
            "## Qualitative (large / full)",
            "",
            *(qual_lines or ["- (none)"]),
            "",
            "## Method",
            "",
            "Induced Intent = silent-wrong near-duplicate **only if** that property "
            "name appears in the prompt's property vocabulary; else gold. "
            "`subset_fallback` uses full when the subset is empty or gold "
            "classes/relationships are missing from subset schema enums.",
            "",
            "Machine-readable: [`track_a_h1.json`](track_a_h1.json).",
            "",
            "```bash",
            "uv run python examples/llm/eval/run_track_a_h1.py --record",
            "```",
            "",
        ]
    )
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Track A H1 full vs subset vs fallback")
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
    verdict = h1_verdict(results)
    payload = {
        "meta": {
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_rev": _git_rev(),
            "profiles": profiles,
            "conditions": list(CONDITIONS),
            "study": "h1_prompt_vocab_induced",
            "issue": 51,
            "harness": "examples/llm/eval/run_track_a_h1.py",
        },
        "verdict": verdict,
        "results": results,
    }

    print()
    print(format_results_table(results))
    print()
    print(f"H1 verdict: {verdict['verdict']}")
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
