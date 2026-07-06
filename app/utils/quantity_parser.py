"""Leading-quantity parsing and the canonical unit vocabulary.

This is the single source of truth for *which tokens count as units* and their
base-unit conversion factors. `unit_converter` builds the dimension logic and
density/piece tables on top of these maps; `ingredient_normalizer` imports
`KNOWN_UNITS` so its name-cleanup regex can't drift from what the parser
recognizes. Kept dependency-free (only `re`) so it stays a leaf module that
schemas and other utils can import without cycles.
"""

import re

# Canonical base-unit factor tables. Keys are canonical unit tokens.
# Mass base unit is grams; volume base unit is millilitres.
MASS_TO_G: dict[str, float] = {
    "g": 1.0,
    "kg": 1000.0,
    "mg": 0.001,
    "oz": 28.3495,  # avoirdupois ounce
    "lb": 453.592,
}
VOLUME_TO_ML: dict[str, float] = {
    "ml": 1.0,
    "l": 1000.0,
    "tsp": 4.92892,  # US teaspoon
    "tbsp": 14.7868,  # US tablespoon
    "cup": 236.588,  # US cup
}
# Count units are dimensionless measure words (not ingredient names). "egg",
# "onion" etc. are deliberately NOT here so "2 eggs" parses as amount=2, name=egg.
COUNT_UNITS: set[str] = {"piece", "clove", "slice"}

# Every accepted spelling -> canonical token. This defines KNOWN_UNITS.
_UNIT_ALIASES: dict[str, str] = {
    # mass
    "g": "g", "gram": "g", "grams": "g", "gm": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    # volume
    "ml": "ml", "milliliter": "ml", "millilitre": "ml", "milliliters": "ml", "millilitres": "ml",
    "l": "l", "liter": "l", "litre": "l", "liters": "l", "litres": "l",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "cup": "cup", "cups": "cup",
    # count
    "piece": "piece", "pieces": "piece", "pc": "piece", "pcs": "piece",
    "clove": "clove", "cloves": "clove",
    "slice": "slice", "slices": "slice",
}

KNOWN_UNITS: frozenset[str] = frozenset(_UNIT_ALIASES)


def canonical_unit(unit: str | None) -> str | None:
    """Map any accepted unit spelling to its canonical token, else None."""
    if not unit:
        return None
    return _UNIT_ALIASES.get(unit.strip().lower().rstrip("."))


_UNICODE_FRACTIONS: dict[str, float] = {
    "½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}

# Leading amount: mixed number ("1 1/2"), fraction ("1/2"), decimal, integer, or
# a single unicode fraction glyph.
_LEADING_AMOUNT = re.compile(
    r"^\s*(?P<num>\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?|\.\d+|[½¼¾⅓⅔⅛⅜⅝⅞])"
)


def _fraction_to_float(token: str) -> float:
    numerator, _, denominator = token.partition("/")
    denom = float(denominator)
    return float(numerator) / denom if denom else 0.0


def _amount_to_float(token: str) -> float | None:
    token = token.strip()
    if token in _UNICODE_FRACTIONS:
        return _UNICODE_FRACTIONS[token]
    if " " in token:  # mixed number like "1 1/2"
        whole, frac = token.split(None, 1)
        return float(whole) + _fraction_to_float(frac)
    if "/" in token:
        return _fraction_to_float(token)
    try:
        return float(token)
    except ValueError:
        return None


def parse_quantity_string(raw: str) -> dict[str, object]:
    """Parse a free-form ingredient string into {name, amount, unit}.

    Examples::

        "150 g chicken breast" -> {"name": "chicken breast", "amount": 150.0, "unit": "g"}
        "2 cups rice"          -> {"name": "rice",           "amount": 2.0,   "unit": "cup"}
        "1 medium egg"         -> {"name": "medium egg",     "amount": 1.0,   "unit": None}
        "chicken breast"       -> {"name": "chicken breast", "amount": None,  "unit": None}

    `name` is never empty: unparseable input falls back to the original text.
    """
    text = (raw or "").strip()
    if not text:
        return {"name": "", "amount": None, "unit": None}

    match = _LEADING_AMOUNT.match(text)
    if not match:
        return {"name": text, "amount": None, "unit": None}

    amount = _amount_to_float(match.group("num"))
    rest = text[match.end():].strip()
    unit: str | None = None

    parts = rest.split(maxsplit=1)
    if parts:
        candidate = canonical_unit(parts[0])
        if candidate is not None:
            unit = candidate
            rest = parts[1] if len(parts) > 1 else ""

    name = rest.strip()
    if not name:
        # e.g. a bare "500 g" with no food named — keep original so name isn't empty.
        name = text

    return {"name": name, "amount": amount, "unit": unit}
