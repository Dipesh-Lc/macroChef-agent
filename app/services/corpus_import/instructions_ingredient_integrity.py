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
#
# Revision round 2 (2026-07-18 advisor ruling on the 231309Z HALT report,
# item 11): "crust", "pie shell", "crepe" added -- MISS 2 class from the
# miss spot-check (imp_15fe9cc27b96537b "Pumpkin-Pecan Pie": "Pour into the
# unbaked pie shell"; imp_3aee17154e8c59e9 "Apple Raisin Cobbler Pie":
# "Spoon into crust"; imp_d63bae35bb3a55bb "Austrian Sweet Cheese Crepes":
# "spread ... filling on each crepe" -- none of `crust`/`pie shell`/`crepe`
# was a trigger, a genuine undisclosed-wheat-carrier miss, same hazard
# class as the round-1 "pastry"/"bread" triggers). Bare `shell` is
# deliberately REJECTED (too polysemous -- "shellfish", "egg shell",
# "seashell" homograph risk with no cited real-corpus benefit).
#
# Revision round 3 (adjudication_20260718T090522Z.md diet_023, advisor-
# reviewed/APPROVED 2026-07-18): "cereal" added -- imp_2bd54fd475cf50fc
# "Butterscotch Chewy Bars" (quarantined via the manual-adjudication path,
# see data/processed/quarantined_recipes.jsonl) says "Remove from heat and
# immediately stir in cereals." with NO cereal row in its ingredient list;
# crisped-rice-style cereals routinely carry barley-malt flavoring and
# wheat-based bar cereals are common, so the cereal's undisclosed identity
# is a genuine gluten miss (spec Known-risk 1's residual-miss class, proven
# by a benchmark-serve adjudication rather than the spot-check). The `s?`
# trailing-morphology idiom in `_find_term_spans` covers "cereals" from this
# singular entry, same as every other term in this set. `cereal` is
# deliberately covered ONLY here (wheat_gluten) -- the advisor's supplementary,
# explicitly non-blocking suggestion to also trigger dairy (FARE lists
# cereals under milk) is a rejected-for-now candidate: the proven miss
# binding from diet_023 is gluten only, and adding an unproven trigger is
# out of this fix's scope.
WHEAT_GLUTEN_TERMS: frozenset[str] = frozenset(
    {
        "bread", "flour", "pasta", "spaghetti", "macaroni", "linguine",
        "fettuccine", "lasagna", "noodle", "wheat", "cracker", "biscuit",
        "tortilla", "pastry", "dumpling", "crouton", "couscous", "bulgur",
        "semolina", "phyllo", "filo", "pita", "bagel", "bran", "barley",
        "rye", "malt", "seitan", "breaded", "floured",
        "soy sauce",
        "crust", "pie shell", "crepe",
        "cereal",
    }
)
# Satisfier-only extras (spec Sec. 2): "dough" and "mix" (e.g. "cake mix"
# ingredient rows) are lenient completions of a wheat mention, never
# themselves triggers (too polysemous as triggers -- that generic-residue
# role is filled by the separate Tier C "dough"/"batter" categories below).
WHEAT_GLUTEN_SATISFIER_EXTRAS: frozenset[str] = frozenset({"dough", "mix"})

