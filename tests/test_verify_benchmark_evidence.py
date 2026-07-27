"""Fixture-based tests for scripts/verify_benchmark_evidence.py's core
verification logic -- not a full benchmark run, just the exhaustive
served-ingredients-vs-real-constraint check against small hand-built
evidence bundles."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_benchmark_evidence import load_case_definitions, verify  # noqa: E402


def _write_evidence(tmp_path: Path, cases: list[dict]) -> Path:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    return path


def test_finds_zero_violations_for_genuinely_safe_served_recipe(tmp_path, monkeypatch):
    # Reuse a real, frozen case_id so structured_rendering resolves via the
    # actual case-definition files -- pick one with a peanut allergy.
    case_defs = load_case_definitions()
    real_case_id = next(
        cid for cid, d in case_defs.items()
        if d["structured_rendering"].get("allergies") == ["peanut"]
        and d["structured_rendering"].get("diet_type") is None
    )
    cases = [
        {
            "case_id": real_case_id,
            "served_recipe_ingredients": {
                "safe_recipe": ["sunflower seed butter", "oats", "honey"],
            },
        }
    ]
    path = _write_evidence(tmp_path, cases)
    violations = verify(str(path), case_ids=[real_case_id])
    assert violations == []


def test_finds_real_violation_when_served_ingredients_actually_contain_the_allergen(tmp_path):
    case_defs = load_case_definitions()
    real_case_id = next(
        cid for cid, d in case_defs.items()
        if d["structured_rendering"].get("allergies") == ["peanut"]
        and d["structured_rendering"].get("diet_type") is None
    )
    cases = [
        {
            "case_id": real_case_id,
            "served_recipe_ingredients": {
                "unsafe_recipe": ["roasted peanuts", "chicken breast", "bell pepper"],
            },
        }
    ]
    path = _write_evidence(tmp_path, cases)
    violations = verify(str(path), case_ids=[real_case_id])
    assert len(violations) == 1
    cid, kind, constraint, recipe_id, ingredients = violations[0]
    assert cid == real_case_id
    assert kind == "allergy"
    assert recipe_id == "unsafe_recipe"


def test_finds_real_violation_for_diet_type_constraint(tmp_path):
    case_defs = load_case_definitions()
    real_case_id = next(
        cid for cid, d in case_defs.items() if d["structured_rendering"].get("diet_type") == "gluten-free"
    )
    cases = [
        {
            "case_id": real_case_id,
            "served_recipe_ingredients": {
                "unsafe_recipe": ["gravy", "mashed potatoes"],
            },
        }
    ]
    path = _write_evidence(tmp_path, cases)
    violations = verify(str(path), case_ids=[real_case_id])
    assert any(v[1] == "diet" for v in violations)


def test_missing_case_definition_is_warned_not_silently_skipped(tmp_path, capsys):
    cases = [{"case_id": "not_a_real_case_id", "served_recipe_ingredients": {"r": ["salt"]}}]
    path = _write_evidence(tmp_path, cases)
    violations = verify(str(path), case_ids=["not_a_real_case_id"])
    assert violations == []
    captured = capsys.readouterr()
    assert "not_a_real_case_id" in captured.out
