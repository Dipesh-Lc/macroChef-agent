# Grounding report

## Corpus-wide summary
- total recipes processed: 1598
- grounded: 3 (0.2%)
- partial: 1354 (84.7%)
- ungrounded: 241 (15.1%)

**Comparability note (A3 prep):** the pre-A3 baseline (`data/processed/grounding_report_pre_A3_baseline.md`, grounded 0.4% / partial 59.2%) was computed against the OLD, pre-A1 corpus of 4,263 recipes (near-zero unit coverage, 0.35%). The A1 corpus rebuild replaced that corpus with 3,853 active imported recipes + 25 hand-authored seeds and raised unit coverage to 76.14% -- the `total recipes processed` count above states THIS run's corpus size so the before/after grounded/partial/ungrounded percentages are read against the right denominator, not silently compared across two different corpora of different sizes. `data/processed/grounding_report_baseline.md` is a separate, even older snapshot (also pre-A1, from an earlier point in phase 1.5) -- do not confuse the two baseline files.

## Top ungrounded ingredients, corpus-wide (top 50 of up to 50)

| ingredient (normalized) | recipes affected |
|---|---|
| pepper | 152 |
| salt | 133 |
| vanilla | 120 |
| all purpose flour | 118 |
| salt and pepper | 97 |
| lemon juice | 86 |
| oil | 78 |
| vanilla extract | 71 |
| garlic, minced | 65 |
| butter or margarine | 56 |
| onion, chopped | 53 |
| white sugar | 49 |
| egg yolk | 43 |
| worcestershire sauce | 41 |
| egg white | 41 |
| cayenne pepper | 41 |
| orange juice | 37 |
| chopped onion | 37 |
| chopped parsley | 36 |
| cream cheese, softened | 36 |
| ground cumin | 34 |
| vinegar | 34 |
| pinch salt | 33 |
| chili powder | 33 |
| mayonnaise | 31 |
| margarine | 31 |
| granulated sugar | 31 |
| ground cinnamon | 30 |
| whipping cream | 30 |
| raisin | 28 |
| chicken stock | 28 |
| ground black pepper | 27 |
| butter | 27 |
| parsley | 27 |
| eggs, beaten | 27 |
| minced garlic | 26 |
| unsalted butter | 26 |
| chicken breast | 25 |
| chicken broth | 25 |
| butter, softened | 25 |
| cooking oil | 25 |
| potatoe | 24 |
| tomato sauce | 24 |
| butter, melted | 24 |
| ground pepper | 24 |
| bay leaf | 24 |
| shortening | 23 |
| shredded cheddar cheese | 23 |
| packed brown sugar | 23 |
| bay leave | 23 |

## Tag-vs-computed ratio distribution, corpus-wide (GROUNDED/PARTIAL recipes with a self-reported tag calorie value)

- n: 1355
- mean: 0.75x
- median: 0.34x
- stdev: 2.35
- min: 0.00x
- max: 49.72x

### Ratio outliers (outside [0.4x, 2.5x]) -- report-only, no demotion
- count: 799

