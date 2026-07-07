"""Single source of truth for whether a recipe's macros can be trusted, and
how that trust state should read to a user.

Both the scorer (nutrition_scorer.macro_fit_score) and the frontend
(recommendation_cards) branch on `macro_display_state` -- the internal
neutral score and the visible "macros unknown" / "partial" label are
therefore guaranteed to agree, since they come from the same function rather
than two independently-maintained checks that could drift apart.

Decision (confirmed): PARTIAL is displayed distinctly (not collapsed into
"unknown") but is never trusted for scoring -- its total only sums the
ingredients that did ground, so it systematically undercounts and would read
as falsely low-calorie if used as a macro-fit target.
"""

from typing import Literal

from app.schemas.nutrition import FoodMacros, GroundingStatus
from app.schemas.recipe import Recipe

MacroDisplayState = Literal["grounded", "partial", "unknown"]


def macro_display_state(recipe: Recipe) -> MacroDisplayState:
    if recipe.nutrition is None:
        return "unknown"
    if recipe.nutrition.status == GroundingStatus.GROUNDED:
        return "grounded"
    if recipe.nutrition.status == GroundingStatus.PARTIAL:
        return "partial"
    return "unknown"


def trusted_per_serving(recipe: Recipe) -> FoodMacros | None:
    """Computed per-serving macros, but only when fully GROUNDED -- PARTIAL
    and UNGROUNDED both return None so callers fall back to a neutral score
    rather than trusting an undercounted or absent total."""
    if recipe.nutrition is None or recipe.nutrition.status != GroundingStatus.GROUNDED:
        return None
    return recipe.nutrition.per_serving
