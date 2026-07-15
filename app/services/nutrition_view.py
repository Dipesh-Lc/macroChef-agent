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

Trust-demoting flags (confirmed, phase 1.5 item 4/P3): `RecipeNutrition.flags`
is computed from the recipe's OWN computed values (see `grounding_job.py`'s
implausible-kcal-band check) -- never from LLM output, never from the
self-reported tag macros. A non-empty `flags` demotes trust to "unknown"
regardless of `status`, EVEN when `status` is `GROUNDED` -- an implausible
number that happens to cover every ingredient is not more trustworthy than
one that doesn't. This module is the one place that check happens, so the
scorer and the frontend/index can never disagree about it.
"""

from typing import Literal

from app.schemas.nutrition import FoodMacros, GroundingStatus
from app.schemas.recipe import Recipe

MacroDisplayState = Literal["grounded", "partial", "unknown"]


def macro_display_state(recipe: Recipe) -> MacroDisplayState:
    if recipe.nutrition is None:
        return "unknown"
    if recipe.nutrition.flags:
        return "unknown"
    if recipe.nutrition.status == GroundingStatus.GROUNDED:
        return "grounded"
    if recipe.nutrition.status == GroundingStatus.PARTIAL:
        return "partial"
    return "unknown"


def trusted_per_serving(recipe: Recipe) -> FoodMacros | None:
    """Computed per-serving macros, but only when fully GROUNDED and free of
    any trust-demoting flag -- PARTIAL, UNGROUNDED, and flagged-GROUNDED all
    return None so callers fall back to a neutral score rather than trusting
    an undercounted, absent, or implausible total."""
    if recipe.nutrition is None or recipe.nutrition.status != GroundingStatus.GROUNDED:
        return None
    if recipe.nutrition.flags:
        return None
    return recipe.nutrition.per_serving
