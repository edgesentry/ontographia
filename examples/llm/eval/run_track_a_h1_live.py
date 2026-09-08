"""Track A H1 live-LLM arm (issue #68).

Runs manufacturing gold questions through a real OpenAI-compatible extractor
under the same three prompt conditions as mechanical H1 (#51):

  full / subset / subset_fallback (→ schema_policy auto)

Measures Property Hit, soft F1, compile, tokens, fallback, near-duplicate
picks, and invent-without-seeing (wrong near-dup not in prompt vocab).

Usage:
  export ONTOGRAPHIA_LLM_BACKEND=openai OPENAI_API_KEY=...
  uv run python examples/llm/eval/run_track_a_h1_live.py --profiles mid,large --record
  uv run python examples/llm/eval/run_track_a_h1_live.py --profiles large --limit 8
"""

from __future__ import annotations

import argparse
import json
import os
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

from llm.eval.distractor import (  # noqa: E402
    generate_distractor_ontology,
    iter_profiles,
    near_duplicate_map,
)
from llm.eval.gold import ALIAS_CLASS, GoldCase, build_gold_cases  # noqa: E402
from llm.eval.metrics import approx_tokens, intent_soft_f1, property_hit  # noqa: E402
from llm.extractors import create_extractor  # noqa: E402
from llm.pipeline import extract_validated_intent  # noqa: E402
from llm.prompt import build_initial_user_message  # noqa: E402
from llm.subset import prompt_views_for_question, subset_ontology  # noqa: E402

Condition = Literal["full", "subset", "subset_fallback"]
CONDITIONS: tuple[Condition, ...] = ("full", "subset", "subset_fallback")

CONDITION_TO_POLICY: dict[Condition, str] = {
    "full": "full",
    "subset": "subset",
    "subset_fallback": "auto",
}


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


def _preferred_distractor(case: GoldCase) -> str | None:
    if not case.corrupt_target:
        return None
    alias, gold_prop = case.corrupt_target
    owner = ALIAS_CLASS.get(alias)
    if not owner:
        return None
    return near_duplicate_map().get((owner, gold_prop))


def _pred_props_for_alias(intent: dict[str, Any], alias: str) -> set[str]:
    out: set[str] = set()
    for key in ("filter", "return"):
        for entry in intent.get(key) or []:
            if entry.get("alias") == alias and entry.get("property"):
                out.add(str(entry["property"]))
    return out


