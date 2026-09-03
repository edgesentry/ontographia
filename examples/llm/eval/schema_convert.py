"""Convert Neo4j Text2Cypher schema strings to Ontographia native YAML.

Supports the common \"Node properties:\" / \"The relationships:\" text format
used for neo4jlabs demo databases in neo4j/text2cypher-2025v1.

JSON introspect dumps and other free-text schemas are best-effort / skipped
with an explicit error — document limitations rather than silently inventing edges.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_DATATYPE_MAP = {
    "STRING": "string",
    "INTEGER": "integer",
    "INT": "integer",
    "FLOAT": "float",
    "BOOLEAN": "boolean",
    "DATE": "string",
    "DATETIME": "string",
    "POINT": "string",
    "LIST": "string",
}


@dataclass
class ConvertResult:
    yaml_text: str
    format: str
    classes: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    properties: int = 0
    warnings: list[str] = field(default_factory=list)


def detect_schema_format(schema: str) -> str:
    s = (schema or "").strip()
    if not s:
        return "empty"
    if s.startswith("{"):
        return "json_introspect"
    if s.startswith("Node properties"):
        return "node_properties"
    if s.startswith("Graph schema:"):
        return "graph_schema_text"
    return "other"


def _map_dtype(raw: str) -> str:
    key = raw.strip().upper().split()[0] if raw.strip() else "STRING"
    return _DATATYPE_MAP.get(key, "string")


def _sanitize_ident(name: str) -> str:
    """Keep Cypher-ish identifiers usable in native YAML."""
    name = name.strip().strip("`")
    if not name:
        return name
    # Native YAML / COM treat names as opaque strings; strip whitespace only.
    return re.sub(r"\s+", "_", name)


def convert_node_properties_schema(schema: str) -> ConvertResult:
    warnings: list[str] = []
    classes: dict[str, None] = {}
    props: list[tuple[str, str, str]] = []  # name, owner, dtype
    rels: list[tuple[str, str, str]] = []  # name, from, to

    # --- node properties ---
    node_section = schema
    rel_props_idx = schema.find("Relationship properties:")
    rels_idx = schema.find("The relationships:")
    cut = len(schema)
    if rel_props_idx >= 0:
        cut = min(cut, rel_props_idx)
    if rels_idx >= 0:
        cut = min(cut, rels_idx)
    node_section = schema[:cut]

    current: str | None = None
    for line in node_section.splitlines():
        m_label = re.match(r"^- \*\*(.+?)\*\*\s*$", line.strip())
        if m_label:
            current = _sanitize_ident(m_label.group(1))
            classes[current] = None
            continue
        m_prop = re.match(
            r"^-\s+`([^`]+)`:\s*([A-Za-z]+)",
            line.strip(),
        )
        if m_prop and current:
            pname = _sanitize_ident(m_prop.group(1))
            dtype = _map_dtype(m_prop.group(2))
            props.append((pname, current, dtype))

    # --- relationships from pattern lines ---
    if rels_idx >= 0:
        rel_section = schema[rels_idx:]
        for m in re.finditer(
            r"\(:\s*([^)\s]+)\s*\)\s*-\s*\[:([^\]]+)\]\s*->\s*\(:\s*([^)\s]+)\s*\)",
            rel_section,
        ):
            src, rel, dst = (
                _sanitize_ident(m.group(1)),
                _sanitize_ident(m.group(2)),
                _sanitize_ident(m.group(3)),
            )
            classes[src] = None
            classes[dst] = None
            rels.append((rel, src, dst))

    if not classes:
        raise ValueError("node_properties schema produced no classes")

    if not rels:
        warnings.append("no relationship patterns found; ontology has classes/properties only")

    yaml_text = _emit_native_yaml(list(classes.keys()), rels, props)
    return ConvertResult(
        yaml_text=yaml_text,
        format="node_properties",
        classes=list(classes.keys()),
        relationships=[r[0] for r in rels],
        properties=len(props),
        warnings=warnings,
    )


def convert_json_introspect_schema(schema: str) -> ConvertResult:
    """Best-effort convert of Neo4j introspect JSON (nodes + relationships)."""
    data = json.loads(schema)
    if not isinstance(data, dict):
        raise ValueError("json schema root must be an object")

    classes: dict[str, None] = {}
    props: list[tuple[str, str, str]] = []
    rels: list[tuple[str, str, str]] = []
    warnings: list[str] = []

    # First pass: node entries
    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        if val.get("type") == "node":
            cname = _sanitize_ident(key)
            classes[cname] = None
            for pname, meta in (val.get("properties") or {}).items():
                dtype = "string"
                if isinstance(meta, dict) and meta.get("type"):
                    dtype = _map_dtype(str(meta["type"]))
                props.append((_sanitize_ident(pname), cname, dtype))

    # Relationships: either top-level type=relationship or nested under node.relationships
    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        if val.get("type") == "relationship":
            # Often missing ends in this dump; try nested labels if present later
            warnings.append(f"top-level relationship {key!r} lacks endpoints; skipped")
            continue

    for key, val in data.items():
        if not isinstance(val, dict) or val.get("type") != "node":
            continue
        src = _sanitize_ident(key)
        for rel_name, rmeta in (val.get("relationships") or {}).items():
            if not isinstance(rmeta, dict):
                continue
            labels = rmeta.get("labels") or []
            direction = (rmeta.get("direction") or "out").lower()
            if not labels:
                warnings.append(f"relationship {rel_name!r} on {src} has no labels; skipped")
                continue
            for dst_raw in labels:
                dst = _sanitize_ident(str(dst_raw))
                classes[dst] = None
                rname = _sanitize_ident(rel_name)
                if direction == "in":
                    rels.append((rname, dst, src))
                else:
                    rels.append((rname, src, dst))

    # Dedup relationships
    uniq: dict[tuple[str, str, str], None] = {}
    for item in rels:
        uniq[item] = None
    rels = list(uniq.keys())

    if not classes:
        raise ValueError("json introspect schema produced no classes")

    yaml_text = _emit_native_yaml(list(classes.keys()), rels, props)
    return ConvertResult(
        yaml_text=yaml_text,
        format="json_introspect",
        classes=list(classes.keys()),
        relationships=[r[0] for r in rels],
        properties=len(props),
        warnings=warnings,
    )


def convert_schema_to_native_yaml(schema: str) -> ConvertResult:
    fmt = detect_schema_format(schema)
    if fmt == "node_properties":
        return convert_node_properties_schema(schema)
    if fmt == "json_introspect":
        return convert_json_introspect_schema(schema)
    raise ValueError(f"unsupported schema format: {fmt}")


def _emit_native_yaml(
    class_names: list[str],
    rels: list[tuple[str, str, str]],
    props: list[tuple[str, str, str]],
) -> str:
    lines = [
        "# Generated from Text2Cypher schema (heuristic). Not a perfect round-trip.",
        "namespaces:",
        "  ex: http://example.org/ontographia/text2cypher#",
        "",
        "classes:",
    ]
    for c in sorted(set(class_names)):
        lines.append(f"  - name: {c}")
        lines.append("    description: Imported from Text2Cypher schema")
    lines.append("")
    if rels:
        lines.append("relationships:")
        seen: set[tuple[str, str, str]] = set()
        for name, frm, to in rels:
            key = (name, frm, to)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"  - name: {name}")
            lines.append(f"    from_class: {frm}")
            lines.append(f"    to_class: {to}")
            lines.append("    direction: out")
    else:
        lines.append("relationships: []")
    lines.append("")
    if props:
        lines.append("properties:")
        seen_p: set[tuple[str, str]] = set()
        for name, owner, dtype in props:
            key = (owner, name)
            if key in seen_p:
                continue
            seen_p.add(key)
            lines.append(f"  - name: {name}")
            lines.append(f"    owner_class: {owner}")
            lines.append(f"    datatype: {dtype}")
    else:
        lines.append("properties: []")
    lines.append("")
    return "\n".join(lines)


def extract_cypher_vocab(cypher: str) -> dict[str, set[str]]:
    """Rough label / relationship / property tokens from a Cypher string."""
    labels = set(re.findall(r":\s*`?([A-Za-z_][A-Za-z0-9_]*)`?", cypher))
    # Relationship types in [:TYPE] or -[:TYPE]-
    rels = set(re.findall(r"\[\s*:\s*`?([A-Za-z_][A-Za-z0-9_]*)`?", cypher))
    # Properties n.prop — exclude common keywords falsely matched poorly
    props = set(re.findall(r"\.[`\"]?([A-Za-z_][A-Za-z0-9_]*)[`\"]?", cypher))
    # Labels also match :REL inside [] — remove those that look like rel-only if in rels
    # Keep intersection handling in coverage metrics instead.
    return {"labels": labels, "relationships": rels, "properties": props}


def vocab_coverage(
    cypher_vocab: dict[str, set[str]],
    ontology: dict[str, Any],
) -> dict[str, float]:
    ont_classes = {str(c.get("name")) for c in ontology.get("classes", []) if c.get("name")}
    ont_rels = {str(r.get("name")) for r in ontology.get("relationships", []) if r.get("name")}
    ont_props = {str(p.get("name")) for p in ontology.get("properties", []) if p.get("name")}

    def cov(pred: set[str], gold: set[str]) -> float:
        if not pred:
            return 1.0
        return len(pred & gold) / len(pred)

    # Cypher :Token can be label or rel; score labels against classes, rels against rels.
    return {
        "label_coverage": cov(cypher_vocab["labels"] - cypher_vocab["relationships"], ont_classes),
        "rel_coverage": cov(cypher_vocab["relationships"], ont_rels),
        "prop_coverage": cov(cypher_vocab["properties"], ont_props),
    }
