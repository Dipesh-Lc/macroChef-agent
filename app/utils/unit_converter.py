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
    # --- additive literal keys for corpus-observed comma'd forms whose
    # handling word ("packed"/"grated") is NOT a _HANDLING_WORDS entry (see
    # that set's module comment for why "grated"/"packed"/"beaten" must never
    # be stripped generically) but which DO already have a same-density base
    # entry above. Added per the grounding-coverage-common-staples fix
    # (advisor-reviewed), mirroring the "cooked white rice" natural-word-
    # order-key precedent -- same citation as the base entry, just an
    # additional exact-match key for the literal corpus string. ---
    "brown sugar, packed": 0.90,  # same King Arthur "brown sugar" 213 g/cup citation as the base entry above
    "parmesan cheese, grated": 0.42,  # same USDA FDC "grated parmesan cheese" 100 g/cup citation as the base entry above
    # --- added for the grounding-coverage-common-staples fix; common
    # tsp/tbsp-measured pantry spices, previously missing a density entry
    # entirely (so a real, correctly-unit-tagged corpus row like "1 tsp
    # cinnamon" still couldn't ground even after Fix 1/Fix 2). Every value
    # below is `foodPortions` "1 tsp" gram weight (live FDC food/{fdcId}
    # lookup) / 4.92892 (this module's 1-tsp-in-mL constant, from
    # quantity_parser.VOLUME_TO_ML) -- same derivation style as the existing
    # "maple syrup" entry above. No estimated/guessed values. ---
    "salt": 1.22,  # USDA FDC "Salt, table" (fdcId 173468): 1 tsp = 6.0 g -> 6.0/4.92892 ml
    "black pepper": 0.47,  # USDA FDC "Spices, pepper, black" (fdcId 170931): 1 tsp, ground = 2.3 g -> 2.3/4.92892 ml
    "cinnamon": 0.53,  # USDA FDC "Spices, cinnamon, ground" (fdcId 171320): 1 tsp = 2.6 g -> 2.6/4.92892 ml
    "baking powder": 1.01,  # USDA FDC "Leavening agents, baking powder, low-sodium" (fdcId 172805): 1 tsp = 5.0 g -> 5.0/4.92892 ml
    "baking soda": 0.93,  # USDA FDC "Leavening agents, baking soda" (fdcId 175040): 1 tsp = 4.6 g -> 4.6/4.92892 ml
    "nutmeg": 0.45,  # USDA FDC "Spices, nutmeg, ground" (fdcId 171326): 1 tsp = 2.2 g -> 2.2/4.92892 ml
    "paprika": 0.47,  # USDA FDC "Spices, paprika" (fdcId 171329): 1 tsp = 2.3 g -> 2.3/4.92892 ml
    "garlic powder": 0.63,  # USDA FDC "Spices, garlic powder" (fdcId 171325): 1 tsp = 3.1 g -> 3.1/4.92892 ml
    "oregano": 0.20,  # USDA FDC "Spices, oregano, dried" (fdcId 171328): 1 tsp, leaves = 1.0 g -> 1.0/4.92892 ml
    "dry mustard": 0.41,  # USDA FDC "Spices, mustard seed, ground" (fdcId 170929): 1 tsp = 2.0 g -> 2.0/4.92892 ml
    "bay leaf": 0.12,  # USDA FDC "Spices, bay leaf" (fdcId 170917): 1 tsp, crumbled = 0.6 g -> 0.6/4.92892 ml
    # additive literal key: "ground" is deliberately NOT a _HANDLING_WORDS
    # entry (it's a physical-form word -- whole vs. ground spices genuinely
    # differ), so Fix 1's comma-stripping alone leaves "cinnamon, ground" as
    # "cinnamon ground", which doesn't exact-match the "cinnamon" entry
    # above. This corpus string is high-volume (116 occurrences per
    # data/processed/grounding_report.md's top-50 table) and IS the same
    # ground form the "cinnamon" entry above already cites, so it gets its
    # own exact-match key with the same citation, mirroring the "cooked
    # white rice" / eggs-brown-sugar-parmesan additive-key precedent rather
    # than generalizing word-stripping further.
    "cinnamon, ground": 0.53,  # same USDA FDC "Spices, cinnamon, ground" (fdcId 171320) citation as the "cinnamon" entry above
    # --- added 2026-07-27 (grams-computable coverage pass): re-measured the
    # corpus fresh with `scripts/measure_grams_computable.py` and re-derived
    # the top-frequency missing-ingredient list from the current corpus state
    # (not reused from any earlier list). Every entry below is a citable
    # reference value (USDA FoodData Central household-measure weight or a
    # King Arthur Baking ingredient-weight-chart figure) drawn from
    # consistently-repeated, standard reference figures -- this session had
    # no live web/database access, so these are NOT fresh fdcId lookups like
    # the pantry-spice batch above; each is a specific, named, commonly-cited
    # standard reference value, not an invented number. See the task report
    # for the explicit list of high-frequency ingredients that were skipped
    # because no such citable figure could be recalled with confidence --
    # cite-or-omit is not weakened for coverage's sake.
    "onion": 0.68,  # USDA FoodData Central: Onions, raw, chopped, 1 cup = 160 g (volume/cup-measured onion; the separate whole-onion PIECE weight below is a different table/use case, no conflict)
    "celery": 0.43,  # USDA FoodData Central: Celery, raw, chopped, 1 cup = 101 g
    "garlic": 0.61,  # USDA FoodData Central: Garlic, raw, chopped, 1 tbsp = 9 g (volume/tbsp-measured minced garlic; the separate per-clove PIECE weight below is a different table/use case, no conflict)
    "green pepper": 0.63,  # USDA FoodData Central: Peppers, sweet, green, raw, chopped, 1 cup = 149 g
    "green bell pepper": 0.63,  # same citation as "green pepper" above, natural-word-order alternate phrasing
    "mushroom": 0.30,  # USDA FoodData Central: Mushrooms, white, raw, pieces or slices, 1 cup = 70 g
    "mushrooms": 0.30,  # same citation as "mushroom" above, plural literal key (comma-attached-handling-word forms like "mushrooms, sliced" only reach this key via the raw/stripped tiers, not the legacy plural-fallback, which fails for this word)
    "fresh mushrooms": 0.30,  # same citation as "mushroom" above
    "vanilla extract": 0.85,  # USDA FoodData Central: Vanilla extract, 1 tsp = 4.2 g -> 4.2/4.92892 ml
    "vanilla": 0.85,  # same "vanilla extract" citation -- bare "vanilla" in a recipe overwhelmingly means vanilla extract, not vanilla bean
    "lemon juice": 1.03,  # USDA FoodData Central: Lemon juice, raw, 1 cup = 244 g
    "fresh lemon juice": 1.03,  # same "lemon juice" citation, natural-word-order alternate phrasing
    "lime juice": 1.04,  # USDA FoodData Central: Lime juice, raw, 1 cup = 246 g
    "fresh lime juice": 1.04,  # same "lime juice" citation, natural-word-order alternate phrasing
    "orange juice": 1.05,  # USDA FoodData Central: Orange juice, raw, 1 cup = 248 g
    "fresh orange juice": 1.05,  # same "orange juice" citation, natural-word-order alternate phrasing
    "pineapple juice": 1.06,  # USDA FoodData Central: Pineapple juice, canned, 1 cup = 250 g
    "margarine": 0.96,  # USDA FoodData Central / King Arthur: 1 cup margarine = 227 g (same cup-weight convention already used for the "butter" entry above)
    "mayonnaise": 0.95,  # USDA FoodData Central: Mayonnaise, 1 tbsp = 14 g
    "ketchup": 1.15,  # USDA FoodData Central: Catsup, 1 tbsp = 17 g
    "catsup": 1.15,  # same "ketchup" citation, alternate spelling
    "molasses": 1.39,  # USDA FoodData Central: Molasses, 1 cup = 328 g
    "half-and-half": 1.02,  # USDA FoodData Central: Half and half cream, 1 cup = 242 g
    "evaporated milk": 1.06,  # USDA FoodData Central: Milk, canned, evaporated, 1 cup = 252 g
    "cottage cheese": 0.96,  # USDA FoodData Central: Cheese, cottage, 1 cup = 226 g
    "buttermilk": 1.04,  # USDA FoodData Central: Buttermilk, cultured, 1 cup = 245 g
    "skim milk": 1.03,  # same "milk" citation above -- fat content difference doesn't meaningfully change density at this precision
    "whole milk": 1.03,  # same "milk" citation above, explicit-fat-level alternate phrasing
    "plain yogurt": 1.03,  # same "yogurt" citation above, natural-word-order alternate phrasing
    "graham cracker crumbs": 0.36,  # King Arthur ingredient weight chart: 1 cup graham cracker crumbs = 84 g
    "pecans": 0.42,  # King Arthur ingredient weight chart: 1 cup chopped pecans = 99 g
    "pecan": 0.42,  # same "pecans" citation, singular
    "walnuts": 0.51,  # King Arthur ingredient weight chart: 1 cup chopped walnuts = 120 g
    "walnut": 0.51,  # same "walnuts" citation, singular
    "almonds": 0.60,  # King Arthur ingredient weight chart: 1 cup whole almonds = 143 g
    "almond": 0.60,  # same "almonds" citation, singular
    "slivered almonds": 0.46,  # King Arthur ingredient weight chart: 1 cup slivered almonds = 108 g (distinct physical form/packing density from whole almonds above -- own citation, not an alias)
    "coconut": 0.39,  # King Arthur ingredient weight chart: 1 cup shredded coconut = 93 g
    "raisins": 0.70,  # King Arthur ingredient weight chart: 1 cup raisins = 165 g
    "raisin": 0.70,  # same "raisins" citation, singular
    "sesame seeds": 0.61,  # USDA FoodData Central: Sesame seeds, whole, 1 tbsp = 9 g
    "sesame seed": 0.61,  # same "sesame seeds" citation, singular
    "cornmeal": 0.58,  # King Arthur ingredient weight chart: 1 cup cornmeal = 138 g
    "corn syrup": 1.39,  # USDA FoodData Central: Corn syrup, light, 1 cup = 328 g
    "light corn syrup": 1.39,  # same "corn syrup" citation, explicit-grade alternate phrasing
    "applesauce": 1.03,  # USDA FoodData Central: Applesauce, unsweetened, 1 cup = 244 g
    "chocolate chips": 0.71,  # USDA FoodData Central: Chocolate chips, semisweet, 1 cup = 168 g
    "semi-sweet chocolate chips": 0.71,  # same "chocolate chips" citation, explicit-grade alternate phrasing
    "cream of tartar": 0.61,  # USDA FoodData Central: Cream of tartar, 1 tsp = 3 g
    "onion powder": 0.49,  # USDA FoodData Central: Spices, onion powder, 1 tsp = 2.4 g
    "shortening": 0.87,  # USDA FoodData Central / King Arthur: 1 cup vegetable shortening = 205 g
    "vegetable shortening": 0.87,  # same "shortening" citation, natural-word-order alternate phrasing
    "ground ginger": 0.37,  # USDA FoodData Central: Spices, ginger, ground, 1 tsp = 1.8 g
    "ginger": 0.37,  # same "ground ginger" citation -- a volume-measured (tsp/tbsp) bare "ginger" row means the ground spice, not fresh root (fresh root is unit/piece-measured, not volume)
    "ginger, ground": 0.37,  # same "ground ginger" citation, literal comma-form
    "ground cumin": 0.43,  # USDA FoodData Central: Spices, cumin seed, ground, 1 tsp = 2.1 g
    "cumin": 0.43,  # same "ground cumin" citation -- a volume-measured bare "cumin" row means the ground spice
    "cumin, ground": 0.43,  # same "ground cumin" citation, literal comma-form
    "turmeric": 0.45,  # USDA FoodData Central: Spices, turmeric, ground, 1 tsp = 2.2 g
    "turmeric powder": 0.45,  # same "turmeric" citation, explicit-form alternate phrasing
    "ground cloves": 0.43,  # USDA FoodData Central: Spices, cloves, ground, 1 tsp = 2.1 g
    "clove, ground": 0.43,  # same "ground cloves" citation, literal comma-form
    "clove": 0.43,  # same "ground cloves" citation -- ONLY reached for a volume-dimensioned row (e.g. "1 tsp clove"); a garlic clove is quantified via the separate "clove" COUNT UNIT token and the "garlic" piece-weight entry below, a different lookup path entirely, so no collision
    "ground coriander": 0.41,  # USDA FoodData Central: Spices, coriander seed, ground, 1 tsp = 2.0 g
    "cayenne pepper": 0.37,  # USDA FoodData Central: Spices, pepper, red or cayenne, 1 tsp = 1.8 g
    "cayenne": 0.37,  # same "cayenne pepper" citation
    "white pepper": 0.49,  # USDA FoodData Central: Spices, pepper, white, 1 tsp = 2.4 g
    "ground black pepper": 0.47,  # same "black pepper" citation above, explicit-form alternate phrasing
    "fresh ground black pepper": 0.47,  # same "black pepper" citation above
    "mustard": 1.01,  # USDA FoodData Central: Mustard, prepared, yellow, 1 tbsp = 15 g
    "prepared mustard": 1.01,  # same "mustard" citation above, explicit-form alternate phrasing
    "dijon mustard": 1.01,  # same "mustard" citation above -- Dijon is a prepared-mustard variety of essentially the same density
    "shredded cheddar cheese": 0.48,  # USDA FoodData Central: Cheese, cheddar, shredded, 1 cup = 113 g
    "cheddar cheese, shredded": 0.48,  # same citation, literal comma-order corpus variant
    "cheddar cheese, grated": 0.48,  # same citation, literal comma-order corpus variant
    "parmesan cheese": 0.42,  # same "grated parmesan cheese" citation above -- parmesan measured by the cup is conventionally the grated form
    "dried oregano": 0.20,  # same "oregano" citation above, explicit-form alternate phrasing
    "unsalted butter": 0.96,  # same "butter" citation above -- salt content doesn't meaningfully change density
    "light brown sugar": 0.90,  # same "brown sugar" citation above -- light and dark brown sugar have essentially the same packed density
    "packed brown sugar": 0.90,  # same "brown sugar" citation above, word-order literal corpus variant
    "brown sugar, firmly packed": 0.90,  # same "brown sugar" citation above, literal comma-form corpus variant
    "firmly packed brown sugar": 0.90,  # same "brown sugar" citation above, word-order literal corpus variant
    "brown sugar firmly packed": 0.90,  # same "brown sugar" citation above, word-order literal corpus variant
    "granulated sugar": 0.85,  # same "sugar" citation above, explicit-grade alternate phrasing
    "white sugar": 0.85,  # same "sugar" citation above, explicit-color alternate phrasing
    "confectioners' sugar": 0.48,  # same "powdered sugar" citation above -- "confectioners' sugar" IS powdered sugar, just a different regional name
    "icing sugar": 0.48,  # same "powdered sugar" citation above -- British-English name for the same product
    "cocoa": 0.36,  # same "cocoa powder" citation above -- bare "cocoa" in a recipe means cocoa powder
    "unsweetened cocoa": 0.36,  # same "cocoa powder" citation above
    "unsweetened cocoa powder": 0.36,  # same "cocoa powder" citation above, literal fully-qualified corpus variant
    "ground cinnamon": 0.53,  # same "cinnamon" citation above, explicit-form alternate phrasing
    "all-purpose flour": 0.53,  # same "flour" citation above -- "flour" already means all-purpose/spooned per that entry's own citation
    "all purpose flour": 0.53,  # same "flour" citation above, no-hyphen literal corpus variant
    "unbleached flour": 0.53,  # same "flour" citation above -- unbleached vs. bleached AP flour has no meaningful density difference
    "unbleached all-purpose flour": 0.53,  # same "flour" citation above
    "plain flour": 0.53,  # same "flour" citation above -- "plain flour" is the British-English name for all-purpose flour
    "cornflour": 0.54,  # same "cornstarch" citation above -- "cornflour" is the British-English name for cornstarch (NOT to be confused with "corn flour", a different, more coarsely-milled US product; this corpus's "cornflour" spelling is the single-word British form)
    "rolled oats": 0.38,  # same "oats" citation above, explicit-form alternate phrasing
    "dry breadcrumbs": 0.46,  # same "breadcrumbs" citation above, explicit-form alternate phrasing
    "light soy sauce": 1.10,  # same "soy sauce" citation above -- "light" here denotes color/style, not a materially different density
    "water, cold": 1.00,  # same "water" citation above, literal comma-form corpus variant (serving temperature doesn't change density at recipe precision)
    "cold water": 1.00,  # same "water" citation above, word-order literal corpus variant
    "boiling water": 1.00,  # same "water" citation above, word-order literal corpus variant
    "hot water": 1.00,  # same "water" citation above, word-order literal corpus variant
    "water hot": 1.00,  # same "water" citation above, stripped-key literal corpus variant
    "water cold": 1.00,  # same "water" citation above, stripped-key literal corpus variant
    "chicken broth": 1.01,  # USDA FoodData Central: Soup, stock, chicken, 1 cup ~= 240 g -- broths/stocks are >95% water by mass, density within ~1% of water across chicken/beef/vegetable variants
    "chicken stock": 1.01,  # same "chicken broth" citation above, alternate naming (broth/stock used interchangeably in recipes)
    "beef broth": 1.01,  # same citation basis as "chicken broth" above (USDA FDC beef stock/broth cup weight is likewise ~240 g)
    "beef stock": 1.01,  # same "beef broth" citation above, alternate naming
    "vegetable stock": 1.01,  # same citation basis as "chicken broth" above (USDA FDC vegetable stock/broth cup weight is likewise ~240 g)
    "vinegar": 1.01,  # USDA FoodData Central: Vinegar, cider, 1 cup = 239 g -- vinegars cluster tightly near this density (>94% water + dilute acetic acid) across the common culinary types below
    "cider vinegar": 1.01,  # same "vinegar" citation above
    "white vinegar": 1.01,  # same "vinegar" citation above
    "apple cider vinegar": 1.01,  # same "vinegar" citation above, fully-qualified alternate phrasing
    "rice vinegar": 1.01,  # same "vinegar" citation above
    "white wine vinegar": 1.01,  # same "vinegar" citation above
    "red wine vinegar": 1.01,  # same "vinegar" citation above
    "butter or 1/2 cup margarine": 0.96,  # corpus parsing artifact ("N butter or margarine" recipe lines) -- safe regardless of which ingredient was meant, since butter and margarine share the same 0.96 citation in this table
    "butter or 1/4 cup margarine": 0.96,  # same rationale as "butter or 1/2 cup margarine" above
    "butter or 1 cup margarine": 0.96,  # same rationale as "butter or 1/2 cup margarine" above
    "butter or 1 tablespoon margarine": 0.96,  # same rationale as "butter or 1/2 cup margarine" above
    "butter or 2 tablespoons margarine": 0.96,  # same rationale as "butter or 1/2 cup margarine" above
    "butter or 3 tablespoons margarine": 0.96,  # same rationale as "butter or 1/2 cup margarine" above
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
    # --- additive literal keys for corpus-observed comma'd forms whose
    # handling word ("beaten") is NOT a _HANDLING_WORDS entry but which
    # already have a same-weight base entry ("egg") above. See the matching
    # comment in _DENSITY_G_PER_ML for the full rationale. ---
    "egg, beaten": 50.0,  # same "egg" 50 g/piece citation as the base entry above
    "eggs, beaten": 50.0,  # same "egg" 50 g/piece citation as the base entry above
    # --- added 2026-07-27 (grams-computable coverage pass). Same discipline
    # as the _DENSITY_G_PER_ML additions above: every entry cites a specific,
    # commonly-repeated standard reference figure (USDA FoodData Central
    # household-measure weight), added without live web/database access this
    # session -- see that block's comment and the task report for the full
    # rationale and the skipped-ingredient list. ---
    "egg white": 33.0,  # USDA FoodData Central: Egg, white, raw, fresh, 1 large = 33 g
    "egg whites": 33.0,  # same "egg white" citation, plural
    "large egg white": 33.0,  # same "egg white" citation, explicit-size alternate phrasing
    "large egg whites": 33.0,  # same "egg white" citation, explicit-size plural
    "egg yolk": 17.0,  # USDA FoodData Central: Egg, yolk, raw, fresh, 1 large = 17 g
    "egg yolks": 17.0,  # same "egg yolk" citation, plural
    "large egg yolk": 17.0,  # same "egg yolk" citation, explicit-size alternate phrasing
    "large egg yolks": 17.0,  # same "egg yolk" citation, explicit-size plural
    "orange": 131.0,  # USDA FoodData Central: Orange, raw, 1 medium (2-5/8" dia) = 131 g
    "oranges": 131.0,  # same "orange" citation, plural
    "mushroom": 18.0,  # USDA FoodData Central: Mushrooms, white, raw, 1 whole (2-1/2" dia) = 18 g (this is the PIECE-count table; the separate volume/cup density entry above is a different table/use case, no conflict)
    "mushrooms": 18.0,  # same "mushroom" citation, plural
    "chicken breast": 172.0,  # USDA FoodData Central: Chicken, broilers or fryers, breast, meat only, raw, 1 breast half (bone and skin removed) = 172 g
    "chicken breasts": 172.0,  # same "chicken breast" citation, plural
    "boneless skinless chicken breast": 172.0,  # same "chicken breast" citation, fully-qualified alternate phrasing
    "boneless skinless chicken breasts": 172.0,  # same "chicken breast" citation, fully-qualified plural
    "boneless skinless chicken breast half": 172.0,  # same "chicken breast" citation, fully-qualified alternate phrasing
    "boneless skinless chicken breast halves": 172.0,  # same "chicken breast" citation, fully-qualified plural
    # --- plural-form literal keys for already-cited whole-item entries above.
    # normalize_ingredient()'s plural-stripping + fuzzy-match legacy fallback
    # (tier 3 of _normalize_for_density_lookup) resolves most simple plurals
    # (e.g. "tomatoes" -> "tomato", "onions" -> "onion") already, but ONLY
    # when there's no trailing comma-attached handling word -- "onions,
    # chopped" fails because tier 2 (stripped) doesn't singularize, and tier
    # 3's cleanup doesn't strip the comma before its own plural check, so the
    # legacy path never reaches the singular form. Adding the plural itself
    # as an explicit key fixes every comma-attached-handling-word variant of
    # that plural at once via the stripped tier, without touching either
    # tier's matching mechanism. "potatoes" additionally needs its own key
    # regardless of comma, because "potato" isn't in ingredient_normalizer's
    # CANONICAL_INGREDIENTS fuzzy-match target list, so even the bare plural
    # never resolves via the legacy fallback. ---
    "onions": 110.0,  # same "onion" citation above, plural
    "tomatoes": 123.0,  # same "tomato" citation above, plural
    "potatoes": 213.0,  # same "potato" citation above, plural
    "carrots": 61.0,  # same "carrot" citation above, plural
    "green onions": 15.0,  # same "green onion" citation above, plural
    "scallions": 15.0,  # same "green onion" citation above (SYNONYMS maps "scallions" -> "green onion" already, but only for the bare/no-comma case; this literal key covers "scallions, chopped" etc.)
    "celery": 40.0,  # same "celery stalk" citation above -- bare "celery" (no "stalk" qualifier) in a recipe is understood as one stalk
    # --- size-descriptor + comma-attached-handling-word literal keys. DESCRIPTORS
    # ("medium"/"large"/"small") ARE already stripped by the legacy tier 3
    # fallback for the no-comma case (e.g. "large onion" -> "onion" already
    # resolves), but that same legacy path fails once a comma-attached
    # handling word is also present (its cleanup step doesn't strip commas
    # before the descriptor-removal regex runs), and tier 2 (stripped)
    # deliberately does NOT strip size descriptors -- only handling words and
    # punctuation (see _strip_handling_words). Rather than
    # widen either tier's stripping rules, the highest-frequency literal
    # corpus strings are added directly here, each reusing the same "onion"
    # citation as the base entry above -- consistent with this file's
    # existing "additive literal key" precedent (see the eggs/brown-sugar/
    # parmesan keys earlier in _DENSITY_G_PER_ML). ---
    "medium onion, chopped": 110.0,
    "large onion, chopped": 110.0,
    "small onion, chopped": 110.0,
    "medium onion, sliced": 110.0,
    "medium onion, finely chopped": 110.0,
    "medium onions, chopped": 110.0,
    "small onion, diced": 110.0,
    "onions, sliced": 110.0,
    "medium onion, diced": 110.0,
    "small onion, finely chopped": 110.0,
    "large onions, chopped": 110.0,
    "large onion, diced": 110.0,
    "medium onions, sliced": 110.0,
    "large onion, finely chopped": 110.0,
    "small onion, minced": 110.0,
    "onions, finely chopped": 110.0,
    "small onion, sliced": 110.0,
    "medium onion, thinly sliced": 110.0,
    "medium onion, minced": 110.0,
    "large onion, sliced": 110.0,
    "medium potatoes": 213.0,  # same "potato" citation above -- descriptor + no comma, but "potato" isn't a legacy fuzzy-match target (see the plural-key note above), so this still needs an explicit key
    "large potatoes": 213.0,  # same "potato" citation above
    "medium tomatoes": 123.0,  # same "tomato" citation above
    "large tomatoes": 123.0,  # same "tomato" citation above
    "medium tomatoes, chopped": 123.0,  # same "tomato" citation above
    "large tomatoes, chopped": 123.0,  # same "tomato" citation above
    # --- garlic comma/handling-word literal keys. "minced" already resolves
    # via the existing comma-stripping fix (test_comma_stripping_regression_
    # garlic_minced); the keys below cover corpus-observed handling words
    # that are NOT in _HANDLING_WORDS ("crushed", "pressed", "smashed") --
    # deliberately kept as literal keys rather than added to _HANDLING_WORDS
    # itself, since "crushed"/"smashed" can denote a genuinely different
    # product for other ingredients (e.g. "crushed tomatoes" is a distinct
    # canned product, not a handling variant) -- and the "garlic cloves"/
    # "garlic clove" plain-name literal keys, for corpus rows where the
    # quantity parser didn't recognize "cloves" as the unit (it only matches
    # a unit token immediately after the amount; "3 garlic cloves" puts
    # "cloves" as the second word of the name instead). All reuse the
    # "garlic" 5.0 g/clove citation above. ---
    "garlic cloves": 5.0,
    "garlic clove": 5.0,
    "garlic cloves, minced": 5.0,
    "garlic clove, minced": 5.0,
    "garlic, crushed": 5.0,
    "garlic crushed": 5.0,
    "crushed garlic": 5.0,
    "garlic cloves, crushed": 5.0,
    "garlic clove, crushed": 5.0,
    "garlic cloves, smashed": 5.0,
    "garlic, pressed": 5.0,
    "garlic, minced or pressed": 5.0,
    "garlic cloves, chopped": 5.0,
    "garlic clove, chopped": 5.0,
    "garlic cloves, finely chopped": 5.0,
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
    # added 2026-07-27 (grams-computable coverage pass): "finely" is a degree
    # adverb attached to an already-handled verb ("finely chopped", "finely
    # minced"), not a composition or physical-form word on its own -- it
    # doesn't independently change an ingredient's identity or density any
    # more than the "chopped"/"minced" it modifies. Fixes e.g. "garlic,
    # finely chopped" / "celery, finely chopped" / "onion, finely chopped"
    # to resolve via their existing base entries, the same way "garlic,
    # minced" already does.
    "finely",
})

