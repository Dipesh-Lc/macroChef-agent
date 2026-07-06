"""Amount-aware pantry reconciliation and shopping-list construction.

Matching is still name-based (via `ingredient_matches`), but once an ingredient
is present we compare *quantities*: convert what's needed and what's on hand to
grams and decide whether the pantry actually covers the recipe. When quantities
can't be compared (missing amounts, or an ingredient with no known density/piece
weight) we fall back to the old "present = satisfied" behavior — but that
fallback is recorded as an explicit `present_uncompared` status rather than a
silent "have enough", so callers can surface that the amount wasn't verified.
"""

from dataclasses import dataclass
from typing import Literal

from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recipe import Recipe
from app.schemas.shopping import ShoppingItem
from app.utils.ingredient_normalizer import ingredient_matches, normalize_ingredient
from app.utils.unit_converter import to_grams

_EPSILON = 1e-6

MatchStatus = Literal["satisfied", "short", "present_uncompared", "missing"]


@dataclass
class IngredientMatchResult:
    """Outcome of reconciling one recipe ingredient against the pantry.

    `status` is deliberately explicit so the name-only fallback
    (`present_uncompared`) is never mistaken for a verified `satisfied`.
    """

    name: str  # normalized recipe ingredient name
    status: MatchStatus
    shortfall_amount: float | None = None
    shortfall_unit: str | None = None


def _available_grams(matches: list[ConfirmedIngredient], name: str) -> float | None:
    """Total grams on hand across matched pantry items, or None if unknowable.

    If any matched pantry item can't be converted to grams (no amount, or an
    unknown unit/density), the true total is unknown and we return None.
    """
    total = 0.0
    for item in matches:
        grams = to_grams(item.amount, item.unit, name=item.name or name)
        if grams is None:
            return None
        total += grams
    return total


def _analyze(recipe: Recipe, inventory: list[ConfirmedIngredient]) -> list[IngredientMatchResult]:
    results: list[IngredientMatchResult] = []
    for ingredient in recipe.ingredients:
        normalized = normalize_ingredient(ingredient.name)
        matches = [item for item in inventory if ingredient_matches(ingredient.name, item.name)]

        if not matches:
            results.append(
                IngredientMatchResult(
                    name=normalized,
                    status="missing",
                    shortfall_amount=ingredient.amount,
                    shortfall_unit=ingredient.unit,
                )
            )
            continue

        need_grams = to_grams(ingredient.amount, ingredient.unit, name=ingredient.name)
        have_grams = _available_grams(matches, ingredient.name)

        if need_grams is None or have_grams is None:
            # Present, but quantities can't be compared — flagged, not silent.
            results.append(IngredientMatchResult(name=normalized, status="present_uncompared"))
        elif have_grams >= need_grams - _EPSILON:
            results.append(IngredientMatchResult(name=normalized, status="satisfied"))
        else:
            deficit_grams = need_grams - have_grams
            per_unit = to_grams(1, ingredient.unit, name=ingredient.name)
            if per_unit:
                shortfall_amount = round(deficit_grams / per_unit, 2)
                shortfall_unit = ingredient.unit
            else:
                shortfall_amount = round(deficit_grams, 2)
                shortfall_unit = "g"
            results.append(
                IngredientMatchResult(
                    name=normalized,
                    status="short",
                    shortfall_amount=shortfall_amount,
                    shortfall_unit=shortfall_unit,
                )
            )
    return results


def split_used_and_missing(
    recipe: Recipe, inventory: list[ConfirmedIngredient]
) -> tuple[list[str], list[str]]:
    """Project the amount-aware analysis to (used, missing) name lists.

    `used` covers ingredients the pantry satisfies or can't disprove
    (`present_uncompared`); `missing` covers `short` and fully absent items.
    """
    used: list[str] = []
    missing: list[str] = []
    for result in _analyze(recipe, inventory):
        if result.status in ("satisfied", "present_uncompared"):
            used.append(result.name)
        else:
            missing.append(result.name)
    return used, missing


def _shortfall_display(result: IngredientMatchResult) -> str | None:
    if result.shortfall_amount is None:
        return None
    amount = f"{result.shortfall_amount:g}"
    quantity = f"{amount} {result.shortfall_unit}" if result.shortfall_unit else amount
    return f"short {quantity}" if result.status == "short" else quantity


def build_shopping_list_for_recipe(
    recipe: Recipe, inventory: list[ConfirmedIngredient]
) -> list[ShoppingItem]:
    items: list[ShoppingItem] = []
    for result in _analyze(recipe, inventory):
        if result.status not in ("short", "missing"):
            continue
        note = "partial — buy more" if result.status == "short" else "not in pantry"
        items.append(
            ShoppingItem(
                name=result.name,
                quantity=_shortfall_display(result),
                amount=result.shortfall_amount,
                unit=result.shortfall_unit,
                reason=f"Needed for {recipe.title} ({note})",
            )
        )
    return items


def _combine_quantities(
    group: list[ShoppingItem], name: str
) -> tuple[float | None, str | None, str | None]:
    """Sum shortfalls across recipes when comparable; else give up gracefully."""
    grams: list[float] = []
    for item in group:
        converted = to_grams(item.amount, item.unit, name=name)
        if converted is None:
            # An incomparable member — keep the first usable display, no total.
            quantity = next((i.quantity for i in group if i.quantity), None)
            return None, None, quantity
        grams.append(converted)

    total_grams = sum(grams)
    target_unit = group[0].unit
    per_unit = to_grams(1, target_unit, name=name) if target_unit else None
    if per_unit:
        amount = round(total_grams / per_unit, 2)
        unit = target_unit
    else:
        amount = round(total_grams, 2)
        unit = "g"
    quantity = f"{amount:g} {unit}" if unit else f"{amount:g}"
    return amount, unit, quantity


def merge_shopping_lists(items: list[ShoppingItem]) -> list[ShoppingItem]:
    groups: dict[str, list[ShoppingItem]] = {}
    for item in items:
        groups.setdefault(normalize_ingredient(item.name), []).append(item)

    merged: list[ShoppingItem] = []
    for key in sorted(groups):
        group = groups[key]
        reasons = sorted({item.reason for item in group if item.reason})
        amount, unit, quantity = _combine_quantities(group, key)
        merged.append(
            ShoppingItem(
                name=key,
                quantity=quantity,
                amount=amount,
                unit=unit,
                reason="; ".join(reasons) or None,
            )
        )
    return merged
