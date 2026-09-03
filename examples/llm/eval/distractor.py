"""Generate manufacturing ontologies bloated with distractor properties/classes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[3]
BASE_ONTOLOGY = ROOT / "examples" / "manufacturing.native.yaml"

# Near-duplicates that look like real manufacturing fields (same owner_class).
NEAR_DUPLICATES: list[tuple[str, str, str]] = [
    # owner_class, distractor_name, gold_field
    ("Plant", "PlantName", "name"),
    ("Plant", "plant_name", "name"),
    ("Plant", "Plant_Name", "name"),
    ("Plant", "facility_name", "name"),
    ("Plant", "site_name", "name"),
    ("Plant", "plantName", "name"),
    ("Line", "LineName", "name"),
    ("Line", "line_name", "name"),
    ("Line", "production_line_name", "name"),
    ("Line", "Line_Name", "name"),
    ("Product", "SKU", "sku"),
    ("Product", "product_sku", "sku"),
    ("Product", "SkuCode", "sku"),
    ("Product", "item_sku", "sku"),
    ("Product", "ProductName", "name"),
    ("Product", "product_name", "name"),
    ("Part", "PartNumber", "part_number"),
    ("Part", "partNumber", "part_number"),
    ("Part", "part_no", "part_number"),
    ("Part", "Part_Name", "name"),
    ("Supplier", "SupplierName", "name"),
    ("Supplier", "supplier_name", "name"),
    ("Supplier", "vendor_name", "name"),
    ("Lot", "LotStatus", "status"),
    ("Lot", "lot_status", "status"),
    ("Lot", "Status", "status"),
    ("Lot", "quarantine_status", "status"),
    ("Lot", "LotId", "lot_id"),
    ("Lot", "lotId", "lot_id"),
    ("DefectType", "DefectCode", "code"),
    ("DefectType", "defect_code", "code"),
    ("DefectType", "Code", "code"),
]

DISTRACTOR_CLASSES = [
    "Facility",
    "WorkCenter",
    "Material",
    "Vendor",
    "Batch",
    "QualityIssue",
    "Site",
]


@dataclass(frozen=True)
class SizeProfile:
    name: str
    target_properties: int  # 0 => base ontology only


PROFILES: dict[str, SizeProfile] = {
    "small": SizeProfile("small", target_properties=0),
    "mid": SizeProfile("mid", target_properties=200),
    "large": SizeProfile("large", target_properties=2000),
}


def _property_block(name: str, owner: str, datatype: str = "string") -> str:
    return (
        f"  - name: {name}\n"
        f"    owner_class: {owner}\n"
        f"    datatype: {datatype}\n"
    )


def _class_block(name: str) -> str:
    return f"  - name: {name}\n    description: Distractor class for Track A stress test\n"


def base_property_count(yaml_text: str) -> int:
    return yaml_text.count("\n    owner_class:")


def near_duplicate_map() -> dict[tuple[str, str], str]:
    """(owner_class, gold_property) -> preferred distractor name for silent-wrong intents."""
    preferred: dict[tuple[str, str], str] = {}
    for owner, distractor, gold in NEAR_DUPLICATES:
        preferred.setdefault((owner, gold), distractor)
    return preferred


def generate_distractor_ontology(
    profile: str,
    *,
    base_path: Path | None = None,
    seed: str = "track-a-v1",
) -> tuple[bytes, dict[str, int | str]]:
    """Return native YAML bytes and stats for the requested size profile."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; choose from {sorted(PROFILES)}")

    base = (base_path or BASE_ONTOLOGY).read_text(encoding="utf-8")
    prop_count_base = base_property_count(base)
    target = PROFILES[profile].target_properties

    if target == 0:
        return base.encode("utf-8"), {
            "profile_name": profile,
            "properties": prop_count_base,
            "distractor_properties": 0,
            "distractor_classes": 0,
            "near_duplicates": 0,
        }

    extra_props: list[str] = []
    seen: set[tuple[str, str]] = set()

    for owner, name, _gold in NEAR_DUPLICATES:
        key = (owner, name)
        if key in seen:
            continue
        seen.add(key)
        extra_props.append(_property_block(name, owner))

    owners = ["Product", "Part", "Supplier", "Plant", "Line", "Lot", "DefectType"]
    need = max(0, target - prop_count_base - len(extra_props))
    for i in range(need):
        owner = owners[i % len(owners)]
        digest = hashlib.sha256(f"{seed}:{profile}:{i}".encode()).hexdigest()[:6]
        name = f"CustomField_{i:04d}_{digest}"
        extra_props.append(_property_block(name, owner))

    if "\nrelationships:\n" not in base:
        raise ValueError("base ontology missing relationships: section")
    head, tail = base.split("\nrelationships:\n", 1)
    class_blocks = "".join(_class_block(c) for c in DISTRACTOR_CLASSES)
    yaml_out = (
        head.rstrip()
        + "\n"
        + class_blocks
        + "\nrelationships:\n"
        + tail.rstrip()
        + "\n"
        + "".join(extra_props)
    )

    return yaml_out.encode("utf-8"), {
        "profile_name": profile,
        "properties": prop_count_base + len(extra_props),
        "distractor_properties": len(extra_props),
        "distractor_classes": len(DISTRACTOR_CLASSES),
        "near_duplicates": len(NEAR_DUPLICATES),
    }


def write_ontology(profile: str, out_dir: Path, **kwargs: object) -> Path:
    data, _stats = generate_distractor_ontology(profile, **kwargs)  # type: ignore[arg-type]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"manufacturing_track_a_{profile}.native.yaml"
    path.write_bytes(data)
    return path


def iter_profiles() -> Iterable[str]:
    return ("small", "mid", "large")