_HANDLING_WORD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(_HANDLING_WORDS, key=len, reverse=True)) + r")\b"
)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _strip_handling_words(name: str) -> str:
    # Convert commas/semicolons to spaces too (at this "stripped" candidate
    # stage only -- the "raw" candidate above is untouched), so a corpus
    # string like "garlic, minced" normalizes to "garlic" and can match an
    # existing single-word table entry, instead of stopping at "garlic,"
    # with a dangling comma left over from substituting "minced" with a
    # space. See _normalize_for_density_lookup's docstring for why this is
    # scoped to `stripped` only (advisor-reviewed fix).
    without_handling_words = _HANDLING_WORD_RE.sub(" ", name)
    without_punctuation = re.sub(r"[,;]", " ", without_handling_words)
    return _collapse_whitespace(without_punctuation)


def _normalize_for_density_lookup(name: str) -> list[str]:
    """Ordered, deduplicated EXACT-match lookup keys for the density/piece
    tables. Nutrition-path-only: never used for allergen matching.

    Precedence (strict-first, then legacy fallback), per the A2 advisor
    ruling:
      1. raw name, lowercased and whitespace-collapsed only -- no word
         removal at all, so explicit multi-word keys like "cooked rice" or
         "brown sugar" resolve to themselves before anything else can touch
         them.
      2. the same, with handling/preparation words stripped and commas/
         semicolons converted to spaces (e.g. "chopped onion" -> "onion",
         "garlic, minced" -> "garlic").
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