# Category-specific composite satisfiers for the NEW `crust`/`pie shell`
# triggers only (revision round 2, ruling item 11) -- deliberately NOT
# added to the general `WHEAT_GLUTEN_SATISFIER_EXTRAS` above (which would
# let a cookie-crumb or nut row silently satisfy an unrelated "bread"/
# "flour" mention elsewhere in the same recipe); wired instead through
# `_wheat_gluten_term_composite_satisfied` below, keyed on the SPECIFIC
# matched term, mirroring `_stock_composite_satisfied`'s per-category (here
# per-term) design.
#
# (a) both `crust` and `pie shell` are satisfied by any row naming a
# cookie/cracker-crumb-style base -- imp_fe5e997cb47c553c
# "Chocolate-Caramel-Pecan Cheesecake" lists "graham cracker crumbs" and
# says "Pour over graham cracker crust" (also independently satisfied via
# the pre-existing bare "cracker" satisfier, kept here as the documented,
# generalizable rule for crumb-crust bases without a literal "cracker" row).
_WHEAT_GLUTEN_CRUST_COOKIE_LIKE_SATISFIERS: frozenset[str] = frozenset(
    {"cookie", "wafer", "crumb", "graham", "oreo", "gingersnap", "pretzel"}
)
# (b) `crust` ONLY (not `pie shell`) is additionally satisfied by any
# TREE_NUT_TERMS or `coconut` row -- a nut/coconut press-in crust is a
# plausible composite of an already-listed nut/coconut row, live in
# imp_21d303d861785454 "Cocoa-Nut Meringue Cheesecake": "Combine coconut,
# pecans, and margarine, press onto bottom of 9-inch springform pan" /
# "...pour over crust" -- no flour, cracker, or cookie row at all, the
# crust IS the listed coconut+pecans. `pie shell` is excluded from this arm
# because a "pie shell" (unlike a press-in crumb crust) conventionally
# implies a pastry-dough shell, not a nut composite -- the pinned
# imp_15fe9cc27b96537b "Pumpkin-Pecan Pie" test asserts pecan rows must NOT
# satisfy its own "pie shell" mention.
_WHEAT_GLUTEN_CRUST_NUT_OR_COCONUT_SATISFIERS: frozenset[str] = TREE_NUT_TERMS | frozenset({"coconut"})

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

# Satisfier-only extras, shared by BOTH `soy` and `wheat_gluten` (revision
# round 2, 2026-07-18 ruling item 8): "ketjap manis"/"kecap manis"/
# "ketjap"/"kecap" -- imp_d287af8d742e5d44 "Katjang Sauce: Peanut Sauce"
# lists "ketjap manis" as an ingredient row, and its own NOTES-adjacent step
# says "*Ketjap manis is a sweet Indonesian soy sauce..." -- the "soy sauce"
# phrase there dual-fires wheat_gluten AND soy (per `_DUAL_CATEGORY_TERMS`),
# but the recipe's own "ketjap manis" row already IS that soy sauce; the
# satisfier gap (not a suppression gap -- the NOTES-prefix rule only clears
# the LEADING "NOTES :" step, not this separate, non-prefixed step) is what
# needs fixing, not the step's wording. Never a trigger (a recipe never
# implies a spice-glossary footnote just because it lists ketjap manis).
_KETJAP_SATISFIER_EXTRAS: frozenset[str] = frozenset(
    {"ketjap manis", "kecap manis", "ketjap", "kecap"}
)

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
# vocabulary didn't catch. Deliberately NOT adding bare "rib"/"ribs" here
# (too polysemous, e.g. "rib of celery") -- see `_MEAT_TRIGGER_ONLY_EXTRAS`
# below for round 2's narrower, guarded way of catching it.
# Revision round 3 (2026-07-19, A1 revise round): "bologna"/"bratwurst"/
# "sirloin" added to keep this set in sync with `constraint_engine.
# MEAT_ALIASES`'s own addition of the same three flesh words (diet-leak
# audit exposed by the A1 scraped-archive re-import; see that module's
# inline citations and docs/BACKLOG.md for the full per-term rationale).
# `test_meat_terms_are_superset_of_meat_alias_flesh_words` is the tripwire
# that caught the drift -- required, not optional.
MEAT_FLESH_TERMS: frozenset[str] = frozenset(
    {
        "bacon", "beef", "chicken", "chorizo", "duck", "goose", "ham",
        "hot dog", "lamb", "pancetta", "pepperoni", "pork", "prosciutto",
        "rabbit", "sausage", "steak", "turkey", "veal",
        "sparerib", "spare rib",
        "bologna", "bratwurst", "sirloin",
    }
)
# Satisfier-only extra (revision round 1, 2026-07-18 ruling): "roast"
# (`\broasts?\b`, deliberately NOT "roasted" -- the word-boundary regex
# already excludes it) -- imp_a52ae950e8dd5eb5 "Sauerbraten & Ginger" lists
# "rump roast" as its ingredient, and its instructions say "beef"/"meat"
# throughout; a roast IS a cut of animal flesh, so its own listed roast
# already satisfies the hidden meat mention.
MEAT_SATISFIER_EXTRAS: frozenset[str] = frozenset({"roast"})

