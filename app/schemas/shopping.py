from pydantic import BaseModel, Field


class ShoppingItem(BaseModel):
    name: str
    quantity: str | None = None  # free-text display, e.g. "short 300 g"
    amount: float | None = Field(default=None, ge=0)  # structured shortfall amount
    unit: str | None = None  # structured shortfall unit
    reason: str | None = None
