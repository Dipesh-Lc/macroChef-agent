# Instructions/ingredient integrity audit -- 20260718T090602Z

Dry run only -- this report never mutated `data/processed/imported_recipes.jsonl` or any quarantine sidecar. See `docs/instructions_integrity_spec.md` for the full rule set and guard-band pre-registration.

## Guard-band verdict

**PROBABLE_BUG**: Floor sanity breach: only 0 row(s) flagged (< 10). The three still-in-corpus planted faults alone guarantee >=3, and the review's 6-of-9 sampled corruption rate makes a near-zero result implausible -- this is almost certainly a check/vocabulary bug, not a clean corpus. Investigate before trusting this run.

- Corpus size: 2889
- Flagged (Tier A+B, quarantine-worthy): 0 (0.00%)
- Tier A: 0
- Tier B: 0
- Tier C (report-only, never quarantines): 697 recipes, 781 mismatch pairs

## Per-category counts (Tier A/B, quarantine-worthy)

(none)

## Per-category counts (Tier C, report-only)

- `oil`: 426
- `sauce`: 269
- `meat_generic`: 37
- `gravy`: 37
- `dough`: 11
- `batter`: 1

## Out-of-scope boundary (spec Sec. 1)

Non-safety-vocabulary omissions (e.g. the imp_f9cc221553155bfc 'orange juice' class) are explicitly out of scope: hidden orange juice cannot produce an engine-visible allergy/diet violation. Title-side bare meat/fish word checking remains unchanged (proven unsafe to do deterministically, per the existing title module and `docs/BACKLOG.md`).

## Sample-audit candidate list (n=0, seed 20260719)

Stratified by category (largest-remainder proportional allocation, min 3 per non-empty category), population unit = one (recipe, category) Tier A/B mismatch case. For the orchestrator/advisor to write per-case CORRECT_QUARANTINE / FALSE_POSITIVE adjudication against (acceptance: <=2/40 false positives, i.e. >=95% precision). Full evidence in the sidecar JSON.

(no quarantine-worthy mismatches to sample)

## Miss spot-check candidate list (n=15, seed 20260719)

15 random UNflagged rows for the orchestrator to read for any Tier A/B-class omission the check should have caught (acceptance: 0 misses; a miss is a spec bug, fix and re-run -- not an acceptance judgment call).

- `imp_6c880f0d11d75682` 'Herbed Pecan Sauce'
  - ingredient names: ['parmesan cheese', 'pecans', 'fresh parsley', 'dried basil', 'garlic', 'salt', 'olive oil']
  - instructions: ['Place cheese in food processor; process, using on/off motion, until finely chopped.', 'Add spinach, pecans, parsley and basil, garlic, and salt; process until evenly chopped.', 'With motor running, gradually add oil; process until mixture is smooth.', 'Serve at room temperature or chilled; or spoon into saucepan and heat, stirring over low heat until hot.', 'Notes: * fresh, firmly packed - washed and dried']
- `imp_6a279a7ffda35c8e` 'Orange-Date Loaves'
  - ingredient names: ['all-purpose flour', 'sugar', 'baking powder', 'baking soda', 'salt', 'eggs', 'dates', 'pecans', 'walnuts']
  - instructions: ['In a large mixing bowl stir together flour, sugar, baking powder, orange peel, baking soda, and salt.', 'In another mixing bowl stir together eggs, 1/2 cup of the thawed orange juice concentrate, the oil, and 1-1/2 cups water.', 'Add to flour mixture. Stir by hand just until combined. Fold in dates and nuts.', 'Divide mixture evenly between two greased 8"x4"x2" loaf pans. Bake in a 350 degree oven for 50 to 55 minutes or until a toothpick inserted near the centers comes out clean. (Or, divide mixture evenly among four 5-1/2"x3"x2" loaf pans and bake for 40 to 45 minutes or until loaves test done.).', 'Cool in pans for 10 minutes; remove from pans.', 'Generously brush tops and sides of loaves with remaining orange juice concentrate. Cool thoroughly on wire racks.', 'Wrap and store overnight before slicing.']
