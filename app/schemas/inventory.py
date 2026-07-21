from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.ingredient import Ingredient

# `quantity` stays as free-text for display/round-trip; `amount`/`unit` are the
# structured, machine-usable quantity used for pantry reconciliation. Both are
# additive and default to unset so legacy inventory keeps working.

# Phase 4 (expiry/waste tracking): a single flat shelf-life window, not a
# per-ingredient shelf-life database -- v1 deliberately keeps this simple (see
# app.services.waste_tracking module docstring). 4 days approximates the
# shelf life of a generic fresh perishable (leafy greens, fresh herbs, ground
# meat): long enough not to nudge on day one, short enough to nudge before
# the item is actually likely spoiled. An item purchased this many days ago
# (or more) is treated as "expiring soon".
PERISHABLE_WINDOW_DAYS = 4


class InventoryObservation(BaseModel):
    raw_name: str
    normalized_name: str
    quantity: str | None = None
    amount: float | None = Field(default=None, ge=0)
    unit: str | None = None
    confidence: float = Field(ge=0, le=1)
    source: Literal["vision", "text", "manual"]
    needs_confirmation: bool = False


class ConfirmedIngredient(BaseModel):
    name: str
    quantity: str | None = None
    amount: float | None = Field(default=None, ge=0)
    unit: str | None = None
    # Optional rough purchase date (roadmap Phase 4: "users log rough
    # purchase dates for perishables"). When set, this is the source of
    # truth for `expires_soon` below -- see `_derive_expires_soon`. None
    # means "no purchase date logged", the same as before this field existed.
    purchase_date: date | None = None
    # Bare boolean expiry signal -- the only one that existed before Phase 4.
    # Kept for backward compatibility (existing callers/tests set this
    # directly and it still works exactly as before) for any ConfirmedIngredient
    # that has no `purchase_date`. Once `purchase_date` IS set, this field is
    # DERIVED from it (see `_derive_expires_soon`) rather than trusted as
    # caller-provided, so downstream readers (procurement_service,
    # waste_tracking, memory_service) never have to know which of the two
    # signals was actually supplied -- they can just read `.expires_soon`.
    expires_soon: bool = False

    @model_validator(mode="after")
    def _derive_expires_soon(self) -> "ConfirmedIngredient":
        if self.purchase_date is not None:
            days_old = (date.today() - self.purchase_date).days
            self.expires_soon = days_old >= PERISHABLE_WINDOW_DAYS
        return self

    def as_ingredient(self) -> Ingredient:
        return Ingredient(name=self.name, amount=self.amount, unit=self.unit)

    def days_until_expiry(self) -> int | None:
        """Rough days remaining in the flat perishable window, or None when
        no `purchase_date` was logged to estimate from. Can go negative once
        already past the window -- callers (e.g. app.services.waste_tracking)
        treat that as "expiring today" for display, never as a reason to
        hide/reject the ingredient (this is a display-only estimate, never a
        safety signal)."""
        if self.purchase_date is None:
            return None
        days_old = (date.today() - self.purchase_date).days
        return PERISHABLE_WINDOW_DAYS - days_old
