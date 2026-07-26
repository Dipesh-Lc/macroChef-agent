# Grounding report

## Corpus-wide summary
- total recipes processed: 3884
- grounded: 21 (0.5%)
- partial: 3540 (91.1%)
- ungrounded: 323 (8.3%)

**Comparability note (A3 prep):** the pre-A3 baseline (`data/processed/grounding_report_pre_A3_baseline.md`, grounded 0.4% / partial 59.2%) was computed against the OLD, pre-A1 corpus of 4,263 recipes (near-zero unit coverage, 0.35%). The A1 corpus rebuild replaced that corpus with 3,853 active imported recipes + 25 hand-authored seeds and raised unit coverage to 76.14% -- the `total recipes processed` count above states THIS run's corpus size so the before/after grounded/partial/ungrounded percentages are read against the right denominator, not silently compared across two different corpora of different sizes. `data/processed/grounding_report_baseline.md` is a separate, even older snapshot (also pre-A1, from an earlier point in phase 1.5) -- do not confuse the two baseline files.

## Top ungrounded ingredients, corpus-wide (top 50 of up to 50)

| ingredient (normalized) | recipes affected |
|---|---|
| lemon juice | 373 |
| vanilla | 347 |
| pepper | 326 |
| all purpose flour | 292 |
| onion, chopped | 241 |
| garlic, minced | 207 |
| oil | 170 |
| butter or margarine | 165 |
| vanilla extract | 164 |
| butter, melted | 157 |
| parsley, chopped | 148 |
| worcestershire sauce | 129 |
| salt | 127 |
| granulated sugar | 126 |
| orange juice | 115 |
| egg white | 113 |
| mayonnaise | 113 |
| vinegar | 112 |
| salt and pepper | 104 |
| cream cheese, softened | 102 |
| raisin | 97 |
| egg yolk | 97 |
| salt & pepper | 92 |
| margarine | 91 |
| unbleached flour | 88 |
| butter, softened | 87 |
| brown sugar, packed | 84 |
| dry mustard | 84 |
| shortening | 82 |
| pinch salt | 81 |
| buttermilk | 77 |
| onions, chopped | 77 |
| eggs, beaten | 76 |
| bay leaf | 75 |
| chili powder | 72 |
| nuts, chopped | 72 |
| egg, beaten | 72 |
| walnuts, chopped | 72 |
| pecans, chopped | 70 |
| boiling water | 69 |
| tomato sauce | 68 |
| curry powder | 65 |
| celery, chopped | 64 |
| brown sugar, firmly packed | 64 |
| lime juice | 64 |
| onion, finely chopped | 63 |
| water, cold | 61 |
| garlic cloves, minced | 61 |
| confectioners' sugar | 59 |
| dijon mustard | 59 |

## Tag-vs-computed ratio distribution, corpus-wide (GROUNDED/PARTIAL recipes with a self-reported tag calorie value)

- n: 3561
- mean: 0.59x
- median: 0.34x
- stdev: 4.10
- min: 0.00x
- max: 238.53x

### Ratio outliers (outside [0.4x, 2.5x]) -- report-only, no demotion
- count: 2059