# TRIGGER-ONLY extra, NOT in MEAT_FLESH_TERMS, NOT a satisfier (revision
# round 2, 2026-07-18 ruling item 10, MISS 1 from the miss spot-check):
# bare "rib" -- imp_635b6cd0fbd557ad "Hutspot" has a vegetarian-looking row
# set (carrots/onions/potatoes/water only) whose own instructions say "Add
# ribs, carrots and onions" -- the round-1 vocabulary deliberately omitted
# bare "rib"/"ribs" over the "rib of celery" homograph risk, but that risk
# is now handled by the guards below (preceding-token "celery" suppression,
# plus the exact-phrase "rib of celery"/"ribs of celery"/"seeds and ribs"
# suppressions) rather than by omitting the word outright. Kept OUT of
# MEAT_FLESH_TERMS itself (not just out of the satisfier set) specifically
# so it can never be picked up by `_ANIMAL_FLESH_OR_SEAFOOD_TERMS` below --
# imp_41bfceea6ba65b47 "Corn Chowder"'s own `-3 celery ribs` ingredient row
# must never count as "an animal row" for the Tier B stock composite arms.
_MEAT_TRIGGER_ONLY_EXTRAS: frozenset[str] = frozenset({"rib"})
# REJECTED (recorded, not implemented): bare "bones" -- redundant for
# Hutspot (rib already catches it) and over-triggers on the unrelated,
# harmless "Flake fish, discarding skin and bones" (imp_d3a91c593c3d55b2
# "Green and Gold Chowder", already a genuine fish miss via the "fish"
# trigger on its own, not a bones one).

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
        # Revision round 2 (ruling item 8): `_KETJAP_SATISFIER_EXTRAS` added
        # here (also added to `soy` below) -- see that constant's own
        # citation comment.
        "satisfiers": WHEAT_GLUTEN_TERMS | WHEAT_GLUTEN_SATISFIER_EXTRAS | _KETJAP_SATISFIER_EXTRAS,
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
        "satisfiers": SOY_TERMS | SOY_SATISFIER_EXTRAS | _KETJAP_SATISFIER_EXTRAS,
        "allergen_labels": frozenset({"soy", "soya"}),
    },
    "meat": {
        "tier": "A",
        # Lenient by design (spec Sec. 2): a row already containing ANY
        # animal-flesh OR fish/crustacean/mollusk term is already
        # non-vegetarian at serve time, so an additional hidden meat adds no
        # incremental engine-visible hazard -- only rows with NO
        # animal-flesh-or-seafood rows at all flag.
        #
        # Revision round 2 (ruling item 10): triggers also include
        # `_MEAT_TRIGGER_ONLY_EXTRAS` ("rib") -- trigger-only, deliberately
        # NOT added to the satisfier side (a "celery ribs" ingredient row
        # must never satisfy a hidden meat mention elsewhere in the same
        # recipe).
        "triggers": MEAT_FLESH_TERMS | _MEAT_TRIGGER_ONLY_EXTRAS,
        # Revision round 2 (ruling item 12): "worcestershire"/"puttanesca"
        # REMOVED from this category's satisfiers (previously included
        # wholesale via `FISH_TERMS`). Honest counter-argument, stated
        # rather than hidden: `constraint_engine.MEAT_ALIASES` already
        # carries "worcestershire" as its own condiment-hazard entry, so a
        # recipe listing a Worcestershire-sauce row is ALREADY blocked for
        # a vegetarian/fish-allergic user at serve time regardless of
        # whether this check also flags it -- removing it here does not
        # change what the constraint engine actually blocks. The reason to
        # remove it anyway is the quarantine's OWN stated purpose: an
        # ingredient-row set that omits its own dish's actual meat (the
        # "Filet Mignon without the filet" class, e.g.
        # imp_6f3463afcc2f5d51 "Pork Spareribs in Tangy Sauce," whose rows
        # are all condiments) is untrustworthy independent of whether the
        # ONE hidden hazard it names happens to be redundant with a
        # different already-listed hazard -- see
        # `tests/test_instructions_ingredient_integrity.py::
        # test_imp_6f3463afcc2f5d51_sparerib_trigger_now_flags_meat_after_
        # worcestershire_satisfier_removed` for the flipped pinned
        # regression, and the accepted residual FP this creates
        # (imp_712db6319e3957c7 "Apricot Basting Sauce": "Use sauce over
        # chicken, pork, and lamb" -- a legitimate serving-target mention
        # for a sauce recipe, not a hidden-meat claim about the sauce
        # itself; deliberately NOT patched with a `^use` rule, recorded as
        # an accepted residual instead per the ruling).
        "satisfiers": (
            MEAT_FLESH_TERMS
            | (FISH_TERMS - {"worcestershire", "puttanesca"})
            | CRUSTACEAN_TERMS
            | MOLLUSK_TERMS
            | MEAT_SATISFIER_EXTRAS
        ),
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
    # Revision round 2 (2026-07-18 ruling item 3): "if serving" --
    # imp_9b2c1d45a9f55ef1 "Alfredo Sauce": "(If serving with shrimp, you
    # might not need much salt.)" -- a conditional serving note about an
    # optional add-in, not a claim the sauce itself contains shrimp.
    "if serving",
)
_SERVING_CUE_PATTERNS = [re.compile(rf"\b{re.escape(phrase)}\b") for phrase in _SERVING_CUE_PHRASES]

