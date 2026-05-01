class MacroChefError(Exception):
    """Base exception for domain-specific failures."""


class RecipeRetrievalError(MacroChefError):
    """Raised when both semantic and fallback recipe retrieval fail."""


class InventoryExtractionError(MacroChefError):
    """Raised when inventory extraction cannot produce usable observations."""
