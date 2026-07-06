from app.schemas.nutrition import (
    FoodMacros,
    GroundingStatus,
    IngredientContribution,
    NutritionIngredient,
    RecipeNutrition,
)
from app.services.usda_client import UsdaClient

# Interim mass-only conversion. Item 1.2 (quantity/unit data model) delivers the
# authoritative unit-conversion layer covering volume and piece units with
# density handling; this table is a deliberately narrow stand-in so grounding
# can ship now. Unknown/volume/piece units resolve to `None` (ungrounded)
# rather than guessing a conversion.
_MASS_TO_GRAMS: dict[str, float] = {
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "mg": 0.001,
    "milligram": 0.001,
    "milligrams": 0.001,
    "oz": 28.3495,
    "ounce": 28.3495,
    "ounces": 28.3495,
    "lb": 453.592,
    "lbs": 453.592,
    "pound": 453.592,
    "pounds": 453.592,
}

_MACRO_FIELDS = ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g")


def _mass_to_grams(amount: float | None, unit: str | None) -> float | None:
    if amount is None or unit is None:
        return None
    factor = _MASS_TO_GRAMS.get(unit.strip().lower().rstrip("."))
    if factor is None:
        return None
    return amount * factor


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

    Each ingredient is converted to grams (mass units only, for now) and
    looked up in USDA FDC via `client`. Ingredients that can't be converted
    or matched are recorded in `ungrounded_ingredients` and excluded from the
    totals — they are never silently treated as contributing zero, and the
    returned `status` makes the coverage gap explicit to callers. See
    `RecipeNutrition` for how to interpret `GROUNDED` / `PARTIAL` /
    `UNGROUNDED`.
    """

    contributions: list[IngredientContribution] = []
    ungrounded_names: list[str] = []
    totals = dict.fromkeys(_MACRO_FIELDS, 0.0)
    grounded_count = 0

    for ingredient in ingredients:
        grams = _mass_to_grams(ingredient.amount, ingredient.unit)
        match = None
        macros = None
        grounded = False

        if grams is not None:
            match = client.search_food(ingredient.name)
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
