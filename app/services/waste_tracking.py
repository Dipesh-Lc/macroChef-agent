"""Phase 4: expiry / waste tracking.

"Users log rough purchase dates for perishables; system nudges 'use your
spinach today -- 3 ways.' Recurring-use hook + quantifiable money/waste
saved." (docs/ROADMAP.md Phase 4.)

This module is purely informational/display -- it never touches allergy or
diet filtering, and it never blocks a recipe from being served. Everything
here runs strictly downstream of (and blind to) `app.services.
constraint_engine`: `build_waste_nudges` only re-surfaces recipes that
already exist in the (already-safety-filtered-elsewhere) corpus, it never
introduces a new recipe candidate of its own. All ingredient matching reuses
`app.utils.ingredient_normalizer.normalize_ingredient`/`ingredient_matches`
-- no new matching logic is invented here, mirroring the same discipline as
`app.services.procurement_service`.

Scope note on the "recurring-use hook + money/waste saved" half of the
roadmap line: this module computes a plain COUNT
(`count_ingredients_used_before_expiring`) -- never a dollar figure. Any
monetary estimate is explicitly out of scope; it belongs to the separately
paused "cost estimation v1" roadmap item, which is blocked on a unit-bearing
corpus decision (see docs/BACKLOG.md, "Units decision -- 2026-07-17"). No
pricing/cost logic of any kind exists in this module.
"""

from __future__ import annotations

from functools import lru_cache

from app.rag.loaders import load_corpus
from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recipe import Recipe
from app.schemas.waste_tracking import SuggestedRecipe, WasteNudge
from app.services.memory_service import get_user_memory
from app.utils.ingredient_normalizer import ingredient_matches, normalize_ingredient

# "A small number (e.g. up to 3)" per the task spec -- no ranking
# sophistication for v1, just the first N corpus matches found.
_DEFAULT_MAX_SUGGESTED_RECIPES = 3


@lru_cache(maxsize=1)
def _cached_corpus() -> tuple[Recipe, ...]:
    # The base corpus (~4k recipes) is effectively static within a process
    # lifetime -- re-walking it on every request that has an expiring-soon
    # inventory item would add real, avoidable latency (measured ~0.8s per
    # `load_corpus()` call). Mirrors `app.services.memory_service.
    # _cached_base_corpus`'s identical @lru_cache(maxsize=1) pattern for the
    # same resource; kept as this module's own copy (rather than importing
    # memory_service's private helper) to avoid reaching into another
    # module's private API. Both callers below only hit this at all when
    # there is at least one expiring-soon ingredient to look up -- the
    # common "nothing expiring" case never touches it.
    return tuple(load_corpus())


def _recipes_using_ingredient(
    ingredient_name: str, corpus: list[Recipe], limit: int
) -> list[SuggestedRecipe]:
    matches: list[SuggestedRecipe] = []
    for recipe in corpus:
        if not recipe.is_active:
            continue
        if any(ingredient_matches(ingredient_name, item.name) for item in recipe.ingredients):
            matches.append(SuggestedRecipe(recipe_id=recipe.recipe_id, title=recipe.title))
            if len(matches) >= limit:
                break
    return matches


def build_waste_nudges(
    inventory: list[ConfirmedIngredient],
    corpus: list[Recipe] | None = None,
    *,
    max_recipes_per_ingredient: int = _DEFAULT_MAX_SUGGESTED_RECIPES,
) -> list[WasteNudge]:
    """Deterministic "use your X today -- N ways" nudges for the caller's
    current inventory.

    An ingredient is "expiring soon" purely via `ConfirmedIngredient.
    expires_soon` -- already the derived signal (see
    `app.schemas.inventory.ConfirmedIngredient._derive_expires_soon`) when a
    `purchase_date` was logged, or the caller's own explicit flag otherwise.
    This function makes no expiry decision of its own; it only reads that
    field.

    `corpus` is injectable for tests (a small synthetic recipe list); a real
    caller omits it and the full base recipe corpus
    (`app.rag.loaders.load_corpus`) is searched. Returns `[]` when nothing in
    `inventory` is expiring soon -- never fabricates a nudge.

    Duplicate ingredient names in `inventory` (same normalized name, e.g.
    two separate "spinach" rows) are merged into a single `WasteNudge` --
    the first matching item's `days_until_expiry` wins (arbitrary but
    deterministic ordering: `inventory`'s own order).
    """
    expiring = [item for item in inventory if item.expires_soon]
    if not expiring:
        return []

    recipes = corpus if corpus is not None else _cached_corpus()
    nudges: list[WasteNudge] = []
    seen_names: set[str] = set()
    for item in expiring:
        key = normalize_ingredient(item.name)
        if not key or key in seen_names:
            continue
        seen_names.add(key)
        suggested = _recipes_using_ingredient(item.name, recipes, max_recipes_per_ingredient)
        nudges.append(
            WasteNudge(
                ingredient_name=key,
                days_until_expiry=item.days_until_expiry(),
                suggested_recipes=suggested,
            )
        )
    return nudges


def count_ingredients_used_before_expiring(
    user_id: str,
    inventory: list[ConfirmedIngredient],
    corpus: list[Recipe] | None = None,
) -> int:
    """Modest "recurring-use hook" metric (roadmap Phase 4): how many of the
    CURRENT inventory's expiring-soon ingredients also appear in a recipe
    this user has already cooked, per their own feedback history
    (`app.services.memory_service.get_user_memory` -- its "liked" bucket
    already includes `feedback_type == "cooked"`, see
    `app.data.repositories.FeedbackRepository.get_liked_recipe_ids`).

    Returns a plain COUNT of distinct expiring ingredient names, never a
    dollar figure -- see the module docstring for why. This is a cheap,
    read-only cross-reference against data the app already tracks; it adds
    no new tracking infrastructure of its own. A deeper "waste-savings
    dashboard" (historical, cross-session tracking of ingredients that
    actually expired unused) is out of scope for v1 -- see docs/BACKLOG.md.

    `corpus` is injectable for tests, mirroring `build_waste_nudges`.
    """
    expiring_names = {
        normalize_ingredient(item.name) for item in inventory if item.expires_soon and item.name
    }
    if not expiring_names:
        return 0

    recipes = corpus if corpus is not None else _cached_corpus()
    recipe_lookup = {recipe.recipe_id: recipe for recipe in recipes}

    cooked_or_liked_ids, _disliked_ids = get_user_memory(user_id)
    used_names: set[str] = set()
    for recipe_id in cooked_or_liked_ids:
        recipe = recipe_lookup.get(recipe_id)
        if recipe is None:
            continue
        for ingredient in recipe.ingredients:
            key = normalize_ingredient(ingredient.name)
            if key in expiring_names:
                used_names.add(key)
    return len(used_names)