# Commentary/attribution markers (revision round 1, 2026-07-18 ruling on the
# 220709Z HALT report; GENERALIZED in revision round 2, 2026-07-18 ruling
# item 1, on the 231309Z HALT report): a marker label -- a "Notes:"/"Tip:"/
# "Variation:" aside, a syndicated-column attribution, a garnish/serving-
# suggestion callout -- introduces commentary ABOUT the recipe, not a
# description of what this recipe itself contains.
#
# Round 1 anchored the marker to the STEP-INITIAL position only
# (`^\s*(?:...)\s*:`) and suppressed the WHOLE step on a match. Round 2
# generalizes this to the marker's EARLIEST occurrence ANYWHERE in the step
# (`_truncate_at_commentary_marker` below): only the text BEFORE the marker
# is evaluated for anything (terms, negation, serving cues); marker-to-end
# is dropped entirely. Round 1's step-initial cases still work identically
# under this rule (the prefix before a step-initial marker is empty, same
# net effect as the old whole-step suppression) -- the generalization is
# needed because a MID-step marker was proven to slip through the old
# anchor: imp_2380cadece955cc7 "Alfredo Sauce with Pasta": "Sprinkle with
# remaining cheese. Variation: Add cooked shrimp, crab or mushrooms." --
# the marker is the SECOND sentence of the step, not its start.
#
# The colon is still REQUIRED so a step that merely uses the word
# "note"/"tip" mid-sentence (not as a label) is untouched. Per-alternative
# citations (unchanged from round 1, still valid under the generalized
# anchor since all were step-initial to begin with):
#   notes                    -- imp_f26d5c5093e25ac7 "NOTES : Trassi is a..."
#   nb                       -- imp_3e5cbefd62c05ed8 "NB: if you like..."
#   tips                     -- imp_4b158d76b28e594d "TIPS: * if using..."
#   variations               -- imp_a7eb6f7b7e885e67 "Variation:  Top with...";
#                                imp_2380cadece955cc7 (round 2, MID-step)
#   column                   -- imp_ce64651a221b54d3 "Column: 'Sausages...'"
#   garnishing note          -- imp_bca827b64d08523e "Garnishing note: ..."
#   serving suggestions      -- imp_72746bdecd895fb1 / imp_c39c91fead915027
#   suggested accompaniments -- imp_6404a96a38aa5c12 "Suggested accompaniments:"
_COMMENTARY_PREFIX_PATTERN = re.compile(
    r"\b(?:nb|notes?|tips?|variations?|column|garnishing note|"
    r"serving suggestions?|suggested accompaniments?)\s*:",
    re.IGNORECASE,
)


def _truncate_at_commentary_marker(step_lower: str) -> str:
    """Revision round 2 (ruling item 1): returns the text BEFORE the
    earliest `_COMMENTARY_PREFIX_PATTERN` occurrence in the step (marker-
    to-end is dropped from ALL downstream evaluation -- terms, negation,
    serving cues, everything), or the step unchanged if no marker is
    present. See the pattern's own citation comment above for the full
    rationale and the mid-step case (imp_2380cadece955cc7) this generalizes
    for."""
    match = _COMMENTARY_PREFIX_PATTERN.search(step_lower)
    if not match:
        return step_lower
    return step_lower[: match.start()]


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
    # Revision round 2 (2026-07-18 ruling item 2): "can add"/"can be added"
    # -- imp_3233766015ca524d "Buttermilk Jalapeno Cornbread": "Can add
    # drained corn, bacon, ... etc. for a different taste" -- an optional,
    # user-initiated addition, not this recipe's own asserted content.
    "can add",
    "can be added",
)
_OPTIONAL_VARIATION_PATTERNS = [re.compile(rf"\b{phrase}\b") for phrase in _OPTIONAL_VARIATION_PHRASES]

