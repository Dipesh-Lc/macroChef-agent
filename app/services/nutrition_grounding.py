import asyncio

from app.schemas.nutrition import (
    FoodMacros,
    FoodMatch,
    GroundingStatus,
    IngredientContribution,
    NutritionIngredient,
    RecipeNutrition,
)
from app.services.usda_client import UsdaClient
from app.utils.unit_converter import to_grams

_MACRO_FIELDS = ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g")


def _scale_macros(macros: FoodMacros, grams: float) -> FoodMacros:
    scale = grams / 100.0
    return FoodMacros(**{field: getattr(macros, field) * scale for field in _MACRO_FIELDS})


def _aggregate_recipe_nutrition(
    ingredients: list[NutritionIngredient],
    lookups: list[tuple[float | None, FoodMatch | None]],
    servings: int,
) -> RecipeNutrition:
    """Shared aggregation tail for `compute_recipe_macros`/`compute_recipe_
    macros_async` (ROADMAP.md Phase 2, Step 2.2): both functions differ only
    in HOW they get each ingredient's `(grams, match)` pair (sequentially vs
    fanned out via `asyncio.gather`) -- once that list exists, in the same
    order as `ingredients` (`asyncio.gather` preserves input order, same as
    the sync loop), turning it into totals/coverage/status is identical pure
    logic, kept in exactly one place so the two paths can never quietly
    diverge in what counts as grounded."""
    contributions: list[IngredientContribution] = []
    ungrounded_names: list[str] = []
    totals = dict.fromkeys(_MACRO_FIELDS, 0.0)
    grounded_count = 0

    for ingredient, (grams, match) in zip(ingredients, lookups, strict=True):
        macros = None
        grounded = False

        if match is not None:
            macros = _scale_macros(match.macros, grams)
            for field in _MACRO_FIELDS:
                totals[field] += getattr(macros, field)
            grounded = True
            grounded_count += 1

        if not grounded:
            ungrounded_names.append(ingredient.name)

        contributions.append(
            IngredientContribution(
                name=ingredient.name,
                grams=grams,
                match=match,
                macros=macros,
                grounded=grounded,
            )
        )

    ingredient_count = len(ingredients)
    coverage = grounded_count / ingredient_count if ingredient_count else 0.0

    if ingredient_count == 0 or grounded_count == 0:
        status = GroundingStatus.UNGROUNDED
    elif grounded_count == ingredient_count:
        status = GroundingStatus.GROUNDED
    else:
        status = GroundingStatus.PARTIAL

    total_macros = FoodMacros(**totals)
    per_serving = FoodMacros(**{field: totals[field] / servings for field in _MACRO_FIELDS})

    return RecipeNutrition(
        status=status,
        servings=servings,
        total=total_macros,
        per_serving=per_serving,
        contributions=contributions,
        ungrounded_ingredients=ungrounded_names,
        coverage=round(coverage, 4),
    )


def compute_recipe_macros(
    ingredients: list[NutritionIngredient],
    servings: int = 1,
    *,
    client: UsdaClient,
) -> RecipeNutrition:
    """Compute a recipe's macros from its quantity-aware ingredient list.

    Each ingredient is converted to grams (mass directly, volume via density,
    counts via per-piece weight — see `unit_converter`) and looked up in USDA
    FDC via `client`, gated to `ingredient.preparation` when set (see
    `UsdaClient.search_food`) so a declared-cooked grain/legume can't silently
    resolve to a raw record. Ingredients that can't be converted or matched
    (including a preparation-gate miss) are recorded in `ungrounded_ingredients`
    and excluded from the totals — they are never silently treated as
    contributing zero, and the returned `status` makes the coverage gap
    explicit to callers. See `RecipeNutrition` for how to interpret
    `GROUNDED` / `PARTIAL` / `UNGROUNDED`.
    """

    lookups: list[tuple[float | None, FoodMatch | None]] = []
    for ingredient in ingredients:
        grams = to_grams(ingredient.amount, ingredient.unit, name=ingredient.name)
        match = None
        if grams is not None:
            match = client.search_food(ingredient.name, preparation=ingredient.preparation)
        lookups.append((grams, match))

    return _aggregate_recipe_nutrition(ingredients, lookups, servings)


async def compute_recipe_macros_async(
    ingredients: list[NutritionIngredient],
    servings: int = 1,
    *,
    client: UsdaClient,
    semaphore: asyncio.Semaphore,
) -> RecipeNutrition:
    """Async, fanned-out sibling of `compute_recipe_macros` (ROADMAP.md
    Phase 2, Step 2.2): looks up every ingredient's USDA match concurrently
    via `asyncio.gather`, bounded by `semaphore` (shared across an entire
    grounding run -- see `grounding_job.run_grounding_async`, which is what
    actually sizes it from `Settings.llm_max_concurrency`), instead of one
    ingredient at a time. Unit conversion (`to_grams`) is pure CPU and stays
    outside the semaphore; only the real network-bound `client.
    search_food_async` call is gated, so the concurrency bound reflects
    actual outbound USDA requests, not incidental Python work.

    Produces the exact same `RecipeNutrition` a sequential `compute_recipe_
    macros` call would for the same ingredients/matches -- see
    `_aggregate_recipe_nutrition`, the single aggregation tail both share.
    """

    async def _lookup(ingredient: NutritionIngredient) -> tuple[float | None, FoodMatch | None]:
        grams = to_grams(ingredient.amount, ingredient.unit, name=ingredient.name)
        if grams is None:
            # No network call to make (mirrors the sync path's `if grams is
            # not None` guard) -- and nothing to gate behind the semaphore.
            return grams, None
        async with semaphore:
            match = await client.search_food_async(
                ingredient.name, preparation=ingredient.preparation
            )
        return grams, match

    lookups = list(await asyncio.gather(*(_lookup(ingredient) for ingredient in ingredients)))
    return _aggregate_recipe_nutrition(ingredients, lookups, servings)
