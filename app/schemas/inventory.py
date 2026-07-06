from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.ingredient import Ingredient

# `quantity` stays as free-text for display/round-trip; `amount`/`unit` are the
# structured, machine-usable quantity used for pantry reconciliation. Both are
# additive and default to unset so legacy inventory keeps working.


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
    expires_soon: bool = False

    def as_ingredient(self) -> Ingredient:
        return Ingredient(name=self.name, amount=self.amount, unit=self.unit)
