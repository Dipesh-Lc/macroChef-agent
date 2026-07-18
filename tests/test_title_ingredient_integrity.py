"""Unit tests for app.services.corpus_import.title_ingredient_integrity --
the shared detection logic behind the 2026-07 corpus safety finding fix
(recipes whose title names an allergen absent from their own ingredient
list, e.g. "Curried Peanut Shrimp" with no peanut ingredient)."""

from app.schemas.ingredient import Ingredient
from app.schemas.recipe import Recipe
from app.services.corpus_import.title_ingredient_integrity import (
    build_quarantine_record,
    find_title_ingredient_mismatches,
)


def _recipe(title: str, ingredient_names: list[str], allergens: list[str] | None = None) -> Recipe:
    return Recipe(
        recipe_id="test_recipe",
        title=title,
        ingredients=[Ingredient(name=name, amount=1, unit=None) for name in ingredient_names],
        instructions=["Cook.", "Serve."],
        allergens=allergens or [],
    )


def test_flags_title_allergen_missing_from_ingredients_and_allergens() -> None:
    recipe = _recipe("Curried Peanut Shrimp", ["orange marmalade", "curry powder", "shrimp"])
    mismatches = find_title_ingredient_mismatches(recipe)
    categories = {m.category for m in mismatches}
    assert "peanut" in categories
    # shrimp genuinely present -> crustacean must NOT be flagged
    assert "crustacean" not in categories


def test_does_not_flag_when_ingredient_literally_present() -> None:
    recipe = _recipe("Peanut Noodles", ["peanut butter", "noodles", "soy sauce"])
    assert find_title_ingredient_mismatches(recipe) == []


def test_does_not_flag_when_only_derived_allergens_field_carries_it() -> None:
    # "satay" isn't in this module's own peanut term list, but a recipe whose
    # allergens field already has "peanut" (e.g. derived from "satay" via
    # constraint_engine.ALLERGEN_ALIASES) must not be double-flagged --
    # recipe.allergens is checked as an OR-arm precisely for this case.
    recipe = _recipe("Chicken Sate with Peanut Sauce", ["chicken", "sate"], allergens=["peanut"])
    assert find_title_ingredient_mismatches(recipe) == []


def test_word_boundary_excludes_concatenated_compounds() -> None:
    # "butter" must not match inside "butternut"; "crab" must not match
    # inside "crabapple" -- both are single tokens with no boundary.
    recipe = _recipe("Baked Butternut Squash", ["butternut squash", "olive oil"])
    assert find_title_ingredient_mismatches(recipe) == []

    recipe2 = _recipe("Crabapple Jelly", ["crabapples", "sugar", "water"])
    assert find_title_ingredient_mismatches(recipe2) == []


def test_plural_and_compound_ingredient_forms_are_recognized() -> None:
    # "lobsters" (plural) and "crabmeat" (compound, no space) must count as
    # the ingredient being present -- these produced real false positives
    # during development against the actual Food.com corpus.
    recipe = _recipe("Lobster Newburg", ["live lobsters", "butter", "cream"])
    assert find_title_ingredient_mismatches(recipe) == []

    recipe2 = _recipe("Crabby Crab Cakes", ["fresh lump crabmeat", "egg", "flour"])
    assert find_title_ingredient_mismatches(recipe2) == []


def test_fruit_and_nut_butter_compounds_are_not_dairy() -> None:
    recipe = _recipe("Low-Fat Strawberry Butter", ["strawberry", "apple cider", "honey"])
    assert find_title_ingredient_mismatches(recipe) == []

    recipe2 = _recipe("Peanut Butter Cookies", ["peanut butter", "flour", "sugar", "egg"])
    categories = {m.category for m in find_title_ingredient_mismatches(recipe2)}
    assert "dairy" not in categories


def test_exact_phrase_suppressions() -> None:
    recipe = _recipe(
        "Cracker Barrel Old Country Store Fried Apples", ["apples", "brown sugar", "butter"]
    )
    assert find_title_ingredient_mismatches(recipe) == []

    recipe2 = _recipe("Texas Spoon Bread", ["cornmeal", "milk", "eggs", "butter"])
    assert find_title_ingredient_mismatches(recipe2) == []

    recipe3 = _recipe(
        "Cape Cod Cranberry Velvet Pie", ["cream cheese", "sugar", "cranberry sauce"]
    )
    assert find_title_ingredient_mismatches(recipe3) == []


def test_mock_prefix_disclaims_the_named_food() -> None:
    recipe = _recipe("Mock Pecan Pie", ["pinto beans", "sugar", "eggs", "salt"])
    assert find_title_ingredient_mismatches(recipe) == []


def test_negation_and_free_suffix_disclaim_the_named_food() -> None:
    recipe = _recipe("No-Bread Sandwiches", ["eggs", "mayonnaise", "lettuce leaves"])
    assert find_title_ingredient_mismatches(recipe) == []

    recipe2 = _recipe("Gluten-Free Pancakes", ["rice flour", "eggs", "milk"])
    assert find_title_ingredient_mismatches(recipe2) == []


def test_build_quarantine_record_shape() -> None:
    recipe = _recipe("Crab Dip", ["cream cheese", "green onions"])
    mismatches = find_title_ingredient_mismatches(recipe)
    assert mismatches  # sanity: this recipe should indeed be flagged

    record = build_quarantine_record(recipe, mismatches)
    assert record["recipe"]["recipe_id"] == "test_recipe"
    assert record["quarantine_reason"]["check"] == "title_ingredient_integrity"
    assert record["quarantine_reason"]["mismatches"][0]["category"] == "crustacean"
    assert "quarantined_at_utc" in record
