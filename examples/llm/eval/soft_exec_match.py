"""Soft Exec Match result-level scorer for Track B (issue #73).

Normalizes execution result rows by dropping column aliases, coercing scalar
values into canonical comparable representations, and comparing row multisets
(order-independent) via value-multiset Jaccard and F1. Optionally computes
entity-set Jaccard when node IDs or primary-key-like values are present on
both sides.

Unlike ``run_track_b_exec.jaccard_rows``, which hashes ``(column_key, value)``
pairs over unique rows, Soft Exec Match strips column keys and compares the
multiset of normalized value tuples so cosmetic projection aliases (e.g.
``m.title`` vs ``movie_title``) or column ordering do not penalize equivalent
results.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any, Mapping, Sequence

FLOAT_REL_TOL = 1e-9
FLOAT_ABS_TOL = 1e-9
FLOAT_SIG_DIGITS = 9

# Candidate keys for primary-key / node-id extraction (normalized lowercase).
_EXPLICIT_ID_KEYS = frozenset(
    {
        "id",
        "_id",
        "node_id",
        "element_id",
        "elementid",
        "identity",
        "uuid",
        "uid",
        " movieid",
        "movieid",
        "personid",
        "userid",
        "tmdb_id",
        "tmdbid",
        "imdb_id",
        "imdbid",
    }
)
_ID_SUFFIXES = ("_id", ".id", "id")


def coerce_scalar(val: Any) -> tuple[str, Any]:
    """Coerce a scalar or structured cell value into a canonical sortable pair.

    Returns a ``(type_tag, canonical_value)`` tuple that is both hashable and
    totality-sortable across heterogeneous types:
    - ``None`` stays ``("null", "")`` (distinct from ``0``, ``False``, ``""``)
    - ``bool`` becomes ``("bool", 0 | 1)`` (checked before ``int`` since
      ``bool`` is a subclass of ``int`` in Python)
    - ``int`` / integral ``float`` becomes ``("num", float_canonical)`` so
      ``1`` and ``1.0`` compare equal
    - ``float`` is normalized to significant digits to absorb minor float repr
      drift while remaining hashable
    - ``str`` is stripped of leading/trailing whitespace; numeric strings are
      kept as strings unless coerced upstream, preserving type distinction
      between ``"1999"`` and ``1999`` while normalizing whitespace
    - Neo4j Node/Relationship-like mappings or sequences are canonicalized
      recursively
    """
    if val is None:
        return ("null", "")
    if isinstance(val, bool):
        return ("bool", 1 if val else 0)
    if isinstance(val, int):
        return ("num", _canon_number(float(val)))
    if isinstance(val, float):
        if math.isnan(val):
            return ("nan", "")
        if math.isinf(val):
            return ("inf", "+" if val > 0 else "-")
        return ("num", _canon_number(val))
    if isinstance(val, str):
        return ("str", val.strip())
    if isinstance(val, (list, tuple)):
        return ("seq", tuple(coerce_scalar(x) for x in val))
    if isinstance(val, (set, frozenset)):
        items = sorted(coerce_scalar(x) for x in val)
        return ("set", tuple(items))
    if isinstance(val, Mapping):
        # Handle dict / Neo4j Node-like mapping by sorting canonicalized items.
        items = sorted(
            (str(k), coerce_scalar(v)) for k, v in val.items()
        )
        return ("map", tuple(items))
    # Fallback for driver objects (e.g. Neo4j Node, Relationship, Date/Time):
    # inspect common id/properties attributes if present, else string repr.
    if hasattr(val, "element_id") or hasattr(val, "id"):
        props = dict(val.items()) if hasattr(val, "items") else {}
        if props:
            items = sorted((str(k), coerce_scalar(v)) for k, v in props.items())
            return ("map", tuple(items))
    try:
        return ("other", json.dumps(val, sort_keys=True, default=str))
    except TypeError:
        return ("other", str(val))


def _canon_number(num: float) -> float:
    if num == 0.0:
        return 0.0
    if math.isclose(num, round(num), rel_tol=FLOAT_REL_TOL, abs_tol=FLOAT_ABS_TOL):
        return float(int(round(num)))
    return float(f"{num:.{FLOAT_SIG_DIGITS}g}")


def normalize_row(row: Mapping[str, Any] | Sequence[Any]) -> tuple[tuple[str, Any], ...]:
    """Drop column names, coerce each cell, and sort cells within the row.

    Sorting cells within the row makes normalization invariant to projection
    column order as well as column aliases (e.g. ``RETURN a.name, a.born`` vs
    ``RETURN a.born AS year, a.name AS actor``).
    """
    if isinstance(row, Mapping):
        values = list(row.values())
    else:
        values = list(row)
    coerced = [coerce_scalar(v) for v in values]
    coerced.sort()
    return tuple(coerced)


def normalize_rows(
    rows: Sequence[Mapping[str, Any] | Sequence[Any]],
) -> list[tuple[tuple[str, Any], ...]]:
    """Normalize a list of rows and sort them deterministically."""
    normalized = [normalize_row(r) for r in rows]
    normalized.sort()
    return normalized


def multiset_jaccard_and_f1(
    pred_rows: Sequence[Mapping[str, Any] | Sequence[Any]],
    gold_rows: Sequence[Mapping[str, Any] | Sequence[Any]],
) -> dict[str, Any]:
    """Compute value-multiset Jaccard, precision, recall, F1, and soft match.

    Empty vs empty is a vacuous match (``1.0`` / ``True``).
    """
    norm_pred = normalize_rows(pred_rows)
    norm_gold = normalize_rows(gold_rows)

    if not norm_pred and not norm_gold:
        return {
            "soft_exec_match": True,
            "soft_jaccard": 1.0,
            "soft_f1": 1.0,
            "soft_precision": 1.0,
            "soft_recall": 1.0,
        }
    if not norm_pred or not norm_gold:
        return {
            "soft_exec_match": False,
            "soft_jaccard": 0.0,
            "soft_f1": 0.0,
            "soft_precision": 0.0,
            "soft_recall": 0.0,
        }

    c_pred = Counter(norm_pred)
    c_gold = Counter(norm_gold)

    intersection = sum((c_pred & c_gold).values())
    union = sum((c_pred | c_gold).values())
    total_pred = len(norm_pred)
    total_gold = len(norm_gold)

    jaccard = intersection / union if union > 0 else 1.0
    precision = intersection / total_pred if total_pred > 0 else 0.0
    recall = intersection / total_gold if total_gold > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    match = c_pred == c_gold

    return {
        "soft_exec_match": match,
        "soft_jaccard": jaccard,
        "soft_f1": f1,
        "soft_precision": precision,
        "soft_recall": recall,
    }


def _is_id_key(key: str) -> bool:
    """Return True if a column or property name looks like a node ID / primary key."""
    k = key.strip().lower()
    if not k:
        return False
    # Strip leading alias prefix like "m.id" -> "id", "movie.movieId" -> "movieid"
    tail = k.rsplit(".", 1)[-1]
    if tail in _EXPLICIT_ID_KEYS or k in _EXPLICIT_ID_KEYS:
        return True
    if tail.endswith("_id") or tail.endswith("id") and len(tail) > 2:
        # e.g. movie_id, tmdbId, imdbId, userId, plant_id
        return True
    return False


def _extract_row_entity_ids(row: Mapping[str, Any] | Sequence[Any]) -> set[tuple[str, Any]]:
    """Extract canonicalized ID values from a single row when present."""
    ids: set[tuple[str, Any]] = set()
    if isinstance(row, Mapping):
        for k, v in row.items():
            if v is None:
                continue
            if _is_id_key(str(k)) and not isinstance(v, (Mapping, list, tuple, set, frozenset)):
                ids.add(coerce_scalar(v))
            elif isinstance(v, Mapping):
                for nk, nv in v.items():
                    if nv is not None and _is_id_key(str(nk)):
                        ids.add(coerce_scalar(nv))
            elif hasattr(v, "element_id") and getattr(v, "element_id", None) is not None:
                ids.add(coerce_scalar(getattr(v, "element_id")))
            elif hasattr(v, "id") and getattr(v, "id", None) is not None:
                ids.add(coerce_scalar(getattr(v, "id")))
    return ids


def extract_entity_ids(
    rows: Sequence[Mapping[str, Any] | Sequence[Any]],
) -> set[tuple[str, Any]] | None:
    """Extract entity IDs across a row list if IDs are present.

    Returns ``None`` if the rows are non-empty and no ID-like keys/values exist,
    or if the rows are empty (so callers only score entity Jaccard when IDs are
    actually present, never forcing it on arbitrary scalar projections).
    """
    if not rows:
        return None
    collected: set[tuple[str, Any]] = set()
    found_any_id_column = False
    for r in rows:
        if isinstance(r, Mapping):
            for k, v in r.items():
                if _is_id_key(str(k)):
                    found_any_id_column = True
                elif isinstance(v, Mapping) and any(_is_id_key(str(nk)) for nk in v.keys()):
                    found_any_id_column = True
                elif hasattr(v, "element_id") or hasattr(v, "id"):
                    found_any_id_column = True
        row_ids = _extract_row_entity_ids(r)
        collected.update(row_ids)
    if not found_any_id_column or not collected:
        return None
    return collected


def entity_jaccard(
    pred_rows: Sequence[Mapping[str, Any] | Sequence[Any]],
    gold_rows: Sequence[Mapping[str, Any] | Sequence[Any]],
) -> float | None:
    """Compute optional entity-set Jaccard when primary-key/node IDs are present.

    Returns ``None`` when neither side (or only one side without ID columns)
    surfaces recognizable node IDs / primary keys, so callers can omit or leave
    ``entity_jaccard`` unset rather than forcing a synthetic entity comparison.
    """
    pred_ids = extract_entity_ids(pred_rows)
    gold_ids = extract_entity_ids(gold_rows)
    if pred_ids is None or gold_ids is None:
        return None
    union = pred_ids | gold_ids
    if not union:
        return None
    return len(pred_ids & gold_ids) / len(union)


def score_soft_exec(
    pred_rows: Sequence[Mapping[str, Any] | Sequence[Any]],
    gold_rows: Sequence[Mapping[str, Any] | Sequence[Any]],
) -> dict[str, Any]:
    """Full Soft Exec Match scoring for a single (pred_rows, gold_rows) pair.

    Always returns:
      - ``soft_exec_match`` (bool)
      - ``soft_jaccard`` (float, rounded to 4 decimals)
      - ``soft_f1`` (float, rounded to 4 decimals)
    And optionally:
      - ``entity_jaccard`` (float, rounded to 4 decimals) when node/entity IDs
        are present on both sides; omitted (or ``None`` if requested) otherwise.
    """
    base = multiset_jaccard_and_f1(pred_rows, gold_rows)
    out: dict[str, Any] = {
        "soft_exec_match": bool(base["soft_exec_match"]),
        "soft_jaccard": round(float(base["soft_jaccard"]), 4),
        "soft_f1": round(float(base["soft_f1"]), 4),
    }
    ent_jac = entity_jaccard(pred_rows, gold_rows)
    if ent_jac is not None:
        out["entity_jaccard"] = round(float(ent_jac), 4)
    return out
