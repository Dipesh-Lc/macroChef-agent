import pytest

from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recipe import Recipe
from app.schemas.shopping import ShoppingItem
from app.services.procurement_service import (
    _analyze,
    build_shopping_list_for_recipe,
    merge_shopping_lists,
    split_used_and_missing,
)


def _recipe(ingredients: list[str]) -> Recipe:
    return Recipe(recipe_id="r", title="Bowl", ingredients=ingredients)


def test_present_and_sufficient_quantity_is_used() -> None:
    recipe = _recipe(["500 g chicken breast"])
    inventory = [ConfirmedIngredient(name="chicken breast", amount=600, unit="g")]

    used, missing = split_used_and_missing(recipe, inventory)

    assert used == ["chicken breast"]
    assert missing == []
    assert build_shopping_list_for_recipe(recipe, inventory) == []


def test_present_but_short_quantity_is_missing_with_shortfall() -> None:
    recipe = _recipe(["500 g chicken breast"])
    inventory = [ConfirmedIngredient(name="chicken breast", amount=200, unit="g")]

    used, missing = split_used_and_missing(recipe, inventory)
    assert used == []
    assert missing == ["chicken breast"]

    (item,) = build_shopping_list_for_recipe(recipe, inventory)
    assert item.amount == pytest.approx(300)
    assert item.unit == "g"


def test_incomparable_quantity_is_present_uncompared_and_flagged() -> None:
    # Unknown density -> the need can't be converted, so we can't verify the amount.
    recipe = _recipe(["1 cup dragonfruit"])
    inventory = [ConfirmedIngredient(name="dragonfruit", amount=1, unit="cup")]

    (result,) = _analyze(recipe, inventory)
    assert result.status == "present_uncompared"  # flagged, not a silent "satisfied"

    used, missing = split_used_and_missing(recipe, inventory)
    assert used == ["dragonfruit"]
    assert missing == []


def test_name_only_inventory_still_matches() -> None:
    # Pantry item with no amount (legacy) -> present but uncompared, not dropped.
    recipe = _recipe(["500 g chicken breast"])
    inventory = [ConfirmedIngredient(name="chicken breast")]

    (result,) = _analyze(recipe, inventory)
    assert result.status == "present_uncompared"
    assert split_used_and_missing(recipe, inventory) == (["chicken breast"], [])


def test_shopping_list_carries_structured_shortfall() -> None:
    recipe = _recipe(["2 cups rice", "300 g tofu"])
    inventory = [ConfirmedIngredient(name="rice", amount=1, unit="cup")]

    items = {item.name: item for item in build_shopping_list_for_recipe(recipe, inventory)}

    assert items["rice"].amount == pytest.approx(1.0)  # short by one cup
    assert items["rice"].unit == "cup"
    assert "short" in items["rice"].quantity
    # tofu is entirely absent -> full requested amount.
    assert items["tofu"].amount == pytest.approx(300)
    assert items["tofu"].unit == "g"


def test_merge_sums_comparable_shortfalls() -> None:
    items = [
        ShoppingItem(name="rice", amount=200, unit="g", reason="Needed for A"),
        ShoppingItem(name="rice", amount=300, unit="g", reason="Needed for B"),
    ]

    (merged,) = merge_shopping_lists(items)

    assert merged.name == "rice"
    assert merged.amount == pytest.approx(500)
    assert merged.unit == "g"
    assert merged.reason == "Needed for A; Needed for B"


def test_merge_falls_back_when_incomparable() -> None:
    items = [
        ShoppingItem(name="rice", amount=200, unit="g", quantity="short 200 g"),
        ShoppingItem(name="rice", amount=None, unit=None, quantity=None),
    ]

    (merged,) = merge_shopping_lists(items)

    assert merged.amount is None
    assert merged.unit is None
