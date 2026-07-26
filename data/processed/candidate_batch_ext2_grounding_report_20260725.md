# Grounding report

## Corpus-wide summary
- total recipes processed: 3146
- grounded: 8 (0.3%)
- partial: 2705 (86.0%)
- ungrounded: 433 (13.8%)

**Comparability note (A3 prep):** the pre-A3 baseline (`data/processed/grounding_report_pre_A3_baseline.md`, grounded 0.4% / partial 59.2%) was computed against the OLD, pre-A1 corpus of 4,263 recipes (near-zero unit coverage, 0.35%). The A1 corpus rebuild replaced that corpus with 3,853 active imported recipes + 25 hand-authored seeds and raised unit coverage to 76.14% -- the `total recipes processed` count above states THIS run's corpus size so the before/after grounded/partial/ungrounded percentages are read against the right denominator, not silently compared across two different corpora of different sizes. `data/processed/grounding_report_baseline.md` is a separate, even older snapshot (also pre-A1, from an earlier point in phase 1.5) -- do not confuse the two baseline files.

## Top ungrounded ingredients, corpus-wide (top 50 of up to 50)

| ingredient (normalized) | recipes affected |
|---|---|
| salt and pepper | 343 |
| salt | 260 |
| lemon juice | 257 |
| pepper | 252 |
| oil | 217 |
| vanilla | 189 |
| all purpose flour | 156 |
| garlic, minced | 146 |
| onion, chopped | 137 |
| mayonnaise | 99 |
| worcestershire sauce | 96 |
| chopped parsley | 94 |
| orange juice | 93 |
| butter or margarine | 83 |
| chopped onion | 80 |
| chili powder | 79 |
| vinegar | 77 |
| vanilla extract | 76 |
| butter, melted | 74 |
| ground cinnamon | 69 |
| garlic cloves, minced | 68 |
| ground black pepper | 65 |
| white sugar | 65 |
| cayenne pepper | 65 |
| tomato sauce | 62 |
| cream cheese, softened | 60 |
| butter | 56 |
| dijon mustard | 56 |
| chicken breast | 55 |
| raisin | 55 |
| margarine | 53 |
| white vinegar | 53 |
| shortening | 52 |
| cumin | 52 |
| thyme | 51 |
| eggs, beaten | 51 |
| water | 51 |
| chicken stock | 50 |
| ground cumin | 50 |
| buttermilk | 50 |
| extra virgin olive oil | 49 |
| freshly ground black pepper | 49 |
| ground ginger | 48 |
| parmesan | 48 |
| dry mustard | 48 |
| egg yolk | 46 |
| ketchup | 46 |
| lime juice | 46 |
| boiling water | 45 |
| granulated sugar | 44 |

## Tag-vs-computed ratio distribution, corpus-wide (GROUNDED/PARTIAL recipes with a self-reported tag calorie value)

- n: 2713
- mean: 0.60x
- median: 0.35x
- stdev: 1.29
- min: 0.00x
- max: 28.82x

### Ratio outliers (outside [0.4x, 2.5x]) -- report-only, no demotion
- count: 1545

