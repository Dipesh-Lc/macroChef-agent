"""The canonical quantity-aware ingredient: {name, amount, unit}.

This is the one structured ingredient shape used across recipes, inventory, and
nutrition grounding. `amount`/`unit` are optional so legacy name-only data and
LLM outputs load without a destructive migration — a bare string is coerced on
read via the leading-quantity parser. Kept in a leaf schema module (imports only
the `quantity_parser` util) so both `recipe.py` and `nutrition.py` can depend on
it without import cycles.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.utils.quantity_parser import parse_quantity_string


class Ingredient(BaseModel):
    name: str
    amount: float | None = Field(default=None, ge=0)
    unit: str | None = None
    # Declared measurement state for ingredients whose raw and cooked/canned
    # forms differ sharply in calorie density (grains, legumes) -- e.g. "150 g
    # cooked rice" vs "150 g raw rice" differ ~3x in calories. None means no
    # state was declared (most ingredients don't need one). Nutrition
    # grounding (app/services/usda_client.py) uses this to gate USDA matches
    # to the same state rather than accepting whichever record ranks first.
    preparation: Literal["raw", "cooked", "canned"] | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        # Accept legacy bare strings ("150 g chicken breast", "spinach") and
        # coerce them to {name, amount, unit}. Dicts and Ingredient instances
        # pass through untouched.
        if isinstance(data, str):
            return parse_quantity_string(data)
        # TODO(flag-2): a dict whose "name" embeds a quantity (e.g.
        # {"name": "150 g chicken"}) is trusted as-is and NOT re-parsed, so its
        # amount stays None. This is safe only because current callers pass
        # already-structured dicts (model_dump output, or recipe_generation_
        # service._coerce_ingredient_list, which parses before building dicts).
        # Revisit if any future caller hand-builds ingredient dicts with
        # embedded quantities in the name.
        return data

    def display(self) -> str:
        """Human-readable form, e.g. '150 g chicken breast' or 'spinach'."""
        if self.amount is None:
            return self.name
        amount = f"{self.amount:g}"
        return f"{amount} {self.unit} {self.name}" if self.unit else f"{amount} {self.name}"