def _ontology_for_mode(
    mode: str,
    *,
    full_schema: dict[str, Any],
    full_ontology: dict[str, Any],
    question: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if mode == "full":
        return full_schema, full_ontology
    sub_schema, sub_ont, _ = prompt_views_for_question(question, full_schema, full_ontology)
    return sub_schema, sub_ont


def evaluate_case(
    engine: Any,
    extractor: Any,
    case: GoldCase,
    *,
    full_schema: dict[str, Any],
    full_ontology: dict[str, Any],
    condition: Condition,
    max_retries: int,
) -> dict[str, Any]:
    policy = CONDITION_TO_POLICY[condition]
    subset = subset_ontology(full_ontology, case.question)

    # Token estimate for the first-phase prompt (matches pipeline phase order).
    if policy == "full":
        first_schema, first_ont = full_schema, full_ontology
        first_mode = "full"
    else:
        if subset.empty:
            first_schema, first_ont = full_schema, full_ontology
            first_mode = "full"
        else:
            first_schema, first_ont = prompt_views_for_question(
                case.question, full_schema, full_ontology
            )[:2]
            first_mode = "subset"

    prompt = build_initial_user_message(case.question, first_schema, ontology=first_ont)
    tokens = approx_tokens(prompt)
    distractor = _preferred_distractor(case)
    distractor_visible_first = bool(distractor and distractor in _prop_names(first_ont))

    compile_ok = False
    compile_error: str | None = None
    used_fallback = False
    schema_mode = first_mode
    llm_calls = 0
    pred: dict[str, Any] | None = None
    soft: dict[str, float] = {"class_f1": 0.0, "rel_f1": 0.0, "prop_f1": 0.0}
    hit = 0.0
    near_dup_picked = False
    invent_without_seeing = False
    visible_props_final: set[str] = _prop_names(first_ont)

    try:
        outcome = extract_validated_intent(
            engine,
            extractor,
            case.question,
            full_schema,
            ontology=full_ontology,
            schema_policy=policy,  # type: ignore[arg-type]
            max_retries=max_retries,
        )
        pred = outcome.intent
        used_fallback = outcome.used_fallback
        schema_mode = outcome.schema_mode
        llm_calls = outcome.llm_calls
        compile_ok = True
        _, final_ont = _ontology_for_mode(
            schema_mode,
            full_schema=full_schema,
            full_ontology=full_ontology,
            question=case.question,
        )
        visible_props_final = _prop_names(final_ont)
        hit = property_hit(pred, case.intent)
        soft = intent_soft_f1(pred, case.intent)

        if case.corrupt_target and distractor:
            alias, gold_prop = case.corrupt_target
            pred_props = _pred_props_for_alias(pred, alias)
            if distractor in pred_props and gold_prop not in pred_props:
                near_dup_picked = True
                if distractor not in visible_props_final:
                    invent_without_seeing = True
    except Exception as exc:  # noqa: BLE001
        compile_error = str(exc)

    return {
        "id": case.id,
        "condition": condition,
        "schema_policy": policy,
        "schema_mode": schema_mode,
        "used_fallback": used_fallback,
        "approx_tokens": tokens,
        "first_schema_mode": first_mode,
        "distractor": distractor,
        "distractor_visible": distractor_visible_first,
        "near_dup_picked": near_dup_picked,
        "invent_without_seeing": invent_without_seeing,
        "property_hit": hit,
        "soft_f1": soft,
        "compile_ok": compile_ok,
        "compile_error": compile_error,
        "llm_calls": llm_calls,
        "subset_empty": subset.empty,
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tokens = [float(r["approx_tokens"]) for r in rows]
    hits = [float(r["property_hit"]) for r in rows]
    soft_prop = [float(r["soft_f1"]["prop_f1"]) for r in rows]
    calls = [float(r["llm_calls"]) for r in rows]
    return {
        "n": len(rows),
        "property_hit_mean": round(_mean(hits), 4),
        "soft_prop_f1_mean": round(_mean(soft_prop), 4),
        "compile_ok": sum(1 for r in rows if r["compile_ok"]),
        "compile_fail": sum(1 for r in rows if not r["compile_ok"]),
        "distractor_visible": sum(1 for r in rows if r["distractor_visible"]),
        "near_dup_picked": sum(1 for r in rows if r["near_dup_picked"]),
        "invent_without_seeing": sum(1 for r in rows if r["invent_without_seeing"]),
        "invent_without_seeing_rate": round(
            sum(1 for r in rows if r["invent_without_seeing"]) / len(rows) if rows else 0.0,
            4,
        ),
        "fallback_rate": round(
            sum(1 for r in rows if r["used_fallback"]) / len(rows) if rows else 0.0,
            4,
        ),
        "mean_llm_calls": round(_mean(calls), 4),
        "prompt_approx_tokens_p50": int(statistics.median(tokens)) if tokens else 0,
        "prompt_approx_tokens_p95": int(
            statistics.quantiles(tokens, n=20, method="inclusive")[18]
        )
        if len(tokens) >= 2
        else (int(tokens[0]) if tokens else 0),
    }


def run_profile(
    profile: str,
    *,
    extractor: Any,
    cases: list[GoldCase],
    max_retries: int,
) -> dict[str, Any]:
    import ontographia

    yaml_bytes, stats = generate_distractor_ontology(profile)
    engine = ontographia.Engine.from_bytes(yaml_bytes, "manufacturing.native.yaml")
    schema = engine.intent_json_schema()
    ontology = engine.ontology_json()

    by_condition: dict[str, Any] = {}
    qualitative: list[dict[str, Any]] = []

    for condition in CONDITIONS:
        rows = [
            evaluate_case(
                engine,
                extractor,
                case,
                full_schema=schema,
                full_ontology=ontology,
                condition=condition,
                max_retries=max_retries,
            )
            for case in cases
        ]
        by_condition[condition] = summarize_rows(rows)

        if condition == "full":
            for row in rows:
                if (row["near_dup_picked"] or row["invent_without_seeing"]) and len(
                    qualitative
                ) < 8:
                    qualitative.append(
                        {
                            "id": row["id"],
                            "distractor": row["distractor"],
                            "property_hit": row["property_hit"],
                            "near_dup_picked": row["near_dup_picked"],
                            "invent_without_seeing": row["invent_without_seeing"],
                            "distractor_visible": row["distractor_visible"],
                        }
                    )

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
        "n_cases": len(cases),
        "conditions": by_condition,
        "deltas_vs_full": deltas,
        "qualitative_full_errors": qualitative,
    }


def h1_live_verdict(results: list[dict[str, Any]]) -> dict[str, Any]:
    large = next((r for r in results if r["profile"] == "large"), None)
    if large is None:
        return {
            "verdict": "inconclusive",
            "reason": "large profile not run",
            "criteria": {},
            "caveat": "Live arm requires large profile for predeclared H1 criteria.",
        }

    full = large["conditions"]["full"]
    subset = large["conditions"]["subset"]
    fallback = large["conditions"]["subset_fallback"]

    def _delta(arm: dict[str, Any]) -> dict[str, Any]:
        hit_gain_pt = (arm["property_hit_mean"] - full["property_hit_mean"]) * 100
        token_rel = (
            arm["prompt_approx_tokens_p95"] / full["prompt_approx_tokens_p95"] - 1.0
            if full["prompt_approx_tokens_p95"]
            else 0.0
        )
        compile_ok = arm["compile_ok"] >= full["compile_ok"]
        return {
            "property_hit_gain_pt": round(hit_gain_pt, 2),
            "token_p95_rel_change": round(token_rel, 4),
            "compile_not_worse": compile_ok,
            "arm_compile_ok": arm["compile_ok"],
            "arm_property_hit": arm["property_hit_mean"],
            "arm_fallback_rate": arm.get("fallback_rate"),
            "invent_without_seeing_rate": arm.get("invent_without_seeing_rate"),
            "near_dup_picked": arm.get("near_dup_picked"),
        }

    subset_d = _delta(subset)
    fallback_d = _delta(fallback)

    criteria = {
        "property_hit_gain_threshold_pt": 10.0,
        "token_p95_reduction_threshold": -0.30,
        "full_compile_ok": full["compile_ok"],
        "full_property_hit": full["property_hit_mean"],
        "full_near_dup_picked": full.get("near_dup_picked"),
        "subset_only": subset_d,
        "subset_fallback": fallback_d,
    }

    # Primary live verdict uses the production policy (subset→full fallback / auto).
    hit_gain = fallback_d["property_hit_gain_pt"]
    token_rel = fallback_d["token_p95_rel_change"]
    compile_ok = fallback_d["compile_not_worse"]
    quality_up = hit_gain >= 10.0
    tokens_down = token_rel <= -0.30
    quality_flat = abs(hit_gain) < 10.0
    quality_down = hit_gain <= -10.0

    if quality_down:
        verdict = "reject"
        reason = (
            "live large subset_fallback: Property Hit fell by ≥10pt vs full"
        )
    elif quality_up and tokens_down and compile_ok:
        verdict = "support"
        reason = (
            "live large subset_fallback (recommended policy): Property Hit ≥ +10pt "
            "vs full, tokens p95 ≤ −30%, compile not worse; "
            f"subset-only alone was "
            f"hit {subset_d['property_hit_gain_pt']:+.1f}pt / "
            f"compile_ok {subset_d['arm_compile_ok']}/{full['compile_ok']}"
        )
    elif tokens_down and quality_flat and compile_ok:
        verdict = "partial_support"
        reason = (
            "live large subset_fallback: tokens down ≥30% with flat Property Hit"
        )
    elif tokens_down and compile_ok:
        verdict = "partial_support"
        reason = (
            "live large subset_fallback: tokens down; quality gain below +10pt "
            "or mixed vs full"
        )
    else:
        verdict = "inconclusive"
        reason = "live large subset_fallback: predeclared thresholds not met cleanly"

    return {
        "verdict": verdict,
        "reason": reason,
        "criteria": criteria,
        "caveat": (
            "Live OpenAI-compatible extractor (temperature=0). Primary verdict is "
            "on subset_fallback (schema_policy=auto), the production path from #45. "
            "subset-only is reported for ablation. invent_without_seeing counts "
            "near-duplicate picks absent from the final prompt property vocabulary. "
            "Mechanical H1 remains the prompt-vocab control experiment."
        ),
    }


def format_results_table(results: list[dict[str, Any]]) -> str:
    lines = [
        "Track A H1 live LLM",
        f"{'profile':<8} {'cond':<16} {'hit':>6} {'compile':>8} {'ndup':>5} "
        f"{'invent':>6} {'fb':>6} {'calls':>6} {'tok_p95':>8}",
    ]
    for row in results:
        for cond in CONDITIONS:
            c = row["conditions"][cond]
            lines.append(
                f"{row['profile']:<8} {cond:<16} {c['property_hit_mean']:>6.2f} "
                f"{c['compile_ok']:>3}/{c['n']:<4} {c['near_dup_picked']:>5} "
                f"{c['invent_without_seeing']:>6} {c['fallback_rate']:>6.2f} "
                f"{c['mean_llm_calls']:>6.2f} {c['prompt_approx_tokens_p95']:>8}"
            )
    return "\n".join(lines)


def write_baseline(
    payload: dict[str, Any],
    results: list[dict[str, Any]],
    verdict: dict[str, Any],
) -> tuple[Path, Path]:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = payload["meta"]["recorded_at"].replace(":", "").replace("-", "")[:15]
    json_path = BASELINES_DIR / "track_a_h1_live.json"
    md_path = BASELINES_DIR / "track_a_h1_live.md"
    dated_json = BASELINES_DIR / f"track_a_h1_live_{stamp}.json"

    text = json.dumps(payload, indent=2) + "\n"
    json_path.write_text(text, encoding="utf-8")
    dated_json.write_text(text, encoding="utf-8")

    meta = payload["meta"]
    qual_lines: list[str] = []
    for row in results:
        if row["profile"] != "large":
            continue
        for q in row.get("qualitative_full_errors") or []:
            kind = (
                "invent-without-seeing"
                if q.get("invent_without_seeing")
                else "near-dup pick"
            )
            qual_lines.append(
                f"- `{q['id']}`: {kind} distractor=`{q.get('distractor')}` "
                f"hit={q['property_hit']} visible={q.get('distractor_visible')}"
            )

    md = "\n".join(
        [
            "# Track A H1 live — full vs subset vs subset+fallback",
            "",
            f"- Recorded: `{meta['recorded_at']}`",
            f"- Git: `{meta.get('git_rev') or 'unknown'}`",
            f"- Model: `{meta.get('model')}`",
            f"- Base URL: `{meta.get('base_url')}`",
            f"- Harness: `examples/llm/eval/run_track_a_h1_live.py`",
            f"- Profiles: {', '.join(meta['profiles'])}",
            f"- Cases per condition: {meta.get('n_cases')}",
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
            "## Qualitative (large / full errors)",
            "",
            *(qual_lines or ["- (none)"]),
            "",
            "## Method",
            "",
            "Live OpenAI-compatible Intent extraction via "
            "`extract_validated_intent` with `schema_policy` mapped from "
            "H1 conditions. Tokens approximate the first-phase prompt. "
            "`invent_without_seeing` = preferred near-duplicate chosen while "
            "absent from the final prompt property list.",
            "",
            "Machine-readable: [`track_a_h1_live.json`](track_a_h1_live.json).",
            "",
            "```bash",
            "uv run python examples/llm/eval/run_track_a_h1_live.py "
            "--profiles mid,large --record",
            "```",
            "",
        ]
    )
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Track A H1 live-LLM arm (#68)")
    parser.add_argument("--profiles", default="mid,large")
    parser.add_argument("--limit", type=int, default=0, help="Max gold cases (0=all)")
    parser.add_argument("--backend", default=None, help="mock|openai (default: env)")
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--no-json-schema", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()

    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    for p in profiles:
        if p not in set(iter_profiles()):
            print(f"unknown profile: {p}", file=sys.stderr)
            return 2

    backend = args.backend or os.environ.get("ONTOGRAPHIA_LLM_BACKEND", "openai")
    extractor = create_extractor(
        backend,
        use_json_schema=not args.no_json_schema,
    )
    model = (
        getattr(extractor, "model", None)
        or getattr(extractor, "_model", None)
        or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    )
    base_url = (
        getattr(extractor, "base_url", None)
        or getattr(extractor, "_base_url", None)
        or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )

    cases = build_gold_cases()
    if args.limit and args.limit > 0:
        # Stratify: take first N/4 from each template family when possible.
        if args.limit < len(cases):
            families = ["bom_suppliers_", "line_plant_", "lot_defect_", "lot_line_"]
            per = max(1, args.limit // len(families))
            selected: list[GoldCase] = []
            for fam in families:
                fam_cases = [c for c in cases if c.id.startswith(fam)]
                selected.extend(fam_cases[:per])
            cases = selected[: args.limit]

    print(
        f"live H1: backend={backend} model={model} "
        f"profiles={profiles} n_cases={len(cases)} retries={args.max_retries}",
        flush=True,
    )

    results = [
        run_profile(
            p,
            extractor=extractor,
            cases=cases,
            max_retries=args.max_retries,
        )
        for p in profiles
    ]
    verdict = h1_live_verdict(results)
    payload = {
        "meta": {
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_rev": _git_rev(),
            "profiles": profiles,
            "conditions": list(CONDITIONS),
            "n_cases": len(cases),
            "max_retries": args.max_retries,
            "backend": backend,
            "model": model,
            "base_url": str(base_url).rstrip("/"),
            "study": "h1_live_llm",
            "issue": 68,
            "harness": "examples/llm/eval/run_track_a_h1_live.py",
        },
        "verdict": verdict,
        "results": results,
    }

    print()
    print(format_results_table(results))
    print()
    print(f"H1 live verdict: {verdict['verdict']}")
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
