# Grounding report

## Corpus-wide summary
- total recipes processed: 109
- grounded: 0 (0.0%)
- partial: 60 (55.0%)
- ungrounded: 49 (45.0%)

**Comparability note (A3 prep):** the pre-A3 baseline (`data/processed/grounding_report_pre_A3_baseline.md`, grounded 0.4% / partial 59.2%) was computed against the OLD, pre-A1 corpus of 4,263 recipes (near-zero unit coverage, 0.35%). The A1 corpus rebuild replaced that corpus with 3,853 active imported recipes + 25 hand-authored seeds and raised unit coverage to 76.14% -- the `total recipes processed` count above states THIS run's corpus size so the before/after grounded/partial/ungrounded percentages are read against the right denominator, not silently compared across two different corpora of different sizes. `data/processed/grounding_report_baseline.md` is a separate, even older snapshot (also pre-A1, from an earlier point in phase 1.5) -- do not confuse the two baseline files.

## Top ungrounded ingredients, corpus-wide (top 50 of up to 50)

| ingredient (normalized) | recipes affected |
|---|---|
| oil | 4 |
| whipping cream | 4 |
| orange juice | 4 |
| salt and pepper | 4 |
| almond extract | 3 |
| semi sweet chocolate chip | 3 |
| salt & pepper | 3 |
| ice cube | 3 |
| granulated sugar | 2 |
| walnut | 2 |
| ginger, ground | 2 |
| all purpose flour | 2 |
| butter | 2 |
| peach preserve | 2 |
| % milk | 2 |
| boiling water | 2 |
| cool whip | 2 |
| vanilla extract | 2 |
| margarine | 2 |
| cream | 2 |
| white bread | 2 |
| cheese, grated | 2 |
| black pepper, ground | 2 |
| cranberry | 2 |
| white candy coating | 2 |
| drops green food coloring | 2 |
| potatoe | 2 |
| fruit | 2 |
| ginger ale | 2 |
| peanut oil | 2 |
| envelope lipton onion soup mix | 2 |
| bottle liquid pectin | 2 |
| ginger ale, chilled | 2 |
| champagne, chilled | 2 |
| rice vinegar | 2 |
| ground clove | 1 |
| salad oil | 1 |
| pumpkin | 1 |
| seedless raisin | 1 |
| mashed potatoe | 1 |
| corn flakes, crushed | 1 |
| sifting | 1 |
| hop | 1 |
| powdered sugar | 1 |
| cherry pie filling | 1 |
| bread, buttered | 1 |
| shrimp | 1 |
| seafood cocktail sauce | 1 |
| white sugar or sugar | 1 |
| citrus peel, some cut with a peeler and some with a zester | 1 |

## Tag-vs-computed ratio distribution, corpus-wide (GROUNDED/PARTIAL recipes with a self-reported tag calorie value)

- n: 60
- mean: 1.18x
- median: 0.42x
- stdev: 4.99
- min: 0.00x
- max: 38.93x

### Ratio outliers (outside [0.4x, 2.5x]) -- report-only, no demotion
- count: 30

| recipe_id | title | tag kcal | computed kcal | ratio |
|---|---|---|---|---|
| imp_025c90934851588b | Pumpkin Spice Cake in Jars | 378 | 15 | 0.04x |
| imp_0cc9a4f295485d98 | Peachy Cheesecake | 170 | 24 | 0.14x |
| imp_1170f8f898445d34 | Fried Cornbread | 611 | 0 | 0.00x |
| imp_19f9ad96919459cf | Lemon Cookies I | 71 | 21 | 0.30x |
| imp_1b9cd177ee285a81 | Rock Candy | 1548 | 0 | 0.00x |
| imp_29fa5e33ef3b5c19 | Kraft Caramel Popcorn Balls | 266 | 0 | 0.00x |
| imp_2c7a98fa5d855ef4 | Strawberry Dump Cake | 4955 | 549 | 0.11x |
| imp_3aace76572455a45 | Heavenly Hash Candy | 62 | 2418 | 38.93x |
| imp_47dbd4328e9d598d | Chocolate Brandy Balls | 110 | 23 | 0.21x |
| imp_59fd2f7c657653db | Angel Food Cake Waldorf | 614 | 36 | 0.06x |
| imp_5b974b2773095cf3 | Sizzler's Cheese Toast | 176 | 40 | 0.23x |
| imp_659d74d531765cbc | Party Punch | 3219 | 764 | 0.24x |
| imp_6e233945e51c5af4 | Microwave Truffles | 976 | 256 | 0.26x |
| imp_75afbf9200e55e1a | Strawberry Punch #1 | 43 | 4 | 0.08x |
| imp_76145255ecfd52c8 | Deb's Zabaglione | 307 | 72 | 0.23x |
| imp_77ee996404cd5ac0 | Mascarpone Cheese - Substitute - Homemade | 907 | 96 | 0.11x |
| imp_82150b191e4c5281 | Beer Can Chicken | 772 | 31 | 0.04x |
| imp_834e36551bbb5242 | Copycat Coffee House Whipped Cappuccino | 274 | 96 | 0.35x |
| imp_8e33ad72f3425fb7 | Peachy Pork Picante | 384 | 10 | 0.03x |
| imp_989a7052e7b8588c | Roast Prime Rib of Beef | 48 | 143 | 2.96x |
| imp_a48ecaef134e5170 | Easy Pita Pockets | 742 | 204 | 0.28x |
| imp_a813ab777be956df | Chicken and Spinach Veloute | 911 | 273 | 0.30x |
| imp_b03c2910ca245f10 | Coconut Drops | 5018 | 1853 | 0.37x |
| imp_b22fa02f96be5877 | Gypsy Tart | 480 | 89 | 0.18x |
| imp_c68e4e50738a5dc6 | Eagle Brand Irish Cream Liqueur | 867 | 21 | 0.02x |
| imp_c89e4bd07d4a5842 | Homemade Butter II | 616 | 0 | 0.00x |
| imp_d72d88450f525a41 | Instant Cappuccino Mix | 811 | 131 | 0.16x |
| imp_e04f1b9cff48523c | Deviled Ham Spread | 1656 | 38 | 0.02x |
| imp_e7290e0ac5ab5fe4 | Margarita Mix | 2640 | 681 | 0.26x |
| imp_fd28b69b085c5986 | Almond Joy Fudge Brownies | 407 | 24 | 0.06x |

