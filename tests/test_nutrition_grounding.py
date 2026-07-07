import pytest

from app.schemas.nutrition import FoodMacros, FoodMatch, GroundingStatus, NutritionIngredient
from app.services.nutrition_grounding import compute_recipe_macros


def _match(name: str, *, calories: float, protein_g: float, carbs_g: float, fat_g: float, fiber_g: float) -> FoodMatch:
    return FoodMatch(
        fdc_id=1,
        description=name,
        data_type="SR Legacy",
        macros=FoodMacros(
            calories=calories, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g, fiber_g=fiber_g
        ),
        query=name,
    )


# Known USDA SR Legacy reference value: raw chicken breast, per 100g.
CHICKEN_BREAST = _match(
    "chicken breast", calories=165, protein_g=31, carbs_g=0, fat_g=3.57, fiber_g=0
)


class FakeUsdaClient:
    def __init__(self, matches: dict[str, FoodMatch | None]):
        self._matches = matches
        self.calls: list[str] = []

    def search_food(self, name: str, *, preparation: str | None = None) -> FoodMatch | None:
        self.calls.append(name)
        return self._matches.get(name)


def test_per_100g_scales_to_portion_against_known_reference() -> None:
    ingredient = NutritionIngredient(name="chicken breast", amount=200, unit="g")
    client = FakeUsdaClient({"chicken breast": CHICKEN_BREAST})

    result = compute_recipe_macros([ingredient], servings=1, client=client)

    assert result.status == GroundingStatus.GROUNDED
    assert result.total.calories == pytest.approx(330)
    assert result.total.protein_g == pytest.approx(62)
    assert result.total.fat_g == pytest.approx(7.14)
    assert result.per_serving.calories == pytest.approx(330)


@pytest.mark.parametrize(
    ("amount", "unit", "expected_grams"),
    [
        (1, "lb", 453.592),
        (1, "kg", 1000.0),
        (8, "oz", 226.796),
    ],
)
def test_mass_unit_conversions_scale_macros_correctly(amount, unit, expected_grams) -> None:
    # A round test food: 100 kcal / 10 P / 10 C / 5 F / 1 fiber per 100g, so the
    # scaled macro equals the gram amount divided by 100 - easy to verify by hand.
    food = _match("test food", calories=100, protein_g=10, carbs_g=10, fat_g=5, fiber_g=1)
    ingredient = NutritionIngredient(name="test food", amount=amount, unit=unit)
    client = FakeUsdaClient({"test food": food})

    result = compute_recipe_macros([ingredient], servings=1, client=client)

    assert result.status == GroundingStatus.GROUNDED
    assert result.contributions[0].grams == pytest.approx(expected_grams)
    assert result.total.calories == pytest.approx(expected_grams / 100 * 100)
    assert result.total.protein_g == pytest.approx(expected_grams / 100 * 10)


def test_multi_ingredient_sum_and_per_serving_average() -> None:
    rice = _match("rice", calories=130, protein_g=2.69, carbs_g=28.17, fat_g=0.28, fiber_g=0.4)
    ingredients = [
        NutritionIngredient(name="chicken breast", amount=200, unit="g"),
        NutritionIngredient(name="rice", amount=150, unit="g"),
    ]
    client = FakeUsdaClient({"chicken breast": CHICKEN_BREAST, "rice": rice})

    result = compute_recipe_macros(ingredients, servings=2, client=client)

    expected_total_calories = 330 + (130 * 1.5)
    assert result.status == GroundingStatus.GROUNDED
    assert result.total.calories == pytest.approx(expected_total_calories)
    assert result.per_serving.calories == pytest.approx(expected_total_calories / 2)


def test_partial_grounding_excludes_unmatched_ingredient_from_totals() -> None:
    ingredients = [
        NutritionIngredient(name="chicken breast", amount=200, unit="g"),
        NutritionIngredient(name="mystery sauce", amount=50, unit="g"),
    ]
    client = FakeUsdaClient({"chicken breast": CHICKEN_BREAST, "mystery sauce": None})

    result = compute_recipe_macros(ingredients, servings=1, client=client)

    assert result.status == GroundingStatus.PARTIAL
    assert result.ungrounded_ingredients == ["mystery sauce"]
    assert result.coverage == pytest.approx(0.5)
    # Totals must reflect only the grounded ingredient, not zero-fill the other.
    assert result.total.calories == pytest.approx(330)