- `imp_6be168a159505699` 'Holiday Eggnog'
  - ingredient names: ['granulated sugar', 'half-and-half', 'Bourbon', 'fresh nutmeg']
  - instructions: ['Combine first 4 ingredients in a saucepan; cook over medium-low heat, stirring constantly until mixture reaches 160:', 'Stir in 3/4 cup bourbon.', 'Cool; cover and chill.', 'Combine chilled mixture and remaining 1/2 cup bourbon in a punch bowl.', 'Gently stir in whipped cream; sprinkle with nutmeg if using.']
- `imp_6857d70c8588521f` 'Soft Zucchini Spice Cookies'
  - ingredient names: ['butter', 'margarine', 'brown sugar', 'egg', 'all-purpose flour', 'baking powder', 'cinnamon', 'salt', 'nutmeg', '1/4 clove', 'milk', 'zucchini', 'walnuts', 'raisins']
  - instructions: ['In a mixing bowl, cream the butter and brown sugar; add the egg and mix well.', 'Combine the dry ingredients; add alternately with milk to creamed mixture. Stir in zucchini, nuts, raisins, and orange peel.', 'Drop by teaspoonfuls 2 inches apart onto greased baking sheets.', 'Bake at 350°F for 12-14 minutes or until edges are lightly browned and cookies are set.', 'Makes about 4 dozen.']
- `imp_5f31fae38cf8588d` 'Bloody Mary'
  - ingredient names: ['vodka', 'tomato juice', 'Worcestershire sauce', 'Tabasco sauce', 'pepper', 'salt', 'green onions']
  - instructions: ['Rub lemon or lime around rim of glass and then put the rim in margarita salt or Tony Chachers, if desired.', 'Add ice to glass.', 'Mix Vodka, tomato juice, lemon juice, Worcestershire sauce, Tabasco, salt, Pepper, celery salt and horseradish (if using) and pour in glass.', 'Garnish with lemon or lime wedge, celery stalk, green onion or pickled green bean.']
- `imp_84d45f89a57252b4` 'Flour Tortillas'
  - ingredient names: ['flour', 'water', 'salt', 'shortening']
  - instructions: ['Mix and knead for 5 minutes.', 'Let rest a few minutes.', 'Pinch off about a  half-dollar size piece and, on a floured surface, roll flat with a rolling pin  until 1/8" thick.', 'Hint: Each time you roll the pin over the tortilla, gently  pick it up and turn it; this gives it the roundness.', 'Also, make sure you are working on a floured surface and keep your rolling pin floured.']
- `imp_4e524f5f9f8759a9` 'Sesame Chicken Cutlets'
  - ingredient names: ['chicken wings', 'soy sauce', 'garlic', 'black pepper', 'Tabasco sauce', 'ginger', 'egg', 'sesame seeds', 'butter', 'margarine']
  - instructions: ['Cut chicken wings in half at the joint and cut off wing tips.', 'Blend next five  ingredients in processor.', 'Pour over chicken and marinate overnight. Remove  chicken from marinade. Pour egg into marinade; combine bread crumbs and sesame  seeds.', 'Dip chicken into crumb mixture; set them in a buttered baking dish.', 'Pour  melted butter over them and bake at 400F for 40 - 50 minutes.']
- `imp_e0cd14eb330f56c0` 'Cowboy Caviar'
  - ingredient names: ['black beans', 'ripe olives', 'onion', 'garlic', 'lime juice', 'salt', 'cumin', 'pepper', 'cream cheese', 'eggs', 'green onions with top']
  - instructions: ['Mix all ingredients except cream cheese, eggs, and green onion.', 'Cover and refrigerate at least 2 hours.', 'Spread cream cheese on serving plate.', 'Spoon bean mixture evenly over cream cheese.', 'Arrange eggs on bean mixture in ring around the edge of the plate; sprinkle with green onion.']
