# Grounding report

## Corpus-wide summary
- total recipes processed: 1436
- grounded: 1 (0.1%)
- partial: 1266 (88.2%)
- ungrounded: 169 (11.8%)

**Comparability note (A3 prep):** the pre-A3 baseline (`data/processed/grounding_report_pre_A3_baseline.md`, grounded 0.4% / partial 59.2%) was computed against the OLD, pre-A1 corpus of 4,263 recipes (near-zero unit coverage, 0.35%). The A1 corpus rebuild replaced that corpus with 3,853 active imported recipes + 25 hand-authored seeds and raised unit coverage to 76.14% -- the `total recipes processed` count above states THIS run's corpus size so the before/after grounded/partial/ungrounded percentages are read against the right denominator, not silently compared across two different corpora of different sizes. `data/processed/grounding_report_baseline.md` is a separate, even older snapshot (also pre-A1, from an earlier point in phase 1.5) -- do not confuse the two baseline files.

## Top ungrounded ingredients, corpus-wide (top 50 of up to 50)

| ingredient (normalized) | recipes affected |
|---|---|
| salt | 143 |
| pepper | 134 |
| lemon juice | 106 |
| oil | 98 |
| salt and pepper | 87 |
| onion, chopped | 73 |
| vanilla | 68 |
| garlic, minced | 66 |
| all purpose flour | 57 |
| chili powder | 54 |
| worcestershire sauce | 51 |
| ghee | 42 |
| butter or margarine | 40 |
| vinegar | 34 |
| tomato sauce | 33 |
| curry powder | 32 |
| lime juice | 31 |
| vanilla extract | 31 |
| mayonnaise | 30 |
| butter, melted | 29 |
| cream cheese, softened | 29 |
| margarine | 28 |
| chopped onion | 27 |
| garlic cloves, minced | 26 |
| raisin | 26 |
| dijon mustard | 25 |
| cardamom powder | 25 |
| egg yolk | 25 |
| orange juice | 25 |
| turmeric powder | 25 |
| egg white | 24 |
| red chili powder | 24 |
| green chily | 24 |
| onion, finely chopped | 24 |
| eggs, beaten | 24 |
| chopped parsley | 23 |
| garlic clove | 23 |
| parsley, chopped | 22 |
| bay leaf | 22 |
| granulated sugar | 22 |
| dry mustard | 21 |
| water | 21 |
| chicken breast | 20 |
| egg, beaten | 20 |
| garlic salt | 20 |
| caster sugar | 19 |
| garlic, crushed | 19 |
| parsley | 19 |
| ginger | 19 |
| white vinegar | 19 |

## Tag-vs-computed ratio distribution, corpus-wide (GROUNDED/PARTIAL recipes with a self-reported tag calorie value)

- n: 1267
- mean: 0.69x
- median: 0.37x
- stdev: 1.53
- min: 0.00x
- max: 22.99x

### Ratio outliers (outside [0.4x, 2.5x]) -- report-only, no demotion
- count: 719