# Whole-step suppressions anchored to the STEP'S OWN START (revision round
# 2, 2026-07-18 ruling items 4 and 5).
#
# Item 4: a step beginning with "serve" is a serving-vehicle/pairing
# description, not a content assertion -- imp_748b6422ecbb5c7d "Polish
# Sausage and Peppers": "Serve the sausage and peppers and onions on French
# bread." The existing serving-cue phrase list ("serve with"/"serve on"/...)
# requires an exact multi-word match and missed this (no "serve on" -- it's
# "serve ... on", with intervening words). Counter-example that must NOT be
# swept up by this same rule: imp_fbf6565762c0590d "Mabo Dofu": "Turn out
# into serving dish, sprinkle with the sesame oil and serve hot." -- "serve"
# is NOT step-initial there (the step starts with "Turn"), so this rule
# correctly leaves it alone and the sesame mention still flags.
_SERVE_INITIAL_PATTERN = re.compile(r"^\s*serve\b", re.IGNORECASE)

# Item 5: a step beginning with "dip" naming a dippable-food ALTERNATIVE
# list (not asserting this recipe contains all of them) is suppressed
# UNLESS the step also contains a bare "in"/"into" -- which signals a
# concrete usage ("dip X in Y") rather than a "here's what you could dip"
# list. Suppressed case: imp_e7fb53c18ced5dc0 "Beer Batter": "Dip fresh
# shrimp, mushrooms or veggies." (no "in"/"into" at all -- the batter's own
# rows are complete; the dippable is user-supplied, same class as "Fish
# Marinade"). Kept case: imp_a22b3c09a6b25bb5 "Crispy Baked Fish & Herbs":
# "Dip fish in egg white, then roll in crumbs." (contains "in" twice --
# this step asserts an actual action on THIS recipe's own fish, egg, and
# crumbs, so it must still flag "fish").
_DIP_INITIAL_PATTERN = re.compile(r"^\s*dip\b", re.IGNORECASE)
_CONTAINS_IN_WORD_PATTERN = re.compile(r"\bin(?:to)?\b")


def _step_has_serve_initial_suppression(step_lower: str) -> bool:
    return bool(_SERVE_INITIAL_PATTERN.search(step_lower))


def _step_has_dip_initial_suppression(step_lower: str) -> bool:
    return bool(_DIP_INITIAL_PATTERN.search(step_lower)) and not _CONTAINS_IN_WORD_PATTERN.search(step_lower)


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
# Revision round 2 (2026-07-18 ruling item 10): "rib" preceded by "celery"
# -- the ubiquitous ingredient-listing idiom "celery ribs"/"rib of celery"
# is a vegetable, not animal flesh; this guards any future INSTRUCTIONS-side
# occurrence of that idiom (imp_41bfceea6ba65b47 "Corn Chowder"'s own
# `-3 celery ribs` is an INGREDIENT row, never scanned as a trigger anyway,
# but this suppressor is the defense-in-depth for a step that phrases it
# the same way, e.g. "Add the celery ribs").
_RIB_PRECEDING_SUPPRESSORS: frozenset[str] = frozenset({"celery"})

_PRECEDING_TOKEN_SUPPRESSIONS: dict[str, frozenset[str]] = {
    "butter": _BUTTER_PRECEDING_SUPPRESSORS,
    "milk": _MILK_PRECEDING_SUPPRESSORS,
    "flour": _FLOUR_PRECEDING_SUPPRESSORS,
    "chestnut": _CHESTNUT_PRECEDING_SUPPRESSORS,
    "rib": _RIB_PRECEDING_SUPPRESSORS,
}

# Following-token suppressions (span-local, immediately-FOLLOWING word only
# -- the mirror image of the preceding-token table above; revision round 2,
# 2026-07-18 ruling item 11). Keyed by the exact trigger term text.
# "crust" followed by "the"/"each"/"both"/"it"/"them" is the VERB sense
# ("to crust [something] with...") not the noun (pastry base) sense --
# imp_06f98881ebf05a75 "Roasted Pork Loin with Bacon and Onion Spaetzle":
# "Remove from pan and crust the loin with cracked black pepper."
_CRUST_FOLLOWING_SUPPRESSORS: frozenset[str] = frozenset({"the", "each", "both", "it", "them"})

