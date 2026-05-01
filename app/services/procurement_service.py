from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recipe import Recipe
from app.schemas.shopping import ShoppingItem
from app.utils.ingredient_normalizer import ingredient_matches, normalize_ingredient


def split_used_and_missing(
    recipe: Recipe, inventory: list[ConfirmedIngredient]
) -> tuple[list[str], list[str]]:
    inventory_names = [normalize_ingredient(item.name) for item in inventory]
    used: list[str] = []
    missing: list[str] = []

    for ingredient in recipe.ingredients:
        normalized = normalize_ingredient(ingredient)
        if any(ingredient_matches(normalized, available) for available in inventory_names):
            used.append(normalized)
        else:
            missing.append(normalized)

    return used, missing


def build_shopping_list_for_recipe(
    recipe: Recipe, inventory: list[ConfirmedIngredient]
) -> list[ShoppingItem]:
    _, missing = split_used_and_missing(recipe, inventory)
    return [
        ShoppingItem(name=name, quantity=None, reason=f"Needed for {recipe.title}") for name in missing
    ]


def merge_shopping_lists(items: list[ShoppingItem]) -> list[ShoppingItem]:
    merged: dict[str, ShoppingItem] = {}
    reasons: dict[str, set[str]] = {}
    for item in items:
        key = normalize_ingredient(item.name)
        if key not in merged:
            merged[key] = ShoppingItem(name=key, quantity=item.quantity, reason=item.reason)
            reasons[key] = set()
        if item.reason:
            reasons[key].add(item.reason)

    return [
        ShoppingItem(name=item.name, quantity=item.quantity, reason="; ".join(sorted(reasons[key])) or None)
        for key, item in sorted(merged.items())
    ]
