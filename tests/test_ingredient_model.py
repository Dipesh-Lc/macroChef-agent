from app.schemas.ingredient import Ingredient
from app.schemas.nutrition import NutritionIngredient
from app.schemas.recipe import Recipe


def test_ingredient_accepts_bare_string() -> None:
    ingredient = Ingredient.model_validate("150 g chicken breast")
    assert ingredient.name == "chicken breast"
    assert ingredient.amount == 150
    assert ingredient.unit == "g"


def test_ingredient_accepts_dict() -> None:
    ingredient = Ingredient.model_validate({"name": "rice", "amount": 2, "unit": "cup"})
    assert (ingredient.name, ingredient.amount, ingredient.unit) == ("rice", 2, "cup")


def test_recipe_coerces_string_list() -> None:
    # Legacy name-only ingredients load as structured objects with null amounts.
    recipe = Recipe(recipe_id="r", title="t", ingredients=["spinach", "200 g rice"])
    assert recipe.ingredients[0] == Ingredient(name="spinach", amount=None, unit=None)
    assert recipe.ingredients[1] == Ingredient(name="rice", amount=200, unit="g")


def test_recipe_roundtrip_model_dump_json() -> None:
    recipe = Recipe(recipe_id="r", title="t", ingredients=["150 g chicken breast", "spinach"])
    restored = Recipe.model_validate_json(recipe.model_dump_json())
    assert restored == recipe
    assert restored.ingredients[0].amount == 150


def test_nutrition_ingredient_is_ingredient_alias() -> None:
    assert NutritionIngredient is Ingredient


def test_ingredient_preparation_defaults_to_none() -> None:
    assert Ingredient(name="spinach").preparation is None


def test_ingredient_accepts_declared_preparation() -> None:
    ingredient = Ingredient(name="rice", amount=150, unit="g", preparation="cooked")
    assert ingredient.preparation == "cooked"


def test_empty_and_whitespace_ingredients_are_dropped() -> None:
    recipe = Recipe(
        recipe_id="r", title="t", ingredients=["chicken breast", "", "   ", "spinach"]
    )
    names = [item.name for item in recipe.ingredients]
    assert names == ["chicken breast", "spinach"]
    assert "" not in names
    assert len(recipe.ingredients) == 2  # length reflects the drop


def test_valid_ingredient_list_is_unchanged() -> None:
    recipe = Recipe(recipe_id="r", title="t", ingredients=["150 g chicken breast", "spinach"])
    assert len(recipe.ingredients) == 2
    assert recipe.ingredients[0] == Ingredient(name="chicken breast", amount=150, unit="g")


def test_empty_ingredient_drop_is_logged(caplog) -> None:
    import logging

    with caplog.at_level(logging.DEBUG, logger="app.schemas.recipe"):
        Recipe(recipe_id="r_bulk", title="t", ingredients=["rice", "", "  "])
    assert any(
        "Dropped 2 empty-name ingredient(s)" in message and "r_bulk" in message
        for message in caplog.messages
    )


def test_candidate_to_recipe_drops_empty_ingredients() -> None:
    from app.schemas.recipe_candidate import RecipeCandidate

    candidate = RecipeCandidate(
        candidate_id="c",
        title="Bowl",
        ingredients=["150 g chicken breast", "", "  "],
        source_type="mock",
    )
    recipe = candidate.to_recipe("u1")
    assert [item.name for item in recipe.ingredients] == ["chicken breast"]


def test_candidate_to_recipe_dedupes_allergens() -> None:
    from app.schemas.recipe_candidate import RecipeCandidate

    # "egg" and "eggs" both depluralize to the same normalized string --
    # derive_allergen_labels deliberately returns both as distinct keys
    # (app/services/constraint_engine.py), so to_recipe must dedupe here.
    candidate = RecipeCandidate(
        candidate_id="c",
        title="Cake",
        ingredients=["flour", "eggs", "sugar"],
        allergens=["egg", "eggs"],
        source_type="mock",
    )
    recipe = candidate.to_recipe("u1")
    assert recipe.allergens == ["egg"]


def test_recipe_derived_allergens_computed_from_ingredients() -> None:
    # Self-reported `allergens=["soy"]` is unrelated to the ingredient list
    # (no soy-containing ingredient), so `derived_allergens` -- which is
    # computed purely from ingredient names via
    # `constraint_engine.derive_allergen_labels` -- must diverge from it:
    # empty, while `allergens` stays exactly what was self-reported.
    from app.services.constraint_engine import derive_allergen_labels

    ingredients = ["rice", "olive oil", "lemon"]
    recipe = Recipe(
        recipe_id="r",
        title="t",
        ingredients=ingredients,
        allergens=["soy"],
    )
    names = [item.name for item in recipe.ingredients]
    assert recipe.derived_allergens == derive_allergen_labels(names)
    assert recipe.derived_allergens == []
    assert recipe.allergens == ["soy"]


def test_recipe_candidate_derived_allergens_computed_from_ingredients() -> None:
    from app.schemas.recipe_candidate import RecipeCandidate
    from app.services.constraint_engine import derive_allergen_labels

    ingredients = ["rice", "olive oil", "lemon"]
    candidate = RecipeCandidate(
        candidate_id="c",
        title="Bowl",
        ingredients=ingredients,
        allergens=["soy"],
        source_type="mock",
    )
    names = [item.name for item in candidate.ingredients]
    assert candidate.derived_allergens == derive_allergen_labels(names)
    assert candidate.derived_allergens == []
    assert candidate.allergens == ["soy"]


def test_recipe_allergens_field_unaffected_by_derived_allergens() -> None:
    # Regression guard: `allergens` (the field constraint_engine's
    # `_recipe_safety_terms` actually unions into its safety scan) must
    # remain a plain self-reported/passthrough field, never silently merged
    # with or overwritten by the new `derived_allergens` computed field --
    # see docs/TO_FIX_AND_UPGRADE.md item 4 for why the two must stay
    # separate.
    recipe = Recipe(
        recipe_id="r",
        title="t",
        ingredients=["peanut butter"],
        allergens=["dairy"],
    )
    assert recipe.allergens == ["dairy"]
    assert "allergens" in Recipe.model_fields
    assert "derived_allergens" not in Recipe.model_fields  # computed_field, not a stored field
    assert "derived_allergens" in Recipe.model_computed_fields


def test_loader_drops_empty_ingredients(tmp_path) -> None:
    import json

    from app.rag.loaders import load_recipes

    path = tmp_path / "recipes.jsonl"
    path.write_text(
        json.dumps({"recipe_id": "r1", "title": "T", "ingredients": ["rice", "", "  ", "tofu"]}) + "\n",
        encoding="utf-8",
    )
    (recipe,) = load_recipes(path)
    assert [item.name for item in recipe.ingredients] == ["rice", "tofu"]