| recipe_id | title | tag kcal | computed kcal | ratio |
|---|---|---|---|---|
| imp_00269fc5f5445b43 | Hong Kong Baby Corn Delight | 369 | 94 | 0.25x |
| imp_0028d729228e57ed | Heavenly Cheesecake Swirl Brownies | 150 | 12 | 0.08x |
| imp_003f92b19e125098 | Pollo Rio Negro (Marinated Chicken) | 464 | 7 | 0.01x |
| imp_00eeb9ef53ab5b5f | Potato Egg Bake | 575 | 61 | 0.11x |
| imp_011715bbb4ba5d5b | Another broccoli Chicken (Brassica oleracea -Gallus domesticus) | 41 | 0 | 0.00x |
| imp_0127720131345933 | Garlic Soup | 485 | 128 | 0.26x |
| imp_012a44451e4f5ad1 | Lennie's Ultimate Rice Pudding | 229 | 1 | 0.01x |
| imp_0173f50642635bb0 | Muffuletta | 263 | 0 | 0.00x |
| imp_01f636eab6a753ef | Pumpkin Spice Cake with Maple Icing | 485 | 5165 | 10.64x |
| imp_023509c2190c5adb | Fresh Pumpkin Pie | 356 | 24 | 0.07x |
| imp_02912dd656535dcb | Baked Sesame Chicken | 680 | 85 | 0.13x |
| imp_02a3b4ccd76358bf | Never-Fail Chocolate Souffles | 240 | 10 | 0.04x |
| imp_030b610668ae59df | Fabulous Hot Chocolate | 315 | 116 | 0.37x |
| imp_031f3dc9d05f5fe6 | Meatball Soup With Cabbage and Parmesan Cheese | 332 | 128 | 0.39x |
| imp_0345a62492875db1 | Tuna Fish Casserole | 295 | 32 | 0.11x |
| imp_0392fa6fe116575d | Coconut Pork and Chilli Chutney | 404 | 18 | 0.04x |
| imp_03f7405d3a3c5122 | Party Meatballs | 505 | 116 | 0.23x |
| imp_044939f1f60c5c83 | Paula's Easy Carrot Cake | 1289 | 4149 | 3.22x |
| imp_04c81f0db4fe575b | Music Parents Famous Frito Pie | 459 | 2447 | 5.33x |
| imp_0510effbf0f15075 | Stuffed Italian Sandwich | 3366 | 1022 | 0.30x |
| imp_0522c1749dde5113 | Ultra-Easy Pumpkin Pie Squares | 443 | 91 | 0.21x |
| imp_05483533c3e551f1 | Spicy Eggplant (Aubergine) | 127 | 30 | 0.23x |
| imp_054f4ff6fe9b590c | Chilled Calamari in a Yoghurt Curry Cream | 522 | 64 | 0.12x |
| imp_0553b4776d625c6c | Oreo Mint Cocoa | 368 | 113 | 0.31x |
| imp_05549c78f0cb5811 | Ham and Cheese Stuffed Potatoes | 566 | 45 | 0.08x |
| imp_057cbc1a3927514c | Burmahs' Bananas | 606 | 239 | 0.40x |
| imp_05995d245eab5e63 | Fat Free Tomato Sauce | 47 | 1 | 0.03x |
| imp_059b35bf957155d1 | Easy Chicken Cacciatore | 749 | 209 | 0.28x |
| imp_05a9144d4a8e58b2 | Vegetable Frittata With Roasted Tomato Salsa | 181 | 21 | 0.11x |
| imp_05b9c18f0be15384 | Sunflower Fruit Cole Slaw | 95 | 10 | 0.10x |
| imp_05bf1e62ba555992 | Honey Mustard Curry Chicken | 346 | 85 | 0.25x |
| imp_05d106c79ee9586a | Marinara Sauce | 93 | 35 | 0.38x |
| imp_05f2dd7cf60950c3 | Bok Choi for Selina | 125 | 9 | 0.07x |
| imp_0603cb5257ea5ff6 | Rich French Onion Soup | 338 | 102 | 0.30x |
| imp_06b34ff471605af1 | Veggie Pizza | 509 | 115 | 0.23x |
| imp_06be71c71b765eed | Potato Soup With Two Cheeses | 653 | 130 | 0.20x |
| imp_06c086899d235b7c | Easy Mexican Pozole Soup (Crock Pot) | 643 | 78 | 0.12x |
| imp_06e925ffca6a5a90 | Chicken Breasts with Sun-Dried Tomato Sauce | 307 | 15 | 0.05x |
| imp_06e9bf6b6aec5ea4 | Cilantro-Scented Tofu Rice Salad | 675 | 62 | 0.09x |
| imp_0702af4536585a99 | Chicken and Apples in Cream | 300 | 116 | 0.39x |
| imp_0708f82b6c51534c | Rocky-Road Brownies | 198 | 0 | 0.00x |
| imp_072845e3f8e35608 | Thai Cucumber Salad With Roasted Peanuts | 80 | 12 | 0.15x |
| imp_0794ed4e204f5519 | Lentil Soup with Sausage | 381 | 20 | 0.05x |
| imp_07990cf36d165a25 | Sushi-Style Roll-Ups | 1282 | 24 | 0.02x |
| imp_07a93315a1e65269 | Quick Apple Turnovers | 196 | 28 | 0.15x |
| imp_07c906be9e1550b3 | Bergy Dim Sum #1, Pork & Lettuce Rolls | 121 | 1 | 0.01x |
| imp_07db4db430075ec8 | Chocolate Oat Bran Cookies With Chocolate Chips | 70 | 7 | 0.10x |
| imp_07dec441177d5d64 | Mexican Layer Dip - Low Fat | 167 | 45 | 0.27x |
| imp_07fddf4517815801 | Lemon Shortbread | 60 | 7 | 0.11x |
| imp_084a9b58cdad5b96 | Sleepy Time Mocha Coffee Mix | 487 | 144 | 0.30x |
| imp_0850473fb89d5cac | Sausage Cheese Balls | 809 | 196 | 0.24x |
| imp_0863633c21fb5641 | Dad's Favorite Pie Crust | 2485 | 935 | 0.38x |
| imp_088e9e19e5395268 | Myrtlewood Pecan Pie | 736 | 225 | 0.31x |
| imp_08d6db54d7fb55c9 | Cheese and Honey Pie | 519 | 127 | 0.25x |
| imp_08ef76ad9cd5557b | Spicy Peanut Sauce | 67 | 9 | 0.14x |
| imp_090bfd56bb145121 | Mifgash Mushrooms | 32 | 1 | 0.03x |
| imp_094bb6c6cbb75320 | HAM TURNOVERS (USDA) | 348 | 0 | 0.00x |
| imp_0967bb78a1155ac0 | Fried Potatoes Without the Fry | 200 | 30 | 0.15x |
| imp_0986a3ddb8c453e9 | Mom's Quick Tuna | 138 | 1 | 0.01x |
| imp_09c45133efd55406 | Broccoli and Leek Puree | 301 | 89 | 0.30x |
| imp_09d496d3bf4b5916 | Sausage and bows | 634 | 17 | 0.03x |
| imp_0a1f120648005fe9 | Crab Nibbles | 413 | 2 | 0.01x |
| imp_0a3c29c452e650a1 | Broccoli Salad | 357 | 119 | 0.33x |
| imp_0a3ead274df55bec | Chicken, Cabbage & Apple Casserole | 473 | 20 | 0.04x |
| imp_0ac8a5a0090c5ac3 | Pear Halves Poached in Sangria With Toffee and Cream | 650 | 199 | 0.31x |
| imp_0b07e5f4b2df5eef | Chicken and Sweet Potato Croquettes | 91 | 17 | 0.19x |
| imp_0b75aebac90255af | BLT Muffins | 1636 | 213 | 0.13x |
| imp_0bf0bdef3e4d5663 | Piña Colada Cola Cake | 463 | 3123 | 6.75x |
| imp_0c058dbd94f8509f | Mashed Garlic & Onion Potatoes | 225 | 20 | 0.09x |
| imp_0c4b22cbe08053ae | Stir fried Garlic Beef with Broccoli | 276 | 10 | 0.04x |
| imp_0c5110e55dfe5921 | Pickled Green Beans | 85 | 4 | 0.04x |
| imp_0c67c942587b519b | Chicken Egg Foo Yong | 107 | 1 | 0.01x |
| imp_0c694b9743875317 | Stoemp With Caramelized Shallots | 370 | 25 | 0.07x |
| imp_0ca00a063fc95c37 | Individual Pumpkin Pies | 82 | 3 | 0.04x |
| imp_0d9f2e5f10695091 | Macadamia-Pear Tart | 194 | 41 | 0.21x |
| imp_0da21146e47e5ae1 | Chicken-Avocado Sandwich Wrap | 608 | 148 | 0.24x |
| imp_0dc1adf081d953d4 | Fruit Kebabs with Honey Cardamom Syrup | 78 | 22 | 0.28x |
| imp_0dd507ecb0f3532b | Eggless Chocolate Sponge Cake | 660 | 154 | 0.23x |
| imp_0e2fa29497085f59 | Scalloped Corn | 169 | 25 | 0.15x |
| imp_0e36d615f8f254d1 | Ham Potato Scallop | 529 | 92 | 0.17x |
| imp_0ea53fba0a9d5305 | Gholar Dal | 24 | 4 | 0.17x |
| imp_0eadcd36f1525d8e | Rosemary Scones | 120 | 31 | 0.26x |
| imp_0ee16b33e86f5863 | No Crust Broccoli Quiche | 110 | 39 | 0.35x |
| imp_0ef1adf3107c5a5c | Chocolate Shortbread X-Mas Trees | 127 | 34 | 0.27x |
| imp_0ef531bc46c8520b | Lentil and Pea Soup (Ham Hocks) | 140 | 10 | 0.07x |
| imp_0ef89be4d15058a6 | Bumya Turkish Okra | 198 | 30 | 0.15x |
| imp_0f0ae64d8b9559e8 | Huachinango a la Veracruzano orRed Snapper in Tomato Sauce | 157 | 20 | 0.13x |
| imp_0f30fd2fba3b5326 | Coconutty Macaroons | 119 | 45 | 0.38x |
| imp_0f38bdd09a325029 | Parcelled Salmon With a Pesto Crust | 477 | 29 | 0.06x |
| imp_0f804587273a5652 | Chicken Jerusalem | 623 | 172 | 0.28x |
| imp_0f8dd23dd66c5d75 | Pineapple Drop Cookies | 282 | 5 | 0.02x |
| imp_0ffa1bbf6b745cad | Potato Chip Cookies | 677 | 96 | 0.14x |
| imp_0ffcd77ad4e75657 | Green Rice Chile Bake | 1043 | 256 | 0.25x |
| imp_1018fbc490a85ffa | Knuckles of Lamb in Red Wine | 93 | 9 | 0.09x |
| imp_1075a51003385b1a | Garlic Lover's Chicken | 271 | 30 | 0.11x |
| imp_116eb1d6db0f5a48 | Cabbage Guacamole | 327 | 57 | 0.18x |
| imp_118200a50d935b24 | Katharine Hepburn's Brownies | 182 | 19 | 0.10x |
| imp_11ac1722fced5fbd | Chicken Breasts with Mustard-Caper Sauce | 216 | 73 | 0.34x |
| imp_11c24ad0abfc5886 | Bergy Dim Sum #3, Baked Wonton Crab Bits | 46 | 6 | 0.14x |
| imp_12470d317c335f4d | Peach Tart with Island Crust | 471 | 37 | 0.08x |
| ... | (1445 more, see full count above) | | | |