- `imp_ea820ddfbe1b5015` 'Mounds Bars'
  - ingredient names: ['sweetened condensed milk', 'vanilla', 'powdered sugar', 'coconut']
  - instructions: ['Blend the milk and the vanilla.', 'Add the sugar a little at a time till  smooth.', 'Stir in the coconut. The mixture should be firm.', 'Pat firmly  into a 9x13 pan and chill till firm.', 'Cut into bars and dip into melted  chocolate and let cool on waxed paper for several hours.']
- `imp_b540173d0f795cb7` 'Apricot Salsa'
  - ingredient names: ['red bell pepper', 'olive oil', 'onion', 'tomatoes', 'apricots', 'dark rum', 'apple cider']
  - instructions: ['Cut a red bell pepper in half; remove seeds; and roast half of it. (Brush with olive oil; put under broiler very close to heat until blackened, about 5 minutes). Chop.', 'Saute onion in about a tablespoon  of olive oil until translucent.', 'Add tomato and jalapeno; saute about another 5 minutes, until tomato is cooked.', 'Add apple cider to cover apricots and boil down until cider is almost all boiled off.', 'Add chopped roasted bell pepper; stir.', 'Add dark rum and flambe. (Light and swirl until flame goes out).', 'Serve hot over grilled shark, swordfish, shrimp, or marlin.']
- `imp_18c2bb193de15bb3` 'Egg Kichelach'
  - ingredient names: ['eggs', 'vanilla', 'sugar', 'flour']
  - instructions: ['Beat eggs well.', 'Add oil slowly, a little at a time, while still beating.', 'Add  vanilla and sugar.', 'Add half the flour and beat about 3-4 minutes.', 'Add remaining  flour and combine well.', 'Drop by the teaspoon on greased cookie sheet. Bake 7  minutes at 400 degrees, t  hen reduce to 375 degrees for 5 minutes.', 'Turn off oven  and leave kichel in oven for 18 minutes.']
- `imp_84586051001a55ff` 'Basic Crepes II'
  - ingredient names: ['eggs', 'flour', 'milk', 'butter', 'salt']
  - instructions: ['Combine all ingredients in a blender.', 'Whirl one minute; scrape down and blend 15 seconds more.', 'Refrigerate at least one hour before making crepes.', 'Heat a lightly greased 6 inch skillet; remove from heat.', 'Spoon in 2 Tbsp batter; lift and tilt skillet to spread evenly.', 'Return to heat; brown on one side only.', 'To remove, invert pan over paper toweling.', 'Repeat with remaining batter.']
- `imp_0cb08a9986c75010` 'Cinnamon Apple Tart'
  - ingredient names: ['butter', 'puff pastry', 'brown sugar', 'apples', 'lemon juice', 'cinnamon']
  - instructions: ['Brush a little of the butter into a loose bottom 23 cm pie tin.  Preheat oven to 200 C / 400 F/ Gas 6.', 'Roll out the pastry and line the base of the tin with the pastry.   Brush generously with butter and sprinkle half the sugar over the  pastry, avoiding the edges.', 'Toss the apple slices in the lemon juice and coat  with the remaining sugar and cinnamon.', 'Cover the base with the apples, leaving  a 2 cm gap around the edge.  Drizzle the remaining butter over the apples and   dust with a little more cinnamon.', 'Bake in the middle of the oven for 20 - 25  minutes until the apple is soft and slightly golden and the pastry rim looks  crisp.']
