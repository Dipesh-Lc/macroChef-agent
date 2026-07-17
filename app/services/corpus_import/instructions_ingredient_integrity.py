"""Shared detection logic for the instructions/ingredient integrity check: does
a recipe's own INSTRUCTIONS text name a safety-relevant food (an allergen
category, an animal-flesh word, or undisclosed stock) that never shows up
anywhere in its structured ingredient list or its derived `allergens` field?

Root cause (established separately, see `title_ingredient_integrity.py`'s
module docstring for the twin defect on the TITLE side): a meaningful slice
of the Food.com CC0 import (`imported_recipes.jsonl`) has an
`instructions`-column that names ingredients the `ingredients` list omits --
e.g. "Chinese Beef and Broccoli" whose instructions repeatedly say
"steak"/"beef" but whose ingredient list has zero animal-flesh rows. This is
the pre-registered, advisor-authored (Fable 5, MODE: ADVISE, 2026-07-17)
implementable spec at `docs/instructions_integrity_spec.md` -- read that
document first; it is the single source of truth for every rule below, and
every section-number citation in this file's comments refers to it.

This module is the single source of truth for the check, used by:
  - `scripts/audit_instructions_integrity.py` -- the corpus-wide dry-run
    audit/report with the pre-registered guard bands.
  - `scripts/quarantine_flagged_recipes.py --check instructions` -- applies
    the quarantine decision using the exact same merge-by-id/atomic-write
    path as the title check.
  - `app.services.corpus_import.pipeline.CorpusImportPipeline` -- so this
    exact defect class is caught and quarantined at import time for any
    FUTURE import, not just retroactively for this one historical corpus.

Design, mirroring `title_ingredient_integrity.py` (spec Sec. 2's "core
asymmetry"):
- **Triggering (instructions side) is STRICT**: word-boundary regex with an
  optional trailing "s" (the exact `_find_term_spans` idiom from the title
  module), longest-phrase-first span consumption, plus the step-local
  suppression rules below (spec Sec. 2).
- **Satisfaction (ingredient-rows side) is LENIENT**: a category is
  satisfied if any ingredient row word-boundary-matches any term in that
  category's (usually larger) satisfier list, OR the category's
  `allergen_labels` intersect `recipe.allergens` (mirrors the title module's
  OR-arm rationale) -- this is a *completeness* check, not an allergen
  classifier; see spec Sec. 2's rationale paragraph.
- Unlike the title module (which scans ONE string, the title), `instructions`
  is `list[str]` -- one element per step -- and several suppression rules
  (negation, serving-cue, "mock") are explicitly STEP-LOCAL, not
  whole-recipe: see spec Sec. 2. This module therefore scans and consumes
  spans per-step, then aggregates hits across steps, so the exact same term
  can be suppressed in one step and still flag in another (the
  imp_997819df41245ec6 "Omit almonds" / "Add ... almonds" case).

Three tiers (spec Sec. 1), carried on every `Mismatch` as `.tier`:
  - Tier A (auto-quarantine): safety-vocabulary cross-check (allergen
    categories, meat flesh words, wheat/gluten terms).
  - Tier B (auto-quarantine): undisclosed standalone stock (`stock`,
    `broth`, `bouillon`).
  - Tier C (report-only, NEVER quarantines): curated generic residue
    (`oil`, `dough`, `batter`, bare `meat`, `sauce`, `gravy`) -- too
    polysemous to quarantine deterministically; carried in the report only
    so a future adjudication has per-row evidence.
Decision rule (spec Sec. 3): a row is quarantined iff it has >=1
un-suppressed Tier A or Tier B mismatch. Tier assignment is fixed by the
vocabulary, never by results.

Explicitly out of scope (spec Sec. 1): non-safety-vocabulary omissions (the
imp_f9cc221553155bfc "orange juice" class) and title-side bare meat/fish
words (title module's existing, deliberate omission) -- neither is an
engine-visible safety hazard or newly caught by this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.schemas.recipe import Recipe

# --- Independent hand-authored vocabulary (spec Sec. 2) ---------------------
#
# Every set below is authored independently of
# `app.services.constraint_engine.ALLERGEN_ALIASES`/`MEAT_ALIASES` -- same
# independence rationale as `title_ingredient_integrity.TITLE_ALLERGEN_
# CATEGORIES` -- so a gap or bug in the production table can't make this
# check blind to the same gap. The one deliberate EXCEPTION is the drift
# test in `tests/test_instructions_ingredient_integrity.py`, which asserts
# this module's meat trigger set is a SUPERSET of the flesh-word subset of
# `MEAT_ALIASES`, so the two can never silently diverge on which words mean
# "animal flesh."

# Peanut (spec Sec. 2 "peanut"): unlike the title module, "satay" is
# INCLUDED here -- a deliberate, pre-registered difference (the title module
# rejected "satay" for real title-side counter-examples; the advisor
# pre-registered it for instructions-side use regardless, spec Sec. 2).
PEANUT_TERMS: frozenset[str] = frozenset(
    {
        "peanut", "peanuts", "groundnut", "groundnuts",
        # Two-word form live in imp_d34a2ab621245cba: "ground nut oil".
        "ground nut", "ground nuts",
        "satay",
    }
)

# Tree nut (spec Sec. 2 "tree_nut"): the title module's species list, plus
# "nutella" and "chestnut" (chestnut gets its own preceding-token suppression
# below, mirroring constraint_engine._LOOKALIKE_EXCLUSIONS's "water chestnut"
# carve-out).
#
# NOTE on "chestnut": deliberately singular-only here (unlike the other
# species below, which mirror the title module's literal singular+plural
# pairs harmlessly). The preceding-token suppression table below
# (`_CHESTNUT_PRECEDING_SUPPRESSORS`) is keyed on the exact authored term
# text "chestnut" -- registering "chestnuts" too would let the LONGER
# plural entry win longest-phrase-first consumption and consume the span
# before the suppression lookup (keyed on the singular) ever ran, silently
# defeating "water chestnut" -> a real bug caught by this module's own test
# suite (`test_synthetic_water_chestnut_preceding_token_suppression`) during
# development. `_find_term_spans`'s own optional trailing "s?" already
# matches "chestnuts" from the singular entry, so no coverage is lost.
TREE_NUT_TERMS: frozenset[str] = frozenset(
    {
        "almond", "almonds", "walnut", "walnuts", "pecan", "pecans",
        "cashew", "cashews", "hazelnut", "hazelnuts", "pistachio",
        "pistachios", "macadamia", "macadamias", "brazil nut", "brazil nuts",
        "pine nut", "pine nuts", "marzipan", "praline", "frangipane",
        "gianduja", "nutella", "chestnut",
    }
)

# Dairy (spec Sec. 2 "dairy"): bare `cream` is deliberately NOT a trigger at
# all -- "Cream together butter and sugar" is a verb, live in
# imp_6ab74a6c238451a3 -- only the multiword cream forms below are triggers.
_DAIRY_CREAM_PHRASES: frozenset[str] = frozenset(
    {
        "heavy cream", "sour cream", "whipping cream", "whipped cream",
        "light cream", "double cream", "half-and-half", "half and half",
    }
)
DAIRY_TERMS: frozenset[str] = frozenset(
    {
        "butter", "milk", "buttermilk", "ghee", "cheese", "cheddar",
        "mozzarella", "parmesan", "parmigiano", "pecorino", "ricotta",
        "feta", "brie", "mascarpone", "yogurt", "yoghurt",
    }
    | _DAIRY_CREAM_PHRASES
)
# Satisfier-only extras (spec Sec. 2): recipes routinely list margarine and
# say "butter" in their own instructions (live in Prize Butter Tarts,
# imp_348d24dd1f4d5284) -- lenient on the satisfier side only, never a
# trigger (margarine is not itself a dairy-hazard word).
# Revision round 1 (2026-07-18 ruling): "soymilk" added -- satisfier-only,
# never a dairy trigger. imp_b3f19d74632257ba "Trifle"'s own ingredient rows
# spell it as one word ("soymilk"), which the word-boundary satisfier match
# on bare "milk" cannot reach (no boundary between "soy" and "milk" in the
# unspaced form), even though the instructions' "Fold in the sugar, milk,
# and lemon juice" / "Whisk in the remaining milk" mentions are plausibly
# that same soymilk.
DAIRY_SATISFIER_EXTRAS: frozenset[str] = frozenset({"margarine", "shortening", "soymilk"})

# Wheat/gluten (spec Sec. 2 "wheat_gluten"): "soy sauce" is a phrase trigger
# that fires BOTH wheat_gluten AND soy (matching the constraint_engine's
# 4bf2377 stance on soy-sauce/hoisin/teriyaki -> wheat) -- see
# `_DUAL_CATEGORY_TERMS` below for the mechanism. "breaded"/"floured" are
# explicit literal terms (not a general `(ed|ing)?` suffix, which would
# create "fished"/"creamed" homograph problems -- spec Sec. 2 morphology
# note).
WHEAT_GLUTEN_TERMS: frozenset[str] = frozenset(
    {
        "bread", "flour", "pasta", "spaghetti", "macaroni", "linguine",
        "fettuccine", "lasagna", "noodle", "wheat", "cracker", "biscuit",
        "tortilla", "pastry", "dumpling", "crouton", "couscous", "bulgur",
        "semolina", "phyllo", "filo", "pita", "bagel", "bran", "barley",
        "rye", "malt", "seitan", "breaded", "floured",
        "soy sauce",
    }
)
# Satisfier-only extras (spec Sec. 2): "dough" and "mix" (e.g. "cake mix"
# ingredient rows) are lenient completions of a wheat mention, never
# themselves triggers (too polysemous as triggers -- that generic-residue
# role is filled by the separate Tier C "dough"/"batter" categories below).
WHEAT_GLUTEN_SATISFIER_EXTRAS: frozenset[str] = frozenset({"dough", "mix"})

# Egg (spec Sec. 2 "egg"): `\begg\b` correctly matches "egg-yolks"/"egg
# wash", correctly ignores "eggplant" (no word boundary inside it) --
# "egg-plant" (hyphenated) DOES have a boundary and needs the explicit
# exact-phrase suppression below.
EGG_TERMS: frozenset[str] = frozenset({"egg", "eggs", "meringue"})

# Fish (spec Sec. 2 "fish"): bare `fish` is a NEW trigger not present in the
# title module (title-side bare fish/meat words are proven unsafe to check,
# spec Sec. 1's "Title side: unchanged" note) -- `sole` is deliberately
# omitted (homograph, no corpus benefit, mirrors the title module).
FISH_TERMS: frozenset[str] = frozenset(
    {
        "fish", "salmon", "tuna", "cod", "halibut", "trout", "snapper",
        "anchovy", "anchovies", "sardine", "sardines", "mackerel",
        "herring", "haddock", "flounder", "sea bass", "worcestershire",
        "puttanesca",
    }
)

# Mollusk / crustacean / sesame / soy (spec Sec. 2): "the title module's
# lists" -- copied, not imported, per this module's independence rationale
# above (a bug in the title module's list must not silently propagate here).
MOLLUSK_TERMS: frozenset[str] = frozenset(
    {"clam", "clams", "mussel", "mussels", "oyster", "oysters", "scallop", "scallops"}
)
CRUSTACEAN_TERMS: frozenset[str] = frozenset(
    {"shrimp", "prawn", "prawns", "crab", "crabmeat", "crab meat", "lobster", "crawfish", "crayfish"}
)
# Satisfier-only extra (revision round 1, 2026-07-18 ruling): "trassi" --
# imp_f26d5c5093e25ac7 "Amazing Nasi Goreng" lists "trassi oedang" as an
# ingredient (an Indonesian shrimp paste) and its own NOTES step names it as
# a shrimp paste; the trassi row already accounts for the crustacean
# mention (also independently suppressed at that step by the new
# commentary-prefix rule below, but this satisfier holds regardless of
# suppression wording).
CRUSTACEAN_SATISFIER_EXTRAS: frozenset[str] = frozenset({"trassi"})
SESAME_TERMS: frozenset[str] = frozenset({"sesame", "tahini"})
SOY_TERMS: frozenset[str] = frozenset({"soy", "soya", "tofu", "edamame", "miso", "tempeh", "tamari"})
# Satisfier-only extra (revision round 1, 2026-07-18 ruling): "soymilk" --
# same imp_b3f19d74632257ba "Trifle" rationale as DAIRY_SATISFIER_EXTRAS
# above (the bare-word "soy"/"soya" satisfiers can't word-boundary-match the
# unspaced ingredient-row spelling), plus imp_3e5cbefd62c05ed8 "Pumpkin Au
# Gratin" (same ingredient-row spelling).
SOY_SATISFIER_EXTRAS: frozenset[str] = frozenset({"soymilk"})

# Meat (spec Sec. 2 "meat", NEW): flesh words ONLY. Deliberately EXCLUDES
# gelatin/marshmallow/worcestershire/suet/lard -- different hazard classes;
# gelatin+worcestershire are fish-side allergen terms, and bare "meat" is the
# separate Tier C `meat_generic` category below, never this one.
#
# `tests/test_instructions_ingredient_integrity.py::test_meat_terms_are_
# superset_of_meat_alias_flesh_words` asserts this set is a SUPERSET of the
# flesh-word subset of `constraint_engine.MEAT_ALIASES` (that set minus the
# same five non-flesh exclusions), so the two vocabularies can never silently
# drift apart on what counts as animal flesh.
#
# Revision round 1 (2026-07-18, advisor ruling on the 220709Z HALT report,
# docs/instructions_integrity_spec.md pre-registration): "sparerib"/"spare
# rib" added -- imp_6f3463afcc2f5d51 "Pork Spareribs in Tangy Sauce" has
# zero flesh-word rows in its ingredient list and its instructions say only
# "Trim spareribs..."/"...pour over the ribs", a genuine miss the bare
# vocabulary didn't catch. Deliberately NOT adding bare "rib"/"ribs" (too
# polysemous, e.g. "rib of celery").
MEAT_FLESH_TERMS: frozenset[str] = frozenset(
    {
        "bacon", "beef", "chicken", "chorizo", "duck", "goose", "ham",
        "hot dog", "lamb", "pancetta", "pepperoni", "pork", "prosciutto",
        "rabbit", "sausage", "steak", "turkey", "veal",
        "sparerib", "spare rib",
    }
)
# Satisfier-only extra (revision round 1, 2026-07-18 ruling): "roast"
# (`\broasts?\b`, deliberately NOT "roasted" -- the word-boundary regex
# already excludes it) -- imp_a52ae950e8dd5eb5 "Sauerbraten & Ginger" lists
# "rump roast" as its ingredient, and its instructions say "beef"/"meat"
# throughout; a roast IS a cut of animal flesh, so its own listed roast
# already satisfies the hidden meat mention.
MEAT_SATISFIER_EXTRAS: frozenset[str] = frozenset({"roast"})

# Tier B (spec Sec. 1 "Tier B"): undisclosed standalone stock. Triggers are
# exactly these three words -- word-boundary-safe with one suppression
# ("stock pot", handled via EXACT_PHRASE_SUPPRESSIONS below).
STOCK_TERMS: frozenset[str] = frozenset({"stock", "broth", "bouillon"})

# Tier C (spec Sec. 1 "Tier C"): curated generic residue, report-only, never
# quarantines.
_OIL_TERMS: frozenset[str] = frozenset({"oil"})
_DOUGH_TERMS: frozenset[str] = frozenset({"dough"})
_BATTER_TERMS: frozenset[str] = frozenset({"batter"})
_MEAT_GENERIC_TERMS: frozenset[str] = frozenset({"meat"})
_SAUCE_TERMS: frozenset[str] = frozenset({"sauce"})
_GRAVY_TERMS: frozenset[str] = frozenset({"gravy"})


CATEGORIES: dict[str, dict] = {
    # --- Tier A: allergen-vocabulary cross-check ---------------------------
    "nut": {
        "tier": "A",
        "triggers": frozenset({"nut", "nuts"}),
        # Lenient by design (spec Sec. 2): satisfied by ANY nut-ish
        # ingredient row, peanut or tree-nut alike -- this is the "combined"
        # bucket, not a species-specific one. Coconut is deliberately NOT a
        # satisfier (spec Sec. 2 explicit exclusion).
        "satisfiers": frozenset({"nut", "nuts"}) | PEANUT_TERMS | TREE_NUT_TERMS,
        "allergen_labels": frozenset({"nuts", "tree nut", "peanut", "peanuts"}),
    },
    "peanut": {
        "tier": "A",
        "triggers": PEANUT_TERMS,
        "satisfiers": PEANUT_TERMS,
        "allergen_labels": frozenset({"peanut", "peanuts", "nuts"}),
    },
    "tree_nut": {
        "tier": "A",
        "triggers": TREE_NUT_TERMS,
        "satisfiers": TREE_NUT_TERMS,
        "allergen_labels": frozenset({"tree nut", "nuts"}),
    },
    "dairy": {
        "tier": "A",
        "triggers": DAIRY_TERMS,
        "satisfiers": DAIRY_TERMS | DAIRY_SATISFIER_EXTRAS,
        "allergen_labels": frozenset({"dairy", "milk"}),
    },
    "wheat_gluten": {
        "tier": "A",
        "triggers": WHEAT_GLUTEN_TERMS,
        "satisfiers": WHEAT_GLUTEN_TERMS | WHEAT_GLUTEN_SATISFIER_EXTRAS,
        "allergen_labels": frozenset({"wheat", "gluten"}),
    },
    "egg": {
        "tier": "A",
        "triggers": EGG_TERMS,
        "satisfiers": EGG_TERMS,
        "allergen_labels": frozenset({"egg", "eggs"}),
    },
    "fish": {
        "tier": "A",
        "triggers": FISH_TERMS,
        "satisfiers": FISH_TERMS,
        "allergen_labels": frozenset({"fish", "seafood"}),
        # Satisfied by plain SUBSTRING "fish" anywhere in an ingredient row
        # name (not just a word-boundary match) so compounds like
        # "swordfish"/"catfish"/"whitefish" -- which have no word boundary
        # before "fish" -- still count as the ingredient being present
        # (spec Sec. 2 "fish" satisfiers).
        "substring_satisfiers": frozenset({"fish"}),
    },
    "mollusk": {
        "tier": "A",
        "triggers": MOLLUSK_TERMS,
        "satisfiers": MOLLUSK_TERMS,
        "allergen_labels": frozenset({"shellfish", "seafood"}),
    },
    "crustacean": {
        "tier": "A",
        "triggers": CRUSTACEAN_TERMS,
        "satisfiers": CRUSTACEAN_TERMS | CRUSTACEAN_SATISFIER_EXTRAS,
        "allergen_labels": frozenset({"crustacean", "shellfish", "seafood"}),
    },
    "sesame": {
        "tier": "A",
        "triggers": SESAME_TERMS,
        "satisfiers": SESAME_TERMS,
        "allergen_labels": frozenset({"sesame"}),
    },
    "soy": {
        "tier": "A",
        "triggers": SOY_TERMS,
        "satisfiers": SOY_TERMS | SOY_SATISFIER_EXTRAS,
        "allergen_labels": frozenset({"soy", "soya"}),
    },
    "meat": {
        "tier": "A",
        # Lenient by design (spec Sec. 2): a row already containing ANY
        # animal-flesh OR fish/crustacean/mollusk term is already
        # non-vegetarian at serve time, so an additional hidden meat adds no
        # incremental engine-visible hazard -- only rows with NO
        # animal-flesh-or-seafood rows at all flag.
        "triggers": MEAT_FLESH_TERMS,
        "satisfiers": MEAT_FLESH_TERMS | FISH_TERMS | CRUSTACEAN_TERMS | MOLLUSK_TERMS | MEAT_SATISFIER_EXTRAS,
        # Not an allergen -- a diet-type (vegetarian) hazard only, so there
        # is no `recipe.allergens` OR-arm for it (empty set is a no-op in
        # `_category_satisfied`).
        "allergen_labels": frozenset(),
    },
    # --- Tier B: undisclosed standalone stock -------------------------------
    #
    # Revision round 1 (2026-07-18 ruling): beyond the literal
    # stock/broth/bouillon satisfier below, `_category_satisfied` also
    # applies a "stock"-specific composite check (`_stock_composite_
    # satisfied`, spec ruling item 5) -- an in-recipe stock is a plausible
    # composite of already-listed rows when (arm 1) any mollusk-term row is
    # present (imp_787ec005979550d2 "Mussels Fra Diavolo"), OR (arm 2) a
    # `water` row AND >=1 animal-flesh/fish/crustacean/mollusk row is
    # present (imp_2391b489ec6459e3 "Down East Haddock Chowder",
    # imp_54fefa2b200d50a7 "Pancit"). Verified NOT to over-suppress the two
    # planted Tier B faults that must still flag: imp_ece8c7dd17b95468
    # "Dirty Rice" (no water row) and imp_acd7c3ec0ed35a51 "Rice, Apple and
    # Raisin Dressing" (no animal rows) -- neither satisfies either arm.
    "stock": {
        "tier": "B",
        "triggers": STOCK_TERMS,
        "satisfiers": STOCK_TERMS,
        "allergen_labels": frozenset(),
    },
    # --- Tier C: curated generic residue, report-only, never quarantines ---
    "oil": {
        "tier": "C",
        "triggers": _OIL_TERMS,
        "satisfiers": _OIL_TERMS,
        "allergen_labels": frozenset(),
    },
    "dough": {
        "tier": "C",
        "triggers": _DOUGH_TERMS,
        # A "dough" mention is a plausible composite of an already-listed
        # flour/mix row -- reuses the wheat_gluten satisfier vocabulary.
        "satisfiers": WHEAT_GLUTEN_TERMS | WHEAT_GLUTEN_SATISFIER_EXTRAS,
        "allergen_labels": frozenset(),
    },
    "batter": {
        "tier": "C",
        "triggers": _BATTER_TERMS,
        # A "batter" mention is plausibly flour+egg+milk already listed.
        "satisfiers": WHEAT_GLUTEN_TERMS | WHEAT_GLUTEN_SATISFIER_EXTRAS | EGG_TERMS | DAIRY_TERMS,
        "allergen_labels": frozenset(),
    },
    "meat_generic": {
        "tier": "C",
        "triggers": _MEAT_GENERIC_TERMS,
        "satisfiers": MEAT_FLESH_TERMS | FISH_TERMS | CRUSTACEAN_TERMS | MOLLUSK_TERMS,
        "allergen_labels": frozenset(),
    },
    "sauce": {
        "tier": "C",
        "triggers": _SAUCE_TERMS,
        "satisfiers": _SAUCE_TERMS,
        "allergen_labels": frozenset(),
    },
    "gravy": {
        "tier": "C",
        "triggers": _GRAVY_TERMS,
        "satisfiers": _GRAVY_TERMS,
        "allergen_labels": frozenset(),
    },
}

# A term matched under one category that must ALSO register a hit for a
# second category from the exact same occurrence (spec Sec. 2: "soy sauce
# (phrase; triggers wheat AND soy, matching the engine's 4bf2377 stance)").
# This is NOT the general longest-phrase-first consumption mechanism (which
# would let only ONE category claim a given span) -- it is a small, explicit,
# cited table for the one case the spec pre-registers as a deliberate
# dual-fire, so the general consumption model stays simple and predictable
# everywhere else.
_DUAL_CATEGORY_TERMS: dict[tuple[str, str], str] = {
    ("wheat_gluten", "soy sauce"): "soy",
}


# --- Step-local suppression rules (spec Sec. 2) -----------------------------

# Generic negation (step-local, NOT term-specific): if a step contains any of
# these, EVERY match in that step is suppressed. "no <term>" and
# "<term>-free" are handled separately below because they name the specific
# disclaimed term.
# Revision round 1 (2026-07-18 ruling): `substitutes?` added --
# imp_3787a22d065b5c3d '"any" Muffins': 'substitute 1 heaping Tbsp of soy
# flour and 1 Tbsp of water.' names soy flour only as a cross-referenced
# swap, not as this recipe's own content. Deliberately `substitutes?`, NOT
# a bare `(ed)?` suffix -- "substituted" (past tense, live in
# imp_348d24dd1f4d5284 "Craisins can be substituted for the raisins") is a
# genuine in-recipe substitution note about an ingredient this recipe DOES
# use and must NOT be step-wide-suppressed.
_GENERIC_NEGATION_PHRASES: tuple[str, ...] = (
    "omit", "without", "instead of", "in place of", "do not add", "leave out",
    r"substitutes?",
)
_GENERIC_NEGATION_PATTERNS = [re.compile(rf"\b{phrase}\b") for phrase in _GENERIC_NEGATION_PHRASES]

# Intended-use/serving cues (step-local): suppress every match in a step
# containing one of these -- clears "Fish Marinade" (imp_e8b6568570965387:
# "Use as a marinade, Then as a basting sauce when you cook fish") while
# "Cut the fish into small pieces and mix through" (Spicy Fish Cakes,
# imp_ffba7239b17c5b29) has no cue in its own step and still flags.
_SERVING_CUE_PHRASES: tuple[str, ...] = (
    "serve with", "serve over", "serve alongside", "serve on",
    "use as", "use it as", "use to", "use on",
    "when you cook", "when cooking", "when grilling", "when serving",
    "goes well with", "great with", "delicious with",
)
_SERVING_CUE_PATTERNS = [re.compile(rf"\b{re.escape(phrase)}\b") for phrase in _SERVING_CUE_PHRASES]

# Commentary/attribution step-prefix markers (step-wide suppression, revision
# round 1, 2026-07-18 ruling on the 220709Z HALT report): a step that OPENS
# with an editorial-aside label -- a "Notes:"/"Tip:"/"Variation:" aside, a
# syndicated-column attribution, a garnish/serving-suggestion callout -- is
# commentary ABOUT the recipe, not a step describing what this recipe itself
# contains, so every match in that step is suppressed. The colon is REQUIRED
# so a step that merely uses the word "note"/"tip" mid-sentence (not as a
# leading label) is untouched -- matches the ruling's exact anchor:
# `^\s*(?:nb|notes?|tips?|variations?|column|garnishing note|serving
# suggestions?|suggested accompaniments?)\s*:`. Per-alternative citations:
#   notes                    -- imp_f26d5c5093e25ac7 "NOTES : Trassi is a..."
#   nb                       -- imp_3e5cbefd62c05ed8 "NB: if you like..."
#   tips                     -- imp_4b158d76b28e594d "TIPS: * if using..."
#   variations               -- imp_a7eb6f7b7e885e67 "Variation:  Top with..."
#   column                   -- imp_ce64651a221b54d3 "Column: 'Sausages...'"
#   garnishing note          -- imp_bca827b64d08523e "Garnishing note: ..."
#   serving suggestions      -- imp_72746bdecd895fb1 / imp_c39c91fead915027
#   suggested accompaniments -- imp_6404a96a38aa5c12 "Suggested accompaniments:"
_COMMENTARY_PREFIX_PATTERN = re.compile(
    r"^\s*(?:nb|notes?|tips?|variations?|column|garnishing note|"
    r"serving suggestions?|suggested accompaniments?)\s*:",
    re.IGNORECASE,
)

# Optional-variation / cross-reference phrases (step-wide suppression, same
# semantics as the serving-cue list above, revision round 1, 2026-07-18
# ruling): a step naming an OPTIONAL add-in, or referencing another
# recipe/ingredient's quantity rather than asserting this recipe's own
# content, is not evidence the named ingredient is actually in this recipe.
_OPTIONAL_VARIATION_PHRASES: tuple[str, ...] = (
    "as desired",  # imp_28766bd14c6c5a24 "shrimp, crab, or curry as desired"
    "if desired",  # imp_14b6c0f7d1df59f4
    "if you like",  # imp_3e5cbefd62c05ed8 "NB: if you like almonds..."
    r"optional(?:s|ly)?",  # imp_0539d1b8b65e58ae
    "same quantities as",  # imp_941617b6247054aa "same quantities as Oyster Sauce"
    "menu featuring",  # imp_0d20dbf56b3b55fa "a menu featuring an egg and cheese dish"
)
_OPTIONAL_VARIATION_PATTERNS = [re.compile(rf"\b{phrase}\b") for phrase in _OPTIONAL_VARIATION_PHRASES]

# Preceding-token suppressions (span-local, immediately-preceding word only
# -- deliberately NOT the title module's whole-text BUTTER_COMPOUND_
# MODIFIERS rule, which would over-suppress in long instructions text, spec
# Sec. 2). Keyed by the exact trigger term text (as authored above, without
# the "s?" morphology).
_BUTTER_PRECEDING_SUPPRESSORS: frozenset[str] = frozenset(
    {
        "apple", "pear", "peach", "plum", "apricot", "pumpkin", "quince",
        "fig", "mango", "cranberry", "cherry", "strawberry", "peanut",
        "almond", "cashew", "sunflower", "cocoa", "nut", "seed",
    }
)
_MILK_PRECEDING_SUPPRESSORS: frozenset[str] = frozenset(
    {"coconut", "almond", "soy", "soya", "rice", "oat", "cashew", "hemp"}
)
_FLOUR_PRECEDING_SUPPRESSORS: frozenset[str] = frozenset(
    {"corn", "rice", "potato", "tapioca", "almond", "coconut", "chickpea", "soy", "oat", "quinoa"}
)
_CHESTNUT_PRECEDING_SUPPRESSORS: frozenset[str] = frozenset({"water"})

_PRECEDING_TOKEN_SUPPRESSIONS: dict[str, frozenset[str]] = {
    "butter": _BUTTER_PRECEDING_SUPPRESSORS,
    "milk": _MILK_PRECEDING_SUPPRESSORS,
    "flour": _FLOUR_PRECEDING_SUPPRESSORS,
    "chestnut": _CHESTNUT_PRECEDING_SUPPRESSORS,
}

# Exact-phrase suppressions (tool/brand/idiom, each individually cited in
# spec Sec. 2). Maps the exact phrase to the SINGLE vocabulary term whose
# occurrence *within that phrase's span* is suppressed -- other terms inside
# the same phrase (e.g. "cracker" in "oyster crackers") are untouched.
EXACT_PHRASE_SUPPRESSIONS: dict[str, str] = {
    # "pastry blender" is live in imp_9ff0ac08d2b353ca's own text; the other
    # pastry/bread/biscuit tool phrases are the same documented SHAPE of
    # false positive (a kitchen tool or product name, not a food mention).
    "pastry blender": "pastry",
    "pastry brush": "pastry",
    "pastry bag": "pastry",
    "pastry cutter": "pastry",
    "pastry cloth": "pastry",
    "biscuit cutter": "biscuit",
    "bread machine": "bread",
    "bread knife": "bread",
    "bread board": "bread",
    # "stock pot" (the utensil) is not itself undisclosed stock (the
    # ingredient) -- both spellings covered.
    "stock pot": "stock",
    "stock-pot": "stock",
    # "Cape Cod" (place name) is not the fish "cod" -- mirrors the title
    # module's own cited exclusion for the same phrase.
    "cape cod": "cod",
    # "Cracker Barrel" (restaurant-chain proper noun) is not the wheat
    # "cracker" -- mirrors the title module's own cited exclusion.
    "cracker barrel": "cracker",
    # "Grape-Nuts"/"grape nuts" (breakfast-cereal brand name) is not a tree
    # nut -- the word "nuts" would otherwise word-boundary-match inside it.
    "grape-nuts": "nut",
    "grape nuts": "nut",
    # "oyster cracker(s)" suppresses "oyster" only -- "cracker" is still
    # independently evaluable (spec Sec. 2 explicit note).
    "oyster crackers": "oyster",
    "oyster cracker": "oyster",
    # "fish out" (e.g. "fish out the bay leaves") is an idiom, not a fish
    # mention.
    "fish out": "fish",
    # "egg-plant" (hyphenated form) DOES have a word boundary between "egg"
    # and "plant" (unlike unhyphenated "eggplant", which \begg\b already
    # correctly ignores) -- needs the explicit suppression.
    "egg-plant": "egg",
}


def _find_term_spans(text: str, term: str) -> list[tuple[int, int]]:
    """Word-boundary match with an optional trailing "s" -- the exact idiom
    `title_ingredient_integrity._find_term_spans` uses, reused here (not
    imported, to keep this module's own vocabulary/matching fully
    independent per this module's docstring)."""
    return [m.span() for m in re.finditer(rf"\b{re.escape(term)}s?\b", text)]


def _overlaps(span: tuple[int, int], consumed: list[tuple[int, int]]) -> bool:
    return any(span[0] < end and start < span[1] for start, end in consumed)


def _step_has_generic_negation(step_lower: str) -> bool:
    return any(pattern.search(step_lower) for pattern in _GENERIC_NEGATION_PATTERNS)


def _step_has_serving_cue(step_lower: str) -> bool:
    return any(pattern.search(step_lower) for pattern in _SERVING_CUE_PATTERNS)


def _step_has_commentary_prefix(step_lower: str) -> bool:
    """Revision round 1 (2026-07-18 ruling): whole-step suppression for a
    leading editorial-commentary label (see `_COMMENTARY_PREFIX_PATTERN`'s
    definition above for the full per-alternative citation list)."""
    return bool(_COMMENTARY_PREFIX_PATTERN.search(step_lower))


def _step_has_optional_variation(step_lower: str) -> bool:
    """Revision round 1 (2026-07-18 ruling): whole-step suppression for an
    optional-add-in / cross-reference phrase (see `_OPTIONAL_VARIATION_
    PHRASES` above for the full per-alternative citation list)."""
    return any(pattern.search(step_lower) for pattern in _OPTIONAL_VARIATION_PATTERNS)


def _term_negated_specific(step_lower: str, term: str) -> bool:
    """"no <term>" / "<term>-free" (spec Sec. 2): unlike the generic
    negation phrases above, these name the SPECIFIC disclaimed term, so this
    check is per-term rather than whole-step."""
    escaped = re.escape(term)
    return bool(
        re.search(rf"\bno[-\s]{escaped}s?\b", step_lower)
        or re.search(rf"\b{escaped}s?[-\s]free\b", step_lower)
    )


def _phrase_suppression_spans(step_lower: str) -> list[tuple[tuple[int, int], str]]:
    spans: list[tuple[tuple[int, int], str]] = []
    for phrase, suppressed_term in EXACT_PHRASE_SUPPRESSIONS.items():
        for match in re.finditer(rf"\b{re.escape(phrase)}\b", step_lower):
            spans.append((match.span(), suppressed_term))
    return spans


def _is_phrase_suppressed(
    span: tuple[int, int], term: str, phrase_spans: list[tuple[tuple[int, int], str]]
) -> bool:
    return any(term == suppressed_term and _overlaps(span, [phrase_span]) for phrase_span, suppressed_term in phrase_spans)


def _preceding_word(text: str, start: int) -> str:
    """The alphabetic word immediately preceding index `start` in `text`
    (used for the span-local preceding-token suppressions above), or "" if
    the span is at the start of the step or preceded by punctuation/digits."""
    before = text[:start]
    match = re.search(r"([a-z]+)[\s-]*$", before)
    return match.group(1) if match else ""


def _is_preceding_token_suppressed(step_lower: str, span: tuple[int, int], term: str) -> bool:
    suppressors = _PRECEDING_TOKEN_SUPPRESSIONS.get(term)
    if not suppressors:
        return False
    return _preceding_word(step_lower, span[0]) in suppressors


def _scan_step_for_categories(step: str) -> dict[str, list[str]]:
    """Returns {category: [matched terms]} for ONE instruction step, across
    every tier. Longest terms are matched first and claim their span so a
    shorter overlapping term of a DIFFERENT category can't also fire for the
    same underlying phrase (e.g. "ground nut oil": the two-word peanut term
    "ground nut" claims that span before the bare "nut" category's one-word
    term gets a chance at the same characters) -- the one pre-registered
    exception is `_DUAL_CATEGORY_TERMS` above, which deliberately fires a
    second category from the same span."""
    step_lower = step.lower()

    # "mock" is the same decades-old recipe convention as the title module's
    # (see that module's docstring) -- a step asserting "mock X" is
    # asserting the ABSENCE of X, so no category can be validly inferred
    # from that step at all. Applied per-step here (not per-recipe), per
    # spec Sec. 2's "per-step mock rule."
    if re.search(r"\bmock\b", step_lower):
        return {}

    # Step-wide suppressions (spec Sec. 2, plus revision round 1's two new
    # whole-step classes, 2026-07-18 ruling): negation, serving/intended-use
    # cues, a leading editorial-commentary label, and an optional-variation/
    # cross-reference phrase each suppress the ENTIRE step's matches, not a
    # specific term.
    if (
        _step_has_generic_negation(step_lower)
        or _step_has_serving_cue(step_lower)
        or _step_has_commentary_prefix(step_lower)
        or _step_has_optional_variation(step_lower)
    ):
        return {}

    all_terms: list[tuple[str, str]] = [
        (term, category) for category, spec in CATEGORIES.items() for term in spec["triggers"]
    ]
    all_terms.sort(key=lambda pair: len(pair[0]), reverse=True)

    phrase_spans = _phrase_suppression_spans(step_lower)
    consumed: list[tuple[int, int]] = []
    hits: dict[str, list[str]] = {}

    for term, category in all_terms:
        for span in _find_term_spans(step_lower, term):
            if _overlaps(span, consumed):
                continue
            if _term_negated_specific(step_lower, term):
                continue
            if _is_phrase_suppressed(span, term, phrase_spans):
                continue
            if _is_preceding_token_suppressed(step_lower, span, term):
                continue
            consumed.append(span)
            hits.setdefault(category, []).append(term)
            extra_category = _DUAL_CATEGORY_TERMS.get((category, term))
            if extra_category:
                hits.setdefault(extra_category, []).append(term)

    return hits


def _ingredient_text_matches(term: str, ingredient_text_lower: str) -> bool:
    return bool(re.search(rf"\b{re.escape(term)}s?\b", ingredient_text_lower))


def _stock_composite_satisfied(ingredient_text_lower: str) -> bool:
    """Tier B composite in-recipe-stock satisfier (spec ruling item 5,
    revision round 1, 2026-07-18): the `stock` category is ALSO satisfied
    (beyond the literal stock/broth/bouillon satisfier list) when the
    ingredient rows already show enough of the stock's own composition that
    a separate stock ingredient is a plausible in-recipe composite, not a
    hidden one --
      (arm 1) any mollusk-term row is present (imp_787ec005979550d2
        "Mussels Fra Diavolo": a `mussels` row, "broth" in the instructions
        -- the mussels' own cooking liquid IS the broth), OR
      (arm 2) a `water` row AND >=1 row naming any animal-flesh/fish/
        crustacean/mollusk term (imp_2391b489ec6459e3 "Down East Haddock
        Chowder": water + haddock; imp_54fefa2b200d50a7 "Pancit": water +
        pork/shrimp -- water simmered with the animal ingredient IS the
        stock).
    Verified NOT to over-suppress the two planted Tier B faults that must
    still flag: imp_ece8c7dd17b95468 "Dirty Rice" has no `water` row (arm 2
    fails on that alone) and no mollusk row (arm 1 fails); imp_acd7c3ec0ed35a51
    "Rice, Apple and Raisin Dressing" has neither a `water` row nor any
    animal row (arm 2 fails on both conjuncts) nor a mollusk row (arm 1
    fails) -- both recipes correctly fall through to the literal
    stock/broth/bouillon check, which is unchanged and still flags them."""
    if any(_ingredient_text_matches(term, ingredient_text_lower) for term in MOLLUSK_TERMS):
        return True
    if not re.search(r"\bwaters?\b", ingredient_text_lower):
        return False
    animal_terms = MEAT_FLESH_TERMS | FISH_TERMS | CRUSTACEAN_TERMS | MOLLUSK_TERMS
    return any(_ingredient_text_matches(term, ingredient_text_lower) for term in animal_terms)


def _category_satisfied(
    category: str, spec: dict, ingredient_text_lower: str, recipe_allergens: set[str]
) -> bool:
    for term in spec["satisfiers"]:
        if _ingredient_text_matches(term, ingredient_text_lower):
            return True
    for term in spec.get("substring_satisfiers", ()):
        if term in ingredient_text_lower:
            return True
    if category == "stock" and _stock_composite_satisfied(ingredient_text_lower):
        return True
    return bool(recipe_allergens & spec["allergen_labels"])


@dataclass
class Mismatch:
    recipe_id: str
    title: str
    category: str
    tier: str
    matched_terms: list[str] = field(default_factory=list)
    # One entry per (term, step) occurrence that fired this category,
    # carrying the FULL quoted step text -- per spec Sec. 5's evidence
    # requirement.
    evidence: list[dict] = field(default_factory=list)


def find_instructions_ingredient_mismatches(recipe: Recipe) -> list[Mismatch]:
    """Returns one `Mismatch` per instructions-implied category (any tier)
    that is absent from both this recipe's ingredient names and its derived
    `allergens` field. Empty list means the recipe is clean. Tier A/B
    mismatches are quarantine-worthy (spec Sec. 3's decision rule); Tier C
    mismatches are report-only and MUST NOT be used to gate a quarantine
    decision -- see `tier_ab_mismatches`/`tier_c_mismatches` below."""
    all_hits: dict[str, list[tuple[str, str]]] = {}
    for step in recipe.instructions:
        step_hits = _scan_step_for_categories(step)
        for category, terms in step_hits.items():
            bucket = all_hits.setdefault(category, [])
            for term in terms:
                pair = (term, step)
                if pair not in bucket:
                    bucket.append(pair)

    if not all_hits:
        return []

    ingredient_text_lower = " | ".join(item.name for item in recipe.ingredients).lower()
    recipe_allergens = {a.lower() for a in recipe.allergens}

    mismatches: list[Mismatch] = []
    for category, hit_pairs in all_hits.items():
        spec = CATEGORIES[category]
        if _category_satisfied(category, spec, ingredient_text_lower, recipe_allergens):
            continue
        mismatches.append(
            Mismatch(
                recipe_id=recipe.recipe_id,
                title=recipe.title,
                category=category,
                tier=spec["tier"],
                matched_terms=sorted({term for term, _ in hit_pairs}),
                evidence=[{"term": term, "quoted_step": step} for term, step in hit_pairs],
            )
        )
    return mismatches


def tier_ab_mismatches(mismatches: list[Mismatch]) -> list[Mismatch]:
    """The quarantine-worthy subset (spec Sec. 3's decision rule): >=1 of
    these is what actually gates a quarantine decision."""
    return [m for m in mismatches if m.tier in ("A", "B")]


def tier_c_mismatches(mismatches: list[Mismatch]) -> list[Mismatch]:
    """The report-only subset (spec Sec. 1's Tier C) -- NEVER used to gate a
    quarantine decision, carried only so a future adjudication has per-row
    evidence."""
    return [m for m in mismatches if m.tier == "C"]


def build_quarantine_record(recipe: Recipe, mismatches: list[Mismatch]) -> dict:
    """The quarantine-sidecar record shape for this check, used by both
    `scripts/quarantine_flagged_recipes.py --check instructions` and
    `CorpusImportPipeline`'s import-time check. Defensively filters to
    Tier A/B mismatches only (spec Sec. 3) even if a caller passes the full
    (all-tier) list `find_instructions_ingredient_mismatches` returns, so a
    Tier C-only report finding can never accidentally trigger a quarantine
    through this function."""
    quarantine_worthy = tier_ab_mismatches(mismatches)
    return {
        "recipe": recipe.model_dump(mode="json"),
        "quarantine_reason": {
            "check": "instructions_ingredient_integrity",
            "mismatches": [
                {
                    "category": m.category,
                    "tier": m.tier,
                    "matched_terms": m.matched_terms,
                    "evidence": m.evidence,
                }
                for m in quarantine_worthy
            ],
            "explanation": (
                "Instructions name a safety-relevant ingredient (allergen category, "
                "animal flesh, or undisclosed stock) absent from both the ingredient "
                "list and the derived allergens field -- the ingredient list is "
                "considered untrustworthy (may omit other facts too), not merely "
                "mislabeled, so it is quarantined rather than repaired."
            ),
        },
        "quarantined_at_utc": datetime.now(timezone.utc).isoformat(),
    }