| recipe_id | title | tag kcal | computed kcal | ratio |
|---|---|---|---|---|
| imp_0018958d8a5a5684 | Stir Fried Prawns | 313 | 3 | 0.01x |
| imp_0046e9331eb0545d | Sardine Curry | 178 | 0 | 0.00x |
| imp_00fdafb6f1b05a14 | Almond Stuffed Tofu Cubes | 18 | 0 | 0.00x |
| imp_01cfa5ee41f653fc | herbed-pizza-dough | 190 | 28 | 0.15x |
| imp_02573904cc925a75 | No Bake Brownies | 2246 | 530 | 0.24x |
| imp_0293a39759f95e25 | Homemade Maple Syrup, Old Fashioned | 3738 | 607 | 0.16x |
| imp_02ca7d2bf4055a37 | Frog Eye Salad | 269 | 38 | 0.14x |
| imp_02eb6855b1355d89 | Cheesy Potato Casserole | 497 | 185 | 0.37x |
| imp_031c9e8b718f5cdd | Israeli Spinach Fritters | 44 | 13 | 0.30x |
| imp_03849b99782a5571 | Swedish Baked Potatoes (Hasselbackspotatis) | 204 | 22 | 0.11x |
| imp_039649b29d605d48 | Jean Pare's Peanut Butter Treats | 200 | 56 | 0.28x |
| imp_04055bf038a954e3 | Olive & Cheddar Canapes | 35 | 5 | 0.13x |
| imp_041ea0e927505881 | Old-Fashioned Herb Stuffing | 159 | 1 | 0.01x |
| imp_04c40e5c8ab5561b | Sunrise Cherry Pie | 374 | 32 | 0.08x |
| imp_051638d745695f15 | Oyster Bisque - Light | 180 | 7 | 0.04x |
| imp_0569435d0d365775 | Curry Flavored Rice Mix | 124 | 2 | 0.02x |
| imp_065d81e8883d5471 | Harriett Bridge's Chicken Breasts | 684 | 227 | 0.33x |
| imp_06ac2b01e3ed5883 | Manhattan Island Clam Chowder | 307 | 76 | 0.25x |
| imp_06bcf2b3388d5274 | Lazy Sausage rolls | 29 | 0 | 0.00x |
| imp_06cd756b9f6151d1 | Wildfire Horseradish Crusted Pork Chops | 650 | 69 | 0.11x |
| imp_071c2746275a5150 | Dale's Renown Pork Butt | 775 | 10 | 0.01x |
| imp_073fd8e3e1535668 | Pie Crust | 937 | 315 | 0.34x |
| imp_07b760f0a9c058cd | Chinese Prawns on Toast | 204 | 7 | 0.03x |
| imp_08c37d3a856d5210 | 'Things Go Better With Coke' Brisket | 201 | 2 | 0.01x |
| imp_0994ffd5ea3c5521 | Veal Schnitzel Parmigiana | 267 | 68 | 0.25x |
| imp_09d3b6a749b35f78 | Cream of Cauliflower Soup | 61 | 1 | 0.02x |
| imp_0a06477533bb58c7 | Hominy - Green Chile Casserole | 220 | 75 | 0.34x |
| imp_0a13b277652752c3 | Baked Corn | 98 | 6 | 0.06x |
| imp_0a3d961167fc5ee8 | Harry's Black Forest Cookies | 1177 | 159 | 0.14x |
| imp_0abeea946eea5162 | Banana Frittatas | 348 | 132 | 0.38x |
| imp_0b292cd827a45d44 | Honey Ginger Grilled Salmon | 307 | 68 | 0.22x |
| imp_0b2efe2d84b55685 | Mushroom Pasta Scampi | 465 | 113 | 0.24x |
| imp_0b9a65fb5f7450a4 | TRADITIONAL ADOBO (Pork in Vinegar and Soy Sauce) | 324 | 11 | 0.03x |
| imp_0be09c69d2245cde | Jo Mama's Beef Stew | 314 | 24 | 0.08x |
| imp_0be688da3e7c58ca | The Frugal Gourmet's Haggis | 254 | 61 | 0.24x |
| imp_0c8f07147bcf5d5c | Sirloin Steak Casserole | 508 | 62 | 0.12x |
| imp_0cbf4e7579a2519e | Crock Pot Curried Lentil Soup | 143 | 26 | 0.18x |
| imp_0ce7011563035f3a | Curried Chicken and Vegetables | 803 | 85 | 0.11x |
| imp_0d12808bd80358c1 | Cornish Game Hens With Orange Stuffing | 172 | 5 | 0.03x |
| imp_0d435c9fcb7d5dbe | Flemish Beef Stew II | 596 | 6 | 0.01x |
| imp_0d472789309557f2 | Honey Dijon Pork Chops | 665 | 105 | 0.16x |
| imp_0d5bcb3c6239586c | Grilled Chicken Breasts with Peanut Sauce | 529 | 9 | 0.02x |
| imp_0d81c6a1574f500f | Homemade BBQ Baked Pork Chops | 246 | 13 | 0.05x |
| imp_0db6f4cc64de5bd3 | Harvest Apple Salsa with Cinnamon Chips | 340 | 24 | 0.07x |
| imp_0dd043694ba25ff2 | Bergen Easter Chicken | 819 | 51 | 0.06x |
| imp_0dfd31c7f4575d3f | HOUSKOVE KNEDLIKY (Bun-dumplings) | 645 | 55 | 0.09x |
| imp_0ebf42aec2d8509d | VEPROVE S KRENEM (Pork w/Horseradish) | 207 | 9 | 0.04x |
| imp_0f18e0b22af657d1 | Fruit Wreath | 154 | 13 | 0.08x |
| imp_101224a290095c56 | Family Tradition Coconut Candy | 821 | 209 | 0.25x |
| imp_10a1386ba2d25494 | Chicken and Sausage Jambalaya | 946 | 182 | 0.19x |
| imp_10efcea5ed295369 | Three Layer Orange Jello Salad | 170 | 1423 | 8.39x |
| imp_113ec8af0c765c92 | Best Cranberry Salad | 202 | 1528 | 7.57x |
| imp_11ddd4cebdcb5caa | Chicken and Spinach Pasta Casserole | 415 | 76 | 0.18x |
| imp_12313d35bd1f5ef2 | Vegetarian Teething Cookies | 22 | 7 | 0.31x |
| imp_12c342ec666e506c | Golden Muffins | 158 | 32 | 0.20x |
| imp_13022ad3536e523d | Amazingly Quick and Good Chicken Balls | 296 | 84 | 0.28x |
| imp_1302bf4e5cf951dd | Simple and Easy Dressing | 1382 | 5 | 0.00x |
| imp_131a76fe27f75b4f | pepperoni biscuits | 156 | 1 | 0.01x |
| imp_133eed43435c5d1f | Black Olives with Orange-Garlic-Hot Pepper Marinade | 576 | 2 | 0.00x |
| imp_13a1dba80b965f77 | Coffee Cake With Cranberry Swirl | 287 | 870 | 3.03x |
| imp_1408fc64d3a455e9 | Steamed Whole Fish With Salted Plums | 76 | 0 | 0.00x |
| imp_14137ad2a3ab5ef6 | Lite Oatmeal Raisin Breakfast Bars | 241 | 56 | 0.23x |
| imp_143975b113205756 | Toffee Slices | 190 | 59 | 0.31x |
| imp_1443d35b418a5988 | Stuffed Veal Brisket | 452 | 2 | 0.00x |
| imp_1500b089fd8b5816 | Cranberry Banana Cheesecake | 405 | 116 | 0.29x |
| imp_150ea6c452be508b | Evil Pork Chops | 371 | 10 | 0.03x |
| imp_151c1385b96f5d35 | My Most Favorite Brownies | 503 | 165 | 0.33x |
| imp_154360f0c50d56f7 | Noodles with Creamed Broccoli Sauce | 537 | 33 | 0.06x |
| imp_15b7134c64805ef2 | Spaghetti Torte | 329 | 26 | 0.08x |
| imp_160dd3098baf5845 | Excellent Chicken Stew | 402 | 138 | 0.34x |
| imp_162670c4c9495197 | Southwestern Turkey Soup | 75 | 25 | 0.33x |
| imp_163e36a705ce5d22 | Apple Cobbler | 131 | 19 | 0.15x |
| imp_168b93c4e8c05705 | Pound Cake With Swirled Chocolate | 346 | 1273 | 3.68x |
| imp_16ae1c6afa4d5c04 | Overnight Blueberry French Toast | 270 | 53 | 0.20x |
| imp_173ca77e88c85819 | Grilled Cajun Potato Wedges | 225 | 81 | 0.36x |
| imp_174a284716755fe3 | Lumpia (philippine Egg Rolls from Scratch) | 81 | 32 | 0.39x |
| imp_1760eaeabc8f5124 | Mexican Layer Dip - YUMMM | 422 | 136 | 0.32x |
| imp_17634ba12a195fa4 | Spicy Low fat, New Potatoes | 274 | 59 | 0.22x |
| imp_17779501f8205152 | Spicy Fried Corn and Sausage Casserole | 312 | 6 | 0.02x |
| imp_1821cbdbc2e350a7 | Chicken with Roasted Red Peppers | 170 | 0 | 0.00x |
| imp_183a45e06d0f5253 | Grilled Tuna & Vegetables W/yellow Pepper Sauce | 346 | 20 | 0.06x |
| imp_18d2f9afeee95377 | Pine Nut Crusted Chicken with Garlic and White Wine | 909 | 2 | 0.00x |
| imp_18e07cde056b5a61 | Lemon Pepper Mushrooms | 189 | 73 | 0.39x |
| imp_18ebb8408dd75331 | Rise & Shine Muffins | 415 | 160 | 0.39x |
| imp_18f7b1f27bba5b73 | Asian Noodle Skillet | 239 | 30 | 0.13x |
| imp_192e24c5ee9e54b7 | Succulent Prawns for the Barbie | 255 | 59 | 0.23x |
| imp_195b8cf682515714 | Spicy & Sweet Pork Chop Steaks for Two | 410 | 0 | 0.00x |
| imp_197dc2593d645de9 | Ham With Pineapple Sauce | 374 | 11 | 0.03x |
| imp_19b75823861f521d | Prawn Sambal | 250 | 15 | 0.06x |
| imp_19d16139fb245d0b | Hearty Potato Soup | 168 | 13 | 0.08x |
| imp_19ea5178ff3f5250 | KFC Twisters | 517 | 142 | 0.27x |
| imp_1adf83da2be853ec | Sunshine Calf or Pork Liver " Brownies " | 89 | 32 | 0.36x |
| imp_1b2cfc3205e75a44 | INJERA (Flat bread) | 363 | 1 | 0.00x |
| imp_1b77fe304dc054e3 | Traditional Eggnog | 340 | 5 | 0.01x |
| imp_1be6ee38947c5a5f | Chicken Flavored Rice Mix | 120 | 12 | 0.10x |
| imp_1bed22f8baa557fd | Ranch Salad | 316 | 91 | 0.29x |
| imp_1c8cbe6044ec5c37 | Cheddar Baked Bagels and Eggs | 540 | 119 | 0.22x |
| imp_1cd2fae0a7df578c | Vegetarian Stuffed Eggplant (Aubergine) | 536 | 49 | 0.09x |
| imp_1ce65cd2f8c75449 | Koofteh Tabrizi (herbed Meat & Rice Balls) | 229 | 0 | 0.00x |
| imp_1d524990abc45b90 | Magic Minestrone | 213 | 77 | 0.36x |
| ... | (699 more, see full count above) | | | |

