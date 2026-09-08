"""Exact-match ontology subsetting for Intent prompts (issue #45).

Reduces class / relationship / property vocabulary shown to the LLM by
case-insensitive exact token match against the user question, then closes
under relationship endpoints and edges between kept classes.

The Engine still validates against the full ontology; this module only
shapes prompt / JSON Schema input. On under-selection, callers should
fall back to the full schema (see ``llm.pipeline``).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Iterable

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


def tokenize_question(question: str) -> set[str]:
    """Lowercased tokens from the question (alnum runs + snake/camel splits)."""
    tokens: set[str] = set()
    for raw in _TOKEN_RE.findall(question):
        lower = raw.lower()
        tokens.add(lower)
        for part in raw.split("_"):
            if part:
                tokens.add(part.lower())
        for part in _CAMEL_RE.findall(raw):
            if part:
                tokens.add(part.lower())
    # Light English plural fold so "suppliers"/"parts" hit Supplier/Part.
    for token in list(tokens):
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            tokens.add(token[:-1])
        if len(token) > 4 and token.endswith("ies"):
            tokens.add(token[:-3] + "y")
    return tokens


def exact_name_matches(names: Iterable[str], tokens: set[str]) -> set[str]:
    """Names whose lowercased form is an exact token (not a substring)."""
    return {name for name in names if name.lower() in tokens}


@dataclass(frozen=True)
class OntologySubset:
    """Filtered ontology view + bookkeeping for prompts / schema enums."""

    ontology: dict[str, Any]
    class_names: frozenset[str]
    relationship_names: frozenset[str]
    property_names: frozenset[str]
    empty: bool

    @property
    def stats(self) -> dict[str, int | bool]:
        return {
            "classes": len(self.class_names),
            "relationships": len(self.relationship_names),
            "properties": len(self.property_names),
            "empty": self.empty,
        }


def subset_ontology(ontology: dict[str, Any], question: str) -> OntologySubset:
    """Build an exact-match subset of ``ontology`` for ``question``."""
    tokens = tokenize_question(question)

    classes = list(ontology.get("classes") or [])
    relationships = list(ontology.get("relationships") or [])
    properties = list(ontology.get("properties") or [])

    class_by_name = {str(c["name"]): c for c in classes if c.get("name")}
    rel_by_name = {str(r["name"]): r for r in relationships if r.get("name")}

    matched_classes = exact_name_matches(class_by_name, tokens)
    matched_rels = exact_name_matches(rel_by_name, tokens)
    matched_props = [
        p
        for p in properties
        if p.get("name") and str(p["name"]).lower() in tokens
    ]

    kept_classes = set(matched_classes)
    for prop in matched_props:
        owner = prop.get("owner_class")
        if owner:
            kept_classes.add(str(owner))
    for rel_name in matched_rels:
        rel = rel_by_name[rel_name]
        for endpoint in (rel.get("from_class"), rel.get("to_class")):
            if endpoint:
                kept_classes.add(str(endpoint))

    kept_rels = set(matched_rels)
    # Close under edges whose endpoints are both kept (enables traversals).
    for name, rel in rel_by_name.items():
        frm = rel.get("from_class")
        to = rel.get("to_class")
        if frm and to and str(frm) in kept_classes and str(to) in kept_classes:
            kept_rels.add(name)

    # Include relationship endpoints introduced by the edge closure.
    for rel_name in list(kept_rels):
        rel = rel_by_name[rel_name]
        for endpoint in (rel.get("from_class"), rel.get("to_class")):
            if endpoint:
                kept_classes.add(str(endpoint))

    kept_prop_names = {str(p["name"]) for p in matched_props}
    # Keep only matched properties whose owner survived (or had no owner).
    kept_props = [
        p
        for p in matched_props
        if not p.get("owner_class") or str(p["owner_class"]) in kept_classes
    ]

    empty = not kept_classes and not kept_rels and not kept_props
    filtered = {
        **ontology,
        "classes": [class_by_name[n] for n in sorted(kept_classes) if n in class_by_name],
        "relationships": [rel_by_name[n] for n in sorted(kept_rels) if n in rel_by_name],
        "properties": kept_props,
    }
    return OntologySubset(
        ontology=filtered,
        class_names=frozenset(kept_classes),
        relationship_names=frozenset(kept_rels),
        property_names=frozenset(kept_prop_names),
        empty=empty,
    )


def filter_intent_schema(
    intent_json_schema: dict[str, Any],
    *,
    class_names: Iterable[str],
    relationship_names: Iterable[str],
) -> dict[str, Any]:
    """Return a deep-copied Intent JSON Schema with narrowed class/rel enums."""
    schema = copy.deepcopy(intent_json_schema)
    classes = sorted(class_names)
    relationships = sorted(relationship_names)

    defs = schema.get("$defs")
    if isinstance(defs, dict):
        node_ref = defs.get("NodeRef")
        if isinstance(node_ref, dict):
            _set_field_enum(node_ref, "class", classes)
        step = defs.get("TraverseStep")
        if isinstance(step, dict):
            _set_field_enum(step, "relationship", relationships)

    props = schema.get("properties")
    if isinstance(props, dict):
        start = props.get("start")
        if isinstance(start, dict):
            _set_field_enum(start, "class", classes)
        traverse = props.get("traverse")
        if isinstance(traverse, dict):
            items = traverse.get("items")
            if isinstance(items, dict):
                item_props = items.get("properties")
                if isinstance(item_props, dict):
                    rel = item_props.get("relationship")
                    if isinstance(rel, dict):
                        rel["enum"] = relationships
                    to = item_props.get("to")
                    if isinstance(to, dict):
                        _set_field_enum(to, "class", classes)

    return schema


def prompt_views_for_question(
    question: str,
    intent_json_schema: dict[str, Any],
    ontology: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], OntologySubset]:
    """Subset ontology + filtered schema for prompting.

    If the subset is empty, returns the originals unchanged (caller should
    treat this as \"use full schema\").
    """
    subset = subset_ontology(ontology, question)
    if subset.empty:
        return intent_json_schema, ontology, subset
    schema = filter_intent_schema(
        intent_json_schema,
        class_names=subset.class_names,
        relationship_names=subset.relationship_names,
    )
    return schema, subset.ontology, subset


def _set_field_enum(parent: dict[str, Any], field: str, values: list[str]) -> None:
    props = parent.get("properties")
    if not isinstance(props, dict):
        return
    target = props.get(field)
    if isinstance(target, dict):
        target["enum"] = values