| recipe_id | title | tag kcal | computed kcal | ratio |
|---|---|---|---|---|
| imp_002d747016c55cc0 | Bibby's Yellow Squash Bake | 151 | 390 | 2.59x |
| imp_0035657e83a75216 | Amaretto Peach Cheesecake | 441 | 94 | 0.21x |
| imp_003ab1b0f9d054ca | Sugar Free Brownies | 68 | 24 | 0.35x |
| imp_004e107d27b75fc2 | White Bean Soup | 93 | 0 | 0.00x |
| imp_00682a126bd151eb | Dill-Lemon Rice | 195 | 0 | 0.00x |
| imp_007080a9b0485889 | Egg Drop Soup | 88 | 0 | 0.00x |
| imp_00d7e68543255f34 | Dill Buttermilk Bread | 1677 | 148 | 0.09x |
| imp_011194df31185a29 | Liqueur Cakes | 412 | 1735 | 4.21x |
| imp_011bd5320eae57d3 | Chicken a la King II | 291 | 0 | 0.00x |
| imp_0134a2a00a95591a | Braised Beef Liver With Vegetables | 1004 | 197 | 0.20x |
| imp_0141e4e6f885578b | Rumaki | 170 | 48 | 0.28x |
| imp_019d2c379b625f78 | King Arthur's Apple Cinnamon Breakfast Bread | 2632 | 152 | 0.06x |
| imp_01ade4e559db5978 | Oatmeal Breakfast Cookies | 68 | 20 | 0.30x |
| imp_01b128b9501a5e19 | Danish Sourdough Pumpernickel | 301 | 0 | 0.00x |
| imp_022adbbb8dbb56c9 | Crab Dip | 256 | 0 | 0.00x |
| imp_02406425ae5c50f1 | Mississippi Mud Pie With Ice Cream | 258 | 99 | 0.39x |
| imp_0244d835f7a65c79 | No-bake Honey Snacks | 162 | 7 | 0.04x |
| imp_0245f163d50057e4 | Crock Pot Rathskeller Pork | 470 | 30 | 0.06x |
| imp_02466cb5e6655705 | Zinfandeli's Chicken Tortilla Soup - S.a. Express - Arlene Light | 206 | 15 | 0.07x |
| imp_0281b314009e5470 | Orange and Lemon Schnitzel Rolls | 577 | 5 | 0.01x |
| imp_0287fc592d1356c1 | Ranch Dressing Mix Plus | 795 | 31 | 0.04x |
| imp_0297a5b9b8da515b | Mushroom Red Pepper Phyllo Puffs | 196 | 23 | 0.12x |
| imp_02a5b6ed7968549e | Strawberry Marbled Cheesecake | 434 | 24 | 0.06x |
| imp_02e8b9e122635553 | Creamy Turkey Pie | 350 | 9 | 0.03x |
| imp_0326b00eade05b1a | Pecan Filling | 2764 | 186 | 0.07x |
| imp_035b1fa3663a5033 | Oatcakes | 495 | 76 | 0.15x |
| imp_036a4f35023f513f | Oatmeal Muffins | 188 | 74 | 0.39x |
| imp_03a56ee8c5775340 | Pork in Cider Sauce | 498 | 23 | 0.05x |
| imp_03aaea4eaafb5601 | Dutch Oven Pot Roast | 413 | 12 | 0.03x |
| imp_03d00dccc2095e6f | Sun of a Gun Beef Stew | 3295 | 12 | 0.00x |
| imp_03d34d5d7adf5719 | Enchiladas Pollo With Green Chilies Cream Sauce | 808 | 145 | 0.18x |
| imp_04076747e2645787 | Chanfana Ou Lampantana | 1266 | 172 | 0.14x |
| imp_040ea38571635a32 | Game Salmi | 1281 | 203 | 0.16x |
| imp_041c6eb156dd5999 | Easy Asian Chicken Soup | 267 | 5 | 0.02x |
| imp_04594870ff31545b | Snickerdoodles II | 93 | 2 | 0.02x |
| imp_045f83b795df50a8 | California Rarebit | 392 | 97 | 0.25x |
| imp_04622e49335754c2 | Kentucky Kernels - S.a. Express News - Karen Haram | 284 | 51 | 0.18x |
| imp_047c9248e21a51a0 | Chiffon Pumpkin Pie | 368 | 20 | 0.05x |
| imp_04875ecba30a5e37 | Soft Corn Muffins | 183 | 35 | 0.19x |
| imp_04a3ba13b7cc5e17 | Cornbread With Corn Casserole | 272 | 36 | 0.13x |
| imp_04ac0d2f8a645070 | Onion Soup | 162 | 11 | 0.07x |
| imp_04b608a36f075cd0 | Chocolate Cherry Cordial Muffins | 329 | 57 | 0.17x |
| imp_04dcee8c7db35373 | Citrus Chicken | 168 | 4 | 0.02x |
| imp_051aa81563645939 | Crafty Crescent Lasagna | 772 | 212 | 0.27x |
| imp_051c7061b89e5faa | Creamy Vegetable Curry with Rice | 1763 | 192 | 0.11x |
| imp_05433c91cc3b5666 | French Roasted Vegetable Sandwiches | 222 | 32 | 0.14x |
| imp_0563fa52cc03502f | Cherry Bars | 122 | 7 | 0.06x |
| imp_059e4d6450c650ec | Snails Sommeroise / Escargots a la Sommeroise | 425 | 132 | 0.31x |
| imp_05bc0340cffb5a85 | Grilled Thai Sirloin with Tangy Lime Sauce | 237 | 28 | 0.12x |
| imp_05c09b087dcf52bf | Streusel-Topped Pumpkin Pie | 504 | 22 | 0.04x |
| imp_05c4ce5de6a25c5d | Pumpkin Swirl Pie | 337 | 31 | 0.09x |
| imp_05d9eb8ccbfa5ebd | Cranberry Sauce With Port, Rosemary and Dried Figs | 219 | 72 | 0.33x |
| imp_05f68b2a1d615a29 | Buttermilk Southern Fried Chicken | 655 | 2 | 0.00x |
| imp_05f8b2ebb84756d0 | Half-Time Beef Sandwiches | 403 | 51 | 0.13x |
| imp_06111ce3958251cd | Roasted Garlic Puree Dip | 395 | 19 | 0.05x |
| imp_06119595d11d52f0 | A-To-Z Bread | 367 | 2935 | 8.00x |
| imp_061a2bb7f4e45904 | Morning Maple Muffins | 212 | 52 | 0.24x |
| imp_061a6bf4b72a51b4 | Clam - Lobster Bake | 990 | 44 | 0.04x |
| imp_065cb86552265bf3 | Amish Cornbread | 1792 | 552 | 0.31x |
| imp_066554e9bc51597c | Wild Goose | 5460 | 409 | 0.07x |
| imp_06b3ec9513ff5005 | Green Chicken Enchiladas | 222 | 24 | 0.11x |
| imp_06f98881ebf05a75 | Roasted Pork Loin with Bacon and Onion Spaetzle | 1186 | 470 | 0.40x |
| imp_070317197449598d | Beef in Red Wine | 156 | 33 | 0.21x |
| imp_075d0e93d33955bc | Ginger Apple Salad | 257 | 32 | 0.12x |
| imp_07849784efaf58bd | Parmesan Croutons | 96 | 13 | 0.14x |
| imp_079476fa25a35a43 | True Texas Chili Con Carne | 1732 | 313 | 0.18x |
| imp_079c4aaf57965ff5 | Salad-in-a-Boat | 331 | 120 | 0.36x |
| imp_07dfa5757af1554f | Vfw Ladies Auxiliary Ceviche | 186 | 44 | 0.24x |
| imp_07e9764049835042 | Fruited Spinach Salad With Honey Mustard Dressing | 107 | 13 | 0.12x |
| imp_07fafcba9dd05c64 | Buttercrunch Shortbread | 3061 | 0 | 0.00x |
| imp_083928a8d2f958d6 | Cracker Barrel Old Country Store Fried Apples | 185 | 35 | 0.19x |
| imp_086356531a07531f | Smoothy Chocolate Cookies | 133 | 22 | 0.17x |
| imp_0886d7d81ae75829 | Orange Muffins | 160 | 21 | 0.13x |
| imp_089c6045d3535615 | Spicy Apple-Stuffed Squash | 93 | 9 | 0.09x |
| imp_08f2b06332435f6d | Baklava | 363 | 103 | 0.28x |
| imp_0941779dcb115194 | Baked Butternut Squash With Orange | 192 | 30 | 0.16x |
| imp_096cab460abf5a97 | Crock Pot Potatoes | 537 | 0 | 0.00x |
| imp_096cd44eb6b95090 | Apple Cranberry Pie | 389 | 83 | 0.21x |
| imp_0975ee18dad851b3 | Low-Fat Blueberry Grunt | 243 | 2 | 0.01x |
| imp_0982148f97be5fce | Low-Fat Thai Steak Salad | 2630 | 1 | 0.00x |
| imp_09aa21fdc43e5392 | Orange Tarragon Dressing | 26 | 0 | 0.00x |
| imp_09c40c8e41f753e5 | Jack Daniel's Marinade | 320 | 34 | 0.11x |
| imp_09d47ae36f695520 | Chocolatey Raisin Chip Cookies | 84 | 32 | 0.38x |
| imp_09deb8dad38b5a76 | Enchiladas Verdes Suizas | 756 | 143 | 0.19x |
| imp_0a0d1babded653b7 | Carrot Ginger Biscuits | 127 | 4 | 0.03x |
| imp_0a25559792285e8c | Herbed Pizza Crust | 268 | 16 | 0.06x |
| imp_0aa2803cf1405629 | Low-Fat Pumpkin Pie | 248 | 64 | 0.26x |
| imp_0ab6d18389435ade | Chocolate Amaretto Cheesecake | 668 | 197 | 0.29x |
| imp_0b13f79007d55de8 | Dutch Mayonnaise | 1627 | 0 | 0.00x |
| imp_0b214e230cfa5409 | Marinated Flank Steak with Citrus Salsa | 687 | 2 | 0.00x |
| imp_0b287cdee3655a9b | Butter Bean Dip with Basil | 83 | 13 | 0.16x |
| imp_0b3f793c87425ce3 | Blueberry Dessert | 381 | 96 | 0.25x |
| imp_0b5f7d74c5815980 | Skillet Beef and Shells | 1022 | 242 | 0.24x |
| imp_0b69887731e15b7e | Crusty Garlic Bread | 72 | 13 | 0.19x |
| imp_0b921f9f9d195623 | Pasta Al Pesto | 310 | 90 | 0.29x |
| imp_0b935770b8b85854 | Old-Fashioned Sage Loaf | 851 | 248 | 0.29x |
| imp_0b9824dd0d8e5f62 | Harvest Cornish Hens | 1112 | 21 | 0.02x |
| imp_0bb2ab7a5f2155cf | "21" Apple Pie | 694 | 8 | 0.01x |
| imp_0bd46b4c3d1b5c3e | Squash & Golden Onion Risotto | 337 | 85 | 0.25x |
| imp_0be203dbe654544a | Breakfast Pudding | 29 | 2 | 0.05x |
| ... | (1959 more, see full count above) | | | |

