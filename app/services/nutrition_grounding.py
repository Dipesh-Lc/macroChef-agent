from app.schemas.nutrition import (
    FoodMacros,
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

    contributions: list[IngredientContribution] = []
    ungrounded_names: list[str] = []
    totals = dict.fromkeys(_MACRO_FIELDS, 0.0)
    grounded_count = 0

    for ingredient in ingredients:
        grams = to_grams(ingredient.amount, ingredient.unit, name=ingredient.name)
        match = None
        macros = None
        grounded = False

        if grams is not None:
            match = client.search_food(ingredient.name, preparation=ingredient.preparation)
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
