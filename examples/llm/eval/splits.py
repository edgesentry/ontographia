"""Frozen stratified splits for the Track A gold set (issue #96, step 2).

The 40 Track A gold cases fall into 4 strata (one per gold template, 10 cases
each). The frozen split ``track_a_v1``:

- holds out 2 cases per stratum (8 total) as the ``test`` partition — never
  used for prompt tuning;
- assigns the remaining 32 cases to 4 folds (2 per stratum per fold) for
  cross-validation on the ``dev`` partition.

Regeneration is deterministic: ``build_split()`` with the fixed seed always
reproduces the committed ``splits/track_a_v1.json`` byte for byte, and
``load_split()`` refuses to run when the current gold set no longer matches
the frozen ``gold_hash``.

Usage (from repo root):
  uv run python examples/llm/eval/splits.py            # print the split JSON
  uv run python examples/llm/eval/splits.py --write    # regenerate splits/track_a_v1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from llm.eval.gold import build_gold_cases
else:
    from .gold import build_gold_cases

SCHEMA_VERSION = "1.0"
DEFAULT_SPLIT_ID = "track_a_v1"
SPLIT_VERSION = "1.0.0"
SEED = 9602
N_FOLDS = 4
HELD_OUT_PER_STRATUM = 2

SPLIT_DIR = Path(__file__).resolve().parent / "splits"


def gold_fingerprint() -> str:
    """sha256 over the normalized JSON of the Track A gold set.

    Normalization: only ``id`` / ``question`` / ``intent`` per case, keys
    sorted, compact separators — so formatting churn elsewhere cannot change
    the hash, but any semantic gold edit does.
    """
    norm = [
        {"id": c.id, "question": c.question, "intent": c.intent}
        for c in build_gold_cases()
    ]
    blob = json.dumps(norm, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _stratum(case_id: str) -> str:
    """Gold template name: the case id without its trailing ``_NN`` index."""
    return re.sub(r"_\d+$", "", case_id)


def build_split(split_id: str = DEFAULT_SPLIT_ID, seed: int = SEED) -> dict[str, Any]:
    """Deterministically build the frozen split structure.

    Per stratum (sorted by name, ids sorted then shuffled with the fixed
    seed): the first ``HELD_OUT_PER_STRATUM`` go to ``test``; the rest are
    dealt round-robin into ``N_FOLDS`` folds, giving 2 per stratum per fold.
    """
    import random

    cases = build_gold_cases()
    strata: dict[str, list[str]] = {}
    for case in cases:
        strata.setdefault(_stratum(case.id), []).append(case.id)

    rng = random.Random(seed)
    held_out: list[str] = []
    folds: list[list[str]] = [[] for _ in range(N_FOLDS)]
    for name in sorted(strata):
        ids = sorted(strata[name])
        rng.shuffle(ids)
        held_out.extend(sorted(ids[:HELD_OUT_PER_STRATUM]))
        for i, case_id in enumerate(ids[HELD_OUT_PER_STRATUM:]):
            folds[i % N_FOLDS].append(case_id)

    return {
        "schema_version": SCHEMA_VERSION,
        "split_id": split_id,
        "version": SPLIT_VERSION,
        "seed": seed,
        "gold_hash": gold_fingerprint(),
        "n_gold": len(cases),
        "held_out_per_stratum": HELD_OUT_PER_STRATUM,
        "n_folds": N_FOLDS,
        "strata": {name: sorted(ids) for name, ids in sorted(strata.items())},
        "partitions": {
            "test": sorted(held_out),
            "folds": [
                {"fold": i, "ids": sorted(ids)} for i, ids in enumerate(folds)
            ],
        },
    }


def split_path(split_id: str = DEFAULT_SPLIT_ID) -> Path:
    return SPLIT_DIR / f"{split_id}.json"


def write_split(split_id: str = DEFAULT_SPLIT_ID) -> Path:
    """Regenerate the committed split file (deterministic)."""
    path = split_path(split_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_split(split_id), indent=2) + "\n", encoding="utf-8")
    return path


def verify_gold_hash(split: dict[str, Any]) -> None:
    """Fail when the current gold set no longer matches the frozen split."""
    current = gold_fingerprint()
    if split.get("gold_hash") != current:
        raise ValueError(
            f"gold hash mismatch for split {split.get('split_id')!r}: "
            f"frozen {split.get('gold_hash')!r} vs current {current!r}. "
            "The Track A gold set changed; either revert the gold edit or "
            "mint a new split version (do not silently re-freeze)."
        )


def load_split(split_id: str = DEFAULT_SPLIT_ID, verify: bool = True) -> dict[str, Any]:
    """Load a committed split by id; verify the gold hash by default."""
    path = split_path(split_id)
    if not path.is_file():
        raise FileNotFoundError(f"unknown split {split_id!r}: no {path}")
    split = json.loads(path.read_text(encoding="utf-8"))
    if verify:
        verify_gold_hash(split)
    return split


def all_ids(split: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for ids in split["strata"].values():
        out.extend(ids)
    return sorted(out)


def fold_ids(split: dict[str, Any], fold: int) -> list[str]:
    for entry in split["partitions"]["folds"]:
        if entry["fold"] == fold:
            return list(entry["ids"])
    raise ValueError(
        f"split {split['split_id']!r} has no fold {fold} "
        f"(0..{len(split['partitions']['folds']) - 1})"
    )


def dev_ids(split: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for entry in split["partitions"]["folds"]:
        out.extend(entry["ids"])
    return sorted(out)


def partition_ids(split: dict[str, Any], partition: str) -> list[str]:
    """Resolve a partition selector to gold case ids.

    ``all`` (every gold case), ``test`` (held-out), ``dev`` (union of folds),
    ``fold:N`` (one fold), ``cv`` (all folds — callers wanting per-fold
    results should iterate ``split['partitions']['folds']`` themselves).
    """
    if partition == "all":
        return all_ids(split)
    if partition == "test":
        return list(split["partitions"]["test"])
    if partition in ("dev", "cv"):
        return dev_ids(split)
    m = re.fullmatch(r"fold:(\d+)", partition)
    if m:
        return fold_ids(split, int(m.group(1)))
    raise ValueError(
        f"unknown partition {partition!r} (expected all | dev | test | cv | fold:N)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", default=DEFAULT_SPLIT_ID)
    parser.add_argument(
        "--write",
        action="store_true",
        help="regenerate the committed split file instead of printing",
    )
    args = parser.parse_args()
    split = build_split(args.split)
    if args.write:
        path = split_path(args.split)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}", file=sys.stderr)
    else:
        print(json.dumps(split, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
