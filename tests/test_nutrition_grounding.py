import asyncio

import pytest

from app.schemas.nutrition import FoodMacros, FoodMatch, GroundingStatus, NutritionIngredient
from app.services.nutrition_grounding import compute_recipe_macros, compute_recipe_macros_async


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


def test_null_amount_ingredient_mixed_with_grounded_does_not_zero_fill() -> None:
    """Locks in the null-amount handling described in `compute_recipe_macros`'s
    docstring: a `None` amount must never be silently coerced to a real zero
    quantity that still goes through USDA lookup and scaling.

    A bare total-value check can't tell "correctly excluded" apart from
    "wrongly coerced to grams=0.0" -- scaling any matched food by 0 grams
    also yields 0 macros, so the total would look identical either way. The
    signal that actually distinguishes the two is whether a lookup was even
    attempted for the null-amount ingredient, and whether it counts toward
    `grounded_count` / coverage / status -- so this test asserts on those,
    not just on the total.
    """
    rice = _match("rice", calories=130, protein_g=2.69, carbs_g=28.17, fat_g=0.28, fiber_g=0.4)
    milk = _match("milk", calories=61, protein_g=3.2, carbs_g=4.8, fat_g=3.3, fiber_g=0)
    ingredients = [
        NutritionIngredient(name="chicken breast", amount=200, unit="g"),
        NutritionIngredient(name="rice", amount=150, unit="g"),
        NutritionIngredient(name="milk", amount=1, unit="cup"),
        NutritionIngredient(name="salt", amount=None, unit="g"),
    ]
    client = FakeUsdaClient(
        {"chicken breast": CHICKEN_BREAST, "rice": rice, "milk": milk, "salt": None}
    )

    result = compute_recipe_macros(ingredients, servings=1, client=client)

    # 1. The null-amount ingredient's contribution is excluded outright, not
    #    zero-filled: no lookup was attempted for it (a wrongly-coerced
    #    grams=0.0 would still trigger a `search_food` call), and its
    #    `grams` field stays `None` rather than becoming a real 0.0.
    assert "salt" not in client.calls
    salt_contribution = next(c for c in result.contributions if c.name == "salt")
    assert salt_contribution.grams is None
    assert salt_contribution.grounded is False
    assert salt_contribution.macros is None

    # 2. It shows up in the exact "ungrounded" tracking structure the module
    #    reports (`ungrounded_ingredients`), not merged away.
    assert result.ungrounded_ingredients == ["salt"]

    # 3. Coverage/status reflect 3 of 4 ingredients grounded, not full
    #    coverage -- if `None` were ever coerced to a lookup-triggering 0,
    #    this would wrongly read back as GROUNDED / coverage 1.0.
    assert result.status == GroundingStatus.PARTIAL
    assert result.coverage == pytest.approx(0.75)

    # Totals reflect only the three grounded ingredients (computed by hand),
    # confirming the null-amount row contributed nothing -- neither a real
    # value nor a silent zero-filled entry that would still count as grounded.
    milk_grams = 236.588 * 1.03
    expected_total_calories = 330 + (130 * 1.5) + (61 * milk_grams / 100)
    assert result.total.calories == pytest.approx(expected_total_calories, rel=1e-3)


def test_incomparable_unit_ungrounded() -> None:
    # A volume unit with no known density can't be converted -> ungrounded, no lookup.
    ingredient = NutritionIngredient(name="mystery sauce", amount=1, unit="cup")
    sauce = _match("mystery sauce", calories=1, protein_g=0, carbs_g=0, fat_g=0, fiber_g=0)
    client = FakeUsdaClient({"mystery sauce": sauce})

    result = compute_recipe_macros([ingredient], servings=1, client=client)

    assert result.status == GroundingStatus.UNGROUNDED
    assert result.ungrounded_ingredients == ["mystery sauce"]
    assert client.calls == []


