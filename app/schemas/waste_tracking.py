"""Phase 4: expiry / waste tracking -- structured, deterministic nudge output.

`WasteNudge` is the ONLY shape `app.services.waste_tracking.build_waste_nudges`
returns: a small, structured object, never free text. The eventual display
copy ("use your spinach today -- 3 ways") is built from this data by a
deterministic Python template in `frontend/components/waste_nudge.py`, the
same "structured data in, templated string out, zero LLM involvement" pattern
already used by `app.schemas.recommendation.RejectedRecipe` /
`app.schemas.recommendation.TasteProfile` and their frontend counterparts
(`frontend/components/safety_banner.py`, `frontend/components/taste_profile.py`).
"""

from pydantic import BaseModel, Field


class SuggestedRecipe(BaseModel):
    """One corpus recipe suggested as a way to use an expiring ingredient
    before it goes bad. Deliberately minimal -- just enough to link/display,
    not a full `app.schemas.recipe.Recipe` (the caller already has the full
    corpus if it needs more)."""

    recipe_id: str
    title: str


class WasteNudge(BaseModel):
    """One expiring-soon inventory ingredient plus up to a few corpus
    recipes that use it. `days_until_expiry` is the same rough,
    flat-shelf-life-window estimate as
    `app.schemas.inventory.ConfirmedIngredient.days_until_expiry` -- None
    when the ingredient's `expires_soon` flag was set explicitly rather than
    derived from a logged `purchase_date` (no date to estimate from).
    `suggested_recipes` can be empty (the ingredient is expiring but no
    corpus recipe uses it) -- an empty list is still a valid, honest nudge,
    never suppressed here; the frontend template decides how to phrase that.
    """

    ingredient_name: str
    days_until_expiry: int | None = None
    suggested_recipes: list[SuggestedRecipe] = Field(default_factory=list)
