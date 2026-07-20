# Grounding report

## Corpus-wide summary
- total recipes processed: 4263
- grounded: 15 (0.4%)
- partial: 2522 (59.2%)
- ungrounded: 1726 (40.5%)

## Top ungrounded ingredients, corpus-wide (top 50 of up to 50)

| ingredient (normalized) | recipes affected |
|---|---|
| salt | 1895 |
| butter | 1252 |
| sugar | 1247 |
| water | 869 |
| flour | 721 |
| milk | 664 |
| pepper | 535 |
| margarine | 457 |
| lemon juice | 439 |
| baking powder | 420 |
| brown sugar | 407 |
| cinnamon | 407 |
| parsley | 393 |
| vanilla | 370 |
| all purpose flour | 337 |
| olive oil | 326 |
| baking soda | 317 |
| green onion | 279 |
| celery | 273 |
| garlic clove | 264 |
| nutmeg | 256 |
| sour cream | 250 |
| black pepper | 236 |
| chicken breast | 223 |
| cream cheese | 204 |
| cornstarch | 202 |
| mushroom | 199 |
| ginger | 187 |
| parmesan | 182 |
| vanilla extract | 180 |
| green pepper | 173 |
| soy sauce | 168 |
| mayonnaise | 161 |
| pecan | 161 |
| honey | 157 |
| worcestershire sauce | 156 |
| raisin | 155 |
| walnut | 155 |
| cheddar cheese | 155 |
| paprika | 153 |
| apple | 148 |
| potatoe | 145 |
| garlic powder | 141 |
| granulated sugar | 141 |
| vinegar | 124 |
| unsalted butter | 121 |
| oregano | 120 |
| bacon | 117 |
| basil | 115 |
| shortening | 114 |

## Tag-vs-computed ratio distribution, corpus-wide (GROUNDED/PARTIAL recipes with a self-reported tag calorie value)

- n: 2537
- mean: 0.21x
- median: 0.03x
- stdev: 1.48
- min: 0.00x
- max: 61.09x

### Ratio outliers (outside [0.4x, 2.5x]) -- report-only, no demotion
- count: 2345

