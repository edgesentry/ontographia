#!/usr/bin/env python3
"""Summarize repeated Track A H1 live runs (Part 3 remeasure, issue #142).

Reads the ``json/run*.json`` files written by
``examples/llm/eval/run_track_a_h1_live.py --json-out ...`` and writes:

- ``aggregate.json``       per profile / condition means and ranges across runs
- ``aggregate_index.json`` index of the repeat set (files + per-run meta)
- ``aggregate.md``         markdown table for pasting next to the published tables

Standard library only. It never invents numbers: every value comes from the run
JSONs, and a run that is missing a profile/condition is simply not counted for
that cell.

Usage:
  python3 scripts/remeasure/aggregate_h1_live.py \
      --out-dir examples/llm/eval/out/remeasure-h1-live-20261101T000000Z
  python3 scripts/remeasure/aggregate_h1_live.py --out-dir DIR --json-glob 'run*.json' --no-write
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONDITIONS = ("full", "subset", "subset_fallback")


def natural_key(path: Path) -> list[Any]:
    return [
        int(part) if part.isdigit() else part
        for part in re.split(r"(\d+)", path.name)
    ]


def mean(values: list[float]) -> float | None:
    return round(float(statistics.fmean(values)), 4) if values else None


def load_run(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise SystemExit(f"error: {path} has no 'results' list (not an H1 run JSON)")
    return payload


def arm_values(arm: dict[str, Any]) -> dict[str, float]:
    return {
        "property_hit_mean": float(arm.get("property_hit_mean") or 0.0),
        "compile_ok": float(arm.get("compile_ok") or 0),
        "n": float(arm.get("n") or 0),
        "fallback_rate": float(arm.get("fallback_rate") or 0.0),
        "mean_llm_calls": float(arm.get("mean_llm_calls") or 0.0),
        "prompt_approx_tokens_p95": float(arm.get("prompt_approx_tokens_p95") or 0.0),
        "near_dup_picked": float(arm.get("near_dup_picked") or 0),
        "invent_without_seeing": float(arm.get("invent_without_seeing") or 0),
    }


def summarize(runs: list[tuple[Path, dict[str, Any]]]) -> dict[str, Any]:
    buckets: dict[str, dict[str, list[dict[str, float]]]] = {}
    for _, payload in runs:
        for row in payload["results"]:
            if not isinstance(row, dict):
                continue
            profile = str(row.get("profile"))
            conditions = row.get("conditions") or {}
            for condition in CONDITIONS:
                arm = conditions.get(condition)
                if not isinstance(arm, dict):
                    continue
                buckets.setdefault(profile, {}).setdefault(condition, []).append(
                    arm_values(arm)
                )

    metrics: dict[str, Any] = {}
    for profile in sorted(buckets):
        metrics[profile] = {}
        for condition in CONDITIONS:
            arms = buckets[profile].get(condition) or []
            if not arms:
                continue

            def column(name: str) -> list[float]:
                return [arm[name] for arm in arms]

            hits = column("property_hit_mean")
            p95s = column("prompt_approx_tokens_p95")
            metrics[profile][condition] = {
                "runs": len(arms),
                "n_total": int(sum(column("n"))),
                "property_hit_mean": mean(hits),
                "property_hit_min": round(min(hits), 4),
                "property_hit_max": round(max(hits), 4),
                "compile_ok": int(sum(column("compile_ok"))),
                "compile_ok_rate": mean(
                    [
                        ok / n if n else 0.0
                        for ok, n in zip(column("compile_ok"), column("n"))
                    ]
                ),
                "fallback_rate_mean": mean(column("fallback_rate")),
                "mean_llm_calls_mean": mean(column("mean_llm_calls")),
                "prompt_tokens_p95_mean": mean(p95s),
                "prompt_tokens_p95_min": round(min(p95s), 1),
                "prompt_tokens_p95_max": round(max(p95s), 1),
                "near_dup_picked_total": int(sum(column("near_dup_picked"))),
                "invent_without_seeing_total": int(
                    sum(column("invent_without_seeing"))
                ),
            }
    return metrics


def format_markdown(metrics: dict[str, Any], runs: int) -> str:
    lines = [
        "# H1 live remeasure aggregate",
        "",
        f"- Runs: {runs}",
        "",
        "| profile | condition | runs | Property Hit (mean, min–max) | compile OK | "
        "fallback | ≈tok p95 (mean) | LLM calls |",
        "|---------|-----------|-----:|------------------------------|-----------:|"
        "---------:|-----------------:|----------:|",
    ]
    for profile in sorted(metrics):
        for condition in CONDITIONS:
            cell = metrics[profile].get(condition)
            if cell is None:
                continue
            lines.append(
                f"| {profile} | {condition} | {cell['runs']} | "
                f"{cell['property_hit_mean']:.2f} "
                f"({cell['property_hit_min']:.2f}–{cell['property_hit_max']:.2f}) | "
                f"{cell['compile_ok']}/{cell['n_total']} | "
                f"{cell['fallback_rate_mean']:.2f} | "
                f"{cell['prompt_tokens_p95_mean']:,.0f} | "
                f"{cell['mean_llm_calls_mean']:.2f} |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("."),
        help="repeat-set directory containing json/run*.json (default: .)",
    )
    parser.add_argument(
        "--json-glob",
        default="run*.json",
        help="glob under <out-dir>/json (default: run*.json)",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="print the markdown table only; do not write aggregate files",
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    json_dir = out_dir / "json"
    files = sorted(json_dir.glob(args.json_glob), key=natural_key)
    if not files:
        print(f"error: no {args.json_glob} under {json_dir}", file=sys.stderr)
        return 1

    runs = [(path, load_run(path)) for path in files]
    metrics = summarize(runs)

    per_run = []
    for path, payload in runs:
        meta = payload.get("meta") or {}
        verdict = payload.get("verdict") or {}
        per_run.append(
            {
                "file": path.name,
                "recorded_at": meta.get("recorded_at"),
                "git_rev": meta.get("git_rev"),
                "model": meta.get("model"),
                "base_url": meta.get("base_url"),
                "profiles": meta.get("profiles"),
                "n_cases": meta.get("n_cases"),
                "verdict": verdict.get("verdict"),
            }
        )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    aggregate = {
        "generated_at": generated_at,
        "issue": 142,
        "harness": "examples/llm/eval/run_track_a_h1_live.py",
        "runs": len(files),
        "files": [path.name for path in files],
        "metrics": metrics,
    }
    index = {
        "generated_at": generated_at,
        "issue": 142,
        "runs": len(files),
        "files": [path.name for path in files],
        "per_run": per_run,
        "metrics_file": "aggregate.json" if not args.no_write else None,
    }

    markdown = format_markdown(metrics, len(files))
    print(markdown, end="")

    if not args.no_write:
        (out_dir / "aggregate.json").write_text(
            json.dumps(aggregate, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / "aggregate_index.json").write_text(
            json.dumps(index, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / "aggregate.md").write_text(markdown, encoding="utf-8")
        print(f"wrote {out_dir / 'aggregate.json'}")
        print(f"wrote {out_dir / 'aggregate_index.json'}")
        print(f"wrote {out_dir / 'aggregate.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
