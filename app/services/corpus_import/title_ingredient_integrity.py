"""Shared detection logic for the title/ingredient integrity check: does a
recipe's OWN TITLE name a food that never shows up anywhere in its
ingredient list or its derived `allergens` field?

Root cause (established separately): a meaningful slice of the Food.com CC0
import (`imported_recipes.jsonl`) is missing its own title's defining
ingredient -- e.g. "Curried Peanut Shrimp" with no peanut ingredient.
Proven to be a SOURCE-column defect (RecipeIngredientParts is short while
RecipeInstructions, parsed by the same code, still names the missing
foods), not a parser bug. This means `constraint_engine.contains_allergen`
cannot catch what was never in the ingredient list -- a peanut-allergic
user could be served a recipe titled "Peanut".

This module is the single source of truth for the check, used by:
  - `scripts/audit_title_ingredient_integrity.py` -- a standalone CI-gate
    audit over the whole corpus file.
  - `scripts/quarantine_flagged_recipes.py` -- the one-time cleanup that
    moved already-flagged legacy rows into `quarantined_recipes.jsonl`.
  - `app.services.corpus_import.pipeline.CorpusImportPipeline` -- so this
    exact defect class is caught and quarantined at import time for any
    FUTURE import, not just retroactively for this one historical corpus.

Design, mirroring `scripts/audit_diet_leaks.py`:
- The TITLE-side vocabulary below (TITLE_ALLERGEN_CATEGORIES) is
  hand-authored from general food-vocabulary knowledge, independent of
  `app.services.constraint_engine.ALLERGEN_ALIASES` -- so a gap or bug in
  that production table can't make this check blind to the same gap. The
  same vocabulary is reused to scan ingredient names (one hand-authored
  "does this food-word appear" concept, applied to two different fields).
- A recipe is flagged only if a title-implied allergen category is absent
  from BOTH (a) every ingredient name (this module's own word-boundary
  scan) AND (b) `recipe.allergens` (already computed via
  ALLERGEN_ALIASES/derive_allergen_labels -- checked here as an OR-arm so a
  genuine synonym ALLERGEN_ALIASES recognizes but this module's smaller
  hand list doesn't -- e.g. "satay" implying peanut -- doesn't produce a
  false mismatch report; recipe.allergens is a different field than the one
  this check exists to validate, so this is not circular).
- Word-boundary matching throughout, not naive substring: this alone
  disposes of most of the obvious false positives ("butter" no longer
  substring-matches inside "butternut", "crab" no longer matches inside
  "crabapple") because a word-boundary requires a non-word-character
  transition, and concatenated compound words have none.
- The remaining false-positive classes need explicit handling; see
  BUTTER_COMPOUND_MODIFIERS, EXACT_PHRASE_SUPPRESSIONS, and the "mock"/
  negation rules below for the documented exclusion approach chosen (a
  hybrid: general rules for broad, recurring SHAPES of false positive, plus
  a small explicit, per-item-cited list for irreducible one-offs).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.schemas.recipe import Recipe

# --- Independent ground-truth vocabulary (NOT shared with constraint_engine.ALLERGEN_ALIASES) ---
#
# Each category maps to:
#   - "terms": food-words that, if they appear as a whole word/phrase in the
#     TITLE, imply this allergen is a defining ingredient of the dish.
#     The same terms are reused to scan ingredient names.
#   - "allergen_labels": the recipe.allergens values (as produced by
#     constraint_engine.derive_allergen_labels, which this module does NOT
#     import or reuse the term lists of) that would already be present if
#     any of this category's foods survived into the ingredient list.
#
# Deliberately NOT included: a bare generic "nuts" or "nut" trigger term
# (collides with "butternut", "doughnuts", "coconut", etc. even at a whole-
# word level in ways a human title-reader would not read as a nut claim),
# and bare "shellfish" (never itself a title word in the corpus this was
# developed against).

TITLE_ALLERGEN_CATEGORIES: dict[str, dict] = {
    "peanut": {
        "terms": {"peanut", "peanuts", "groundnut", "groundnuts"},
        "allergen_labels": {"peanut", "peanuts", "nuts"},
    },
    "tree_nut": {
        "terms": {
            "almond", "almonds", "walnut", "walnuts", "pecan", "pecans",
            "cashew", "cashews", "hazelnut", "hazelnuts", "pistachio",
            "pistachios", "macadamia", "macadamias", "brazil nut",
            "brazil nuts", "pine nut", "pine nuts",
        },
        "allergen_labels": {"tree nut", "nuts"},
    },
    "dairy": {
        "terms": {
            "butter", "cheese", "cheddar", "mozzarella", "parmesan", "cream",
            "milk", "yogurt", "yoghurt", "buttermilk", "ghee", "custard",
            "brie", "feta", "ricotta",
        },
        "allergen_labels": {"dairy", "milk"},
    },
    "wheat_gluten": {
        "terms": {
            "bread", "flour", "pasta", "spaghetti", "macaroni", "wheat",
            "cracker", "crackers", "biscuit", "tortilla", "pastry",
            "dumpling", "dumplings",
        },
        "allergen_labels": {"wheat", "gluten"},
    },
    "egg": {
        "terms": {"egg", "eggs"},
        "allergen_labels": {"egg", "eggs"},
    },
    "fish": {
        "terms": {
            "salmon", "tuna", "cod", "halibut", "trout", "snapper",
            "anchovy", "anchovies", "sardine", "sardines", "mackerel",
            "herring",
        },
        "allergen_labels": {"fish", "seafood"},
    },
    "mollusk": {
        "terms": {"clam", "clams", "mussel", "mussels", "oyster", "oysters", "scallop", "scallops"},
        "allergen_labels": {"shellfish", "seafood"},
    },
    "crustacean": {
        # "crabmeat"/"crab meat" added explicitly: a plain "s?" plural suffix
        # (see _find_term_spans) can't bridge a compound word with no
        # trailing "s" at all -- "crabmeat" is common enough as an
        # ingredient-list entry (e.g. "Crab Bisque", "Crabby Crab Cakes")
        # that missing it produced real false-positive mismatches during
        # development (the ingredient list DID have crab, just spelled as
        # one word with "meat").
        "terms": {"shrimp", "prawn", "prawns", "crab", "crabmeat", "crab meat", "lobster", "crawfish", "crayfish"},
        "allergen_labels": {"crustacean", "shellfish", "seafood"},
    },
    "sesame": {
        "terms": {"sesame", "tahini"},
        "allergen_labels": {"sesame"},
    },
    "soy": {
        "terms": {"soy", "soya", "tofu", "edamame", "miso", "tempeh", "tamari"},
        "allergen_labels": {"soy", "soya"},
    },
}

# --- False-positive handling -----------------------------------------------
#
# Two documented mechanisms, chosen deliberately over a single "smarter
# regex": a general rule generalizes to any future dataset row of the same
# SHAPE (any fruit/nut + "butter" compound), while the exact-phrase list
# stays small, auditable, and each entry is individually cited -- neither
# approach alone covers both classes cleanly.

# General rule: "<word> butter" is a compound spread/preserve name, not a
# claim of dairy butter, whenever <word> is a fruit (apple butter, pear
# butter, ...) or another nut/seed (peanut butter, almond butter, ...) --
# real, common cooking terms in both classes, and neither is dairy-based.
# Applied by checking the whole title (not just the immediately preceding
# word) because "Apple Brandy Butter" has "Brandy" immediately before
# "butter", not "Apple" -- the fruit/nut word can be non-adjacent.
BUTTER_COMPOUND_MODIFIERS = {
    "apple", "pear", "peach", "plum", "apricot", "pumpkin", "quince", "fig",
    "rhubarb", "mango", "cranberry", "cherry", "papaya", "strawberry",  # fruit butters
    "peanut", "almond", "cashew", "sunflower", "cocoa", "cookie",  # nut/seed/other butters
}

# Exact phrases, each an irreducible one-off that a general rule can't
# clean up. Cited individually:
#   - "cracker barrel": Cracker Barrel Old Country Store is a proper-noun
#     restaurant-chain brand name; "cracker" here names the brand, not a
#     wheat-cracker ingredient.
#   - "spoon bread": a traditional Southern US dish (a cornmeal souffle-like
#     side), not literal yeast/wheat bread -- can genuinely be made
#     wheat-free.
#   - "cape cod": Cape Cod, Massachusetts is a place name; confirmed by
#     inspecting the one corpus title that matches ("Cape Cod Cranberry
#     Velvet Pie" -- a cream-cheese dessert with no cod fish anywhere in
#     it), not merely assumed from the word alone.
EXACT_PHRASE_SUPPRESSIONS: dict[str, str] = {
    "cracker barrel": "cracker",
    "spoon bread": "bread",
    "cape cod": "cod",
}


def _find_term_spans(text: str, term: str) -> list[tuple[int, int]]:
    # Optional trailing "s": most terms above are authored singular, but
    # ingredient-list text is very often plural ("lobsters", "tortillas").
    # Harmless for terms already plural in the table (e.g. "eggs" + s? just
    # never finds the unused "eggss" match) and still word-boundary-safe --
    # it cannot bridge into an unrelated following word ("crabs?" still does
    # not match inside "crabapple", which has no "s" after "crab" at all).
    return [m.span() for m in re.finditer(rf"\b{re.escape(term)}s?\b", text)]


def _overlaps(span: tuple[int, int], consumed: list[tuple[int, int]]) -> bool:
    return any(span[0] < end and start < span[1] for start, end in consumed)


def _suppressed_terms_for_title(title_lower: str) -> set[str]:
    suppressed = set()
    for phrase, term in EXACT_PHRASE_SUPPRESSIONS.items():
        if phrase in title_lower:
            suppressed.add(term)
    return suppressed


def _negated_terms_for_title(title_lower: str, all_terms: set[str]) -> set[str]:
    """General rule (not a one-off list): a title explicitly disclaiming an
    ingredient -- "No-Bread Sandwiches", "Egg-Free Pancakes", "Gluten-Free
    ..." -- is asserting the opposite of what the bare term would imply, so
    that term must not be treated as a title-side allergen claim. Found via
    a real corpus case ("No-Bread Sandwiches": a lettuce-wrap egg-salad
    recipe with no bread ingredient at all, correctly so) rather than
    invented speculatively; the "-free" arm is included pre-emptively for
    the same, obviously-analogous naming pattern ("Gluten-Free ...") even
    though no corpus title currently trips a term match on it.
    """
    negated = set()
    for term in all_terms:
        escaped = re.escape(term)
        if re.search(rf"\bno[-\s]{escaped}\b", title_lower) or re.search(rf"\b{escaped}[-\s]free\b", title_lower):
            negated.add(term)
    return negated


def _scan_text_for_categories(text: str, *, is_title: bool) -> dict[str, list[str]]:
    """Returns {category: [matched terms]} for every TITLE_ALLERGEN_CATEGORIES
    category with >=1 whole-word/phrase hit in `text`. Longest terms are
    matched first and claim their span so a shorter overlapping term (e.g.
    bare "butter" inside "peanut butter") can't also fire -- see
    BUTTER_COMPOUND_MODIFIERS's docstring for why that overlap matters."""
    text_lower = text.lower()

    # "Mock" is an established, decades-old recipe-title convention (era:
    # Depression-era economy cooking) meaning "imitation of X, does not
    # contain X" -- e.g. "Mock Apple Pie" (Ritz crackers, no apple), "Mock
    # Pecan Pie" (pinto beans, no pecan; a real corpus title, confirmed by
    # inspecting its ingredient list: pinto beans/sugar/eggs/salt). A title
    # asserting "mock" is asserting the ABSENCE of its named food, the exact
    # opposite of the claim this scan otherwise reads from a bare term
    # match, so no category can be validly inferred from a "mock" title at
    # all.
    if is_title and re.search(r"\bmock\b", text_lower):
        return {}

    all_terms: list[tuple[str, str]] = [
        (term, category)
        for category, spec in TITLE_ALLERGEN_CATEGORIES.items()
        for term in spec["terms"]
    ]
    all_terms.sort(key=lambda pair: len(pair[0]), reverse=True)

    suppressed_terms = _suppressed_terms_for_title(text_lower) if is_title else set()
    negated_terms = (
        _negated_terms_for_title(text_lower, {term for term, _ in all_terms}) if is_title else set()
    )

    consumed: list[tuple[int, int]] = []
    hits: dict[str, list[str]] = {}
    for term, category in all_terms:
        if term in suppressed_terms or term in negated_terms:
            continue
        for span in _find_term_spans(text_lower, term):
            if _overlaps(span, consumed):
                continue
            if is_title and term == "butter" and any(
                re.search(rf"\b{re.escape(modifier)}\b", text_lower) for modifier in BUTTER_COMPOUND_MODIFIERS
            ):
                continue
            consumed.append(span)
            hits.setdefault(category, []).append(term)
    return hits