| recipe_id | title | tag kcal | computed kcal | ratio |
|---|---|---|---|---|
| imp_0069b6d84ca85358 | Cuba Libre | 194 | 20 | 0.10x |
| imp_00889d58fddd523d | Zesty Burgers | 1605 | 483 | 0.30x |
| imp_00e5b8934fdd5be6 | Sultani Chops | 159 | 37 | 0.23x |
| imp_01149350e3c55dd7 | Chicken Enchilada Casserole | 344 | 3 | 0.01x |
| imp_0162e07475be5491 | Vegetable Fish Fillets | 361 | 0 | 0.00x |
| imp_01791fd6af3f5446 | Low-Carb Taco Patties | 910 | 242 | 0.27x |
| imp_018c01cb43375854 | Cranberry Dessert | 278 | 85 | 0.31x |
| imp_019bed292f785529 | Chicken Green Enchiladas | 607 | 34 | 0.06x |
| imp_02d7caa0ead95b29 | Pork Tenderloins Asian Style | 218 | 72 | 0.33x |
| imp_0311fd2d70eb580d | strawberry tiramisu | 172 | 50 | 0.29x |
| imp_0315627df52d57f0 | Pork Tenderloin on a Vegetable Bed | 245 | 20 | 0.08x |
| imp_03cd238579705c4b | Independence Day Punch | 371 | 4 | 0.01x |
| imp_03fd4e81b77c5ac6 | Tasty Chicken Tacos | 408 | 0 | 0.00x |
| imp_04a68879da525a1a | Muslim Naan | 400 | 6 | 0.02x |
| imp_0513f94f72435dc6 | Special bread | 4219 | 1598 | 0.38x |
| imp_0615f288b7c2559a | Tofu and Scallions | 154 | 39 | 0.25x |
| imp_075e7a8749b85217 | Spicy Picnic Chicken | 232 | 5 | 0.02x |
| imp_07b62b71eefe53be | Asparagus Curry | 198 | 17 | 0.08x |
| imp_07bfacf40ae65227 | Victory Chocolate Cake | 261 | 16 | 0.06x |
| imp_07ff177575b05f50 | Artichokes, Lamb, and Orzo Avgolemono | 783 | 224 | 0.29x |
| imp_08ffd78d477452af | Rack of Spring Lamb with Roasted Garlic | 150 | 50 | 0.33x |
| imp_09201e69e21a5bcd | Chicken and Sweet Potatoes | 238 | 83 | 0.35x |
| imp_0a185dbac4965096 | Spicy Vegetarian Chili | 124 | 37 | 0.30x |
| imp_0a3e02ca67f45f4d | Chicken Breasts With Spicy Rub | 370 | 100 | 0.27x |
| imp_0a5183cadeaf5c26 | Triple Cheeseburgers | 925 | 246 | 0.27x |
| imp_0a52b43c070e5038 | Aviyal | 1048 | 36 | 0.03x |
| imp_0a6313f8899e5251 | Mysorepaak | 6651 | 1146 | 0.17x |
| imp_0a647fd8e6c45948 | Cake Fantasy | 315 | 40 | 0.13x |
| imp_0a93e32006c255a1 | Halloumi and Vegetable Kebabs | 41 | 277 | 6.80x |
| imp_0ad4f85b481e576e | Samantha's Fabulous Chicken and Eggplant (Aubergine) | 1466 | 492 | 0.34x |
| imp_0b1d2389a67f515b | Tapenade | 396 | 152 | 0.38x |
| imp_0b7b7974a1c7590f | BULGOGI (marinated grilled beef) | 2136 | 845 | 0.40x |
| imp_0bb609793a4856f5 | Cranberry Applesauce | 335 | 0 | 0.00x |
| imp_0beb87f691985bc7 | Fried Quail | 447 | 53 | 0.12x |
| imp_0c2061063a27551b | Fried Bhindi | 250 | 0 | 0.00x |
| imp_0c3bdac7916451bc | Healthy Banana Nut Bread | 1905 | 573 | 0.30x |
| imp_0cbe3d5057955acd | Lettuce and Egg salad | 240 | 55 | 0.23x |
| imp_0cc2f80052055f3b | Sweet/Sour Lime Pickle | 245 | 96 | 0.39x |
| imp_0ce79d65437e54bb | Kadukash ( Sindhi Mango Pickle) | 1187 | 1 | 0.00x |
| imp_0d6da76dcbf15055 | Pork Chops with Garlic and Onions (Suon Uop Hanh Toi Nuong) | 348 | 48 | 0.14x |
| imp_0e054aaf4d045d93 | Big Apple | 357 | 117 | 0.33x |
| imp_100fa62eb1bc57a9 | Mustard and Wine Marinated Lamb Chops | 58 | 0 | 0.00x |
| imp_1036024b43af5a0e | Margo Knudson's Chili Con Carne | 1688 | 54 | 0.03x |
| imp_11304e5763db512b | Betty's Fumi Salad | 160 | 4 | 0.03x |
| imp_11e838ae1d30506b | M'Juderah (Lebanese rice and lentils) | 561 | 60 | 0.11x |
| imp_12016158aeba57af | Audrey's Oriental Chicken | 315 | 17 | 0.06x |
| imp_12ed354ae2aa5010 | Mild Spicy Garlic Chicken on Seasoned Pita Bread | 918 | 208 | 0.23x |
| imp_14b4e53206515b00 | Blue Ribbon Burgers | 943 | 353 | 0.37x |
| imp_14e5422027cd5a44 | Artichoke and Lamb Shanks Crock Pot Dinner | 881 | 11 | 0.01x |
| imp_1501688d73a356ce | Easy Sticky Pecan Rolls | 2012 | 737 | 0.37x |
| imp_150b269300625834 | Chicken and Broccoli Braid | 574 | 0 | 0.00x |
| imp_150c60c3f4dc5e17 | Crawfish or Shrimp Fettuccini | 602 | 172 | 0.29x |
| imp_152f476c9e8a53a9 | Green Chile Sauce | 82 | 9 | 0.11x |
| imp_153ba44b77385dbc | Raspberry Meringue Crunch | 290 | 70 | 0.24x |
| imp_15695a57bbdd5064 | Healthy Oatmeal Yogurt Bran Muffins | 245 | 16 | 0.07x |
| imp_15cc1f3212ba5340 | Longhorn Chili Dip | 432 | 152 | 0.35x |
| imp_1646018c28af52e3 | Marions Best Ever Apple Pie | 326 | 55 | 0.17x |
| imp_16478e997f3f5409 | Walter's Potato, Bacon, Corn Chowder | 392 | 61 | 0.16x |
| imp_16d4b24ae3325606 | SU-NO-MO-NO SALAD | 84 | 6 | 0.07x |
| imp_16d5a5b126aa5817 | BBQ Ribs | 1301 | 0 | 0.00x |
| imp_1725ba99e8cf511d | Creamy Loaf | 546 | 143 | 0.26x |
| imp_17959603cc0850ba | Beef and Cabbage Joes | 536 | 121 | 0.23x |
| imp_18281aa767f350aa | Jarlsberg Oven Omelet | 353 | 62 | 0.18x |
| imp_18e166d6e5a85e2d | Tomato Salsa (adopted) | 22 | 0 | 0.00x |
| imp_18f0123f30015203 | Black Bean Casserole | 95 | 12 | 0.12x |
| imp_1959d5cedc0a58c5 | Rosemary Chicken | 760 | 128 | 0.17x |
| imp_195e2de3cdfa5beb | Chocolate Earthquake Cake | 754 | 190 | 0.25x |
| imp_1a1d777d778c5d4d | No Sugar Apple Pie | 437 | 98 | 0.22x |
| imp_1a48eabb123f59f2 | Mic's Wonderful HOT Wings | 431 | 1275 | 2.96x |
| imp_1a4f1cfe9c4953bf | Mushroom Stuffed Flank Steak | 374 | 41 | 0.11x |
| imp_1a575f276bde5532 | Tomato Beef | 204 | 28 | 0.14x |
| imp_1b06fe5fd2c4525f | Baked Salmon with Orange Juice | 258 | 21 | 0.08x |
| imp_1b11a11453a15361 | Tomato Pappu | 348 | 30 | 0.09x |
| imp_1b481914bde45b7b | Chilled Dal Shorba | 519 | 189 | 0.36x |
| imp_1b707c8a4467522c | Turkey Club | 386 | 14 | 0.04x |
| imp_1b9fdfaaf0a653da | Crispy Scallops with Soy Dipping Sauce | 263 | 35 | 0.13x |
| imp_1bd1196e98735b18 | Cornbread Dressing Salad | 123 | 22 | 0.18x |
| imp_1bddb75b465a5153 | Broccoli Cornbread | 593 | 18 | 0.03x |
| imp_1bf9a6aa21905141 | Crock Pot Pizza | 1213 | 57 | 0.05x |
| imp_1d1666ac888c5949 | John Wayne Casserole | 795 | 246 | 0.31x |
| imp_1d53f2b381b2588c | Vegetarian White Bean Soup | 189 | 40 | 0.21x |
| imp_1d7247f6c0505f62 | Braised Prawns with Vegetables | 242 | 36 | 0.15x |
| imp_1dac2da90fd753ab | Wheaten Bread | 2024 | 0 | 0.00x |
| imp_1ddd83912ad55fcc | Peasant Capers | 100 | 0 | 0.00x |
| imp_1def8b086a2954c7 | Rice with a Chilean Flair | 260 | 5 | 0.02x |
| imp_1e9d2ddd31905c52 | Punjabi Bhindi Masala | 833 | 330 | 0.40x |
| imp_1eff8547934d59b0 | Veloute (used for "Lobster enchiladas w/white wine sauce") | 8672 | 1667 | 0.19x |
| imp_1f940ed838ca5cff | Balti Butter Chicken | 837 | 191 | 0.23x |
| imp_1fb271c80d8f5698 | Phoney Abalone | 502 | 96 | 0.19x |
| imp_1fb2b083fe2b5399 | Chicken Piccata | 486 | 183 | 0.38x |
| imp_1fda88fa5b0657d3 | Easy Braised Pork Chops | 381 | 20 | 0.05x |
| imp_1ff9a90aa7685b44 | Turkey Soup Continental | 244 | 0 | 0.00x |
| imp_201b7541f19454f1 | Teriyaki Grilled Chicken Kabobs | 408 | 26 | 0.06x |
| imp_20aa165119f35b4c | Spicy Cucumber Salad | 65 | 2 | 0.03x |
| imp_2112d611c15c5b03 | Sue's Seafood Jambalaya | 517 | 110 | 0.21x |
| imp_2141ee80e1fa53db | Easy Chocolate Dipping Sauce | 406 | 147 | 0.36x |
| imp_22621218ee6c52b5 | Raisin Cinnamon Scones | 159 | 62 | 0.39x |
| imp_22925f0d310656b4 | Triple Layer Cookie Bars | 183 | 37 | 0.20x |
| imp_22b6f75444935157 | Caramel Pecan Pie | 634 | 96 | 0.15x |
| imp_236b3f4504c05ed1 | Sausage and Potatoes | 583 | 169 | 0.29x |
| ... | (619 more, see full count above) | | | |