## Corpus-wide implausible kcal/serving band (<20 or >2000), GROUNDED/PARTIAL only
- count: 606

## Corpus-wide ingredient-occurrence terminal outcomes (what actually happens to every ingredient row)

Every ingredient occurrence in the corpus lands in EXACTLY ONE of the buckets below (mutually exclusive, and reconciled at grounding time to sum to the corpus's total ingredient-row count -- see `grounding_job._terminal_outcome_for_ingredient`). This is the table that explains ungroundedness; the rejection-counts table further below does NOT.

| outcome | count | % of occurrences |
|---|---|---|
| grounded | 7750 | 27.2% |
| no_unit | 7486 | 26.3% |
| unit_unconvertible | 11214 | 39.4% |
| no_relevant_candidate | 1728 | 6.1% |
| all_candidates_rejected | 286 | 1.0% |

## Individual-candidate rejection counts by reason, corpus-wide (NOT a table of ungroundedness causes)

**Read this table carefully.** Each count is the number of individual FDC CANDIDATES skipped during matching for the reason shown -- tallied once per candidate, across every `search_food` call this run made. It is NOT a count of queries/occurrences that failed to ground, and it is NOT a list of "why ingredients are ungrounded" (see the terminal-outcome table above for that). A query whose candidate was skipped here may still have gone on to ground successfully via a later candidate or the Branded fallback -- e.g. `processed_state_modifier:creamed` is almost entirely the imported corpus's egg occurrences correctly skipping an 'Egg, creamed' candidate while still grounding fine against a different candidate.

| reason | candidates skipped |
|---|---|
| kcal_too_low_branded | 1331 |
| processed_state_modifier:creamed | 504 |
| atwater_mismatch | 362 |
| branded_high_dispersion | 250 |
| processed_state_modifier:powdered | 65 |
| processed_state_modifier:sweetened | 54 |
| processed_state_modifier:fried | 49 |
| processed_state_modifier:smoked | 44 |
| processed_state_modifier:juice | 39 |
| processed_state_modifier:dehydrated | 34 |
| processed_state_modifier:pickled | 22 |
| processed_state_modifier:cured | 12 |
| processed_state_modifier:sauce | 12 |
| processed_state_modifier:candied | 10 |
| processed_state_modifier:marinated | 8 |
| processed_state_modifier:syrup | 4 |
| processed_state_modifier:soup | 4 |
| mass_over_105g | 3 |
| kcal_too_high | 1 |

## Branded-tier high-dispersion queries, corpus-wide (3+ candidates, >3.0x calorie spread -- left ungrounded)

- count: 250

| query | min kcal | max kcal | candidates |
|---|---|---|---|
| pumpkin | 29 | 400 | 25 |
| button mushroom, sliced | 13 | 123 | 9 |
| garlic, chopped | 67 | 500 | 15 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| sliced mushroom | 7 | 33 | 24 |
| minced garlic | 67 | 213 | 19 |
| pumpkin | 29 | 400 | 25 |
| cut green bean | 12 | 37 | 25 |
| garlic, minced | 67 | 213 | 17 |
| artichoke heart | 19 | 89 | 24 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| garlic, chopped | 67 | 500 | 15 |
| peach slice | 36 | 386 | 8 |
| garlic, chopped | 67 | 500 | 15 |
| hash brown | 82 | 368 | 4 |
| strawberry | 85 | 350 | 7 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti, | 104 | 375 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| beef broth | 6 | 167 | 10 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
| pineapple chunk | 36 | 375 | 23 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| cranberry | 50 | 375 | 3 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| artichoke heart | 19 | 89 | 24 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| sliced mushroom | 7 | 33 | 24 |
| sliced mushroom | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| black eyed pea | 62 | 343 | 15 |
| garlic, minced | 67 | 213 | 17 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| beef broth | 6 | 167 | 10 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| angel hair pasta | 5 | 375 | 16 |
| unsweetened coconut milk | 38 | 200 | 24 |
| cranberry | 50 | 375 | 3 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| angel hair pasta | 5 | 375 | 16 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| orange juice | 45 | 183 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, chopped | 67 | 500 | 15 |
| minced garlic | 67 | 213 | 19 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| hash brown | 82 | 368 | 4 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| philadelphia cream cheese | 91 | 375 | 8 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| cranberry | 50 | 375 | 3 |
| green beans, cut | 12 | 37 | 25 |
| carrot, diced | 9 | 49 | 8 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| sliced mushroom | 7 | 33 | 24 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| philadelphia cream cheese | 91 | 375 | 8 |
| french onion dip | 71 | 267 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| pumpkin | 29 | 400 | 25 |
| ginger paste | 67 | 500 | 5 |
| garlic, minced | 67 | 213 | 17 |
| button mushrooms, sliced | 13 | 123 | 9 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| orange juice | 45 | 183 | 25 |
| hash brown | 82 | 368 | 4 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| marinated artichoke heart | 36 | 117 | 10 |
| unsweetened coconut milk | 38 | 200 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| cherry tomatoe | 21 | 346 | 5 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| sliced mushroom | 7 | 33 | 24 |
| beef broth | 6 | 167 | 10 |
| mushroom, sliced | 7 | 33 | 24 |
| beef broth | 6 | 167 | 10 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| mung bean sprout | 29 | 96 | 3 |
| garlic, minced | 67 | 213 | 17 |
| salmon fillet | 71 | 283 | 12 |
| garlic, minced | 67 | 213 | 17 |
| sliced mushroom | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| pineapple tidbit | 50 | 389 | 14 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| garlic, chopped | 67 | 500 | 15 |
| mushrooms, sliced | 7 | 33 | 24 |
| button mushrooms, sliced | 13 | 123 | 9 |
| sliced mushroom | 7 | 33 | 24 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| cut green bean | 12 | 37 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| minced garlic | 67 | 213 | 19 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, chopped | 67 | 500 | 15 |
| spaghetti | 104 | 375 | 25 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mild salsa | 17 | 54 | 25 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| minced garlic | 67 | 213 | 19 |
| cut green bean | 12 | 37 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| minced garlic | 67 | 213 | 19 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, chopped | 67 | 500 | 15 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| beef broth | 6 | 167 | 10 |
| pineapple ring | 49 | 350 | 10 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| pineapple chunk | 36 | 375 | 23 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
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