@dataclass
class Mismatch:
    recipe_id: str
    title: str
    category: str
    title_terms: list[str]


def find_title_ingredient_mismatches(recipe: Recipe) -> list[Mismatch]:
    """Returns one `Mismatch` per title-implied allergen category that is
    absent from both this recipe's ingredient names and its derived
    `allergens` field. Empty list means the recipe is clean."""
    title_hits = _scan_text_for_categories(recipe.title, is_title=True)
    if not title_hits:
        return []

    ingredient_text = " | ".join(item.name for item in recipe.ingredients)
    ingredient_hits = _scan_text_for_categories(ingredient_text, is_title=False)
    recipe_allergens = {a.lower() for a in recipe.allergens}

    mismatches = []
    for category, title_terms in title_hits.items():
        spec = TITLE_ALLERGEN_CATEGORIES[category]
        in_ingredients = category in ingredient_hits
        in_allergens = bool(recipe_allergens & spec["allergen_labels"])
        if not in_ingredients and not in_allergens:
            mismatches.append(
                Mismatch(
                    recipe_id=recipe.recipe_id,
                    title=recipe.title,
                    category=category,
                    title_terms=sorted(set(title_terms)),
                )
            )
    return mismatches


def build_quarantine_record(recipe: Recipe, mismatches: list[Mismatch]) -> dict:
    """The one shared shape for a quarantine-sidecar row, used by both the
    one-time `scripts/quarantine_flagged_recipes.py` cleanup and
    `CorpusImportPipeline`'s import-time check, so the two can never drift
    into two different quarantine-record schemas."""
    return {
        "recipe": recipe.model_dump(mode="json"),
        "quarantine_reason": {
            "check": "title_ingredient_integrity",
            "mismatches": [{"category": m.category, "title_terms": m.title_terms} for m in mismatches],
            "explanation": (
                "Title names an allergen-bearing food absent from both the ingredient "
                "list and the derived allergens field -- the ingredient list is "
                "considered untrustworthy (may omit other facts too), not merely "
                "mislabeled, so it is quarantined rather than repaired."
            ),
        },
        "quarantined_at_utc": datetime.now(timezone.utc).isoformat(),
    }