- `imp_fea503705584524e` "Patout's Boiled Crawfish"
  - ingredient names: ['crawfish', 'salt', 'white pepper', 'black pepper', 'corn', 'new potatoes', 'white pepper', 'black pepper', 'salt']
  - instructions: ['Wash the crawfish well and pick out any fish bones or other debris.', 'Fill a great big (40-quart) Stockpot a quarter full of water.', 'Add the salt and peppers and bring to boil.', 'Add the whole onions, the corn, and the new potatoes (it will be easy to remove them later if you put them in a cloth sack).', 'Return to boil, cover, lower heat to medium, and let cook for 8 minutes.', 'Add crawfish, cover again and raise heat to high.', 'After steam begins to escape from under the lid, cook 7 minutes more.', 'Remove from heat and let sit for 4 minutes.', 'Do *NOT* remove the lid until this point!', 'Remove the onions, corn, and potatoes to a bowl and drain the crawfish.', 'Place the crawfish in a large insulated container (an ce chest works well, as do the thick waterproof boxes chickens are shipped in, which your butcher may give you for free).', 'Have your *SPRINKLE* ready and sprinkle over the crawfish and mix them well to coat.', 'Cover and let sit for 7 minutes.', 'Serve immediately with the onions, corn, new potatoes, and lots of French bread on a large table covered with plenty of paper.', 'When everyone has eaten his fill, everyone "peels for the house." The peeled tails can then be used in cold crawfish cocktail or salad or for Fried Crawfish the next day.', 'NOTE: Most of the salt is not added until after the cooking process because too much salt added during cooking makes the flesh of the crawfish adhere to the shell.']
- `imp_6892825a21295ba5` "Jan's Butter Tart Squares"
  - ingredient names: ['butter', 'flour', 'brown sugar', 'eggs', 'brown sugar', 'oatmeal', 'salt', 'vanilla', 'walnuts', 'raisins']
  - instructions: ['Filling: 2 eggs 1 1/2 cups brown sugar 1/2 cup oatmeal 1/4 tsp salt 1 tsp vanilla 1/2 cup chopped walnuts 1/2 cup raisins Crust: Cut butter into flour until crumbly.', 'Press into 9x9" buttered pan.', 'Bake at 350F for 15 minutes.', 'Filling: Mix filling ingredients.', 'Pour over partially baked crust and return to oven for 20 minutes.', 'Cool before cutting.']

## Revisions

**Round 1** (2026-07-18, advisor ruling on this round's own 220709Z HALT
report; docs/instructions_integrity_spec.md remains the frozen base spec).
Baseline (pre-round-1, 220709Z report): 1197/4045 = 29.59% flagged.
This round's result (all changes below active together): 1130/4045 = 27.94%
flagged -- still a HALT (> 12% ceiling); a HUMAN GATE per spec Sec. 3
("maximum two revision rounds") if round 2 does not clear the ceiling.

