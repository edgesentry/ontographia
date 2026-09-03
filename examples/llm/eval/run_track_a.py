"""Track A stress test: large ontology + silent wrong field selection.

Demonstrates Kervin's failure mode without requiring a live LLM:
gold Intents still compile, but near-duplicate distractor properties also
compile on mid/large ontologies (validation cannot see semantic wrongness).
Prompt size grows with full vocabulary dump.

Usage (from repo root):
  uv run python examples/llm/eval/run_track_a.py
  uv run python examples/llm/eval/run_track_a.py --profiles small,mid,large --write-ontologies
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(EXAMPLES))

from llm.eval.distractor import (  # noqa: E402
    generate_distractor_ontology,
    iter_profiles,
    write_ontology,
)
from llm.eval.gold import build_gold_cases, make_silent_wrong_intent  # noqa: E402
from llm.eval.metrics import approx_tokens, intent_soft_f1, property_hit  # noqa: E402
from llm.prompt import build_initial_user_message  # noqa: E402


def _mean(xs: list[float]) -> float:
    return float(statistics.fmean(xs)) if xs else 0.0


def run_profile(profile: str, *, sample_prompt_n: int = 5) -> dict[str, Any]:
    import ontographia

    yaml_bytes, stats = generate_distractor_ontology(profile)
    engine = ontographia.Engine.from_bytes(yaml_bytes, "manufacturing.native.yaml")
    schema = engine.intent_json_schema()
    ontology = engine.ontology_json()

    gold_cases = build_gold_cases()
    gold_ok = 0
    gold_fail = 0
    wrong_ok = 0
    wrong_fail = 0
    wrong_skipped = 0
    prop_hits_wrong: list[float] = []
    soft_prop_f1_wrong: list[float] = []

    for case in gold_cases:
        try:
            engine.build(case.intent)
            gold_ok += 1
        except Exception:
            gold_fail += 1
            continue

        if not case.corrupt_target:
            wrong_skipped += 1
            continue
        wrong = make_silent_wrong_intent(case.intent, case.corrupt_target)
        if wrong is None:
            wrong_skipped += 1
            continue
        prop_hits_wrong.append(property_hit(wrong, case.intent))
        soft_prop_f1_wrong.append(intent_soft_f1(wrong, case.intent)["prop_f1"])
        try:
            engine.build(wrong)
            wrong_ok += 1
        except Exception:
            wrong_fail += 1

    prompt_token_samples: list[int] = []
    prompt_char_samples: list[int] = []
    for case in gold_cases[:sample_prompt_n]:
        msg = build_initial_user_message(case.question, schema, ontology=ontology)
        prompt_char_samples.append(len(msg))
        prompt_token_samples.append(approx_tokens(msg))

    return {
        "profile": profile,
        "ontology": stats,
        "n_gold": len(gold_cases),
        "gold_compile_ok": gold_ok,
        "gold_compile_fail": gold_fail,
        "silent_wrong_compile_ok": wrong_ok,
        "silent_wrong_compile_fail": wrong_fail,
        "silent_wrong_skipped": wrong_skipped,
        "silent_wrong_property_hit_mean": round(_mean(prop_hits_wrong), 4),
        "silent_wrong_prop_f1_mean": round(_mean(soft_prop_f1_wrong), 4),
        "prompt_chars_p50": int(statistics.median(prompt_char_samples)),
        "prompt_approx_tokens_p50": int(statistics.median(prompt_token_samples)),
        "prompt_approx_tokens_max": max(prompt_token_samples) if prompt_token_samples else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Track A distractor ontology stress test")
    parser.add_argument(
        "--profiles",
        default="small,mid,large",
        help="Comma-separated: small,mid,large",
    )
    parser.add_argument(
        "--write-ontologies",
        action="store_true",
        help="Write generated YAML under examples/llm/eval/out/",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write full results JSON to this path",
    )
    args = parser.parse_args()
    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    for p in profiles:
        if p not in set(iter_profiles()):
            print(f"unknown profile: {p}", file=sys.stderr)
            return 2

    if args.write_ontologies:
        out_dir = EXAMPLES / "llm" / "eval" / "out"
        for p in profiles:
            path = write_ontology(p, out_dir)
            print(f"wrote {path}")

    results = [run_profile(p) for p in profiles]

    print()
    print("Track A stress test (full-schema prompt + compile)")
    print(
        f"{'profile':<8} {'props':>7} {'gold_ok':>8} {'wrong_ok':>8} "
        f"{'wrong_fail':>10} {'prop_hit':>8} {'tok_p50':>8}"
    )
    for row in results:
        print(
            f"{row['profile']:<8} {row['ontology']['properties']:>7} "
            f"{row['gold_compile_ok']:>8} {row['silent_wrong_compile_ok']:>8} "
            f"{row['silent_wrong_compile_fail']:>10} "
            f"{row['silent_wrong_property_hit_mean']:>8.2f} "
            f"{row['prompt_approx_tokens_p50']:>8}"
        )

    print()
    print(
        "Interpretation: on mid/large, silent_wrong_compile_ok ≈ gold_ok means "
        "Engine::build accepts plausible wrong fields (Kervin failure mode). "
        "On small, wrong_fail should be high because distractors are absent."
    )

    payload = {"results": results}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json_out}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
