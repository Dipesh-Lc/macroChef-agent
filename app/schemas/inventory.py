from typing import Literal

from pydantic import BaseModel, Field


class InventoryObservation(BaseModel):
    raw_name: str
    normalized_name: str
    quantity: str | None = None
    confidence: float = Field(ge=0, le=1)
    source: Literal["vision", "text", "manual"]
    needs_confirmation: bool = False


class ConfirmedIngredient(BaseModel):
    name: str
    quantity: str | None = None
    expires_soon: bool = False