Per-rule leave-one-out ablation (flagged-recipe count with ONLY that one
rule reverted, all others held active, vs. this round's 1130 final count):

- Commentary-prefix step-wide suppression (new; "NOTES:"/"NB:"/"TIPS:"/
  "VARIATIONS:"/"COLUMN:"/"GARNISHING NOTE:"/"SERVING SUGGESTIONS:"/
  "SUGGESTED ACCOMPANIMENTS:"): 1138 without it -> 1130 with it (clears 8
  recipes' worth of quarantine-worthy mismatches).
- Optional-variation/cross-reference step-wide suppression (new; "as
  desired"/"if desired"/"if you like"/`\boptional(?:s|ly)?\b`/"same
  quantities as"/"menu featuring"): 1147 without it -> 1130 with it
  (clears 17).
- `\bsubstitutes?\b` added to the generic whole-step negation phrases:
  1135 without it -> 1130 with it (clears 5). Deliberately excludes
  "substituted" (past tense) -- see the module's inline citation.
- "soymilk" added as a satisfier-only extra for BOTH `soy` and `dairy`:
  1134 without it -> 1130 with it (clears 4).
- "roast" (`\broasts?\b`, not "roasted") added as a satisfier-only extra
  for `meat`: 1132 without it -> 1130 with it (clears 2).
- "trassi" added as a satisfier-only extra for `crustacean`: 1130 without
  it -> 1130 with it (clears 0 marginally in this leave-one-out ordering --
  its one cited case, imp_f26d5c5093e25ac7, is already independently
  cleared by the commentary-prefix rule above for the same step; kept as
  defense-in-depth per the ruling for any future row that mentions trassi
  outside a suppressed step).
- Tier B composite in-recipe-stock satisfier (mollusk-row arm OR
  water-row+animal-row arm): 1161 without it -> 1130 with it (clears 31 --
  this round's single largest contributor). Both planted Tier B faults
  (imp_ece8c7dd17b95468 "Dirty Rice", imp_acd7c3ec0ed35a51 "Rice, Apple and
  Raisin Dressing") were re-verified to still flag after this change.
- "sparerib"/"spare rib" added to MEAT_FLESH_TERMS (triggers AND
  satisfiers): 1128 without it -> 1130 with it -- this is the one rule in
  this round that INCREASES the flagged count (catches 2 real corpus
  misses net), rather than suppressing false positives.

**Discovered conflict, flagged rather than silently patched:** the ruling's
own cited example for the sparerib addition, imp_6f3463afcc2f5d51 "Pork
Spareribs in Tangy Sauce," does NOT end up in this round's quarantine-worthy
list despite "sparerib" now correctly firing as a trigger. Its own
"Worcestershire sauce" ingredient row already satisfies the `meat` category
via the PRE-EXISTING (spec Sec. 2, not part of this ruling) satisfier
design -- `meat`'s satisfiers include `FISH_TERMS`, which contains
"worcestershire" (cited there as a fish-allergen condiment), on the
documented rationale that "a row already containing ANY animal-flesh OR
fish/crustacean/mollusk term is already non-vegetarian at serve time." This
executor pass did NOT alter `meat`'s satisfier composition (out of this
ruling's literal scope, and a corpus-wide architectural call); the
sparerib/spare-rib addition is still net positive (+2 other real corpus
misses caught) despite not fixing its own cited example. See
`tests/test_instructions_ingredient_integrity.py::
test_imp_6f3463afcc2f5d51_sparerib_trigger_added_but_worcestershire_row_still_satisfies_meat`
for the pinned regression and a companion synthetic test isolating the
trigger's effect without the conflict.

**Resolved in round 2** (see below, ruling item 12): the architectural call
this conflict was flagging for was made -- "worcestershire"/"puttanesca"
removed from `meat`'s satisfiers. The pinned regression test was rewritten
(renamed to `test_imp_6f3463afcc2f5d51_sparerib_trigger_now_flags_meat_
after_worcestershire_satisfier_removed`) to assert the FLIPPED, now-correct
behavior.

**Rejected candidates (spec ruling item 7 -- recorded, not implemented):**
- `except` as a negation phrase: corpus evidence (imp_2433f1f7486a57dc,
  imp_19ce1a09db625d96, imp_180066ee5652529a) shows "except" marks
  sequencing/exclusion-from-a-later-step, not an absence claim about the
  recipe's own content.
- "also a great addition" as a suppression phrase: imp_c846d8efd9895c8d's
  own step contains a genuine "Add cranberries and nuts" alongside it, so
  whole-step suppression there would hide a real mismatch.
- An addition-verb requirement for Tier B stock satisfaction: would rewrite
  the frozen Tier B semantics and misses "simmer in broth"-shaped
  in-recipe-stock forms that have no explicit addition verb.


**Round 2** (2026-07-18, advisor ruling on round 1's own 231309Z HALT
report's sample audit and miss spot-check; docs/instructions_integrity_
spec.md remains the frozen base spec -- every round-2 rule below is a
per-item ruling on top of it, not a spec amendment).
Baseline (round 1 final, 231309Z report): 1130/4045 = 27.94% flagged.
This round's result (all changes below active together): 1156/4045 = 28.58%
flagged -- still a HALT (> 12% ceiling), a slight RISE from round 1
(misses fixed -- rules 10, 11, 12 -- outweigh the false positives cleared
by rules 1-5, 7, 8, 9). Per spec Sec. 3 ("maximum two revision rounds"),
this is round 2 of 2: the outcome is the pre-registered HUMAN GATE on the
corpus itself -- reported without alarm, exactly as pre-registered.

Per-rule leave-one-out ablation (flagged-recipe count with ONLY that one
rule reverted, all others -- round 1's and round 2's -- held active, vs.
this round's 1156 final count):

- Item 1, commentary-prefix marker generalized from step-initial to
  ANYWHERE-in-step: 1160 without it (reverted to step-initial-only) -> 1156
  with it (clears 4). Cite imp_2380cadece955cc7 "Alfredo Sauce with Pasta"
  (mid-step "Variation:" marker the round-1 anchor missed).
- Item 2, "can add"/"can be added" added to the optional-variation
  step-wide suppression phrases: 1158 without it -> 1156 with it (clears
  2). Cite imp_3233766015ca524d "Buttermilk Jalapeno Cornbread".
- Item 3, "if serving" added to the serving-cue phrases: 1157 without it ->
  1156 with it (clears 1). Cite imp_9b2c1d45a9f55ef1 "Alfredo Sauce".
- Item 4, whole-step suppression on `^\s*serve\b`: 1179 without it -> 1156
  with it (clears 23 -- this round's single largest FP-clearing
  contributor). Cite imp_748b6422ecbb5c7d "Polish Sausage and Peppers".
  Counter-case imp_fbf6565762c0590d "Mabo Dofu" (non-initial "serve")
  re-verified to still flag sesame.
- Item 5, whole-step suppression on `^\s*dip\b` AND NOT `\bin(?:to)?\b`:
  1157 without it -> 1156 with it (clears 1). Cite imp_e7fb53c18ced5dc0
  "Beer Batter". Counter-case imp_a22b3c09a6b25bb5 "Crispy Baked Fish &
  Herbs" (contains "in") re-verified to still flag fish.
- Item 7, "cheese cloth"/"cheese-cloth" exact-phrase suppression (->
  "cheese"): 1158 without it -> 1156 with it (clears 2). Cite
  imp_13e739367b505085 "Spiced Pear Butter".
- Item 8, "ketjap manis"/"kecap manis"/"ketjap"/"kecap" satisfier-only
  extras for BOTH `soy` and `wheat_gluten`: 1158 without it -> 1156 with it
  (clears 2). Cite imp_d287af8d742e5d44 "Katjang Sauce: Peanut Sauce".
- Item 9, Tier B pot-liquor arm 3 (occurrence-level addition-verb/
  purchased-word evidence filter, applied only when >=1 animal row is
  present): 1172 without it -> 1156 with it (clears 16 -- this round's
  second-largest FP-clearing contributor). Cite imp_a76aa35639d85deb
  "Borscht II". All five pinned arm-3 cases (Borscht cleared; Lasagna
  Rollups, Escalope of Salmon, Dirty Rice, Beef Stroganoff kept) re-
  verified.
- Item 10, bare "rib" TRIGGER-ONLY extra for `meat` (with the celery/
  "rib of celery"/"seeds and ribs" guards): 1149 without it -> 1156 with it
  -- INCREASES the flagged count by 7 (a genuine-miss fix, not an FP
  suppression). Cite imp_635b6cd0fbd557ad "Hutspot". Guard re-verified:
  imp_41bfceea6ba65b47 "Corn Chowder"'s `-3 celery ribs` ingredient row
  does not flag meat.
- Item 11, `crust`/`pie shell`/`crepe` added as wheat_gluten triggers (with
  the crust-verb-use following-token guard, the "crepe pan" exact-phrase
  guard, and the crust/pie-shell cookie-like and crust-only nut/coconut
  composite satisfiers): 1099 without it -> 1156 with it -- INCREASES the
  flagged count by 57, this round's single largest miss-fixing contributor
  (matches the miss spot-check's MISS 2 CLASS finding, which was one
  vocabulary gap spanning many corpus rows, not an isolated case). Cite
  imp_15fe9cc27b96537b "Pumpkin-Pecan Pie" (pie shell), imp_d63bae35bb3a55bb
  "Austrian Sweet Cheese Crepes" (crepe); composite satisfier verified NOT
  to over-suppress via imp_fe5e997cb47c553c "Chocolate-Caramel-Pecan
  Cheesecake" (graham cracker crumbs row satisfies crust) while still
  catching imp_15fe9cc27b96537b's pecan-only row set (pecans do NOT satisfy
  "pie shell" -- only the `crust` term gets the nut/coconut composite arm).
- Item 12, "worcestershire"/"puttanesca" removed from `meat`'s satisfiers:
  1141 without it -> 1156 with it -- INCREASES the flagged count by 15 (the
  round-1-discovered conflict's resolution). Cite imp_6f3463afcc2f5d51
  "Pork Spareribs in Tangy Sauce" (now correctly flags meat). Accepted
  residual FP this creates: imp_712db6319e3957c7 "Apricot Basting Sauce"
  ("Use sauce over chicken, pork, and lamb" -- a legitimate serving-target
  mention for a sauce recipe, not a hidden-meat claim; deliberately NOT
  patched with a `^use` rule per the ruling, pinned as an accepted-residual
  test instead).

**Rejected candidates (recorded, not implemented):**
- Item 6, named variation-block header suppression (e.g. "San Francisco:")
  for imp_ab6b542e34555631 "The Bottomless Chicken Soup Pot": REJECTED.
  Rationale (per the ruling): any generic header-line suppression rule
  (a capitalized word/phrase followed by a colon, step-initial or not)
  would also swallow genuine sub-component headers this same corpus uses
  constantly -- "CINNAMON WHIPPED CREAM:", "For the Meringue:", "Cooking
  the steak:", the MasterCook praline block header -- each of which
  introduces REAL recipe content, not an optional variation. No safe,
  general distinguishing rule between the two header shapes was found;
  imp_ab6b542e34555631 remains a documented residual FP (see RESIDUALS
  below), not a suppressed one.
- Bare "bones" as a meat trigger (considered alongside item 10's "rib"):
  REJECTED. Redundant for imp_635b6cd0fbd557ad "Hutspot" ("rib" already
  catches it) and over-triggers on the harmless "Flake fish, discarding
  skin and bones" (imp_d3a91c593c3d55b2 "Green and Gold Chowder" --
  already a genuine fish miss via its own "fish" trigger, not a bones one).

## Residuals (documented, not fixed this round)

Three known false-positive/leniency classes, recorded here with enough
detail to act on later (per this repo's "Default to backlog" convention)
rather than patched with an overfit, single-case rule:

1. **imp_ab6b542e34555631 "The Bottomless Chicken Soup Pot" (item 6,
   rejected above).** Its "San Francisco: ... 2 tablespoons soy sauce ..."
   named-variation-block header is not suppressed and remains a
   quarantine-worthy soy/wheat_gluten flag on this recipe, even though the
   base chicken-soup dish itself is complete. Any future fix needs a
   distinguishing signal between an optional-regional-variant header and a
   genuine recipe-component sub-header ("For the Meringue:") that this
   round did not find.
2. **imp_3aee17154e8c59e9 "Apple Raisin Cobbler Pie" (item 11).** Will NOT
   flag wheat_gluten for its own "Spoon into crust" mention, despite being
   the SAME miss-spot-check MISS 2 class as imp_15fe9cc27b96537b/
   imp_d63bae35bb3a55bb above -- its own "all-purpose flour" ingredient row
   satisfies the wheat_gluten category under the PRE-EXISTING, category-
   wide core leniency (any WHEAT_GLUTEN_TERMS-matching row satisfies ANY
   wheat_gluten trigger in the same recipe, not just the specific one that
   fired) before the new per-term crust/pie-shell composite filter is even
   reached. Not a bug in the new rule -- a pre-existing design property
   surfaced by it. No action taken (working as designed for every OTHER
   wheat_gluten trigger too).
3. **imp_712db6319e3957c7 "Apricot Basting Sauce" (item 12).** Accepted
   residual FP -- see item 12's own entry above. Pinned as
   `test_imp_712db6319e3957c7_apricot_basting_sauce_accepted_residual_fp_
   flags_meat` so it shows up as an intentional, documented diff rather
   than a silent surprise on any future vocabulary change.

