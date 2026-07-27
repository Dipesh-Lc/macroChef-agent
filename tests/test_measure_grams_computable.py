"""Unit tests for scripts/measure_grams_computable.py's core counting logic
-- a fixture-based check with hand-constructed recipes of known
grams-computable/non-computable ingredients, not a full corpus scan.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.schemas.recipe import Recipe  # noqa: E402
from measure_grams_computable import categorize, measure  # noqa: E402


def _recipe(recipe_id: str, ingredients: list[dict]) -> Recipe:
    return Recipe(recipe_id=recipe_id, title=recipe_id, ingredients=ingredients)


def test_measure_counts_mass_units_as_fully_computable():
    recipes = [
        _recipe("r1", [{"name": "chicken breast", "amount": 150, "unit": "g"}]),
        _recipe("r2", [{"name": "flour", "amount": 1, "unit": "kg"}]),
    ]
    result = measure(recipes)
    assert result.total_rows == 2
    assert result.unit_populated_rows == 2
    assert result.computable_rows == 2
    assert result.by_category["mass"].total == 2
    assert result.by_category["mass"].computable == 2


def test_measure_counts_volume_with_no_density_as_non_computable():
    recipes = [
        # "milk" has a density entry -> computable.
        _recipe("r1", [{"name": "milk", "amount": 1, "unit": "cup"}]),
        # "shallot" has no density entry -> unit populated, but NOT computable.
        _recipe("r2", [{"name": "shallot", "amount": 2, "unit": "cup"}]),
    ]
    result = measure(recipes)
    assert result.total_rows == 2
    assert result.unit_populated_rows == 2  # both have a unit string
    assert result.computable_rows == 1  # only milk converts
    assert result.by_category["volume"].total == 2
    assert result.by_category["volume"].computable == 1


def test_measure_counts_count_units_by_piece_weight_availability():
    recipes = [
        # "egg" has a piece weight -> computable, bare count (no unit).
        _recipe("r1", [{"name": "egg", "amount": 2, "unit": None}]),
        # "shallot" has no piece weight -> bare count, NOT computable.
        _recipe("r2", [{"name": "shallot", "amount": 3, "unit": None}]),
        # "clove" unit with a known piece weight name ("garlic").
        _recipe("r3", [{"name": "garlic", "amount": 2, "unit": "clove"}]),
    ]
    result = measure(recipes)
    assert result.total_rows == 3
    # Bare-count rows (r1, r2) have no unit string at all.
    assert result.unit_populated_rows == 1  # only r3's "clove"
    assert result.computable_rows == 2  # r1 (egg) and r3 (garlic/clove) convert; r2 does not
    assert result.by_category["no_unit"].total == 2
    assert result.by_category["no_unit"].computable == 1
    assert result.by_category["count"].total == 1
    assert result.by_category["count"].computable == 1


def test_measure_no_unit_with_unweighted_name_is_not_computable():
    recipes = [_recipe("r1", [{"name": "mystery seasoning", "amount": 1, "unit": None}])]
    result = measure(recipes)
    assert result.total_rows == 1
    assert result.unit_populated_rows == 0
    assert result.computable_rows == 0
    assert result.by_category["no_unit"].total == 1
    assert result.by_category["no_unit"].computable == 0


def test_measure_none_amount_is_never_computable_regardless_of_unit():
    recipes = [_recipe("r1", [{"name": "salt", "amount": None, "unit": "tsp"}])]
    result = measure(recipes)
    assert result.total_rows == 1
    assert result.unit_populated_rows == 1  # unit string is present
    assert result.computable_rows == 0  # but amount is None, so to_grams is None


def test_measure_aggregates_percentages_across_multiple_recipes():
    recipes = [
        _recipe(
            "r1",
            [
                {"name": "chicken breast", "amount": 150, "unit": "g"},
                {"name": "shallot", "amount": 2, "unit": "cup"},
            ],
        ),
        _recipe("r2", [{"name": "egg", "amount": 2, "unit": None}]),
    ]
    result = measure(recipes)
    assert result.total_rows == 3
    assert result.computable_rows == 2  # chicken breast (mass) + egg (piece weight)
    assert result.unit_populated_rows == 2  # chicken breast + shallot
    assert result.computable_pct == 2 / 3
    assert result.unit_populated_pct == 2 / 3


def test_categorize_matches_unit_dimension_buckets():
    assert categorize(_recipe("r", [{"name": "flour", "amount": 1, "unit": "g"}]).ingredients[0]) == "mass"
    assert categorize(_recipe("r", [{"name": "milk", "amount": 1, "unit": "cup"}]).ingredients[0]) == "volume"
    assert categorize(_recipe("r", [{"name": "garlic", "amount": 1, "unit": "clove"}]).ingredients[0]) == "count"
    assert categorize(_recipe("r", [{"name": "egg", "amount": 1, "unit": None}]).ingredients[0]) == "no_unit"