def test_fully_ungrounded_status_is_distinguishable_from_a_real_zero_calorie_recipe() -> None:
    ingredients = [
        NutritionIngredient(name="mystery sauce", amount=50, unit="g"),
        NutritionIngredient(name="secret spice", amount=5, unit="g"),
    ]
    client = FakeUsdaClient({"mystery sauce": None, "secret spice": None})

    result = compute_recipe_macros(ingredients, servings=1, client=client)

    # Numerically the totals are 0, but callers must branch on `status` before
    # trusting that -- this is the whole point of GroundingStatus existing.
    assert result.status == GroundingStatus.UNGROUNDED
    assert result.total.calories == 0
    assert set(result.ungrounded_ingredients) == {"mystery sauce", "secret spice"}
    assert result.coverage == 0.0


def test_volume_or_piece_unit_is_ungrounded_until_unit_converter_lands() -> None:
    ingredient = NutritionIngredient(name="chicken breast", amount=1, unit="cup")
    client = FakeUsdaClient({"chicken breast": CHICKEN_BREAST})

    result = compute_recipe_macros([ingredient], servings=1, client=client)

    assert result.status == GroundingStatus.UNGROUNDED
    assert result.contributions[0].grounded is False
    assert result.contributions[0].grams is None
    # Unsupported units must not even trigger a lookup.
    assert client.calls == []


def test_missing_amount_is_ungrounded() -> None:
    ingredient = NutritionIngredient(name="chicken breast", amount=None, unit="g")
    client = FakeUsdaClient({"chicken breast": CHICKEN_BREAST})

    result = compute_recipe_macros([ingredient], servings=1, client=client)

    assert result.status == GroundingStatus.UNGROUNDED
    assert client.calls == []


def test_degradation_never_raises_and_never_substitutes_tag_macros() -> None:
    """A client with no API key (or any failure mode) always returns None from
    search_food -- compute_recipe_macros must not raise, and must report
    UNGROUNDED rather than quietly falling back to some other macro source."""

    ingredients = [
        NutritionIngredient(name="chicken breast", amount=200, unit="g"),
        NutritionIngredient(name="rice", amount=150, unit="g"),
    ]
    client = FakeUsdaClient({"chicken breast": None, "rice": None})

    result = compute_recipe_macros(ingredients, servings=1, client=client)

    assert result.status == GroundingStatus.UNGROUNDED
    assert result.total == FoodMacros(calories=0, protein_g=0, carbs_g=0, fat_g=0, fiber_g=0)


def test_volume_ingredient_grounds_via_density() -> None:
    # 1 cup milk -> 236.588 ml * 1.03 g/ml density before USDA scaling.
    ingredient = NutritionIngredient(name="milk", amount=1, unit="cup")
    milk = _match("milk", calories=61, protein_g=3.2, carbs_g=4.8, fat_g=3.3, fiber_g=0)
    client = FakeUsdaClient({"milk": milk})

    result = compute_recipe_macros([ingredient], servings=1, client=client)

    assert result.status == GroundingStatus.GROUNDED
    assert result.contributions[0].grams == pytest.approx(236.588 * 1.03, rel=1e-3)


def test_incomparable_unit_ungrounded() -> None:
    # A volume unit with no known density can't be converted -> ungrounded, no lookup.
    ingredient = NutritionIngredient(name="mystery sauce", amount=1, unit="cup")
    sauce = _match("mystery sauce", calories=1, protein_g=0, carbs_g=0, fat_g=0, fiber_g=0)
    client = FakeUsdaClient({"mystery sauce": sauce})

    result = compute_recipe_macros([ingredient], servings=1, client=client)

    assert result.status == GroundingStatus.UNGROUNDED
    assert result.ungrounded_ingredients == ["mystery sauce"]
    assert client.calls == []
