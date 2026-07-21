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

from app.schemas.day_plan import DayPlan, PlanItem
from app.schemas.ingredient import Ingredient, scale_ingredients
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


def analyze_ingredients(recipe: Recipe, inventory: list[ConfirmedIngredient]) -> list[IngredientMatchResult]:
    """Public per-ingredient match results, aligned 1:1 (same order, same length)
    with `recipe.ingredients`.

    The fine-grained sibling of `split_used_and_missing` for callers that need
    more than a flattened name list -- e.g. `nutrition_scorer.pantry_match_score`,
    which pairs each result back up with its source `Ingredient` to weight the
    score by mass rather than by count.
    """
    return _analyze(recipe, inventory)


def split_used_and_missing(
    recipe: Recipe, inventory: list[ConfirmedIngredient]
) -> tuple[list[str], list[str]]:
    """Project the amount-aware analysis to (used, missing) name lists.

    `used` covers ingredients the pantry satisfies or can't disprove
    (`present_uncompared`); `missing` covers `short` and fully absent items.
    """
    used: list[str] = []
    missing: list[str] = []
    for result in analyze_ingredients(recipe, inventory):
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


def build_shopping_list_for_items(
    items: list[PlanItem],
    recipe_lookup: dict[str, Recipe],
    inventory: list[ConfirmedIngredient],
) -> list[ShoppingItem]:
    """Aggregate a shopping list across an arbitrary list of `PlanItem`s
    (extracted from `build_shopping_list_for_plan`, roadmap item B4, so the
    meal-prep batch solver -- `app.services.batch_planner` /
    `app.api.routes_day_planner.plan_batch` -- can reuse the exact same
    combine-then-reconcile-once logic against `BatchPlan.items` with zero
    duplication; `build_shopping_list_for_plan` below is now a one-line
    delegate to this function).

    Scale factor (confirmed against app.services.day_planner and
    app.services.grounding_job): `PlanItem.servings` is a COUNT OF SERVINGS
    of that recipe selected into the plan -- `_build_day_plan` sums
    `trusted_per_serving(recipe).calories * count` -- while `Recipe.
    ingredients` is written for the WHOLE recipe as authored, which yields
    `recipe.servings` servings (see grounding_job.py's
    `compute_recipe_macros(recipe.ingredients, servings=recipe.servings)`,
    the same divisor used to produce `per_serving`). So the amount-scaling
    factor from as-written ingredients to "ingredients needed for
    `item.servings` servings" is `item.servings / (recipe.servings or 1)`,
    NOT `item.servings` alone (which would over-scale any recipe whose
    `servings` != 1). A `PlanItem` whose `recipe_id` isn't in `recipe_lookup`
    is skipped, never fabricated.

    IMPORTANT deviation from the naive "call build_shopping_list_for_recipe
    per PlanItem, then merge_shopping_lists the results" composition: that
    naive approach double-counts pantry availability whenever two recipes in
    the same plan share an ingredient and the pantry covers each recipe's
    INDIVIDUAL need but not their SUM -- `_analyze` compares each recipe's
    need against the full, undepleted inventory independently, so an
    ingredient can be "satisfied" (shortfall 0) against recipe A and
    "satisfied" again against recipe B even though the pantry only actually
    has enough for one of them. merge_shopping_lists then sums those
    (wrong) per-recipe shortfalls, which are BOTH artificially low --
    breaking the roadmap's reconciliation gate ("list quantities equal plan
    requirements minus pantry, exactly"). See the worked failing case this
    caught in tests/test_procurement_service.py's B4 tests.

    The fix: combine every PlanItem's scaled ingredient requirements into
    ONE consolidated need per (normalized) ingredient name BEFORE any pantry
    comparison, then run pantry reconciliation exactly once (a single
    `build_shopping_list_for_recipe` call against a synthetic combined-need
    Recipe) -- reusing `_analyze`'s existing grams-based comparison and
    `present_uncompared`/`missing`/`short` semantics unmodified. This is the
    only aggregation logic B4 adds; the actual pantry comparison and
    shortfall/status computation still come entirely from `_analyze` via
    `build_shopping_list_for_recipe`, and per-ingredient contributing-recipe
    titles are reattached afterward for display.
    """
    grams_by_name: dict[str, float | None] = {}
    display_unit_by_name: dict[str, str | None] = {}
    fallback_ingredient_by_name: dict[str, Ingredient] = {}
    titles_by_name: dict[str, list[str]] = {}

    for plan_item in items:
        recipe = recipe_lookup.get(plan_item.recipe_id)
        if recipe is None:
            continue
        factor = plan_item.servings / (recipe.servings or 1)
        for ingredient in scale_ingredients(recipe.ingredients, factor):
            key = normalize_ingredient(ingredient.name)
            if not key:
                continue
            titles_by_name.setdefault(key, [])
            if recipe.title not in titles_by_name[key]:
                titles_by_name[key].append(recipe.title)

            if key not in fallback_ingredient_by_name:
                fallback_ingredient_by_name[key] = ingredient
                display_unit_by_name[key] = ingredient.unit
                grams_by_name[key] = 0.0

            grams = to_grams(ingredient.amount, ingredient.unit, name=ingredient.name)
            if grams is None or grams_by_name[key] is None:
                # Once any contributor's need can't be converted to grams,
                # the true combined total is unknown -- fall back below
                # rather than silently under/over-counting it.
                grams_by_name[key] = None
            else:
                grams_by_name[key] += grams

    combined_ingredients: list[Ingredient] = []
    for key, grams in grams_by_name.items():
        if grams is None:
            # Not every contribution was quantity-comparable -- fall back to
            # the first contributor's raw (name, amount, unit) so the
            # existing present_uncompared / missing-without-amount paths in
            # _analyze still apply rather than fabricating a combined number.
            combined_ingredients.append(fallback_ingredient_by_name[key])
            continue
        unit = display_unit_by_name[key]
        per_unit = to_grams(1, unit, name=key) if unit else None
        if per_unit:
            combined_ingredients.append(Ingredient(name=key, amount=grams / per_unit, unit=unit))
        else:
            combined_ingredients.append(Ingredient(name=key, amount=grams, unit="g"))

    plan_recipe = Recipe(recipe_id="__plan__", title="Day Plan", ingredients=combined_ingredients)
    shopping_items = build_shopping_list_for_recipe(plan_recipe, inventory)

    attributed: list[ShoppingItem] = []
    for item in shopping_items:
        titles = titles_by_name.get(item.name)
        reason = f"Needed for {', '.join(sorted(titles))}" if titles else item.reason
        attributed.append(item.model_copy(update={"reason": reason}))
    return attributed


def build_shopping_list_for_plan(
    plan: DayPlan,
    recipe_lookup: dict[str, Recipe],
    inventory: list[ConfirmedIngredient],
) -> list[ShoppingItem]:
    """Aggregate a shopping list across every `PlanItem` in a `DayPlan`
    (roadmap item B4). Thin delegate onto `build_shopping_list_for_items`
    (extracted so the meal-prep batch solver can reuse the exact same
    combine-then-reconcile-once logic against a `BatchPlan`'s items without
    duplicating it -- see that function's docstring for the full algorithm
    and the double-counting bug it fixes) -- byte-identical behavior to
    the pre-extraction implementation, verified by
    tests/test_procurement_service.py's existing B4 reconciliation tests.
    """
    return build_shopping_list_for_items(plan.items, recipe_lookup, inventory)