## Corpus-wide implausible kcal/serving band (<20 or >2000), GROUNDED/PARTIAL only
- count: 284

## Corpus-wide ingredient-occurrence terminal outcomes (what actually happens to every ingredient row)

Every ingredient occurrence in the corpus lands in EXACTLY ONE of the buckets below (mutually exclusive, and reconciled at grounding time to sum to the corpus's total ingredient-row count -- see `grounding_job._terminal_outcome_for_ingredient`). This is the table that explains ungroundedness; the rejection-counts table further below does NOT.

| outcome | count | % of occurrences |
|---|---|---|
| grounded | 3622 | 27.5% |
| no_unit | 3260 | 24.8% |
| unit_unconvertible | 5299 | 40.3% |
| no_relevant_candidate | 826 | 6.3% |
| all_candidates_rejected | 142 | 1.1% |

## Individual-candidate rejection counts by reason, corpus-wide (NOT a table of ungroundedness causes)

**Read this table carefully.** Each count is the number of individual FDC CANDIDATES skipped during matching for the reason shown -- tallied once per candidate, across every `search_food` call this run made. It is NOT a count of queries/occurrences that failed to ground, and it is NOT a list of "why ingredients are ungrounded" (see the terminal-outcome table above for that). A query whose candidate was skipped here may still have gone on to ground successfully via a later candidate or the Branded fallback -- e.g. `processed_state_modifier:creamed` is almost entirely the imported corpus's egg occurrences correctly skipping an 'Egg, creamed' candidate while still grounding fine against a different candidate.

| reason | candidates skipped |
|---|---|
| kcal_too_low_branded | 664 |
| processed_state_modifier:creamed | 197 |
| atwater_mismatch | 157 |
| branded_high_dispersion | 115 |
| processed_state_modifier:dehydrated | 34 |
| processed_state_modifier:smoked | 34 |
| processed_state_modifier:juice | 24 |
| processed_state_modifier:sweetened | 22 |
| processed_state_modifier:powdered | 18 |
| processed_state_modifier:sauce | 15 |
| processed_state_modifier:fried | 11 |
| processed_state_modifier:pickled | 10 |
| processed_state_modifier:candied | 9 |
| processed_state_modifier:cured | 5 |
| mass_over_105g | 4 |
| processed_state_modifier:soup | 3 |
| processed_state_modifier:syrup | 1 |

## Branded-tier high-dispersion queries, corpus-wide (3+ candidates, >3.0x calorie spread -- left ungrounded)

- count: 115

| query | min kcal | max kcal | candidates |
|---|---|---|---|
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| cherry tomatoe | 21 | 346 | 5 |
| garlic, minced | 67 | 213 | 17 |
| ocean spray cranberry | 33 | 429 | 6 |
| garlic, minced | 67 | 213 | 17 |
| orange juice | 45 | 183 | 25 |
| garlic, minced | 67 | 213 | 17 |
| pineapple chunk | 36 | 375 | 23 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| sliced mushroom | 7 | 33 | 24 |
| sliced mushroom | 7 | 33 | 24 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| chopped garlic | 67 | 500 | 14 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| pasta sauce | 31 | 520 | 25 |
| pumpkin pie filling | 62 | 278 | 3 |
| hash brown | 82 | 368 | 4 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| minced garlic | 67 | 213 | 19 |
| carrot, diced | 9 | 49 | 8 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| strawberry gelatin | 67 | 400 | 6 |
| strawberry | 85 | 350 | 7 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| strawberry | 85 | 350 | 7 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| peppercorn ranch dressing | 83 | 586 | 14 |
| garlic, minced | 67 | 213 | 17 |
| strawberry | 85 | 350 | 7 |
| peach slice | 36 | 386 | 8 |
| pineapple chunk | 36 | 375 | 23 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| pina colada mix | 27 | 178 | 8 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| rotini pasta | 114 | 375 | 10 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| french style green bean | 11 | 41 | 25 |
| pineapple chunk | 36 | 375 | 23 |
| spaghetti | 104 | 375 | 25 |
| gelatin | 25 | 429 | 8 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| orange juice | 45 | 183 | 25 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| catfish fillet | 71 | 268 | 15 |
| tuna steak | 53 | 181 | 6 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, chopped | 67 | 500 | 15 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| cut green bean | 12 | 37 | 25 |
| mushrooms, sliced | 7 | 33 | 24 |
| chopped garlic | 67 | 500 | 14 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| orange juice | 45 | 183 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |

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
