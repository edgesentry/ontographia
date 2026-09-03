"""Track B: HF Text2Cypher schema → Ontographia + vocab coverage spot eval.

Requires the optional `datasets` package:
  uv run --with datasets python examples/llm/eval/run_track_b.py --record

Default scope: neo4jlabs demo DB rows whose schema starts with \"Node properties\".
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "examples"
EVAL_DIR = EXAMPLES / "llm" / "eval"
BASELINES_DIR = EVAL_DIR / "baselines"
sys.path.insert(0, str(EXAMPLES))

from llm.eval.schema_convert import (  # noqa: E402
    convert_schema_to_native_yaml,
    detect_schema_format,
    extract_cypher_vocab,
    vocab_coverage,
)


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


def _mean(xs: list[float]) -> float:
    return float(statistics.fmean(xs)) if xs else 0.0


def load_test_rows(
    *,
    dataset: str,
    split: str,
    refs: list[str] | None,
    limit_per_ref: int,
) -> list[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing dependency: install with\n"
            "  uv run --with datasets python examples/llm/eval/run_track_b.py ...\n"
            f"({exc})"
        ) from exc

    ds = load_dataset(dataset, split=split)
    by_ref: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ds:
        ref = row.get("database_reference_alias")
        schema = row.get("schema") or ""
        if not ref:
            continue
        if refs and ref not in refs:
            continue
        if detect_schema_format(schema) != "node_properties":
            continue
        if len(by_ref[ref]) >= limit_per_ref:
            continue
        by_ref[ref].append(
            {
                "question": row["question"],
                "schema": schema,
                "cypher": row["cypher"],
                "database_reference_alias": ref,
                "instance_id": row.get("instance_id"),
                "data_source": row.get("data_source"),
            }
        )
    rows: list[dict[str, Any]] = []
    for ref in sorted(by_ref):
        rows.extend(by_ref[ref])
    return rows


def evaluate_rows(
    rows: list[dict[str, Any]],
    *,
    write_ontologies_dir: Path | None,
) -> dict[str, Any]:
    import ontographia

    # One conversion per demo DB (schema text is repeated per question).
    schema_by_ref: dict[str, str] = {}
    for row in rows:
        ref = row["database_reference_alias"]
        schema_by_ref.setdefault(ref, row["schema"])

    per_ref: list[dict[str, Any]] = []
    engines: dict[str, Any] = {}
    convert_ok = 0
    convert_fail = 0
    load_ok = 0
    load_fail = 0

    for ref, schema in schema_by_ref.items():
        entry: dict[str, Any] = {"database_reference_alias": ref}
        try:
            result = convert_schema_to_native_yaml(schema)
            convert_ok += 1
            entry.update(
                {
                    "convert_ok": True,
                    "format": result.format,
                    "n_classes": len(result.classes),
                    "n_relationships": len(result.relationships),
                    "n_properties": result.properties,
                    "warnings": result.warnings,
                }
            )
            if write_ontologies_dir is not None:
                write_ontologies_dir.mkdir(parents=True, exist_ok=True)
                path = write_ontologies_dir / f"{ref}.native.yaml"
                path.write_text(result.yaml_text, encoding="utf-8")
                entry["ontology_path"] = str(path)
            try:
                engine = ontographia.Engine.from_bytes(
                    result.yaml_text.encode("utf-8"),
                    f"{ref}.native.yaml",
                )
                _ = engine.intent_json_schema()
                engines[ref] = engine
                load_ok += 1
                entry["engine_load_ok"] = True
            except Exception as exc:
                load_fail += 1
                entry["engine_load_ok"] = False
                entry["engine_error"] = str(exc)
        except Exception as exc:
            convert_fail += 1
            entry["convert_ok"] = False
            entry["convert_error"] = str(exc)
        per_ref.append(entry)

    label_cov: list[float] = []
    rel_cov: list[float] = []
    prop_cov: list[float] = []
    row_ok = 0
    row_skip = 0

    for row in rows:
        ref = row["database_reference_alias"]
        engine = engines.get(ref)
        if engine is None:
            row_skip += 1
            continue
        ont = engine.ontology_json()
        cov = vocab_coverage(extract_cypher_vocab(row["cypher"]), ont)
        label_cov.append(cov["label_coverage"])
        rel_cov.append(cov["rel_coverage"])
        prop_cov.append(cov["prop_coverage"])
        row_ok += 1

    return {
        "n_rows": len(rows),
        "n_refs": len(schema_by_ref),
        "convert_ok": convert_ok,
        "convert_fail": convert_fail,
        "engine_load_ok": load_ok,
        "engine_load_fail": load_fail,
        "coverage_rows": row_ok,
        "coverage_skipped": row_skip,
        "label_coverage_mean": round(_mean(label_cov), 4),
        "rel_coverage_mean": round(_mean(rel_cov), 4),
        "prop_coverage_mean": round(_mean(prop_cov), 4),
        "per_ref": per_ref,
    }


def write_baseline(payload: dict[str, Any]) -> tuple[Path, Path]:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    json_path = BASELINES_DIR / "track_b_schema_convert.json"
    md_path = BASELINES_DIR / "track_b_schema_convert.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    summary = payload["summary"]
    meta = payload["meta"]
    lines = [
        "# Track B baseline — Text2Cypher schema → Ontographia",
        "",
        f"- Recorded: `{meta['recorded_at']}`",
        f"- Git: `{meta.get('git_rev') or 'unknown'}`",
        f"- Dataset: `{meta['dataset']}` split `{meta['split']}`",
        f"- Filter: demo `database_reference_alias` + `Node properties` schema",
        f"- Limit per ref: {meta['limit_per_ref']}",
        "",
        "## Summary",
        "",
        f"| metric | value |",
        f"|--------|------:|",
        f"| demo DBs (refs) | {summary['n_refs']} |",
        f"| questions scored | {summary['coverage_rows']} |",
        f"| convert OK | {summary['convert_ok']} |",
        f"| convert fail | {summary['convert_fail']} |",
        f"| Engine.load OK | {summary['engine_load_ok']} |",
        f"| Engine.load fail | {summary['engine_load_fail']} |",
        f"| mean label coverage (gold Cypher ∩ ontology) | {summary['label_coverage_mean']} |",
        f"| mean relationship coverage | {summary['rel_coverage_mean']} |",
        f"| mean property coverage | {summary['prop_coverage_mean']} |",
        "",
        "## Per database",
        "",
        "| ref | classes | rels | props | load |",
        "|-----|--------:|-----:|------:|------|",
    ]
    for ref in summary["per_ref"]:
        if not ref.get("convert_ok"):
            lines.append(
                f"| `{ref['database_reference_alias']}` | — | — | — | convert fail |"
            )
            continue
        load = "ok" if ref.get("engine_load_ok") else "fail"
        lines.append(
            f"| `{ref['database_reference_alias']}` | {ref['n_classes']} | "
            f"{ref['n_relationships']} | {ref['n_properties']} | {load} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This measures **schema conversion external validity**, not Intent generation quality.",
            "Coverage asks whether labels/rels/properties appearing in gold Cypher exist in the",
            "converted ontology. Gaps usually mean missing relationship patterns in the schema text,",
            "or Cypher using tokens the heuristic extractor mis-parses.",
            "",
            "Regenerate:",
            "",
            "```bash",
            "uv run --with datasets python examples/llm/eval/run_track_b.py --record",
            "```",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Track B HF Text2Cypher → Ontographia spot eval")
    parser.add_argument("--dataset", default="neo4j/text2cypher-2025v1")
    parser.add_argument("--split", default="test")
    parser.add_argument(
        "--refs",
        default="",
        help="Comma-separated database_reference_alias filter (default: all demo refs)",
    )
    parser.add_argument("--limit-per-ref", type=int, default=20)
    parser.add_argument(
        "--write-ontologies",
        action="store_true",
        help="Write converted YAML under examples/llm/eval/out/track_b/",
    )
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    refs = [r.strip() for r in args.refs.split(",") if r.strip()] or None
    rows = load_test_rows(
        dataset=args.dataset,
        split=args.split,
        refs=refs,
        limit_per_ref=args.limit_per_ref,
    )
    if not rows:
        print("no rows matched filters", file=sys.stderr)
        return 2

    out_dir = EVAL_DIR / "out" / "track_b" if args.write_ontologies else None
    summary = evaluate_rows(rows, write_ontologies_dir=out_dir)
    payload = {
        "meta": {
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_rev": _git_rev(),
            "dataset": args.dataset,
            "split": args.split,
            "limit_per_ref": args.limit_per_ref,
            "refs_filter": refs,
            "harness": "examples/llm/eval/run_track_b.py",
            "license_note": "Dataset neo4j/text2cypher-2025v1 — check HF card before redistribution",
        },
        "summary": summary,
    }

    print(
        f"refs={summary['n_refs']} rows={summary['coverage_rows']} "
        f"convert_ok={summary['convert_ok']}/{summary['n_refs']} "
        f"load_ok={summary['engine_load_ok']}/{summary['n_refs']} "
        f"label_cov={summary['label_coverage_mean']:.3f} "
        f"rel_cov={summary['rel_coverage_mean']:.3f} "
        f"prop_cov={summary['prop_coverage_mean']:.3f}"
    )

    if args.record:
        j, m = write_baseline(payload)
        print(f"recorded {j}")
        print(f"recorded {m}")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json_out}")
    elif not args.record:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
