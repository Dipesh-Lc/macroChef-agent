"""Deterministic unit conversion for quantity-aware ingredients.

Same-dimension conversions (mass<->mass, volume<->volume) are exact. Cross-
dimension conversions (volume<->mass, count<->mass) require an ingredient's
density or per-piece weight; these live in small, curated, single-sourced tables
below. When the ingredient isn't in a table the conversion returns ``None``
("incomparable") — callers must degrade visibly rather than guess a density.

The unit vocabulary and base factors come from :mod:`app.utils.quantity_parser`
so parsing and conversion can't drift.
"""

import re
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
    # --- added for task A2 (widened conversion surface); every entry below
    # is a named, citable reference weight -- no LLM-recalled figures. ---
    "butter": 0.96,  # USDA FoodData Central / King Arthur: 1 cup butter = 227 g -> 227/236.588 ml
    "brown sugar": 0.90,  # King Arthur ingredient weight chart: 1 cup packed brown sugar = 213 g
    "powdered sugar": 0.48,  # King Arthur ingredient weight chart: 1 cup confectioners' sugar (unsifted) = 113 g
    "cooked rice": 0.67,  # USDA FoodData Central: "Rice, white, cooked", 1 cup = 158 g (fixes the uncooked-density bug on "1 cup cooked rice")
    "cooked white rice": 0.67,  # same USDA FDC "Rice, white, cooked" 1 cup = 158 g citation, natural-word-order key (see advisor revision #2)
    "oats": 0.38,  # King Arthur ingredient weight chart: 1 cup rolled oats = 89 g (corrected per advisor revision #3; was mis-cited as 85 g)
    "cornstarch": 0.54,  # USDA FoodData Central: 1 cup cornstarch = 128 g
    "cocoa powder": 0.36,  # King Arthur ingredient weight chart: 1 cup unsweetened cocoa powder = 84 g
    "peanut butter": 1.09,  # USDA FoodData Central: 1 cup peanut butter = 258 g
    "maple syrup": 1.35,  # USDA FoodData Central: 1 tbsp maple syrup = 20 g -> 20/14.7868 ml
    "heavy cream": 1.01,  # USDA FoodData Central: 1 cup heavy whipping cream = 238 g
    "sour cream": 0.97,  # USDA FoodData Central: 1 cup sour cream = 230 g
    "grated parmesan": 0.42,  # USDA FoodData Central: 1 cup grated parmesan cheese = 100 g (re-keyed to natural word order per advisor revision #1; "parmesan grated" was dead code no recipe writes)
    "grated parmesan cheese": 0.42,  # same USDA FDC 100 g/cup citation, alternate natural-word-order phrasing
    "breadcrumbs": 0.46,  # USDA FoodData Central: 1 cup dry bread crumbs = 108 g
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
    # --- added for task A2; every entry cites a named reference weight. ---
    "potato": 213.0,  # USDA FoodData Central: potato, raw, 1 medium (2-1/4" to 3-1/4" dia.)
    "apple": 182.0,  # USDA FoodData Central: apple, raw with skin, 1 medium (3" dia.)
    "celery stalk": 40.0,  # USDA FoodData Central: celery, raw, 1 stalk (7-1/2" to 8" long)
    "cucumber": 301.0,  # USDA FoodData Central: cucumber, with peel, raw, 1 cucumber (8-1/4" long)
    "zucchini": 196.0,  # USDA FoodData Central: summer squash/zucchini, raw, 1 medium
    "green onion": 15.0,  # USDA FoodData Central: onions, spring/scallion (bulb + top), 1 medium (4-1/8" long) = 15 g (USDA's "small" portion is 5 g, not 15 -- corrected per advisor revision #4a)
    # NOTE: no "shallot" entry -- USDA FoodData Central has no whole-bulb
    # shallot portion (only "1 tbsp chopped = 10 g", which isn't a piece
    # weight). Removed per advisor revision #4b: cite-or-remove, and no
    # citable whole-shallot reference is available without web access.
}

# Handling/preparation words only -- NEVER composition or physical-form words
# (those change the actual density/weight and must be explicit multi-word
# table keys instead, e.g. "cooked rice", "brown sugar"). These words are NOT
# claimed to leave density/weight perfectly unchanged -- e.g. "sifted" flour
# is measurably less dense than spooned flour (roughly a 10% difference).
# Stripping it anyway is an accepted approximation error on this nutrition-
# only, non-safety path (advisor ruling): the alternative -- leaving "sifted
# flour" unresolved entirely -- is worse for the deterministic nutrition
# math than a ~10% density estimate, and this path never influences allergen
# matching (that's name-based and reads neither amount nor unit; see
# app.services.constraint_engine).
_HANDLING_WORDS: frozenset[str] = frozenset({
    "chopped", "diced", "sliced", "minced", "melted", "softened",
    "peeled", "trimmed", "halved", "quartered", "julienned",
    "mashed", "cubed", "sifted", "crumbled",
})

_HANDLING_WORD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(_HANDLING_WORDS, key=len, reverse=True)) + r")\b"
)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _strip_handling_words(name: str) -> str:
    return _collapse_whitespace(_HANDLING_WORD_RE.sub(" ", name))


def _normalize_for_density_lookup(name: str) -> list[str]:
    """Ordered, deduplicated EXACT-match lookup keys for the density/piece
    tables. Nutrition-path-only: never used for allergen matching.

    Precedence (strict-first, then legacy fallback), per the A2 advisor
    ruling:
      1. raw name, lowercased and whitespace-collapsed only -- no word
         removal at all, so explicit multi-word keys like "cooked rice" or
         "brown sugar" resolve to themselves before anything else can touch
         them.
      2. the same, with handling/preparation words stripped (e.g. "chopped
         onion" -> "onion").
      3. the existing `normalize_ingredient(name).lower()` path, unchanged,
         as a legacy fallback (descriptor stripping, synonyms, fuzzy match).

    Every candidate is looked up with an exact dict `.get()` by the caller --
    no fuzzy or substring matching is introduced here.
    """
    raw = _collapse_whitespace(name)
    stripped = _strip_handling_words(raw)
    legacy = normalize_ingredient(name).lower()

    candidates: list[str] = []
    for candidate in (raw, stripped, legacy):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


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
    for key in _normalize_for_density_lookup(name):
        if key in _DENSITY_G_PER_ML:
            return _DENSITY_G_PER_ML[key]
    return None


def _piece_weight(name: str | None) -> float | None:
    if not name:
        return None
    for key in _normalize_for_density_lookup(name):
        if key in _PIECE_WEIGHT_G:
            return _PIECE_WEIGHT_G[key]
    return None


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
