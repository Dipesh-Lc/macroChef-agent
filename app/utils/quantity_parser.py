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
    "qt": 946.353,  # US quart
    "pt": 473.176,  # US pint
    "floz": 29.5735,  # US fluid ounce
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
    "qt": "qt", "qts": "qt", "quart": "qt", "quarts": "qt",
    "pt": "pt", "pts": "pt", "pint": "pt", "pints": "pt",
    "floz": "floz", "fl oz": "floz", "fluid ounce": "floz", "fluid ounces": "floz",
    # count
    "piece": "piece", "pieces": "piece", "pc": "piece", "pcs": "piece",
    "clove": "clove", "cloves": "clove",
    "slice": "slice", "slices": "slice",
}

KNOWN_UNITS: frozenset[str] = frozenset(_UNIT_ALIASES)


def canonical_unit(unit: str | None) -> str | None:
    """Map any accepted unit spelling to its canonical token, else None.

    Multi-word abbreviations can carry internal periods ("fl. oz.") in
    addition to the trailing one already stripped below. Rather than
    loosening the alias table itself (which would let stray periods match
    unrelated tokens), a normalized fallback key -- internal periods
    dropped, whitespace collapsed -- is tried second so "fl. oz." and
    "fl oz." both resolve to the same clean "fl oz" alias.
    """
    if not unit:
        return None
    key = unit.strip().lower().rstrip(".")
    canonical = _UNIT_ALIASES.get(key)
    if canonical is not None:
        return canonical
    normalized = re.sub(r"\s+", " ", key.replace(".", " ")).strip()
    if normalized == key:
        return None
    return _UNIT_ALIASES.get(normalized)


