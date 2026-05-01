from pydantic import BaseModel


class ShoppingItem(BaseModel):
    name: str
    quantity: str | None = None
    reason: str | None = None