| recipe_id | title | tag kcal | computed kcal | ratio |
|---|---|---|---|---|
| imp_0035657e83a75216 | Amaretto Peach Cheesecake | 441 | 11 | 0.02x |
| imp_003ab1b0f9d054ca | Sugar Free Brownies | 68 | 0 | 0.00x |
| imp_004e107d27b75fc2 | White Bean Soup | 93 | 6 | 0.07x |
| imp_005e6018423e5f71 | Gazpacho 1 (adopted) | 179 | 18 | 0.10x |
| imp_006b3d01133f555e | Baked Red Onions | 160 | 1 | 0.01x |
| imp_007080a9b0485889 | Egg Drop Soup | 88 | 18 | 0.21x |
| imp_007bd1fec5fd5e08 | Hung Shao Pork | 2530 | 7 | 0.00x |
| imp_00a34af8ec095c83 | Soft Potato Bread Stuffing | 93 | 13 | 0.14x |
| imp_00efafa3c86e5b9e | Beef Stroganoff with Dill | 1098 | 6 | 0.01x |
| imp_011194df31185a29 | Liqueur Cakes | 412 | 9 | 0.02x |
| imp_0134a2a00a95591a | Braised Beef Liver With Vegetables | 1004 | 172 | 0.17x |
| imp_01581d6dce025b73 | East Indian Chicken | 558 | 6 | 0.01x |
| imp_01f7efb72e7b5af9 | Slow-Cooker Grape Jelly Meatballs | 22 | 72 | 3.22x |
| imp_01f8776d18bc54b5 | Scrambled Eggs and Ham | 313 | 3 | 0.01x |
| imp_02344598c0a758e5 | Crawfish Pie | 370 | 14 | 0.04x |
| imp_02466cb5e6655705 | Zinfandeli's Chicken Tortilla Soup - S.a. Express - Arlene Light | 206 | 32 | 0.16x |
| imp_025c90934851588b | Pumpkin Spice Cake in Jars | 378 | 7 | 0.02x |
| imp_026073a067615a51 | Carla's Turkey Loaf | 213 | 6 | 0.03x |
| imp_02a164f4a2b65adc | Easy Peasey Bread Pudding | 614 | 34 | 0.06x |
| imp_02a5b6ed7968549e | Strawberry Marbled Cheesecake | 434 | 7 | 0.02x |
| imp_02e8b9e122635553 | Creamy Turkey Pie | 350 | 10 | 0.03x |
| imp_02f9c5861cd05c8e | Layered Mexican Dip | 252 | 35 | 0.14x |
| imp_02ff2336265c57c6 | Mixed Onion Soup in Sourdough Bread Bowls | 809 | 4 | 0.00x |
| imp_030591e83db85591 | Hungarian Goulash Soup | 190 | 24 | 0.13x |
| imp_0326b00eade05b1a | Pecan Filling | 2764 | 82 | 0.03x |
| imp_03311d2fa6d755f7 | Pizza Pockets | 421 | 19 | 0.05x |
| imp_033dd5cc647753b2 | Ice-Water Pickles | 292 | 44 | 0.15x |
| imp_034cf87edb9f5e9b | Fried Chicken Livers II | 1215 | 28 | 0.02x |
| imp_036a4f35023f513f | Oatmeal Muffins | 188 | 28 | 0.15x |
| imp_03872087026150bb | Ground Beef Stuffed Red Bell Peppers | 1754 | 22000 | 12.54x |
| imp_03a56ee8c5775340 | Pork in Cider Sauce | 498 | 6 | 0.01x |
| imp_03aaea4eaafb5601 | Dutch Oven Pot Roast | 413 | 46 | 0.11x |
| imp_03d00dccc2095e6f | Sun of a Gun Beef Stew | 3295 | 101 | 0.03x |
| imp_03d34d5d7adf5719 | Enchiladas Pollo With Green Chilies Cream Sauce | 808 | 26 | 0.03x |
| imp_03dcbe6587375d85 | Grilled Salmon | 666 | 5 | 0.01x |
| imp_04076747e2645787 | Chanfana Ou Lampantana | 1266 | 5507 | 4.35x |
| imp_040ea38571635a32 | Game Salmi | 1281 | 47 | 0.04x |
| imp_041c6eb156dd5999 | Easy Asian Chicken Soup | 267 | 5 | 0.02x |
| imp_045f83b795df50a8 | California Rarebit | 392 | 7 | 0.02x |
| imp_047c9248e21a51a0 | Chiffon Pumpkin Pie | 368 | 14 | 0.04x |
| imp_048143cd0c5d5a4d | White Sauce Seafood Lasagna | 472 | 2 | 0.00x |
| imp_0489e1831ad55000 | Libby's Jeweled Relish | 571 | 25 | 0.04x |
| imp_04a3ba13b7cc5e17 | Cornbread With Corn Casserole | 272 | 55 | 0.20x |
| imp_04abc2d9c3bc5600 | Sunday Black-Bean Soup | 384 | 49 | 0.13x |
| imp_04ac0d2f8a645070 | Onion Soup | 162 | 53 | 0.33x |
| imp_04b608a36f075cd0 | Chocolate Cherry Cordial Muffins | 329 | 2 | 0.01x |
| imp_05002beb175a5aac | Potato Spinach Soup | 1180 | 44 | 0.04x |
| imp_051aa81563645939 | Crafty Crescent Lasagna | 772 | 64 | 0.08x |
| imp_05433c91cc3b5666 | French Roasted Vegetable Sandwiches | 222 | 11 | 0.05x |
| imp_0563fa52cc03502f | Cherry Bars | 122 | 2 | 0.02x |
| imp_0569647ef2c2583b | Grandma's Apple Muffins | 160 | 55 | 0.34x |
| imp_059e4d6450c650ec | Snails Sommeroise / Escargots a la Sommeroise | 425 | 5 | 0.01x |
| imp_05bc0340cffb5a85 | Grilled Thai Sirloin with Tangy Lime Sauce | 237 | 4 | 0.02x |
| imp_05c09b087dcf52bf | Streusel-Topped Pumpkin Pie | 504 | 28 | 0.05x |
| imp_05c4ce5de6a25c5d | Pumpkin Swirl Pie | 337 | 3 | 0.01x |
| imp_06119595d11d52f0 | A-To-Z Bread | 367 | 23 | 0.06x |
| imp_0613d1f5a68955f5 | Quick Barbecue Sauce | 348 | 6 | 0.02x |
| imp_061a2bb7f4e45904 | Morning Maple Muffins | 212 | 14 | 0.06x |
| imp_061a6bf4b72a51b4 | Clam - Lobster Bake | 990 | 44 | 0.04x |
| imp_06417c1d6fd0509f | Black Coffee Barbecue Sauce | 772 | 44 | 0.06x |
| imp_065cb86552265bf3 | Amish Cornbread | 1792 | 55 | 0.03x |
| imp_066554e9bc51597c | Wild Goose | 5460 | 157 | 0.03x |
| imp_066bbc90afa15f57 | Low-Fat Chicken With Caramelized Onions | 169 | 11 | 0.07x |
| imp_067b4604c9aa5f72 | Green Mango Salad With Cilantro Vinaigrette | 92 | 6 | 0.07x |
| imp_069a3957e9845585 | Mango Salsa | 100 | 7 | 0.07x |
| imp_06b3ec9513ff5005 | Green Chicken Enchiladas | 222 | 88 | 0.40x |
| imp_06bc46d645225dc0 | Pacific Blue Marlin (Kajiki) | 111 | 11 | 0.10x |
| imp_06f98881ebf05a75 | Roasted Pork Loin with Bacon and Onion Spaetzle | 1186 | 1 | 0.00x |
| imp_070317197449598d | Beef in Red Wine | 156 | 15 | 0.10x |
| imp_070d4579ad1256b3 | Biscotti Di Anise | 962 | 21 | 0.02x |
| imp_071082b7aec05d7e | Extra-Rich Chocolate Pecan Pie | 649 | 9 | 0.01x |
| imp_072a543988f85a97 | Raisin-Almond Bread | 230 | 3 | 0.01x |
| imp_079476fa25a35a43 | True Texas Chili Con Carne | 1732 | 36 | 0.02x |
| imp_0798a2a391015c23 | Buttertart Squares | 294 | 5 | 0.02x |
| imp_079c4aaf57965ff5 | Salad-in-a-Boat | 331 | 18 | 0.06x |
| imp_07d4900d6d2055ef | Asparagus Strata | 495 | 55 | 0.11x |
| imp_07dc18bc6e545e6f | Blueberry Cookies | 58 | 1 | 0.01x |
| imp_07fb931d1d415cd5 | Penne Piperade | 467 | 23 | 0.05x |
| imp_086356531a07531f | Smoothy Chocolate Cookies | 133 | 1 | 0.01x |
| imp_087266c2e7c550a1 | Corn Casserole II | 202 | 9 | 0.05x |
| imp_08a8f9de773d57eb | Pumpkin Pie Squares | 340 | 41 | 0.12x |
| imp_08f2b06332435f6d | Baklava | 363 | 1 | 0.00x |
| imp_092d4aea4df65760 | Lemony Herbed Drumsticks | 2445 | 44 | 0.02x |
| imp_0930e089069e5d96 | Caesar for Two | 276 | 20 | 0.07x |
| imp_096552b6325d5645 | Sopa Leao Velloso | 251 | 4 | 0.02x |
| imp_097c3c0c319e5b52 | Chicken Breasts Florentine | 490 | 10 | 0.02x |
| imp_0982148f97be5fce | Low-Fat Thai Steak Salad | 2630 | 2 | 0.00x |
| imp_0995a404a5135c69 | 7-Up Cake | 550 | 5 | 0.01x |
| imp_09c0cbf187d850eb | Seafood Pasta Saute | 845 | 2 | 0.00x |
| imp_09c936ec1c8754a1 | Crabby Quiche Pie | 362 | 14 | 0.04x |
| imp_09ca8915c85450ca | Chicken-Fried Steak With Cracked Pepper Gravy | 1636 | 14 | 0.01x |
| imp_09da1a4f1201506e | Chicken Curry | 360 | 26 | 0.07x |
| imp_09deb8dad38b5a76 | Enchiladas Verdes Suizas | 756 | 33 | 0.04x |
| imp_09f840f9b831568f | Orange Cupcakes | 1804 | 55 | 0.03x |
| imp_0a0d1babded653b7 | Carrot Ginger Biscuits | 127 | 1 | 0.01x |
| imp_0a3f277639cc56f6 | Cheese and Meatball Soup | 458 | 10 | 0.02x |
| imp_0a5ee9a653145c20 | Key Lime Bars | 132 | 3 | 0.02x |
| imp_0a98dc6855795a71 | Greek Salad | 1043 | 144 | 0.14x |
| imp_0aa9ea1739cc54ca | Carina's Garden Ratatouille | 823 | 167 | 0.20x |
| imp_0ab6d18389435ade | Chocolate Amaretto Cheesecake | 668 | 5 | 0.01x |
| ... | (2245 more, see full count above) | | | |

