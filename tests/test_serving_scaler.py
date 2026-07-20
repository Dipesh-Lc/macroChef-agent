"""B2: serving scaler -- pure, deterministic ingredient-amount scaling.

`scale_ingredients` (app.schemas.ingredient) is display/shopping-list math
only: it never touches nutrition grounding, never calls the USDA client, and
never recomputes per-serving macros (those are already serving-invariant;
only the batch total for the chosen serving count changes, a trivial
`per_serving * target_servings` done inline by the frontend -- not this
function's job).
"""

from app.schemas.ingredient import Ingredient, scale_ingredients


def test_scale_factor_one_is_a_noop() -> None:
    ingredients = [Ingredient(name="chicken breast", amount=150, unit="g")]
    scaled = scale_ingredients(ingredients, 1.0)

    assert scaled == ingredients
    assert scaled is not ingredients  # new objects, not the same list


def test_scale_factor_two_doubles_amount() -> None:
    ingredients = [Ingredient(name="rice", amount=100, unit="g")]
    scaled = scale_ingredients(ingredients, 2.0)

    assert scaled[0].amount == 200
    assert scaled[0].name == "rice"
    assert scaled[0].unit == "g"


def test_scale_factor_half_halves_amount() -> None:
    ingredients = [Ingredient(name="olive oil", amount=2, unit="tbsp")]
    scaled = scale_ingredients(ingredients, 0.5)

    assert scaled[0].amount == 1


def test_none_amount_is_never_fabricated() -> None:
    ingredients = [Ingredient(name="salt to taste", amount=None, unit=None)]
    scaled = scale_ingredients(ingredients, 3.0)

    assert scaled[0].amount is None
    assert scaled[0].name == "salt to taste"


def test_unit_name_and_preparation_are_preserved() -> None:
    ingredients = [
        Ingredient(name="rice", amount=150, unit="g", preparation="cooked"),
    ]
    scaled = scale_ingredients(ingredients, 4.0)

    assert scaled[0].unit == "g"
    assert scaled[0].preparation == "cooked"
    assert scaled[0].amount == 600


def test_empty_list_returns_empty_list() -> None:
    assert scale_ingredients([], 2.0) == []
