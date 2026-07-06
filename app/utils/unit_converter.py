"""Deterministic unit conversion for quantity-aware ingredients.

Same-dimension conversions (mass<->mass, volume<->volume) are exact. Cross-
dimension conversions (volume<->mass, count<->mass) require an ingredient's
density or per-piece weight; these live in small, curated, single-sourced tables
below. When the ingredient isn't in a table the conversion returns ``None``
("incomparable") — callers must degrade visibly rather than guess a density.

The unit vocabulary and base factors come from :mod:`app.utils.quantity_parser`
so parsing and conversion can't drift.
"""

from typing import Literal

from app.utils.ingredient_normalizer import normalize_ingredient
from app.utils.quantity_parser import (
    COUNT_UNITS,
    MASS_TO_G,
    VOLUME_TO_ML,
    canonical_unit,
)

Dimension = Literal["mass", "volume", "count"]

# Ingredient densities in grams per millilitre, keyed by normalized (lowercased)
# name. Small and curated on purpose. Sources: engineering/food-density
# references and USDA FoodData Central serving weights (approximate room-temp).
_DENSITY_G_PER_ML: dict[str, float] = {
    "water": 1.00,
    "milk": 1.03,
    "greek yogurt": 1.03,
    "yogurt": 1.03,
    "olive oil": 0.91,
    "vegetable oil": 0.92,
    "coconut milk": 0.98,
    "soy sauce": 1.10,
    "honey": 1.42,
    "rice": 0.85,  # uncooked long-grain, packed in a measuring cup
    "flour": 0.53,  # all-purpose, spooned
    "sugar": 0.85,  # granulated
}

# Approximate weight of one common piece, in grams, keyed by normalized name.
# Sources: USDA FoodData Central average weights for a medium item (garlic is
# per clove, the unit people actually count).
_PIECE_WEIGHT_G: dict[str, float] = {
    "egg": 50.0,
    "onion": 110.0,
    "tomato": 123.0,
    "lemon": 58.0,
    "lime": 67.0,
    "avocado": 150.0,
    "bell pepper": 119.0,
    "carrot": 61.0,
    "banana": 118.0,
    "garlic": 5.0,  # one clove
}


def unit_dimension(unit: str | None) -> Dimension | None:
    """Return the measurement dimension of a unit, or None if unrecognized."""
    canonical = canonical_unit(unit)
    if canonical is None:
        return None
    if canonical in MASS_TO_G:
        return "mass"
    if canonical in VOLUME_TO_ML:
        return "volume"
    if canonical in COUNT_UNITS:
        return "count"
    return None


def convert(amount: float | None, from_unit: str, to_unit: str) -> float | None:
    """Convert within a single dimension. Returns None if incomparable."""
    if amount is None:
        return None
    source = canonical_unit(from_unit)
    target = canonical_unit(to_unit)
    if source is None or target is None:
        return None
    dimension = unit_dimension(source)
    if dimension is None or dimension != unit_dimension(target):
        return None
    if dimension == "mass":
        return amount * MASS_TO_G[source] / MASS_TO_G[target]
    if dimension == "volume":
        return amount * VOLUME_TO_ML[source] / VOLUME_TO_ML[target]
    return amount  # count <-> count


def _density(name: str | None) -> float | None:
    if not name:
        return None
    return _DENSITY_G_PER_ML.get(normalize_ingredient(name).lower())


def _piece_weight(name: str | None) -> float | None:
    if not name:
        return None
    return _PIECE_WEIGHT_G.get(normalize_ingredient(name).lower())


def to_grams(amount: float | None, unit: str | None, *, name: str | None = None) -> float | None:
    """Resolve an ingredient amount to grams, or None when it can't be known.

    Resolution order: mass units directly -> volume via density[name] -> count
    (or a bare count with no unit) via piece-weight[name]. Any unknown density,
    piece weight, or unit yields None so callers never silently assume a weight.
    """
    if amount is None:
        return None

    canonical = canonical_unit(unit) if unit else None

    if canonical is None:
        # Bare count with no unit (e.g. "2 eggs") -> try per-piece weight.
        if unit is None and name is not None:
            weight = _piece_weight(name)
            if weight is not None:
                return amount * weight
        return None

    dimension = unit_dimension(canonical)
    if dimension == "mass":
        return amount * MASS_TO_G[canonical]
    if dimension == "volume":
        density = _density(name)
        return None if density is None else amount * VOLUME_TO_ML[canonical] * density
    if dimension == "count":
        weight = _piece_weight(name)
        return None if weight is None else amount * weight
    return None
