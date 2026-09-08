"""Track B Exec Match spot eval (issue #53).

Question → LLM Intent → Engine.build → exec on demo.neo4jlabs.com
compared to gold Cypher execution (row-set Jaccard).

Default scope: neo4jlabs movies (+ optional recommendations), 50–100 questions.

Usage:
  source scripts/litellm/use-provider.sh gemini
  uv run --with datasets --with neo4j python examples/llm/eval/run_track_b_exec.py --record
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
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
from llm.extractors import create_extractor  # noqa: E402
from llm.pipeline import extract_validated_intent  # noqa: E402

DEFAULT_REFS = (
    "neo4jlabs_demo_db_movies",
    "neo4jlabs_demo_db_recommendations",
)

DEMO_URI = "neo4j+s://demo.neo4jlabs.com"
_WRITE_RE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV)\b",
    re.IGNORECASE,
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


def _normalize_cypher(cypher: str) -> str:
    """HF rows often embed literal \\n / \\t sequences instead of real newlines."""
    text = cypher or ""
    if "\\n" in text and "\n" not in text:
        text = text.replace("\\n", "\n")
    if "\\t" in text:
        text = text.replace("\\t", "\t")
    return text.strip()


def _is_read_only(cypher: str) -> bool:
    return _WRITE_RE.search(cypher or "") is None


def _mean(xs: list[float]) -> float:
    return float(statistics.fmean(xs)) if xs else 0.0


def _db_name(ref: str) -> str:
    # neo4jlabs_demo_db_movies → movies
    prefix = "neo4jlabs_demo_db_"
    if ref.startswith(prefix):
        return ref[len(prefix) :]
    return ref


def _row_fingerprint(row: dict[str, Any]) -> str:
    """Stable hash for comparing Neo4j result rows (order-insensitive set)."""
    items = []
    for k in sorted(row.keys()):
        v = row[k]
        try:
            items.append((k, json.dumps(v, sort_keys=True, default=str)))
        except TypeError:
            items.append((k, str(v)))
    blob = json.dumps(items, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def jaccard_rows(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> float:
    sa = {_row_fingerprint(r) for r in a}
    sb = {_row_fingerprint(r) for r in b}
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def load_spot_rows(
    *,
    dataset: str,
    split: str,
    refs: list[str],
    n: int,
    seed: int,
) -> list[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Missing dependency: install with\n"
            "  uv run --with datasets --with neo4j python "
            "examples/llm/eval/run_track_b_exec.py ...\n"
            f"({exc})"
        ) from exc

    ds = load_dataset(dataset, split=split)
    by_ref: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ds:
        ref = row.get("database_reference_alias")
        schema = row.get("schema") or ""
        if ref not in refs:
            continue
        if detect_schema_format(schema) != "node_properties":
            continue
        by_ref[ref].append(
            {
                "question": row["question"],
                "schema": schema,
                "cypher": row["cypher"],
                "database_reference_alias": ref,
                "instance_id": row.get("instance_id"),
            }
        )

    rng = random.Random(seed)
    # Stratify across refs, then fill to n.
    per = max(1, n // max(1, len(refs)))
    selected: list[dict[str, Any]] = []
    for ref in refs:
        pool = list(by_ref.get(ref) or [])
        rng.shuffle(pool)
        selected.extend(pool[:per])
    if len(selected) < n:
        rest: list[dict[str, Any]] = []
        for ref in refs:
            pool = list(by_ref.get(ref) or [])
            for row in pool:
                if row not in selected:
                    rest.append(row)
        rng.shuffle(rest)
        selected.extend(rest[: n - len(selected)])
    return selected[:n]


def _exec_cypher(
    driver: Any,
    cypher: str,
    params: dict[str, Any] | None = None,
    *,
    database: str | None = None,
) -> list[dict[str, Any]]:
    params = params or {}
    cypher = _normalize_cypher(cypher)
    with driver.session(database=database) as session:
        result = session.run(cypher, params)
        return [dict(record) for record in result]


def _structure_overlap(pred_cypher: str, gold_cypher: str) -> dict[str, float]:
    pred = extract_cypher_vocab(pred_cypher)
    gold = extract_cypher_vocab(gold_cypher)

    def _f1(a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        tp = len(a & b)
        p = tp / len(a)
        r = tp / len(b)
        return 0.0 if p + r == 0 else 2 * p * r / (p + r)

    return {
        "label_f1": _f1(pred["labels"], gold["labels"]),
        "rel_f1": _f1(pred["relationships"], gold["relationships"]),
        "prop_f1": _f1(pred["properties"], gold["properties"]),
    }


def evaluate(
    rows: list[dict[str, Any]],
    *,
    extractor: Any,
    schema_policy: str,
    max_retries: int,
    skip_exec: bool,
    repair_mapping_path: str | None,
) -> dict[str, Any]:
    import ontographia

    try:
        from neo4j import GraphDatabase
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "neo4j package required: uv run --with neo4j --with datasets ..."
        ) from exc

    # Convert once per DB.
    schema_by_ref: dict[str, str] = {}
    for row in rows:
        schema_by_ref.setdefault(row["database_reference_alias"], row["schema"])

    engines: dict[str, Any] = {}
    drivers: dict[str, Any] = {}
    for ref, schema in schema_by_ref.items():
        converted = convert_schema_to_native_yaml(schema)
        engine = ontographia.Engine.from_bytes(
            converted.yaml_text.encode("utf-8"),
            f"{ref}.native.yaml",
        )
        engines[ref] = engine
        if not skip_exec:
            db = _db_name(ref)
            drivers[ref] = GraphDatabase.driver(DEMO_URI, auth=(db, db))

    case_rows: list[dict[str, Any]] = []
    try:
        for i, row in enumerate(rows):
            ref = row["database_reference_alias"]
            engine = engines[ref]
            schema = engine.intent_json_schema()
            ontology = engine.ontology_json()
            entry: dict[str, Any] = {
                "i": i,
                "ref": ref,
                "db": _db_name(ref),
                "instance_id": row.get("instance_id"),
                "question": row["question"],
            }
            gold_cypher = _normalize_cypher(row["cypher"])
            gold_vocab = extract_cypher_vocab(gold_cypher)
            entry["gold_vocab_coverage"] = vocab_coverage(gold_vocab, ontology)
            if not _is_read_only(gold_cypher):
                entry["compile_ok"] = None
                entry["exec_match"] = None
                entry["jaccard"] = None
                entry["note"] = "skipped_write_gold"
                entry["structure"] = {"label_f1": 0.0, "rel_f1": 0.0, "prop_f1": 0.0}
                case_rows.append(entry)
                continue

            try:
                outcome = extract_validated_intent(
                    engine,
                    extractor,
                    row["question"],
                    schema,
                    ontology=ontology,
                    schema_policy=schema_policy,  # type: ignore[arg-type]
                    max_retries=max_retries,
                    repair_mapping_path=repair_mapping_path,
                )
                entry["compile_ok"] = True
                entry["schema_mode"] = outcome.schema_mode
                entry["used_fallback"] = outcome.used_fallback
                entry["llm_calls"] = outcome.llm_calls
                pred_cypher = outcome.result.get("query") or ""
                pred_params = outcome.result.get("params") or {}
                entry["structure"] = _structure_overlap(pred_cypher, gold_cypher)
            except Exception as exc:  # noqa: BLE001
                entry["compile_ok"] = False
                entry["compile_error"] = str(exc)
                entry["structure"] = {"label_f1": 0.0, "rel_f1": 0.0, "prop_f1": 0.0}
                entry["exec_match"] = None
                entry["jaccard"] = None
                entry["note"] = "compile_failed"
                case_rows.append(entry)
                continue

            if skip_exec:
                entry["exec_match"] = None
                entry["jaccard"] = None
                entry["note"] = "skip_exec"
                case_rows.append(entry)
                continue

            driver = drivers[ref]
            db = _db_name(ref)
            try:
                gold_rows = _exec_cypher(driver, gold_cypher, database=db)
                pred_rows = _exec_cypher(driver, pred_cypher, pred_params, database=db)
                jac = jaccard_rows(pred_rows, gold_rows)
                entry["jaccard"] = round(jac, 4)
                entry["exec_match"] = jac >= 1.0 - 1e-9
                entry["gold_row_count"] = len(gold_rows)
                entry["pred_row_count"] = len(pred_rows)
                entry["note"] = "ok" if entry["exec_match"] else "exec_mismatch"
            except Exception as exc:  # noqa: BLE001
                entry["jaccard"] = None
                entry["exec_match"] = False
                entry["exec_error"] = str(exc)
                entry["note"] = "exec_error"

            case_rows.append(entry)
            if (i + 1) % 10 == 0:
                print(f"  … {i + 1}/{len(rows)}", flush=True)
    finally:
        for d in drivers.values():
            d.close()

    compiled = [r for r in case_rows if r.get("compile_ok")]
    execed = [r for r in case_rows if r.get("jaccard") is not None]
    summary = {
        "n": len(case_rows),
        "compile_ok": len(compiled),
        "compile_rate": round(len(compiled) / len(case_rows), 4) if case_rows else 0.0,
        "exec_scored": len(execed),
        "exec_match": sum(1 for r in execed if r.get("exec_match")),
        "exec_match_rate": round(
            sum(1 for r in execed if r.get("exec_match")) / len(execed), 4
        )
        if execed
        else None,
        "jaccard_mean": round(_mean([float(r["jaccard"]) for r in execed]), 4)
        if execed
        else None,
        "structure_label_f1_mean": round(
            _mean([float(r["structure"]["label_f1"]) for r in compiled]), 4
        )
        if compiled
        else 0.0,
        "structure_rel_f1_mean": round(
            _mean([float(r["structure"]["rel_f1"]) for r in compiled]), 4
        )
        if compiled
        else 0.0,
        "structure_prop_f1_mean": round(
            _mean([float(r["structure"]["prop_f1"]) for r in compiled]), 4
        )
        if compiled
        else 0.0,
        "by_ref": {},
    }
    for ref in sorted({r["ref"] for r in case_rows}):
        subset = [r for r in case_rows if r["ref"] == ref]
        sub_exec = [r for r in subset if r.get("jaccard") is not None]
        summary["by_ref"][ref] = {
            "n": len(subset),
            "compile_ok": sum(1 for r in subset if r.get("compile_ok")),
            "exec_match_rate": round(
                sum(1 for r in sub_exec if r.get("exec_match")) / len(sub_exec), 4
            )
            if sub_exec
            else None,
            "jaccard_mean": round(_mean([float(r["jaccard"]) for r in sub_exec]), 4)
            if sub_exec
            else None,
        }

    qualitative = [
        {
            "instance_id": r.get("instance_id"),
            "ref": r["ref"],
            "note": r.get("note"),
            "jaccard": r.get("jaccard"),
            "question": (r.get("question") or "")[:120],
        }
        for r in case_rows
        if r.get("note") not in {"ok", "skip_exec"}
    ][:12]

    return {"summary": summary, "cases": case_rows, "qualitative": qualitative}


def write_baseline(payload: dict[str, Any]) -> tuple[Path, Path]:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    json_path = BASELINES_DIR / "track_b_exec_spot.json"
    md_path = BASELINES_DIR / "track_b_exec_spot.md"
    stamp = payload["meta"]["recorded_at"].replace(":", "").replace("-", "")[:15]
    dated = BASELINES_DIR / f"track_b_exec_spot_{stamp}.json"
    text = json.dumps(payload, indent=2) + "\n"
    json_path.write_text(text, encoding="utf-8")
    dated.write_text(text, encoding="utf-8")

    meta = payload["meta"]
    s = payload["results"]["summary"]
    md = "\n".join(
        [
            "# Track B Exec Match — spot evaluation",
            "",
            f"- Recorded: `{meta['recorded_at']}`",
            f"- Git: `{meta.get('git_rev') or 'unknown'}`",
            f"- Model: `{meta.get('model')}`",
            f"- Refs: {', '.join(meta['refs'])}",
            f"- N: {meta['n']} (seed={meta['seed']})",
            f"- URI: `{meta['neo4j_uri']}`",
            "",
            "## Summary",
            "",
            f"- Compile OK: {s['compile_ok']}/{s['n']} ({s['compile_rate']})",
            f"- Exec Match: {s.get('exec_match')} / {s.get('exec_scored')} "
            f"(rate={s.get('exec_match_rate')})",
            f"- Jaccard mean: {s.get('jaccard_mean')}",
            f"- Structure F1 (label/rel/prop): "
            f"{s['structure_label_f1_mean']} / {s['structure_rel_f1_mean']} / "
            f"{s['structure_prop_f1_mean']}",
            "",
            "## Claim boundary",
            "",
            "Spot external validity for Intent → deterministic Cypher on public demo DBs. "
            "No Intent Exact Match (HF gold is Cypher). Not a Text2Cypher SOTA claim; "
            "not comparable to Track A H1–H3 mechanical support.",
            "",
            "```bash",
            "uv run --with datasets --with neo4j python "
            "examples/llm/eval/run_track_b_exec.py --record",
            "```",
            "",
        ]
    )
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Track B Exec Match spot (#53)")
    parser.add_argument("--dataset", default="neo4j/text2cypher-2025v1")
    parser.add_argument("--split", default="test")
    parser.add_argument(
        "--refs",
        default=",".join(DEFAULT_REFS),
        help="Comma-separated database_reference_alias values",
    )
    parser.add_argument("--n", type=int, default=60)
    parser.add_argument("--seed", type=int, default=53)
    parser.add_argument("--schema-policy", default="auto", choices=("auto", "subset", "full"))
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--backend", default=None)
    parser.add_argument("--no-json-schema", action="store_true")
    parser.add_argument(
        "--repair-mapping",
        default="",
        help="Optional repair mapping path (empty = manufacturing default; "
        "use movies mapping for movie DBs)",
    )
    parser.add_argument("--skip-exec", action="store_true", help="Structure-only (no Neo4j)")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    refs = [r.strip() for r in args.refs.split(",") if r.strip()]
    rows = load_spot_rows(
        dataset=args.dataset,
        split=args.split,
        refs=refs,
        n=args.n,
        seed=args.seed,
    )
    print(f"loaded {len(rows)} questions across {refs}", flush=True)

    backend = args.backend or os.environ.get("ONTOGRAPHIA_LLM_BACKEND", "openai")
    extractor = create_extractor(backend, use_json_schema=not args.no_json_schema)
    model = (
        getattr(extractor, "_model", None)
        or os.environ.get("OPENAI_MODEL", "unknown")
    )

    # Prefer movies mapping when only movie-like DBs; else default manufacturing
    # (mostly no-ops on movie questions) unless overridden.
    repair_path = args.repair_mapping or None
    if repair_path == "":
        repair_path = None
    if repair_path is None and all("movies" in r or "recommendations" in r for r in refs):
        repair_path = str(
            EXAMPLES / "llm" / "mappings" / "movies.repair.yaml"
        )

    results = evaluate(
        rows,
        extractor=extractor,
        schema_policy=args.schema_policy,
        max_retries=args.max_retries,
        skip_exec=args.skip_exec,
        repair_mapping_path=repair_path,
    )
    payload = {
        "meta": {
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_rev": _git_rev(),
            "issue": 53,
            "harness": "examples/llm/eval/run_track_b_exec.py",
            "dataset": args.dataset,
            "split": args.split,
            "refs": refs,
            "n": len(rows),
            "seed": args.seed,
            "schema_policy": args.schema_policy,
            "model": model,
            "neo4j_uri": DEMO_URI if not args.skip_exec else None,
            "skip_exec": args.skip_exec,
            "repair_mapping_path": repair_path,
            "selection": (
                f"HF {args.dataset} {args.split}; Node properties only; "
                f"refs={refs}; stratified sample n={args.n} seed={args.seed}"
            ),
            "license_note": "Dataset neo4j/text2cypher-2025v1 — check HF card before redistribution",
        },
        "results": {
            "summary": results["summary"],
            "qualitative": results["qualitative"],
            # Keep cases out of default committed baseline size; store summary-focused.
            "cases_sample": results["cases"][:5],
        },
    }

    s = results["summary"]
    print(
        f"compile {s['compile_ok']}/{s['n']} exec_match "
        f"{s.get('exec_match')}/{s.get('exec_scored')} "
        f"jaccard_mean={s.get('jaccard_mean')}"
    )

    if args.record:
        # Full cases in dated file only
        full = dict(payload)
        full["results"] = results
        jp, mp = write_baseline(payload)
        stamp = payload["meta"]["recorded_at"].replace(":", "").replace("-", "")[:15]
        (BASELINES_DIR / f"track_b_exec_spot_{stamp}_full.json").write_text(
            json.dumps(full, indent=2) + "\n", encoding="utf-8"
        )
        print(f"recorded {jp}")
        print(f"recorded {mp}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