## Corpus-wide implausible kcal/serving band (<20 or >2000), GROUNDED/PARTIAL only
- count: 355

## Corpus-wide ingredient-occurrence terminal outcomes (what actually happens to every ingredient row)

Every ingredient occurrence in the corpus lands in EXACTLY ONE of the buckets below (mutually exclusive, and reconciled at grounding time to sum to the corpus's total ingredient-row count -- see `grounding_job._terminal_outcome_for_ingredient`). This is the table that explains ungroundedness; the rejection-counts table further below does NOT.

| outcome | count | % of occurrences |
|---|---|---|
| grounded | 3791 | 27.1% |
| no_unit | 3432 | 24.5% |
| unit_unconvertible | 5712 | 40.8% |
| no_relevant_candidate | 891 | 6.4% |
| all_candidates_rejected | 157 | 1.1% |

## Individual-candidate rejection counts by reason, corpus-wide (NOT a table of ungroundedness causes)

**Read this table carefully.** Each count is the number of individual FDC CANDIDATES skipped during matching for the reason shown -- tallied once per candidate, across every `search_food` call this run made. It is NOT a count of queries/occurrences that failed to ground, and it is NOT a list of "why ingredients are ungrounded" (see the terminal-outcome table above for that). A query whose candidate was skipped here may still have gone on to ground successfully via a later candidate or the Branded fallback -- e.g. `processed_state_modifier:creamed` is almost entirely the imported corpus's egg occurrences correctly skipping an 'Egg, creamed' candidate while still grounding fine against a different candidate.

| reason | candidates skipped |
|---|---|
| kcal_too_low_branded | 648 |
| processed_state_modifier:creamed | 264 |
| atwater_mismatch | 176 |
| branded_high_dispersion | 137 |
| processed_state_modifier:smoked | 69 |
| processed_state_modifier:sweetened | 46 |
| processed_state_modifier:powdered | 35 |
| processed_state_modifier:dehydrated | 24 |
| processed_state_modifier:juice | 19 |
| processed_state_modifier:cured | 13 |
| processed_state_modifier:pickled | 9 |
| processed_state_modifier:fried | 8 |
| processed_state_modifier:sauce | 5 |
| mass_over_105g | 3 |
| processed_state_modifier:syrup | 2 |
| processed_state_modifier:candied | 2 |
| processed_state_modifier:breaded | 1 |

## Branded-tier high-dispersion queries, corpus-wide (3+ candidates, >3.0x calorie spread -- left ungrounded)

- count: 137

| query | min kcal | max kcal | candidates |
|---|---|---|---|
| garlic, minced | 67 | 213 | 17 |
| hash brown | 82 | 368 | 4 |
| garlic, chopped | 67 | 500 | 15 |
| salmon fillet | 71 | 283 | 12 |
| garlic, minced | 67 | 213 | 17 |
| sliced mushroom | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| roasted red pepper | 18 | 179 | 4 |
| minced garlic | 67 | 213 | 19 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| artichoke heart | 19 | 89 | 24 |
| garlic, minced | 67 | 213 | 17 |
| pineapple chunk | 36 | 375 | 23 |
| spaghetti, | 104 | 375 | 15 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| strawberry | 85 | 350 | 7 |
| orange juice | 45 | 183 | 25 |
| salmon fillet | 71 | 283 | 12 |
| minced garlic | 67 | 213 | 19 |
| orange juice | 45 | 183 | 25 |
| garlic, minced | 67 | 213 | 17 |
| carrot, diced | 9 | 49 | 8 |
| sliced mushroom | 7 | 33 | 24 |
| french cut green bean | 12 | 42 | 23 |
| black eyed pea | 62 | 343 | 15 |
| sliced mushroom | 7 | 33 | 24 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| pineapple chunk | 36 | 375 | 23 |
| chunk pineapple | 36 | 375 | 23 |
| garlic, minced | 67 | 213 | 17 |
| strawberry | 85 | 350 | 7 |
| garlic, minced | 67 | 213 | 17 |
| minced garlic | 67 | 213 | 19 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| farmer cheese | 70 | 381 | 16 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| minced garlic | 67 | 213 | 19 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| orange juice | 45 | 183 | 25 |
| blackberry | 25 | 250 | 3 |
| cranberry | 50 | 375 | 3 |
| minced garlic | 67 | 213 | 19 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti, | 104 | 375 | 15 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| cranberry | 50 | 375 | 3 |
| button mushroom, , sliced | 13 | 123 | 9 |
| lemon gelatin | 25 | 389 | 5 |
| mushroom, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| angel hair pasta | 5 | 375 | 16 |
| hash brown | 82 | 368 | 4 |
| cranberry | 50 | 375 | 3 |
| sliced mushroom | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
| pineapple slice | 53 | 350 | 5 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| spaghetti | 104 | 375 | 25 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| philadelphia cream cheese | 91 | 375 | 8 |
| garlic, chopped | 67 | 500 | 15 |
| carrots, diced | 9 | 49 | 8 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mixed fruit | 32 | 429 | 20 |
| garlic, minced | 67 | 213 | 17 |
| chopped garlic | 67 | 500 | 14 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushrooms, sliced | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| salmon fillet | 71 | 283 | 12 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| pumpkin | 29 | 400 | 25 |
| mushrooms, sliced | 7 | 33 | 24 |
| orange juice | 45 | 183 | 25 |
| spaghetti | 104 | 375 | 25 |
| garlic, minced | 67 | 213 | 17 |
| pumpkin | 29 | 400 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| hash browns, | 82 | 368 | 3 |
| garlic, minced | 67 | 213 | 17 |
| minced garlic | 67 | 213 | 19 |
| sliced mushroom | 7 | 33 | 24 |
| garlic, minced | 67 | 213 | 17 |
| gelatin | 25 | 429 | 8 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| orange juice | 45 | 183 | 25 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, chopped | 67 | 500 | 15 |
| garlic, chopped | 67 | 500 | 15 |
| angel hair pasta | 5 | 375 | 16 |
| pineapple slice | 53 | 350 | 5 |
| garlic, minced | 67 | 213 | 17 |
| brown rice | 88 | 400 | 25 |
| beef broth | 6 | 167 | 10 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| garlic, minced | 67 | 213 | 17 |
| mushroom, sliced | 7 | 33 | 24 |

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