# ---------------------------------------------------------------------------
# compute_recipe_macros_async (ROADMAP.md Phase 2, Step 2.2) -- produces the
# same RecipeNutrition a sequential compute_recipe_macros call would, over
# ingredients looked up concurrently instead of one at a time. No
# `pytest-asyncio` dependency -- each test drives its own coroutine via a
# plain `asyncio.run(...)`.
# ---------------------------------------------------------------------------


class FakeAsyncUsdaClient:
    """Async-sibling test double of this file's `FakeUsdaClient` -- same
    fixed-match-per-name contract, just an `async def search_food_async`
    instead of a sync `search_food`."""

    def __init__(self, matches: dict[str, FoodMatch | None]):
        self._matches = matches
        self.calls: list[str] = []

    async def search_food_async(
        self, name: str, *, preparation: str | None = None
    ) -> FoodMatch | None:
        self.calls.append(name)
        return self._matches.get(name)


def test_compute_recipe_macros_async_matches_the_sync_result_for_the_same_inputs() -> None:
    """The async path must be a pure concurrency change, never a behavior
    change -- same ingredients/matches must produce the identical
    RecipeNutrition (status, totals, per-serving, coverage, ungrounded
    list) either way."""
    ingredients = [
        NutritionIngredient(name="chicken breast", amount=200, unit="g"),
        NutritionIngredient(name="rice", amount=150, unit="g"),
        NutritionIngredient(name="mystery sauce", amount=50, unit="g"),
    ]
    rice = _match("rice", calories=130, protein_g=2.69, carbs_g=28.17, fat_g=0.28, fiber_g=0.4)
    matches = {"chicken breast": CHICKEN_BREAST, "rice": rice, "mystery sauce": None}

    sync_result = compute_recipe_macros(ingredients, servings=2, client=FakeUsdaClient(matches))

    async_client = FakeAsyncUsdaClient(matches)
    async_result = asyncio.run(
        compute_recipe_macros_async(
            ingredients, servings=2, client=async_client, semaphore=asyncio.Semaphore(4)
        )
    )

    assert async_result.status == sync_result.status
    assert async_result.total == sync_result.total
    assert async_result.per_serving == sync_result.per_serving
    assert async_result.coverage == sync_result.coverage
    assert async_result.ungrounded_ingredients == sync_result.ungrounded_ingredients
    async_names = [c.name for c in async_result.contributions]
    sync_names = [c.name for c in sync_result.contributions]
    assert async_names == sync_names


def test_compute_recipe_macros_async_never_looks_up_an_ingredient_with_no_grams() -> None:
    """Mirrors test_volume_or_piece_unit_is_ungrounded_until_unit_converter_
    lands's sync assertion: an unconvertible unit must never trigger a
    lookup (and so never touch the semaphore) in the async path either."""
    ingredient = NutritionIngredient(name="chicken breast", amount=1, unit="cup")
    client = FakeAsyncUsdaClient({"chicken breast": CHICKEN_BREAST})

    result = asyncio.run(
        compute_recipe_macros_async(
            [ingredient], servings=1, client=client, semaphore=asyncio.Semaphore(4)
        )
    )

    assert result.status == GroundingStatus.UNGROUNDED
    assert result.contributions[0].grounded is False
    assert result.contributions[0].grams is None
    assert client.calls == []


def test_compute_recipe_macros_async_respects_the_semaphore_bound() -> None:
    """Every ingredient lookup is gated by the caller-supplied semaphore --
    with a semaphore of 1, lookups can never overlap even though they're all
    launched via asyncio.gather."""
    in_flight = {"current": 0, "max": 0}

    class _SlowAsyncClient:
        async def search_food_async(self, name: str, *, preparation: str | None = None):
            in_flight["current"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["current"])
            await asyncio.sleep(0.01)
            in_flight["current"] -= 1
            return CHICKEN_BREAST

    ingredients = [NutritionIngredient(name=f"food {i}", amount=100, unit="g") for i in range(5)]

    result = asyncio.run(
        compute_recipe_macros_async(
            ingredients, servings=1, client=_SlowAsyncClient(), semaphore=asyncio.Semaphore(1)
        )
    )

    assert result.status == GroundingStatus.GROUNDED
    assert in_flight["max"] == 1