## Corpus-wide implausible kcal/serving band (<20 or >2000), GROUNDED/PARTIAL only
- count: 13

## Corpus-wide ingredient-occurrence terminal outcomes (what actually happens to every ingredient row)

Every ingredient occurrence in the corpus lands in EXACTLY ONE of the buckets below (mutually exclusive, and reconciled at grounding time to sum to the corpus's total ingredient-row count -- see `grounding_job._terminal_outcome_for_ingredient`). This is the table that explains ungroundedness; the rejection-counts table further below does NOT.

| outcome | count | % of occurrences |
|---|---|---|
| grounded | 81 | 17.8% |
| no_unit | 138 | 30.4% |
| unit_unconvertible | 172 | 37.9% |
| no_relevant_candidate | 56 | 12.3% |
| all_candidates_rejected | 7 | 1.5% |

## Individual-candidate rejection counts by reason, corpus-wide (NOT a table of ungroundedness causes)

**Read this table carefully.** Each count is the number of individual FDC CANDIDATES skipped during matching for the reason shown -- tallied once per candidate, across every `search_food` call this run made. It is NOT a count of queries/occurrences that failed to ground, and it is NOT a list of "why ingredients are ungrounded" (see the terminal-outcome table above for that). A query whose candidate was skipped here may still have gone on to ground successfully via a later candidate or the Branded fallback -- e.g. `processed_state_modifier:creamed` is almost entirely the imported corpus's egg occurrences correctly skipping an 'Egg, creamed' candidate while still grounding fine against a different candidate.

| reason | candidates skipped |
|---|---|
| kcal_too_low_branded | 13 |
| branded_high_dispersion | 6 |
| atwater_mismatch | 5 |
| processed_state_modifier:creamed | 3 |
| processed_state_modifier:sweetened | 3 |
| processed_state_modifier:juice | 2 |
| processed_state_modifier:powdered | 2 |
| processed_state_modifier:pickled | 1 |
| processed_state_modifier:cured | 1 |
| mass_over_105g | 1 |

## Branded-tier high-dispersion queries, corpus-wide (3+ candidates, >3.0x calorie spread -- left ungrounded)

- count: 6

| query | min kcal | max kcal | candidates |
|---|---|---|---|
| pumpkin | 29 | 400 | 25 |
| cranberry | 50 | 375 | 3 |
| fruit punch | 12 | 375 | 24 |
| strawberry | 85 | 350 | 7 |
| mushrooms, sliced | 7 | 33 | 24 |
| salmon fillet | 71 | 283 | 12 |

## Seed macro-computation accuracy (pre-registered A3 eval)

Pre-registered gate (docs/ROADMAP.md item A3): "macro-computation accuracy measured against the 25 hand-authored seed recipes as ground truth." These metric definitions (see `SeedMacroAccuracy`/`compute_seed_macro_accuracy` in `app/services/grounding_job.py`) were fixed BEFORE the corpus-wide A3 grounding run and are not adjusted after seeing results. A seed contributes to a macro's error only when its status is GROUNDED or PARTIAL (an UNGROUNDED seed has no real computed value) AND it has a non-null, non-zero self-reported tag value for that macro -- every seed excluded either way is counted as "missing" below, never silently dropped. **kcal is the PRIMARY metric.**

- seeds: 0 total -- 0 grounded, 0 partial, 0 ungrounded

| macro | n compared | median abs relative error | mean abs relative error | missing (excluded) |
|---|---|---|---|---|
| **kcal (PRIMARY)** | 0 | n/a | n/a | 0 |
| protein_g | 0 | n/a | n/a | 0 |
| carbs_g | 0 | n/a | n/a | 0 |
| fat_g | 0 | n/a | n/a | 0 |

## Seed tag-vs-computed comparison (0 recipes)

| recipe_id | title | status | coverage | tag kcal | computed kcal | ratio |
|---|---|---|---|---|---|---|

## Flags: raw/cooked-scale blowup (>1.6x)
None.

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