## Corpus-wide implausible kcal/serving band (<20 or >2000), GROUNDED/PARTIAL only
- count: 1439

## Corpus-wide ingredient-occurrence terminal outcomes (what actually happens to every ingredient row)

Every ingredient occurrence in the corpus lands in EXACTLY ONE of the buckets below (mutually exclusive, and reconciled at grounding time to sum to the corpus's total ingredient-row count -- see `grounding_job._terminal_outcome_for_ingredient`). This is the table that explains ungroundedness; the rejection-counts table further below does NOT.

| outcome | count | % of occurrences |
|---|---|---|
| grounded | 3749 | 10.6% |
| no_unit | 31495 | 89.0% |
| unit_unconvertible | 124 | 0.4% |
| no_relevant_candidate | 9 | 0.0% |
| all_candidates_rejected | 1 | 0.0% |

## Individual-candidate rejection counts by reason, corpus-wide (NOT a table of ungroundedness causes)

**Read this table carefully.** Each count is the number of individual FDC CANDIDATES skipped during matching for the reason shown -- tallied once per candidate, across every `search_food` call this run made. It is NOT a count of queries/occurrences that failed to ground, and it is NOT a list of "why ingredients are ungrounded" (see the terminal-outcome table above for that). A query whose candidate was skipped here may still have gone on to ground successfully via a later candidate or the Branded fallback -- e.g. `processed_state_modifier:creamed` is almost entirely the imported corpus's egg occurrences correctly skipping an 'Egg, creamed' candidate while still grounding fine against a different candidate.

| reason | candidates skipped |
|---|---|
| processed_state_modifier:creamed | 1203 |
| processed_state_modifier:dehydrated | 338 |
| kcal_too_low_branded | 22 |
| atwater_mismatch | 3 |
| processed_state_modifier:pickled | 2 |
| mass_over_105g | 1 |

## Branded-tier high-dispersion queries, corpus-wide (3+ candidates, >3.0x calorie spread -- left ungrounded)

- count: 0

## Seed tag-vs-computed comparison (25 recipes)

| recipe_id | title | status | coverage | tag kcal | computed kcal | ratio |
|---|---|---|---|---|---|---|
| r_001 | Mediterranean Chicken Rice Bowl | grounded | 100% | 610 | 590 | 0.97x |
| r_002 | Thai Peanut Tofu Stir Fry | grounded | 100% | 540 | 605 | 1.12x |
| r_003 | Mexican Turkey Black Bean Skillet | grounded | 100% | 520 | 638 | 1.23x |
| r_004 | Italian Lentil Tomato Pasta | grounded | 100% | 590 | 1007 | 1.71x **[RAW/COOKED BLOWUP]** |
| r_005 | Japanese Salmon Sushi Bowl | partial | 88% | 650 | 835 | 1.28x |
| r_006 | American Egg White Veggie Omelet | partial | 86% | 330 | 727 | 2.20x |
| r_007 | Indian Chickpea Spinach Curry | partial | 75% | 560 | 392 | 0.70x |
| r_008 | Mediterranean Quinoa Chickpea Salad | grounded | 100% | 480 | 835 | 1.74x **[RAW/COOKED BLOWUP]** |
| r_009 | Dairy-Free Chicken Fajita Plate | grounded | 100% | 620 | 684 | 1.10x |
| r_010 | Gluten-Free Turkey Meatballs | partial | 75% | 500 | 602 | 1.20x |
| r_011 | Thai Basil Shrimp Rice | partial | 88% | 470 | 417 | 0.89x |
| r_012 | American Turkey Sweet Potato Chili | grounded | 100% | 570 | 632 | 1.11x |
| r_013 | Japanese Miso Tofu Soup Bowl | grounded | 100% | 410 | 426 | 1.04x |
| r_014 | Indian Chicken Tikka Lettuce Bowls | partial | 88% | 580 | 317 | 0.55x |
| r_015 | Mexican Vegan Burrito Bowl | grounded | 100% | 530 | 615 | 1.16x |
| r_016 | Italian Caprese Chicken | grounded | 100% | 620 | 807 | 1.30x |
| r_017 | Mediterranean Lentil Soup | grounded | 100% | 430 | 572 | 1.33x |
| r_018 | American Greek Yogurt Protein Parfait | partial | 83% | 420 | 513 | 1.22x |
| r_019 | Thai Green Curry Chicken | partial | 88% | 680 | 626 | 0.92x |
| r_020 | Japanese Chicken Teriyaki Bowl | grounded | 100% | 590 | 570 | 0.97x |
| r_021 | Indian Paneer Pea Curry | partial | 88% | 640 | 628 | 0.98x |
| r_022 | Mediterranean Tuna White Bean Salad | grounded | 100% | 450 | 478 | 1.06x |
| r_023 | American Beef Quinoa Stuffed Peppers | grounded | 100% | 610 | 953 | 1.56x |
| r_024 | Mexican Shrimp Taco Salad | partial | 88% | 500 | 470 | 0.94x |
| r_025 | Italian White Bean Zucchini Stew | grounded | 100% | 420 | 440 | 1.05x |

## Flags: raw/cooked-scale blowup (>1.6x)
- **r_004** (Italian Lentil Tomato Pasta): ratio 1.71x
- **r_008** (Mediterranean Quinoa Chickpea Salad): ratio 1.74x

## Flags: implausible kcal/serving band (<20 or >2000)
None.

## Known residuals (investigated, deliberately not fixed further)

- **jasmine rice / basmati rice**: No variety-specific Foundation/SR Legacy/Survey record exists for either (confirmed live, even with the query augmented by the declared 'cooked' state) -- only generic 'Rice, white, cooked' entries exist. Rather than silently substitute a different variety, jasmine rice stays on its Branded match (JASMINE COOKED RICE, JASMINE, ~225 kcal/100g -- notably above a true ~130 kcal/100g, likely includes added oil/seasoning) and basmati stays UNGROUNDED. Not preparation-fixable.
- **zucchini (RESOLVED by phase 1.5/P4)**: Previously stuck on a Branded 'Zucchini, pickled' match: FDC's canonical zucchini record is filed under 'Squash' (e.g. 'Squash, summer, green, zucchini, includes skin, raw'), not 'Zucchini', so the relevance check's head-noun rule correctly refused to treat that as the same food as a bare 'zucchini' query without an explicit vocabulary mapping. Resolved by adding usda_client._FDC_QUERY_ALIASES['zucchini'] = 'squash zucchini' -- now resolves to the real raw Foundation record (~17-21 kcal/100g).
- **ginger (RESOLVED by phase 1.5/P4)**: Previously the only reachable Branded record reported 0 kcal/100g (a data defect the P1 plausibility gate correctly rejects as 'kcal_too_low_branded'), leaving it UNGROUNDED. Resolved by adding usda_client._FDC_QUERY_ALIASES['ginger'] = 'spices ginger ground', which reaches the real SR Legacy 'Spices, ginger, ground' record (~335 kcal/100g) at the generic tier, never reaching the defective Branded record at all.
- **shrimp / tomato sauce**: Explicitly excluded via usda_client._KNOWN_UNRELIABLE_QUERIES -- both reliably resolve to a wrong-form match with no preparation declaration able to gate it (a sauce/seafood has no honest raw/cooked/canned state), and both wrong-form matches' macros are plausible-looking enough to clear the P1 plausibility gate too. Render UNGROUNDED rather than a confidently wrong number.
- **chili powder**: The only reachable Branded record reports 0 kcal/100g -- a data defect the P1 plausibility gate correctly rejects as 'kcal_too_low_branded', and no generic-tier 'Spices, chili powder' record was found to alias to (unlike the other spices resolved in phase 1.5/P4) -- stays on usda_client._KNOWN_UNRELIABLE_QUERIES as a disclosed, deliberate exclusion pending that verification.
- **salt / baking soda / baking powder (RESOLVED by phase 1.5 closeout/P2 -- was a plausibility-gate tension, NOT alias-fixable; the corpus-wide cap on these is now the unit problem below, not this)**: Live-verified (phase 1.5/P4 investigation): the real, relevant FDC records for these (e.g. 'Salt, table') report a true, physically correct near-zero kcal/100g -- not a data defect. The gate's absolute floor (_PLAUSIBLE_MIN_KCAL = 5, written to catch a 0-kcal Branded data-entry defect) used to reject them for the same reason it correctly rejects a genuine defect: it could not distinguish 'this food really is ~calorie-free' from 'this record is wrong.' RESOLVED by phase 1.5 closeout/P2: the floor is now applied only to Branded candidates (see usda_client._plausibility_reject_reason's module comment) -- Foundation/SR Legacy/Survey candidates fall through to the mass + Atwater checks instead, which correctly pass a genuine all-zero record. This does NOT mean salt/baking soda/baking powder now ground corpus-wide, though: the overwhelming majority of their occurrences never reach `search_food` at all, because the imported corpus's ingredient rows have `unit: None` at the data level (see the corpus-wide terminal-outcome tally's `no_unit` bucket) -- a separate, NOT-fixed-here problem. In practice these ingredients' calorie contribution to a recipe is genuinely negligible regardless.
- **olive oil**: Deterministically matches 'Oil, corn, peanut, and olive' (SR Legacy) instead of pure olive oil -- wrong specific product, but zero practical calorie impact (~884-900 kcal/100g either way, consistent with any pure fat). Left as-is.
- **general case: undeclared-preparation same-food-wrong-state matches**: The `preparation` field and the relevance check only cover ingredients that declare a state. Any ingredient without one (i.e. everything outside the seeds' explicitly-audited set) can still land on a processed/wrong-state USDA record purely by dataType-tier order -- this was the root cause behind chicken breast, ground turkey, corn, and tofu before they were individually audited and fixed for the 25 seeds. Unaudited for the imported corpus at large -- see docs/ROADMAP.md.

## Per-ingredient grounding detail

### r_001 -- Mediterranean Chicken Rice Bowl (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 180.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| brown rice | True | 150.0 | matched: Rice, brown, cooked, as ingredient (Survey (FNDDS)) |
| spinach | True | 40.0 | matched: Spinach, baby (Foundation) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| Greek yogurt | True | 61.8 | matched: Yogurt, Greek, plain, nonfat (Foundation) |
| lemon | True | 15.0 | matched: Lemon, raw (Survey (FNDDS)) |
| cucumber | True | 80.0 | matched: Cucumber, raw (Survey (FNDDS)) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |

### r_002 -- Thai Peanut Tofu Stir Fry (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| tofu | True | 150.0 | matched: Tofu, raw, firm, prepared with calcium sulfate (SR Legacy) |
| rice noodles | True | 120.0 | matched: Rice noodles, cooked (SR Legacy) |
| broccoli | True | 80.0 | matched: Broccoli, raw (Foundation) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| peanut butter | True | 30.0 | matched: Peanut butter (Survey (FNDDS)) |
| soy sauce | True | 16.5 | matched: Soy sauce (Survey (FNDDS)) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |

### r_003 -- Mexican Turkey Black Bean Skillet (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| ground turkey | True | 170.0 | matched: Turkey, Ground, raw (SR Legacy) |
| black beans | True | 130.0 | matched: Beans, black turtle, mature seeds, canned (SR Legacy) |
| corn | True | 80.0 | matched: Corn, sweet, white, raw (SR Legacy) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| avocado | True | 75.0 | matched: Avocados, raw, California (SR Legacy) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |
| coriander | True | 5.0 | matched: Spices, coriander seed (SR Legacy) |

### r_004 -- Italian Lentil Tomato Pasta (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| whole wheat pasta | True | 100.0 | matched: Pasta, whole grain, 51% whole wheat, remaining unenriched semolina, dry (SR Legacy) |
| lentils | True | 100.0 | matched: Lentils, dry (Foundation) |
| tomato | True | 246.0 | matched: Tomato, roma (Foundation) |
| spinach | True | 40.0 | matched: Spinach, baby (Foundation) |
| parmesan | True | 20.0 | matched: Cheese, parmesan, grated (Foundation) |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |
| basil | True | 5.0 | matched: Basil, fresh (SR Legacy) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |

### r_005 -- Japanese Salmon Sushi Bowl (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| salmon | True | 170.0 | matched: SALMON (Branded) |
| white rice | True | 180.0 | matched: Rice, cooked, NFS (Survey (FNDDS)) |
| cucumber | True | 60.0 | matched: Cucumber, raw (Survey (FNDDS)) |
| avocado | True | 75.0 | matched: Avocados, raw, California (SR Legacy) |
| edamame | True | 60.0 | matched: Edamame, frozen, prepared (SR Legacy) |
| soy sauce | True | 16.5 | matched: Soy sauce (Survey (FNDDS)) |
| nori | False | 3.0 | ungrounded: no USDA match |
| sesame seeds | True | 6.0 | matched: Seeds, sesame seeds, whole, dried (SR Legacy) |

### r_006 -- American Egg White Veggie Omelet (partial, coverage 86%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| egg whites | True | 150.0 | matched: Egg, white, dried (Foundation) |
| whole egg | False | n/a | ungrounded: amount/unit not convertible to grams |
| spinach | True | 30.0 | matched: Spinach, baby (Foundation) |
| mushroom | True | 40.0 | matched: Mushroom, beech (Foundation) |
| bell pepper | True | 59.5 | matched: Peppers, bell, green, raw (Foundation) |
| cheddar cheese | True | 30.0 | matched: Cheese, cheddar (Foundation) |
| green onion | True | 10.0 | matched: Onions, young green, tops only (SR Legacy) |

### r_007 -- Indian Chickpea Spinach Curry (partial, coverage 75%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chickpeas | True | 150.0 | matched: Chickpeas, from canned, fat added (Survey (FNDDS)) |
| spinach | True | 60.0 | matched: Spinach, baby (Foundation) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |
| ginger | True | 5.0 | matched: Spices, ginger, ground (SR Legacy) |
| coconut milk | False | 98.0 | ungrounded: no USDA match for declared state 'canned' |
| basmati rice | False | 150.0 | ungrounded: no USDA match for declared state 'cooked' |

### r_008 -- Mediterranean Quinoa Chickpea Salad (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| quinoa | True | 90.0 | matched: Quinoa, uncooked (SR Legacy) |
| chickpeas | True | 100.0 | matched: Chickpeas, from canned, fat added (Survey (FNDDS)) |
| cucumber | True | 80.0 | matched: Cucumber, raw (Survey (FNDDS)) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| feta cheese | True | 40.0 | matched: FETA (Branded) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |
| lemon | True | 15.0 | matched: Lemon, raw (Survey (FNDDS)) |
| parsley | True | 5.0 | matched: Parsley, freeze-dried (SR Legacy) |

### r_009 -- Dairy-Free Chicken Fajita Plate (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 180.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| onion | True | 110.0 | matched: Onions, raw (SR Legacy) |
| brown rice | True | 150.0 | matched: Rice, brown, cooked, as ingredient (Survey (FNDDS)) |
| black beans | True | 100.0 | matched: Beans, black turtle, mature seeds, canned (SR Legacy) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |
| avocado | True | 75.0 | matched: Avocados, raw, California (SR Legacy) |
| coriander | True | 5.0 | matched: Spices, coriander seed (SR Legacy) |

### r_010 -- Gluten-Free Turkey Meatballs (partial, coverage 75%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| ground turkey | True | 200.0 | matched: Turkey, Ground, raw (SR Legacy) |
| whole egg | False | n/a | ungrounded: amount/unit not convertible to grams |
| almond flour | True | 30.0 | matched: Flour, almond (Foundation) |
| tomato sauce | False | 100.0 | ungrounded: no USDA match |
| zucchini noodles | True | 150.0 | matched: ZUCCHINI NOODLES (Branded) |
| parmesan | True | 20.0 | matched: Cheese, parmesan, grated (Foundation) |
| garlic | True | 5.0 | matched: Garlic, raw (Foundation) |
| basil | True | 5.0 | matched: Basil, fresh (SR Legacy) |

### r_011 -- Thai Basil Shrimp Rice (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| shrimp | False | 180.0 | ungrounded: no USDA match |
| jasmine rice | True | 150.0 | matched: JASMINE COOKED RICE, JASMINE (Branded) |
| green beans | True | 60.0 | matched: Green beans, raw (Survey (FNDDS)) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| basil | True | 5.0 | matched: Basil, fresh (SR Legacy) |
| soy sauce | True | 16.5 | matched: Soy sauce (Survey (FNDDS)) |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |

### r_012 -- American Turkey Sweet Potato Chili (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| ground turkey | True | 170.0 | matched: Turkey, Ground, raw (SR Legacy) |
| sweet potato | True | 150.0 | matched: SWEET POTATO (Branded) |
| black beans | True | 130.0 | matched: Beans, black turtle, mature seeds, canned (SR Legacy) |
| tomato | True | 246.0 | matched: Tomato, roma (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| chili powder | True | 5.0 | matched: CHILI POWDER (Branded) |
| spinach | True | 40.0 | matched: Spinach, baby (Foundation) |

### r_013 -- Japanese Miso Tofu Soup Bowl (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| tofu | True | 120.0 | matched: Tofu, raw, firm, prepared with calcium sulfate (SR Legacy) |
| miso paste | True | 20.0 | matched: MISO PASTE (Branded) |
| brown rice | True | 150.0 | matched: Rice, brown, cooked, as ingredient (Survey (FNDDS)) |
| mushroom | True | 40.0 | matched: Mushroom, beech (Foundation) |
| spinach | True | 30.0 | matched: Spinach, baby (Foundation) |
| green onion | True | 10.0 | matched: Onions, young green, tops only (SR Legacy) |
| seaweed | True | 5.0 | matched: Seaweed, agar, raw (SR Legacy) |
| soy sauce | True | 11.0 | matched: Soy sauce (Survey (FNDDS)) |

### r_014 -- Indian Chicken Tikka Lettuce Bowls (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 200.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| Greek yogurt | True | 61.8 | matched: Yogurt, Greek, plain, nonfat (Foundation) |
| lettuce | True | 60.0 | matched: Lettuce, raw (Survey (FNDDS)) |
| cucumber | True | 60.0 | matched: Cucumber, raw (Survey (FNDDS)) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| basmati rice | False | 150.0 | ungrounded: no USDA match for declared state 'cooked' |
| garam masala | True | 5.0 | matched: GARAM MASALA (Branded) |
| lemon | True | 20.0 | matched: Lemon, raw (Survey (FNDDS)) |

### r_015 -- Mexican Vegan Burrito Bowl (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| brown rice | True | 150.0 | matched: Rice, brown, cooked, as ingredient (Survey (FNDDS)) |
| black beans | True | 130.0 | matched: Beans, black turtle, mature seeds, canned (SR Legacy) |
| corn | True | 80.0 | matched: Corn, sweet, white, raw (SR Legacy) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| lettuce | True | 40.0 | matched: Lettuce, raw (Survey (FNDDS)) |
| avocado | True | 112.5 | matched: Avocados, raw, California (SR Legacy) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |
| coriander | True | 5.0 | matched: Spices, coriander seed (SR Legacy) |

### r_016 -- Italian Caprese Chicken (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 200.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| mozzarella | True | 60.0 | matched: MOZZARELLA (Branded) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| basil | True | 5.0 | matched: Basil, fresh (SR Legacy) |
| balsamic vinegar | True | 15.0 | matched: Vinegar, balsamic (SR Legacy) |
| olive oil | True | 9.1 | matched: Oil, corn, peanut, and olive (SR Legacy) |
| zucchini | True | 100.0 | matched: Squash, summer, green, zucchini, includes skin, raw (Foundation) |
| quinoa | True | 80.0 | matched: Quinoa, uncooked (SR Legacy) |

### r_017 -- Mediterranean Lentil Soup (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| lentils | True | 100.0 | matched: Lentils, dry (Foundation) |
| carrot | True | 61.0 | matched: Carrots, baby, raw (Foundation) |
| celery | True | 40.0 | matched: Celery, raw (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| spinach | True | 30.0 | matched: Spinach, baby (Foundation) |
| lemon | True | 10.0 | matched: Lemon, raw (Survey (FNDDS)) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |

### r_018 -- American Greek Yogurt Protein Parfait (partial, coverage 83%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| Greek yogurt | True | 206.0 | matched: Yogurt, Greek, plain, nonfat (Foundation) |
| berries | False | 80.0 | ungrounded: no USDA match |
| oats | True | 40.0 | matched: Oats, raw (Survey (FNDDS)) |
| chia seeds | True | 15.0 | matched: Chia seeds, dry, raw (Foundation) |
| honey | True | 21.3 | matched: Honey (SR Legacy) |
| almonds | True | 15.0 | matched: Nuts, almonds, whole, raw (Foundation) |

### r_019 -- Thai Green Curry Chicken (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 200.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| coconut milk | False | 147.0 | ungrounded: no USDA match for declared state 'canned' |
| green curry paste | True | 20.0 | matched: GREEN CURRY PASTE (Branded) |
| zucchini | True | 80.0 | matched: Squash, summer, green, zucchini, includes skin, raw (Foundation) |
| bell pepper | True | 119.0 | matched: Peppers, bell, green, raw (Foundation) |
| basil | True | 5.0 | matched: Basil, fresh (SR Legacy) |
| jasmine rice | True | 150.0 | matched: JASMINE COOKED RICE, JASMINE (Branded) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |

### r_020 -- Japanese Chicken Teriyaki Bowl (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| chicken breast | True | 200.0 | matched: Chicken, breast, boneless, skinless, raw (Foundation) |
| white rice | True | 180.0 | matched: Rice, cooked, NFS (Survey (FNDDS)) |
| broccoli | True | 70.0 | matched: Broccoli, raw (Foundation) |
| carrot | True | 61.0 | matched: Carrots, baby, raw (Foundation) |
| soy sauce | True | 22.0 | matched: Soy sauce (Survey (FNDDS)) |
| honey | True | 14.2 | matched: Honey (SR Legacy) |
| garlic | True | 5.0 | matched: Garlic, raw (Foundation) |
| ginger | True | 5.0 | matched: Spices, ginger, ground (SR Legacy) |

### r_021 -- Indian Paneer Pea Curry (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| paneer | True | 150.0 | matched: PANEER (Branded) |
| peas | True | 100.0 | matched: PEAS (Branded) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |
| ginger | True | 5.0 | matched: Spices, ginger, ground (SR Legacy) |
| basmati rice | False | 150.0 | ungrounded: no USDA match for declared state 'cooked' |
| spinach | True | 40.0 | matched: Spinach, baby (Foundation) |

### r_022 -- Mediterranean Tuna White Bean Salad (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| tuna | True | 150.0 | matched: TUNA (Branded) |
| white beans | True | 120.0 | matched: Beans, white, mature seeds, canned (SR Legacy) |
| cucumber | True | 80.0 | matched: Cucumber, raw (Survey (FNDDS)) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| red onion | True | 50.0 | matched: Onions, red, raw (Foundation) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |
| lemon | True | 15.0 | matched: Lemon, raw (Survey (FNDDS)) |
| parsley | True | 5.0 | matched: Parsley, freeze-dried (SR Legacy) |

### r_023 -- American Beef Quinoa Stuffed Peppers (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| ground beef | True | 180.0 | matched: Beef, ground, raw (Survey (FNDDS)) |
| quinoa | True | 80.0 | matched: Quinoa, uncooked (SR Legacy) |
| bell pepper | True | 238.0 | matched: Peppers, bell, green, raw (Foundation) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| cheddar cheese | True | 40.0 | matched: Cheese, cheddar (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| spinach | True | 30.0 | matched: Spinach, baby (Foundation) |

### r_024 -- Mexican Shrimp Taco Salad (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| shrimp | False | 180.0 | ungrounded: no USDA match |
| lettuce | True | 60.0 | matched: Lettuce, raw (Survey (FNDDS)) |
| black beans | True | 100.0 | matched: Beans, black turtle, mature seeds, canned (SR Legacy) |
| corn | True | 70.0 | matched: Corn, sweet, white, raw (SR Legacy) |
| avocado | True | 75.0 | matched: Avocados, raw, California (SR Legacy) |
| tomato | True | 123.0 | matched: Tomato, roma (Foundation) |
| lime | True | 15.0 | matched: Limes, raw (SR Legacy) |
| tortilla strips | True | 30.0 | matched: TORTILLA STRIPS, TORTILLA (Branded) |

### r_025 -- Italian White Bean Zucchini Stew (grounded, coverage 100%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| white beans | True | 150.0 | matched: Beans, white, mature seeds, canned (SR Legacy) |
| zucchini | True | 120.0 | matched: Squash, summer, green, zucchini, includes skin, raw (Foundation) |
| tomato | True | 246.0 | matched: Tomato, roma (Foundation) |
| carrot | True | 61.0 | matched: Carrots, baby, raw (Foundation) |
| onion | True | 55.0 | matched: Onions, raw (SR Legacy) |
| garlic | True | 10.0 | matched: Garlic, raw (Foundation) |
| spinach | True | 40.0 | matched: Spinach, baby (Foundation) |
| olive oil | True | 13.7 | matched: Oil, corn, peanut, and olive (SR Legacy) |
