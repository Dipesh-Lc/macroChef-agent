import re
from functools import lru_cache

from app.utils.quantity_parser import KNOWN_UNITS

try:
    from rapidfuzz import fuzz, process, utils as fuzz_utils
except ImportError:  # pragma: no cover - optional dependency fallback
    fuzz = None
    process = None
    fuzz_utils = None

# Unit alternation built from the shared vocabulary so name cleanup and quantity
# parsing recognize exactly the same unit tokens (single source, no drift).
# Longest-first so multi-char tokens win over their prefixes ("grams" before "g").
_UNIT_ALTERNATION = "|".join(re.escape(unit) for unit in sorted(KNOWN_UNITS, key=len, reverse=True))

# A leading number: integer/decimal ("150", "1.5"), simple fraction ("1/2"), or a
# single unicode fraction glyph. Used only to recognize a *quantity* prefix.
_NUMBER = r"(?:\d+(?:[./]\d+)?|[½¼¾⅓⅔⅛⅜⅝⅞])"

# Strip a unit token ONLY when it is directly attached to a number, i.e. a real
# quantity like "150 g", "2l", "1/2 cup". A bare unit *word* that is part of a
# food name ("pound cake", "cheese slice") is never adjacent to a number, so it
# is left untouched. This makes the widened KNOWN_UNITS set safe by construction:
# it can only ever remove a quantity, never a letter or word inside a name.
_QUANTITY_WITH_UNIT = re.compile(rf"\b{_NUMBER}\s*(?:{_UNIT_ALTERNATION})\b", flags=re.I)

# A standalone number with no unit (e.g. the "3" in "3 eggs"). Kept as its own
# pass so bare counts are still cleaned off the name.
_STANDALONE_NUMBER = re.compile(rf"\b{_NUMBER}\b")


SYNONYMS = {
    "bell peppers": "bell pepper",
    "capsicum": "bell pepper",
    "chix": "chicken",
    "chicken": "chicken breast",
    "chicken breasts": "chicken breast",
    "chickpeas": "chickpea",
    "garbanzo": "chickpea",
    "garbanzo beans": "chickpea",
    "greek yoghurt": "Greek yogurt",
    "greek yogurt": "Greek yogurt",
    "yoghurt": "yogurt",
    "courgette": "zucchini",
    "aubergine": "eggplant",
    "cilantro": "coriander",
    "scallion": "green onion",
    "scallions": "green onion",
    "spring onion": "green onion",
    "spring onions": "green onion",
    "brown rice": "brown rice",
    "white rice": "rice",
    "eggs": "egg",
    "egg whites": "egg white",
    "shrimp": "shrimp",
    "prawns": "shrimp",
    "peanuts": "peanut",
    "peanut butter": "peanut butter",
    "coconut milk": "coconut milk",
    "soy sauce": "soy sauce",
    "tamari": "soy sauce",
    "gluten free tamari": "soy sauce",
    "mozzarella cheese": "mozzarella",
    "parmesan cheese": "parmesan",
    "feta cheese": "feta",
    "bell pepper": "bell pepper",
}

CANONICAL_INGREDIENTS = sorted(
    {
        *SYNONYMS.values(),
        "almond",
        "avocado",
        "basil",
        "bean",
        "beef",
        "black bean",
        "bread",
        "broccoli",
        "brown rice",
        "carrot",
        "cauliflower",
        "cheddar",
        "chicken breast",
        "chickpea",
        "coconut milk",
        "coriander",
        "corn",
        "cucumber",
        "egg",
        "eggplant",
        "feta",
        "garlic",
        "ginger",
        "green onion",
        "Greek yogurt",
        "ground turkey",
        "lemon",
        "lentil",
        "lime",
        "mozzarella",
        "mushroom",
        "oats",
        "olive oil",
        "onion",
        "paneer",
        "parmesan",
        "pasta",
        "peanut",
        "quinoa",
        "rice",
        "salmon",
        "shrimp",
        "soy sauce",
        "spinach",
        "sweet potato",
        "tofu",
        "tomato",
        "tortilla",
        "turkey",
        "zucchini",
    }
)

DESCRIPTORS = {
    "fresh",
    "frozen",
    "canned",
    "organic",
    "raw",
    "cooked",
    "large",
    "small",
    "medium",
    "low fat",
    "reduced fat",
    "boneless",
    "skinless",
}


def cleanup_ingredient_name(name: str) -> str:
    cleaned = name.strip().replace("_", " ").replace("-", " ")
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    # Order matters: remove number+unit quantities *before* stripping bare numbers,
    # so the number-adjacency that authorizes unit removal is still present.
    cleaned = _QUANTITY_WITH_UNIT.sub(" ", cleaned)
    cleaned = _STANDALONE_NUMBER.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


@lru_cache(maxsize=4096)
def normalize_ingredient(name: str) -> str:
    """Normalize free-form ingredient names for matching and scoring.

    `@lru_cache`d (2026-07-22 pantry-tiebreak follow-up): pure function of
    `name` alone (`SYNONYMS`/`DESCRIPTORS`/`CANONICAL_INGREDIENTS` are
    module-level constants, never mutated after import), so memoizing is a
    pure performance change with zero behavior difference -- added because
    `app.services.day_planner`'s new pantry-coverage tiebreak calls this
    (via `ingredient_matches`/`pantry_coverage_fraction`) at a materially
    higher frequency than before (once per candidate combo during
    enumeration, not once per request), and the underlying
    `fuzzy_normalize_ingredient` rapidfuzz lookup is expensive enough that
    the same small set of ingredient/pantry-item names being re-normalized
    thousands of times per request was the dominant cost (see
    `tests/test_weekly_planner.py`'s mandatory timing smoke test)."""

    if not name:
        return ""

    cleaned = cleanup_ingredient_name(name)
    key = cleaned.lower()

    if key in SYNONYMS:
        return SYNONYMS[key]

    for descriptor in sorted(DESCRIPTORS, key=len, reverse=True):
        key = re.sub(rf"\b{re.escape(descriptor)}\b", " ", key)

    key = re.sub(r"\s+", " ", key).strip()
    if key in SYNONYMS:
        return SYNONYMS[key]

    if key.endswith("ies"):
        key = f"{key[:-3]}y"
    elif key.endswith("s") and not key.endswith(("ss", "us")):
        key = key[:-1]

    if key == "greek yogurt":
        return "Greek yogurt"

    return fuzzy_normalize_ingredient(key)


def fuzzy_normalize_ingredient(name: str, threshold: int = 85) -> str:
    """Map close misspellings to known pantry names when rapidfuzz is installed.

    Uses token_sort_ratio so that multi-token inputs (e.g. "greeek yogurt") prefer
    the canonical that covers all tokens ("Greek yogurt") over shorter subsets
    ("yogurt").  default_process normalises case so that canonicals like "Greek
    yogurt" aren't penalised for their capital letter.
    """

    if not name or process is None or fuzz is None or fuzz_utils is None:
        return name

    match = process.extractOne(
        name,
        CANONICAL_INGREDIENTS,
        scorer=fuzz.token_sort_ratio,
        processor=fuzz_utils.default_process,
    )
    if match and match[1] >= threshold:
        return match[0]
    return name


def normalize_many(names: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for name in names:
        value = normalize_ingredient(name)
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized


def ingredient_matches(candidate: str, inventory_item: str) -> bool:
    left = normalize_ingredient(candidate).lower()
    right = normalize_ingredient(inventory_item).lower()
    if not left or not right:
        return False
    return left == right or left in right or right in left
