"""Issue #48: mapping-driven repair / semantic_validate parity tests."""

from __future__ import annotations

from ontographia.llm.mapping_loader import MAPPINGS_DIR, load_repair_mapping
from ontographia.llm.repair import repair_intent
from ontographia.llm.semantic_validate import semantic_validate_intent


def test_manufacturing_sku_parity() -> None:
    question = "List suppliers for parts in product SKU SPX-100"
    incomplete = {
        "start": {"class": "Product", "alias": "product"},
        "traverse": [],
        "filter": [],
        "return": [{"alias": "supplier", "property": "name"}],
        "limit": None,
    }
    fixed = repair_intent(question, incomplete)
    assert fixed["start"]["class"] == "Product"
    assert any(f.get("property") == "sku" and f.get("value") == "SPX-100" for f in fixed["filter"])
    rels = {s["relationship"] for s in fixed["traverse"]}
    assert "has_part" in rels
    assert "supplied_by" in rels
    assert fixed["return"][0]["as_name"] == "supplier_name"
    assert fixed["limit"] == 20
    semantic_validate_intent(question, fixed)


def test_manufacturing_quarantine_validate() -> None:
    question = "Which defect codes affect lots with status quarantine?"
    bad = {
        "start": {"class": "Lot", "alias": "lot"},
        "traverse": [],
        "filter": [],
        "return": [{"alias": "defect", "property": "code", "as_name": "defect_code"}],
        "limit": 20,
    }
    try:
        semantic_validate_intent(question, bad)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    fixed = repair_intent(question, bad)
    semantic_validate_intent(question, fixed)
    assert any(
        f.get("property") == "status" and str(f.get("value")).lower() == "quarantine"
        for f in fixed["filter"]
    )


def test_movies_mapping_file_driven() -> None:
    path = MAPPINGS_DIR / "movies.repair.yaml"
    mapping = load_repair_mapping(path)
    question = 'Find the movie titled "The Matrix"'
    incomplete = {
        "start": {"class": "Movie", "alias": "movie"},
        "filter": [],
        "return": [{"alias": "movie", "property": "title"}],
        "limit": None,
    }
    fixed = repair_intent(question, incomplete, mapping=mapping)
    assert any(
        f.get("property") == "title" and f.get("value") == "The Matrix"
        for f in fixed["filter"]
    )
    assert fixed["limit"] == 25
    assert fixed["return"][0]["as_name"] == "movie_title"
    semantic_validate_intent(question, fixed, mapping=mapping)


def test_movies_mapping_does_not_apply_manufacturing_sku() -> None:
    mapping = load_repair_mapping(MAPPINGS_DIR / "movies.repair.yaml")
    question = "List suppliers for parts in product SKU SPX-100"
    incomplete = {
        "start": {"class": "Movie", "alias": "movie"},
        "filter": [],
        "return": [{"alias": "movie", "property": "title", "as_name": "t"}],
        "limit": 10,
    }
    fixed = repair_intent(question, incomplete, mapping=mapping)
    assert not any(f.get("property") == "sku" for f in fixed["filter"])
