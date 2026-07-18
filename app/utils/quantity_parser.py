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

# Range dashes accepted between two leading numbers: ASCII hyphen, en dash,
# em dash. The hyphen is listed first in every character class below so it is
# read as a literal, not a range operator.
_RANGE_DASH_CHARS = "-–—"

# Leading amount, longest/most-specific alternative first (regex alternation
# takes the first branch that matches, not the longest overall match, so order
# here is load-bearing):
#   1. numeric range: "2-4" / "2–4" / "2—4" (ASCII hyphen, en dash, em dash)
#   2. mixed unicode fraction, glued or spaced: "1½" / "1 ½"
#   3. mixed digit fraction: "1 1/2"
#   4. simple fraction: "1/2"
#   5. decimal or integer: "1.5" / "150"
#   6. bare decimal: ".5"
#   7. bare unicode fraction: "½"
_LEADING_AMOUNT = re.compile(
    r"^\s*(?P<num>"
    rf"\d+(?:\.\d+)?\s*[{_RANGE_DASH_CHARS}]\s*\d+(?:\.\d+)?"
    r"|\d+\s*[½¼¾⅓⅔⅛⅜⅝⅞]"
    r"|\d+\s+\d+/\d+"
    r"|\d+/\d+"
    r"|\d+(?:\.\d+)?"
    r"|\.\d+"
    r"|[½¼¾⅓⅔⅛⅜⅝⅞]"
    r")"
)


def _fraction_to_float(token: str) -> float:
    numerator, _, denominator = token.partition("/")
    denom = float(denominator)
    return float(numerator) / denom if denom else 0.0


def _split_range(token: str) -> tuple[str, str] | None:
    """Split a numeric-range token on its first ASCII hyphen/en dash/em dash."""
    for dash in _RANGE_DASH_CHARS:
        if dash in token:
            low, _, high = token.partition(dash)
            return low, high
    return None


def _amount_to_float(token: str) -> float | None:
    token = token.strip()

    # Numeric range ("2-4", "2–4 tbsp", "2—4 tbsp"): take the deterministic
    # MIDPOINT ("2–4" -> 3.0). This is a documented convention, not a measured
    # value -- see the parse_quantity_string docstring. It is safe from a safety
    # standpoint because allergen matching is name-based and quantity-independent
    # (see app.services.constraint_engine._recipe_safety_terms); the midpoint only
    # affects nutrition/procurement math, where it minimizes expected error.
    range_parts = _split_range(token)
    if range_parts is not None:
        low = _amount_to_float(range_parts[0])
        high = _amount_to_float(range_parts[1])
        if low is None or high is None:
            return None
        return (low + high) / 2

    if token in _UNICODE_FRACTIONS:
        return _UNICODE_FRACTIONS[token]

    # Mixed unicode fraction, glued ("1½") or spaced ("1 ½"): strip internal
    # whitespace and check for <digits><fraction glyph>.
    glued = token.replace(" ", "")
    if len(glued) >= 2 and glued[-1] in _UNICODE_FRACTIONS and glued[:-1].isdigit():
        return float(glued[:-1]) + _UNICODE_FRACTIONS[glued[-1]]

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
        "1½ cup heavy whipping cream" -> {"name": "heavy whipping cream", "amount": 1.5, "unit": "cup"}
        "1 ½ cups sugar"       -> {"name": "sugar", "amount": 1.5, "unit": "cup"}
        "2–4 tbsp milk"        -> {"name": "milk", "amount": 3.0, "unit": "tbsp"}

    `name` is never empty: unparseable input falls back to the original text.

    Numeric ranges ("2-4", "2–4", "2—4" -- ASCII hyphen, en dash, and em dash
    are all accepted) collapse to their arithmetic MIDPOINT as a single,
    documented, deterministic convention (e.g. "2–4 tbsp" -> amount=3.0). This
    is a modeling choice for downstream nutrition/procurement math, not a
    measured quantity -- callers consuming `amount` for shopping-list
    quantities should treat it as an estimate, not an exact figure. It carries
    no safety weight: allergen matching (app.services.constraint_engine) is
    keyed on `name` only and is quantity-independent by design.
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
