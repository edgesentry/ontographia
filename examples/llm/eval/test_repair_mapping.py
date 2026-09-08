"""Issue #48: mapping-driven repair / semantic_validate parity tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(EXAMPLES))

from llm.mapping_loader import MAPPINGS_DIR, load_repair_mapping  # noqa: E402
from llm.repair import repair_intent  # noqa: E402
from llm.semantic_validate import semantic_validate_intent  # noqa: E402


class RepairMappingTests(unittest.TestCase):
    def test_manufacturing_sku_parity(self) -> None:
        question = "List suppliers for parts in product SKU SPX-100"
        incomplete = {
            "start": {"class": "Product", "alias": "product"},
            "traverse": [],
            "filter": [],
            "return": [{"alias": "supplier", "property": "name"}],
            "limit": None,
        }
        fixed = repair_intent(question, incomplete)
        self.assertEqual(fixed["start"]["class"], "Product")
        self.assertTrue(
            any(f.get("property") == "sku" and f.get("value") == "SPX-100" for f in fixed["filter"])
        )
        rels = {s["relationship"] for s in fixed["traverse"]}
        self.assertIn("has_part", rels)
        self.assertIn("supplied_by", rels)
        self.assertEqual(fixed["return"][0]["as_name"], "supplier_name")
        self.assertEqual(fixed["limit"], 20)
        semantic_validate_intent(question, fixed)

    def test_manufacturing_quarantine_validate(self) -> None:
        question = "Which defect codes affect lots with status quarantine?"
        bad = {
            "start": {"class": "Lot", "alias": "lot"},
            "traverse": [],
            "filter": [],
            "return": [{"alias": "defect", "property": "code", "as_name": "defect_code"}],
            "limit": 20,
        }
        with self.assertRaises(ValueError):
            semantic_validate_intent(question, bad)
        fixed = repair_intent(question, bad)
        semantic_validate_intent(question, fixed)
        self.assertTrue(
            any(
                f.get("property") == "status" and str(f.get("value")).lower() == "quarantine"
                for f in fixed["filter"]
            )
        )

    def test_movies_mapping_file_driven(self) -> None:
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
        self.assertTrue(
            any(
                f.get("property") == "title" and f.get("value") == "The Matrix"
                for f in fixed["filter"]
            )
        )
        self.assertEqual(fixed["limit"], 25)
        self.assertEqual(fixed["return"][0]["as_name"], "movie_title")
        semantic_validate_intent(question, fixed, mapping=mapping)

    def test_movies_mapping_does_not_apply_manufacturing_sku(self) -> None:
        mapping = load_repair_mapping(MAPPINGS_DIR / "movies.repair.yaml")
        question = "List suppliers for parts in product SKU SPX-100"
        incomplete = {
            "start": {"class": "Movie", "alias": "movie"},
            "filter": [],
            "return": [{"alias": "movie", "property": "title", "as_name": "t"}],
            "limit": 10,
        }
        fixed = repair_intent(question, incomplete, mapping=mapping)
        self.assertFalse(any(f.get("property") == "sku" for f in fixed["filter"]))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