_FOLLOWING_TOKEN_SUPPRESSIONS: dict[str, frozenset[str]] = {
    "crust": _CRUST_FOLLOWING_SUPPRESSORS,
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
    # Revision round 2 (2026-07-18 ruling item 7): "cheese cloth"/
    # "cheese-cloth" (the fabric, cheesecloth) is not dairy -- both
    # spellings suppress "cheese" only. Live in imp_13e739367b505085
    # "Spiced Pear Butter": "Tie broken cinnamon spices, gingerroot,
    # allspice and cloves in a piece of cheese cloth" (a recipe with zero
    # dairy ingredients or content otherwise).
    "cheese cloth": "cheese",
    "cheese-cloth": "cheese",
    # Revision round 2 (2026-07-18 ruling item 10): "rib of celery"/
    # "ribs of celery" (reversed word order from the ingredient-listing
    # idiom) and "seeds and ribs" (a tomato/pepper's internal membrane, not
    # animal flesh) -- live in imp_0ea6e8bb1fd85633 "Pickled Tomato
    # Parcels": "With a melon baller remove seeds and ribs, leaving outer
    # wall intact."
    "rib of celery": "rib",
    "ribs of celery": "rib",
    "seeds and ribs": "rib",
    # Revision round 2 (2026-07-18 ruling item 11): "crepe pan" (the
    # utensil/pan shape) is not a "crepe" ingredient-carrier mention --
    # live in imp_968a7fa664885493 "Emerald Fried Rice": "Heat 1 tablespoon
    # of oil in a frying-pan or crepe pan." (a recipe with no crepe/flour
    # content at all -- an omelette-style fried rice).
    "crepe pan": "crepe",
    # Revision round 3 follow-up (2026-07-18, orchestrator sample check of
    # the 20260718T113546Z report's round-3 5-case list; same utensil/
    # serving-vessel class as "stock pot" above): "cereal bowl" is the
    # SERVING CONTAINER for an already-listed dish, not a second,
    # undisclosed cereal ingredient -- live in imp_9fb0ca4a0fa65c48 "Low-Fat
    # Swiss Muesli": "spoon some of the muesli into a cereal bowl." This
    # recipe's own dish IS the muesli (its "rolled oats" ingredient row is
    # already present and already satisfies wheat_gluten independently);
    # "a cereal bowl" here is the dish's serving vehicle, structurally
    # identical to "stock pot" the utensil vs. "stock" the ingredient.
    # Orchestrator-adjudicated FALSE_POSITIVE 2026-07-18.
    "cereal bowl": "cereal",
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


def _following_word(text: str, end: int) -> str:
    """The alphabetic word immediately following index `end` in `text`
    (mirror of `_preceding_word` above, revision round 2 ruling item 11),
    or "" if the span is at the end of the step or followed by
    punctuation/digits."""
    after = text[end:]
    match = re.match(r"[\s-]*([a-z]+)", after)
    return match.group(1) if match else ""


def _is_following_token_suppressed(step_lower: str, span: tuple[int, int], term: str) -> bool:
    suppressors = _FOLLOWING_TOKEN_SUPPRESSIONS.get(term)
    if not suppressors:
        return False
    return _following_word(step_lower, span[1]) in suppressors


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

    # Whole-step suppressions anchored to the step's OWN START (revision
    # round 2 ruling items 4 and 5) -- checked against the ORIGINAL,
    # untruncated step text, since both anchors care only about how the
    # step itself begins, never about text after a later commentary marker.
    if _step_has_serve_initial_suppression(step_lower) or _step_has_dip_initial_suppression(step_lower):
        return {}

    # Revision round 2 (ruling item 1): truncate at the earliest commentary
    # marker anywhere in the step (generalized from round 1's step-initial-
    # only anchor) -- see `_truncate_at_commentary_marker`'s own docstring.
    # EVERYTHING downstream (the remaining whole-step suppressions, and all
    # term scanning) operates on this truncated, scoped text only; the
    # marker-to-end text is not evaluated for anything.
    scoped_lower = _truncate_at_commentary_marker(step_lower)

    # Step-wide suppressions (spec Sec. 2, plus revision round 1's two
    # whole-step classes, 2026-07-18 ruling): negation, serving/intended-use
    # cues, and an optional-variation/cross-reference phrase each suppress
    # the ENTIRE (scoped) step's matches, not a specific term.
    if (
        _step_has_generic_negation(scoped_lower)
        or _step_has_serving_cue(scoped_lower)
        or _step_has_optional_variation(scoped_lower)
    ):
        return {}

    all_terms: list[tuple[str, str]] = [
        (term, category) for category, spec in CATEGORIES.items() for term in spec["triggers"]
    ]
    all_terms.sort(key=lambda pair: len(pair[0]), reverse=True)

    phrase_spans = _phrase_suppression_spans(scoped_lower)
    consumed: list[tuple[int, int]] = []
    hits: dict[str, list[str]] = {}

    for term, category in all_terms:
        for span in _find_term_spans(scoped_lower, term):
            if _overlaps(span, consumed):
                continue
            if _term_negated_specific(scoped_lower, term):
                continue
            if _is_phrase_suppressed(span, term, phrase_spans):
                continue
            if _is_preceding_token_suppressed(scoped_lower, span, term):
                continue
            if _is_following_token_suppressed(scoped_lower, span, term):
                continue
            consumed.append(span)
            hits.setdefault(category, []).append(term)
            extra_category = _DUAL_CATEGORY_TERMS.get((category, term))
            if extra_category:
                hits.setdefault(extra_category, []).append(term)

    return hits


def _ingredient_text_matches(term: str, ingredient_text_lower: str) -> bool:
    return bool(re.search(rf"\b{re.escape(term)}s?\b", ingredient_text_lower))


# Shared union (extracted in revision round 2 so the pre-existing arm 2
# above and the NEW arm 3 evidence filter below can't silently drift apart
# on what counts as "an animal row" -- deliberately excludes the round-2
# `_MEAT_TRIGGER_ONLY_EXTRAS` ("rib"): a "celery ribs" ingredient row must
# never count as an animal row for either arm, per ruling item 10).
_ANIMAL_FLESH_OR_SEAFOOD_TERMS: frozenset[str] = MEAT_FLESH_TERMS | FISH_TERMS | CRUSTACEAN_TERMS | MOLLUSK_TERMS


def _has_animal_flesh_or_seafood_row(ingredient_text_lower: str) -> bool:
    return any(_ingredient_text_matches(term, ingredient_text_lower) for term in _ANIMAL_FLESH_OR_SEAFOOD_TERMS)


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
    stock/broth/bouillon check, which is unchanged and still flags them.

    See `_stock_pot_liquor_filtered_pairs` below for arm 3 (revision round
    2, ruling item 9), which is NOT a satisfier (does not belong in this
    function) -- it is an occurrence-level evidence filter applied
    separately in `find_instructions_ingredient_mismatches`."""
    if any(_ingredient_text_matches(term, ingredient_text_lower) for term in MOLLUSK_TERMS):
        return True
    if not re.search(r"\bwaters?\b", ingredient_text_lower):
        return False
    return _has_animal_flesh_or_seafood_row(ingredient_text_lower)


# Tier B arm 3: pot-liquor evidence filter (revision round 2, 2026-07-18
# ruling item 9, on the 231309Z HALT report's FP class (viii)): arm 2 above
# requires a LISTED `water` row, but "water" is a commonly-unlisted item
# (spec Sec. 2's own exclusion) -- so a recipe that simmers a LISTED animal
# ingredient in its own rendered juices (no separate water row at all) was
# falling through arm 2 and flagging as if the broth were purchased/hidden.
# imp_a76aa35639d85deb "Borscht II": "keeping the broth at a simmer" is the
# pot liquor from the recipe's own LISTED "beef stew meat" -- no water row,
# no purchased stock.
#
# This is deliberately NOT a `_category_satisfied` satisfier (it does not
# clear the WHOLE stock category the way arms 1/2 do) -- it is a per-
# OCCURRENCE evidence filter: when the recipe has >=1 animal row (flesh,
# fish, crustacean, or mollusk; a `water` row is explicitly NOT required,
# unlike arm 2), a stock/broth/bouillon OCCURRENCE only counts as evidence
# of a HIDDEN stock if its own step has an addition verb (the mention
# describes putting something INTO the pot, i.e. a purchased/prepared
# addition) or a purchased-stock word. An occurrence with neither is
# presumed to be the recipe's own pot liquor and is dropped; if ALL
# occurrences for a recipe's stock mismatch are dropped this way, the whole
# mismatch is dropped. Arms 1 and 2 are completely unchanged.
_STOCK_ADDITION_VERB_PATTERN = re.compile(
    r"\badd(?:s|ed|ing)?\b"
    r"|\bstir(?:red|ring)?\s+in(?:to)?\b"
    r"|\bpour(?:ed|ing)?\s+in(?:to)?\b"
    r"|\bmix(?:ed|ing)?\s+in\b"
    r"|\bwhisk(?:ed|ing)?\s+in\b"
)
_STOCK_PURCHASED_WORD_PATTERN = re.compile(
    r"\b(?:instant|canned|can of|cubes?|granules?|base|powders?|powdered|"
    r"packets?|envelopes?|cartons?|store-bought|boxed)\b"
)


def _stock_occurrence_survives_pot_liquor_filter(step_lower: str) -> bool:
    return bool(_STOCK_ADDITION_VERB_PATTERN.search(step_lower) or _STOCK_PURCHASED_WORD_PATTERN.search(step_lower))


def _stock_pot_liquor_filtered_pairs(
    hit_pairs: list[tuple[str, str]], ingredient_text_lower: str
) -> list[tuple[str, str]]:
    """Arm 3 (see `_STOCK_ADDITION_VERB_PATTERN`'s citation comment above).
    Only applies when the recipe has >=1 animal row; otherwise `hit_pairs`
    is returned unchanged (arm 3 inapplicable -- pinned by
    imp_00efafa3c86e5b9e "Beef Stroganoff with Dill", which has no animal
    ingredient row at all and must still flag `stock` on the unfiltered
    literal check)."""
    if not _has_animal_flesh_or_seafood_row(ingredient_text_lower):
        return hit_pairs
    return [(term, step) for term, step in hit_pairs if _stock_occurrence_survives_pot_liquor_filter(step.lower())]


# wheat_gluten `crust`/`pie shell` category-specific composite satisfiers
# (revision round 2, ruling item 11) -- see the two constants'
# `_WHEAT_GLUTEN_CRUST_COOKIE_LIKE_SATISFIERS` /
# `_WHEAT_GLUTEN_CRUST_NUT_OR_COCONUT_SATISFIERS` definitions above (with
# `WHEAT_GLUTEN_TERMS`) for the full citations. This is an occurrence-level
# evidence filter, exactly like arm 3 above, NOT a `_category_satisfied`
# satisfier -- it applies per matched TERM, not per category, so a `crepe`
# occurrence in the same category is never affected by it.
def _wheat_gluten_term_composite_satisfied(term: str, ingredient_text_lower: str) -> bool:
    if term not in ("crust", "pie shell"):
        return False
    if any(_ingredient_text_matches(t, ingredient_text_lower) for t in _WHEAT_GLUTEN_CRUST_COOKIE_LIKE_SATISFIERS):
        return True
    if term == "crust" and any(
        _ingredient_text_matches(t, ingredient_text_lower) for t in _WHEAT_GLUTEN_CRUST_NUT_OR_COCONUT_SATISFIERS
    ):
        return True
    return False


def _wheat_gluten_crust_filtered_pairs(
    hit_pairs: list[tuple[str, str]], ingredient_text_lower: str
) -> list[tuple[str, str]]:
    return [
        (term, step)
        for term, step in hit_pairs
        if not _wheat_gluten_term_composite_satisfied(term, ingredient_text_lower)
    ]


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

        # Occurrence-level evidence filters (revision round 2, ruling items
        # 9 and 11): these operate AFTER the whole-category satisfier check
        # above fails, and can shrink `hit_pairs` -- possibly to empty, in
        # which case the whole mismatch is dropped, not just narrowed.
        if category == "stock":
            hit_pairs = _stock_pot_liquor_filtered_pairs(hit_pairs, ingredient_text_lower)
        elif category == "wheat_gluten":
            hit_pairs = _wheat_gluten_crust_filtered_pairs(hit_pairs, ingredient_text_lower)
        if not hit_pairs:
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