_UNICODE_FRACTIONS: dict[str, float] = {
    "½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3,
    "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}

# Range dashes accepted between two leading numbers: ASCII hyphen, en dash,
# em dash. The hyphen is listed first in every character class below so it is
# read as a literal, not a range operator.
_RANGE_DASH_CHARS = "-–—"

# A single leading-amount value with NO range logic: mixed unicode fraction,
# mixed digit fraction, simple fraction, decimal/integer, bare decimal, bare
# unicode fraction -- in this order because regex alternation takes the first
# branch that matches, not the longest overall match. Factored out so both
# the dash-range and the word-range ("X to Y") alternatives below can reuse
# it verbatim for their X and Y operands without drifting from the single-
# value case.
_AMOUNT_TOKEN = (
    r"\d+\s*[½¼¾⅓⅔⅛⅜⅝⅞]"
    r"|\d+\s+\d+/\d+"
    r"|\d+/\d+"
    r"|\d+(?:\.\d+)?"
    r"|\.\d+"
    r"|[½¼¾⅓⅔⅛⅜⅝⅞]"
)

# Leading amount, longest/most-specific alternative first (regex alternation
# takes the first branch that matches, not the longest overall match, so order
# here is load-bearing):
#   1. word range: "1/2 to 3/4" / "1 to 2" (case-insensitive "to", each side
#      any single-amount form). Tried FIRST because its operands are prefixes
#      of the plain single-amount alternatives below -- if this weren't tried
#      first, "1 1/2 to 3" would stop after matching just "1 1/2".
#   2. numeric range: "2-4" / "2–4" / "2—4" (ASCII hyphen, en dash, em dash)
#   3. any single amount (mixed unicode fraction, mixed digit fraction,
#      simple fraction, decimal/integer, bare decimal, bare unicode fraction)
_LEADING_AMOUNT = re.compile(
    r"^\s*(?P<num>"
    rf"(?:{_AMOUNT_TOKEN})\s+(?i:to)\s+(?:{_AMOUNT_TOKEN})"
    rf"|\d+(?:\.\d+)?\s*[{_RANGE_DASH_CHARS}]\s*\d+(?:\.\d+)?"
    rf"|{_AMOUNT_TOKEN}"
    r")"
)

# "to" surrounded by whitespace, case-insensitive. Only used to split an
# already-matched _LEADING_AMOUNT span (see _amount_to_float below) -- never
# used standalone, so it can't misfire on food names containing "to".
_WORD_RANGE_RE = re.compile(r"\s+to\s+", flags=re.I)


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


def _split_word_range(token: str) -> tuple[str, str] | None:
    """Split a "X to Y" word-range token on its first whitespace-bounded "to"."""
    match = _WORD_RANGE_RE.search(token)
    if match is None:
        return None
    return token[: match.start()], token[match.end() :]


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

    # Word range ("1/2 to 3/4", "1 to 2"): identical MIDPOINT convention as
    # the dash range above, just spelled with the word "to" instead of a dash
    # -- same rationale, same no-safety-weight guarantee (see the
    # parse_quantity_string docstring and _split_range's comment above).
    word_range_parts = _split_word_range(token)
    if word_range_parts is not None:
        low = _amount_to_float(word_range_parts[0])
        high = _amount_to_float(word_range_parts[1])
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


# Pack-size lines: "1 (8 ounce) package cream cheese" -> amount=8.0 (=N*M),
# unit="oz" (the parenthetical unit), name="cream cheese". The container word
# itself ("package", "can", ...) is NEVER a unit -- no can/package pseudo-
# units, consistent with the standing density/piece-table ruling. This is a
# strict, fully-anchored leading pattern; if any part fails to match or the
# parenthetical text isn't a known unit, parse_quantity_string falls through
# to the ordinary parsing path below, unchanged.
_CONTAINER_WORDS = (
    "package", "packages", "pkg",
    "can", "cans",
    "jar", "jars",
    "box", "boxes",
    "bag", "bags",
    "bottle", "bottles",
    "container", "containers",
)
_CONTAINER_ALT = "|".join(re.escape(word) for word in _CONTAINER_WORDS)

_PACK_SIZE_RE = re.compile(
    r"^\s*(?P<n>\d+(?:\.\d+)?)\s*"
    r"\(\s*(?P<m>\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z.]+(?:\s+[A-Za-z.]+)?)\s*\)\s*"
    rf"(?:{_CONTAINER_ALT})\b\s*"
    r"(?P<rest>.*)$",
    flags=re.I,
)


def _parse_pack_size(text: str) -> dict[str, object] | None:
    """Parse a strict "N (M UNIT) container_word rest" pack-size line.

    Returns None (never a partial/best-effort result) unless every part of
    the pattern matches AND the parenthetical text resolves to a known unit
    AND a non-empty name remains -- callers must fall through to the regular
    parser on any of those failures rather than guess.
    """
    match = _PACK_SIZE_RE.match(text)
    if match is None:
        return None
    unit = canonical_unit(match.group("unit"))
    if unit is None:
        return None
    name = match.group("rest").strip()
    if not name:
        return None
    n = float(match.group("n"))
    m = float(match.group("m"))
    return {"name": name, "amount": n * m, "unit": unit}


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
        "1/2 to 3/4 cup milk"  -> {"name": "milk", "amount": 0.625, "unit": "cup"}
        "1 (8 ounce) package cream cheese" -> {"name": "cream cheese", "amount": 8.0, "unit": "oz"}

    `name` is never empty: unparseable input falls back to the original text.

    Numeric ranges ("2-4", "2–4", "2—4" -- ASCII hyphen, en dash, and em dash
    are all accepted) collapse to their arithmetic MIDPOINT as a single,
    documented, deterministic convention (e.g. "2–4 tbsp" -> amount=3.0). This
    is a modeling choice for downstream nutrition/procurement math, not a
    measured quantity -- callers consuming `amount` for shopping-list
    quantities should treat it as an estimate, not an exact figure. It carries
    no safety weight: allergen matching (app.services.constraint_engine) is
    keyed on `name` only and is quantity-independent by design.

    Word ranges spelled with "to" instead of a dash ("1/2 to 3/4 cup milk",
    "1 to 2 eggs" -- the word is matched case-insensitively) follow the exact
    same MIDPOINT convention as the dash-range case above, for the same
    reason and with the same no-safety-weight guarantee: only the arithmetic
    midpoint of the two operands is kept as `amount`, allergen matching never
    sees or uses it. Only a literal standalone "to" between two otherwise-
    valid leading amounts is accepted -- "1 tomato" and "2 toasted bread
    slices" are NOT ranges (the word after the number isn't "to" followed by
    a second amount) and parse as an ordinary single amount, unchanged.
    """
    text = (raw or "").strip()
    if not text:
        return {"name": "", "amount": None, "unit": None}

    pack_size = _parse_pack_size(text)
    if pack_size is not None:
        return pack_size

    match = _LEADING_AMOUNT.match(text)
    if not match:
        return {"name": text, "amount": None, "unit": None}

    amount = _amount_to_float(match.group("num"))
    rest = text[match.end():].strip()
    unit: str | None = None

    # Longest-match-first: a unit can be spelled as two tokens ("fl oz",
    # "fluid ounces"), so try consuming the first two whitespace-separated
    # tokens as a single unit before falling back to the one-token check.
    # The two-token attempt only ever *reads* `rest`; it doesn't touch it
    # unless it actually resolves to a known unit, so the single-token path
    # below is byte-for-byte the pre-existing behavior when no two-token
    # unit matches.
    two_token_match = re.match(r"^(\S+)\s+(\S+)\s*", rest)
    two_token_unit = (
        canonical_unit(f"{two_token_match.group(1)} {two_token_match.group(2)}")
        if two_token_match
        else None
    )

    if two_token_unit is not None:
        unit = two_token_unit
        rest = rest[two_token_match.end():]
    else:
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