## Corpus-wide implausible kcal/serving band (<20 or >2000), GROUNDED/PARTIAL only
- count: 833

## Corpus-wide ingredient-occurrence terminal outcomes (what actually happens to every ingredient row)

Every ingredient occurrence in the corpus lands in EXACTLY ONE of the buckets below (mutually exclusive, and reconciled at grounding time to sum to the corpus's total ingredient-row count -- see `grounding_job._terminal_outcome_for_ingredient`). This is the table that explains ungroundedness; the rejection-counts table further below does NOT.

| outcome | count | % of occurrences |
|---|---|---|
| grounded | 11287 | 30.4% |
| no_unit | 7423 | 20.0% |
| unit_unconvertible | 15666 | 42.3% |
| no_relevant_candidate | 2354 | 6.3% |
| all_candidates_rejected | 343 | 0.9% |

## Individual-candidate rejection counts by reason, corpus-wide (NOT a table of ungroundedness causes)

**Read this table carefully.** Each count is the number of individual FDC CANDIDATES skipped during matching for the reason shown -- tallied once per candidate, across every `search_food` call this run made. It is NOT a count of queries/occurrences that failed to ground, and it is NOT a list of "why ingredients are ungrounded" (see the terminal-outcome table above for that). A query whose candidate was skipped here may still have gone on to ground successfully via a later candidate or the Branded fallback -- e.g. `processed_state_modifier:creamed` is almost entirely the imported corpus's egg occurrences correctly skipping an 'Egg, creamed' candidate while still grounding fine against a different candidate.

| reason | candidates skipped |
|---|---|
| kcal_too_low_branded | 2613 |
| processed_state_modifier:creamed | 751 |
| atwater_mismatch | 504 |
| branded_high_dispersion | 304 |
| processed_state_modifier:sweetened | 296 |
| processed_state_modifier:powdered | 83 |
| processed_state_modifier:dehydrated | 49 |
| processed_state_modifier:smoked | 41 |
| processed_state_modifier:juice | 32 |
| processed_state_modifier:cured | 24 |
| processed_state_modifier:pickled | 23 |
| processed_state_modifier:sauce | 20 |
| processed_state_modifier:candied | 19 |
| processed_state_modifier:fried | 18 |
| mass_over_105g | 16 |
| processed_state_modifier:marinated | 8 |
| processed_state_modifier:syrup | 6 |
| kcal_too_high | 1 |
| processed_state_modifier:breaded | 1 |
| processed_state_modifier:soup | 1 |

## Branded-tier high-dispersion queries, corpus-wide (3+ candidates, >3.0x calorie spread -- left ungrounded)

- count: 304

| query | min kcal | max kcal | candidates |
|---|---|---|---|
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| unsweetened coconut milk | 38 | 200 | 24 |
| pork rind | 107 | 571 | 10 |
| pumpkin | 29 | 400 | 25 |
| cranberry | 50 | 375 | 3 |
| garlic, minced | 67 | 213 | 17 |
| apple cider vinegar | 13 | 222 | 3 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti, | 104 | 375 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| orange juice | 45 | 183 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| artichoke hearts, marinated | 36 | 117 | 10 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| tuna steak | 53 | 181 | 6 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, , sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| country ham | 170 | 698 | 7 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mixed fruit | 32 | 429 | 20 |
| garlic, minced | 67 | 213 | 17 |
| button mushrooms, sliced | 13 | 123 | 9 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| pineapple chunk | 36 | 375 | 23 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| cranberry | 50 | 375 | 3 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| philadelphia cream cheese | 91 | 375 | 8 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| broad bean | 104 | 467 | 5 |
| pumpkin | 29 | 400 | 25 |
| spaghetti, | 104 | 375 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| philadelphia cream cheese | 91 | 375 | 8 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| cherry tomatoe | 21 | 346 | 5 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| strawberry | 85 | 350 | 7 |
| artichoke heart | 19 | 89 | 24 |
| garlic, minced | 67 | 213 | 17 |
| lemon gelatin | 25 | 389 | 5 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| spaghetti | 104 | 375 | 25 |
| garlic, chopped | 67 | 500 | 15 |
| cranberry | 50 | 375 | 3 |
| garlic, minced | 67 | 213 | 17 |
| pineapple chunk | 36 | 375 | 23 |
| mushrooms, sliced | 7 | 33 | 24 |
| mushrooms, sliced | 7 | 33 | 24 |
| strawberry gelatin | 67 | 400 | 6 |
| angel hair pasta | 5 | 375 | 16 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| salmon fillet | 71 | 283 | 12 |
| unsweetened coconut milk | 38 | 200 | 24 |
| philadelphia cream cheese | 91 | 375 | 8 |
| chunk pineapple | 36 | 375 | 23 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| mushrooms, sliced | 7 | 33 | 24 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| philadelphia cream cheese | 91 | 375 | 8 |
| hash brown | 82 | 368 | 4 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| pineapple chunk | 36 | 375 | 23 |
| orange juice | 45 | 183 | 25 |
| crawfish | 14 | 82 | 3 |
| unsweetened coconut milk | 38 | 200 | 24 |
| carrots, diced | 9 | 49 | 8 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| beets, sliced | 17 | 67 | 25 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| salmon fillet | 71 | 283 | 12 |
| self rising flour | 110 | 367 | 14 |
| garlic, minced | 67 | 213 | 17 |
| button mushrooms, sliced | 13 | 123 | 9 |
| french style green bean | 11 | 41 | 25 |
| pumpkin | 29 | 400 | 25 |
| catfish fillet | 71 | 268 | 15 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| angel hair pasta, | 5 | 375 | 16 |
| garlic, minced | 67 | 213 | 17 |
| cranberry | 50 | 375 | 3 |
| cranberry | 50 | 375 | 3 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| catfish fillet | 71 | 268 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| beef broth | 6 | 167 | 10 |
| garlic, minced | 67 | 213 | 17 |
| fruit punch | 12 | 375 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| salmon fillet | 71 | 283 | 12 |
| pineapple tidbit | 50 | 389 | 14 |
| garlic, minced | 67 | 213 | 17 |
| strawberry | 85 | 350 | 7 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| strawberry gelatin | 67 | 400 | 6 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| lemon gelatin | 25 | 389 | 5 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, , sliced | 7 | 33 | 24 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| angel hair pasta | 5 | 375 | 16 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| self rising flour | 110 | 367 | 14 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| mixed fruit | 32 | 429 | 20 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| orange juice | 45 | 183 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| button mushrooms, sliced | 13 | 123 | 9 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| pineapple chunk | 36 | 375 | 23 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| salmon fillet | 71 | 283 | 12 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| pineapple chunk | 36 | 375 | 23 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| pumpkin | 29 | 400 | 25 |
| pineapple tidbit | 50 | 389 | 14 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| self rising flour | 110 | 367 | 14 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| crawfish | 14 | 82 | 3 |
| garlic, minced | 67 | 213 | 17 |

## Seed macro-computation accuracy (pre-registered A3 eval)

Pre-registered gate (docs/ROADMAP.md item A3): "macro-computation accuracy measured against the 25 hand-authored seed recipes as ground truth." These metric definitions (see `SeedMacroAccuracy`/`compute_seed_macro_accuracy` in `app/services/grounding_job.py`) were fixed BEFORE the corpus-wide A3 grounding run and are not adjusted after seeing results. A seed contributes to a macro's error only when its status is GROUNDED or PARTIAL (an UNGROUNDED seed has no real computed value) AND it has a non-null, non-zero self-reported tag value for that macro -- every seed excluded either way is counted as "missing" below, never silently dropped. **kcal is the PRIMARY metric.**

- seeds: 25 total -- 14 grounded, 11 partial, 0 ungrounded

| macro | n compared | median abs relative error | mean abs relative error | missing (excluded) |
|---|---|---|---|---|
| **kcal (PRIMARY)** | 25 | 16.1% | 25.3% | 0 |
| protein_g | 25 | 21.4% | 35.0% | 0 |
| carbs_g | 25 | 34.8% | 34.4% | 0 |
| fat_g | 25 | 31.7% | 39.4% | 0 |

## Seed tag-vs-computed comparison (25 recipes)

| recipe_id | title | status | coverage | tag kcal | computed kcal | ratio |
|---|---|---|---|---|---|---|
| r_001 | Mediterranean Chicken Rice Bowl | grounded | 100% | 610 | 590 | 0.97x |
| r_002 | Thai Peanut Tofu Stir Fry | grounded | 100% | 540 | 605 | 1.12x |
| r_003 | Mexican Turkey Black Bean Skillet | grounded | 100% | 520 | 638 | 1.23x |
| r_004 | Italian Lentil Tomato Pasta | partial | 88% | 590 | 923 | 1.56x |
| r_005 | Japanese Salmon Sushi Bowl | partial | 88% | 650 | 835 | 1.28x |
| r_006 | American Egg White Veggie Omelet | partial | 86% | 330 | 727 | 2.20x |
| r_007 | Indian Chickpea Spinach Curry | partial | 75% | 560 | 392 | 0.70x |
| r_008 | Mediterranean Quinoa Chickpea Salad | grounded | 100% | 480 | 835 | 1.74x **[RAW/COOKED BLOWUP]** |
| r_009 | Dairy-Free Chicken Fajita Plate | grounded | 100% | 620 | 684 | 1.10x |
| r_010 | Gluten-Free Turkey Meatballs | partial | 62% | 500 | 415 | 0.83x |
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

### r_004 -- Italian Lentil Tomato Pasta (partial, coverage 88%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| whole wheat pasta | True | 100.0 | matched: Pasta, whole grain, 51% whole wheat, remaining unenriched semolina, dry (SR Legacy) |
| lentils | True | 100.0 | matched: Lentils, dry (Foundation) |
| tomato | True | 246.0 | matched: Tomato, roma (Foundation) |
| spinach | True | 40.0 | matched: Spinach, baby (Foundation) |
| vegetarian hard cheese | False | 20.0 | ungrounded: no USDA match |
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

### r_010 -- Gluten-Free Turkey Meatballs (partial, coverage 62%)
| ingredient | grounded | grams | detail |
|---|---|---|---|
| ground turkey | True | 200.0 | matched: Turkey, Ground, raw (SR Legacy) |
| whole egg | False | n/a | ungrounded: amount/unit not convertible to grams |
| almond meal | False | 30.0 | ungrounded: no USDA match |
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
