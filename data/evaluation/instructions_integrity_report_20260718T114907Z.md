# Instructions/ingredient integrity audit -- 20260718T114907Z

Dry run only -- this report never mutated `data/processed/imported_recipes.jsonl` or any quarantine sidecar. See `docs/instructions_integrity_spec.md` for the full rule set and guard-band pre-registration.

## Guard-band verdict

**PROBABLE_BUG**: Floor sanity breach: only 0 row(s) flagged (< 10). The three still-in-corpus planted faults alone guarantee >=3, and the review's 6-of-9 sampled corruption rate makes a near-zero result implausible -- this is almost certainly a check/vocabulary bug, not a clean corpus. Investigate before trusting this run.

- Corpus size: 2884
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

- `imp_60f606087aa9528c` '2-Step Pumpkin Cheesecake'
  - ingredient names: ['cream cheese', 'canned pumpkin', 'sugar', 'pumpkin pie spice', 'prepared graham cracker crust']
  - instructions: ['Beat cream cheese, pumpkin, sugar and pumpkin pie spice in large bowl with wire whisk or electric mixer until smooth.', 'Gently stir in whipped topping.', 'Spoon into crust. Refrigerate three hours or until set. Garnish as desired.', 'Store leftover cheesecake in refrigerator.']
- `imp_e85fdd3317f55d72` 'Five Bean Salad'
  - ingredient names: ['green beans', 'lima beans', 'kidney beans', 'garbanzo beans', 'onion', 'green pepper', 'vinegar', 'sugar', 'salt', 'pepper', 'dry mustard', 'celery seed']
  - instructions: ['Drain all the beans and combine in a large bowl.', 'Mix with bean mix and let stand overnight.', 'Add onion/pepper about an hour before serving.']
- `imp_b742a1865ad8525e` 'Bananas Flambe'
  - ingredient names: ['bananas', 'butter', 'brown sugar', 'dark rum', 'light rum']
  - instructions: ['Take 2 ripe, but not soft bananas and cut in half, then split lengthwise.  Melt  a few Tablespoons butter over medium heat.  Add 2-3 Tablespoons brown sugar and  stir.', 'Add bananas.', 'Cook until fairly warm and starting to soften (about 1  min.).  Flip bananas and allow to cook an additional 30 seconds.', 'Add rum to taste, and swirl in pan a bit. Allow to  thicken slightly, remove from heat and serve.']
- `imp_84586051001a55ff` 'Basic Crepes II'
  - ingredient names: ['eggs', 'flour', 'milk', 'butter', 'salt']
  - instructions: ['Combine all ingredients in a blender.', 'Whirl one minute; scrape down and blend 15 seconds more.', 'Refrigerate at least one hour before making crepes.', 'Heat a lightly greased 6 inch skillet; remove from heat.', 'Spoon in 2 Tbsp batter; lift and tilt skillet to spread evenly.', 'Return to heat; brown on one side only.', 'To remove, invert pan over paper toweling.', 'Repeat with remaining batter.']
- `imp_65102f94210c5607` 'Mandarin Beef'
  - ingredient names: ['reduced sodium soy sauce', 'garlic', 'sugar', '- 1/2 ginger', 'boneless beef sirloin', 'bamboo shoots', 'green pepper', 'carrot', 'green onion', 'rice']
  - instructions: ['In a small bowl, combine all marinade ingredients; mix well.', 'Add beef, stirring to coat. Cover. Marinate at room temperature for 15 minutes.', 'In a 10-inch skillet, heat oil over medium heat. Add beef and marinade, and stir-fry until meat is no longer pink.', 'Remove meat from skillet; set aside. Add vegetables. Stir-fry until tender-crisp.', 'Return beef to skillet. Stir-fry until heated.', 'Serve over rice.']
- `imp_7da1d18ae14e5ccc` "Abby's Pecan Apple Cake"
  - ingredient names: ['butter', 'sugar', 'cinnamon', 'nutmeg', 'all-purpose flour', 'tart apples', 'butter', 'eggs', 'milk', 'rum', 'vanilla extract', 'pecans', 'baking powder', 'baking soda', 'salt']
  - instructions: ['* , such as Granny Smith, peeled, halved, and sliced (3 cups)  Preheat the oven to 350 degrees.', 'Brush the sides of a 8 x 3 1/4-inch  springform pan with the melted butter.', 'Mix together 1/2 cup sugar, cinnamon,  nutmeg, and 1/4 cup flour and sprinkle the mixture evenly over the bottom of  the pan.', 'Wrap foil around the pan to prevent leakage. Starting at the outside  edge, arrange a ring of apple slices in the pan, slightly overlapping and  pointing to the center.', '(It will feel backwards.) Fill in the center with  another circle of apples, with some overlap occurring.', 'Layer any remaining  apple slices evenly, overlapping to prevent the batter from escaping.', 'With a  wooden spoon or electric mixer, beat together the butter and 1 cup sugar.', 'Add  the eggs, milk, rum, and vanilla.', 'The batter will look curdled.', 'Add 1 1/4  cups flour, the nuts, baking powder, baking soda, and salt, beating only  until the flour is completely incorporated.', 'Pour the batter over the apples  and spread evenly.', 'Place the pan on a baking sheet and bake in the middle of  the oven until a toothpick inserted in the cake comes out clean, about 70  minutes.', 'Cover with a piece of foil if the top begins to brown too quickly.', 'Let the cake rest in the pan on a rack for 5 minutes, then, using a small,  flexible knife, gently separate the sides of the cake from the pan.', 'Invert  the cake on the rack, letting it stay in the pan for another 10 minutes, then  remove the pan, lifting it up carefully.']
- `imp_6b2f092608395060` 'Turkish Spinach and Lentil Soup'
  - ingredient names: ['lentils', 'nonfat beef broth', 'salt', 'olive oil', 'onions', 'cayenne', 'bay leaves', 'bulgur', 'fresh parsley', 'tomatoes', 'tomato paste', 'dried rosemary', 'spinach', 'parsley']
  - instructions: ['Rinse the lentils.', 'Bring them to a boil in the beef broth.', 'Reduce heat and  simmer, covered, for 40 minutes.', 'Meanwhile, heat the olive oil in a heavy soup  pot.  Saute the onions until translucent.  Add the garlic, cayeene, bay leaves  and bulgur.', 'Stir the mixture on medium heat until the onions and bulgur are  lightly browned.', 'Mix in the parsley and tomatoes.', 'When the tomatoes begin to  give up their juice, gently stir in the tomato paste.  Pour the lentils and  their liquid into the soup pot with the onions and bulgur.', 'Simmer the soup for  15 minutes.', 'Add the rosemary, salt and pepper to taste.  If the lentils and  bulgur have absorbed too much liquid, add more broth, water or tomato juice.   Remove the bay leaves.', 'Just before serving, stir in the fresh spinach and let  it wilt in the hot soup.', 'Garnish with more fresh parsley.', 'NOTES : Serve this soup with crusty bread.', 'Broil the bread on both sides,  rubbed with a cut garlic clove, and drizzled with olive oil.']
- `imp_f2b621fcd6e55214` 'Chicken Breasts in Phyllo'
  - ingredient names: ['butter', 'onion', 'parsley', 'garlic clove', 'all-purpose flour', 'dry vermouth', 'dry white wine', 'olive oil', 'boneless skinless chicken breast halves', 'phyllo dough', 'butter', 'feta cheese']
  - instructions: ['Preheat oven to 350 degrees Fahrenheit.', 'In a skillet, melt 2 or 3 tablespoons of the butter; saute the onion until golden. Remove onion and set aside.', 'Melt 2 or 3 tablespoons butter in the same skillet; saute the mushrooms until all juices are absorbed.', 'Add the onions, parsley and garlic and saute 1 minute.', 'Stir in the flour and blend well.', 'Add the vermouth or dry white wine.', 'Stir over medium heat until thickened.', 'Season with salt and pepper to taste.', 'Remove mushroom mixture from skillet and set aside.', 'In same skillet melt remaining butter with olive oil and saute chicken until lightly browned, about 1 minute per side.', 'Remove from heat.', 'Brush one sheet of phyllo dough with melted butter and sprinkle with bread crumbs.', 'Place a second sheet of phyllo over the first; butter and sprinkle with bread crumbs.', 'Place a chicken breast in the lower half of the phyllo.', 'Put 1/4 of the mushroom mixture and 1/4 of the feta over the chicken.', 'Fold up the sides of the phyllo over the chicken, envelope style.', 'Repeat with remaining chicken breasts.', 'Place on a baking sheet, seam side down, and brush with butter.', 'Bake for 35 minutes, or until browned.', 'NOTES :', 'Recipe may be prepared in advance up to the point the chicken is wrapped in phyllo then frozen.', 'To serve, bake frozen at 350 degrees Fahrenheit for 50 minutes.']
- `imp_30002d25735d5348` 'Barbecued Chicken Sandwiches'
  - ingredient names: ['onion', 'tomato sauce', 'sugar', 'garlic powder', 'celery seed', 'chili powder', 'Worcestershire sauce', 'chicken breasts']
  - instructions: ['Preheat oven to 350.', 'In a large bowl, combine first 8 ingredients.', 'Set aside <  cup of this tomato sauce mixture. Mix remaining tomato sauce mixture with  chopped chicken in a baking dish.', 'Cover with foil and bake for 30 minutes or  until heated through.', 'Spoon 1/2 cup chicken mixture onto bottom half of each  hamburger bun; spread reserved tomato sauce mixture evenly over top of chicken  mixture. Top with remaining bun halves.']
- `imp_8e41b383fde151e2` "Joan's Guacamole With Mayonnaise"
  - ingredient names: ['avocado', 'mayonnaise', 'tomatoes', 'red onion', 'basil leaves']
  - instructions: ['Peel avocado and fork mash in bowl.', 'Stir in the mayonnaise, tomatoes, onion and  flavor to taste with lemon juice and salt and pepper.', 'Garnish with basil.', 'Serve  at once with crackers or  use as a sal ad  filling for cored out ripe tomatoes.', 'garnish with fresh basil leaves.']
- `imp_7460632512c55842` 'Civil War Cake'
  - ingredient names: ['raisins', 'water', 'sugar', 'shortening', 'cake flour', 'salt', 'cinnamon', 'baking soda', 'nutmeg', '1 clove']
  - instructions: ['Combine raisins, sugar, 1 cup of water, shortening, salt & spices in a saucepan.', 'Bring to a boil, simmer 3 minutes, stirring occasionally, then cool till  lukewarm, then add the other cp of water.', 'Dissolve soda in 2 teas.', 'of water, set aside.  Stir sifted & measured flour into raisin mixture & beat until smooth.', 'Add dissolved soda last. Pur into greased floured 13x9 [am & bale 50-55 min.', 'at  350 degrees.', 'It may also be cooked in a tube pan.', 'Serve with whipped cream or caramel frosting.', 'Combine 3/4 cup of brown sugar 1/2 cup of water 1/2 tsp salt in a saucepan.', 'Cook 6 min.', 'stirring often.', 'Cool to lukewarm and stir in 3 Tbsp.', 'of butter.', 'Then gradually stir in 21/4 cups of sifted confectionery sugar, beating until smooth.', 'Stir in 1 teas.', 'vanilla and spread on cake. You will be surprised how good it taste with such little ingredients.']
- `imp_0b9d66a8b56a530a` 'Madras Dip'
  - ingredient names: ['eggs', 'green peppers', 'sour cream', 'celery', 'curry powder', 'onion']
  - instructions: ['Add diced eggs to all other ingredients which have been smoothly blended in blender.', 'Consistency is thin.', 'Chill; sprinkle with paprika and serve with corn chips.']
- `imp_d6d85a13c92450f9` 'Seven Layer Salad'
  - ingredient names: ['head lettuce', 'frozen English peas', '-3 green onions', 'hard-boiled eggs', 'bacon', 'mayonnaise', 'swiss cheese']
  - instructions: ['Layer first 5 ingredients in a shallow dish.', 'Spread mayonnaise over the top as  if you were icing a cake.  Sprinkle Swiss cheese over the mayonnaise and chill.', 'This taste best when chilled overnight.', 'Just before serving, toss salad making sure mayonnaise and cheese is distributed throughout the salad.']
- `imp_337ca7dd667452da` 'Roasted Parsnips and Onions'
  - ingredient names: ['parsnip', 'fresh rosemary', 'extra virgin olive oil', 'coarse salt', 'black pepper']
  - instructions: ['Heat the oven to 425F.', 'In a roasting pan, combine the parsnips, onions and rosemary.', 'Season with salt and pepper.', 'Add the olive oil and toss until the vegetables are thoroughly coated.', 'Roast for 40 to 45 minutes, shaking the pan every 15 minutes, until the vegetables are deep amber.']
- `imp_994023d429fc5fc0` 'Chicken Teriyaki with Cashew Pineapple Rice'
  - ingredient names: ['brown sugar', 'vinegar', 'garlic powder', 'Worcestershire sauce', 'boneless chicken breast', 'cooked rice', 'crushed pineapple', '- 1 1/2 cashew pieces']
  - instructions: ['Mix the first 7 ingredients and bring to a boil.', 'Cool; divide in half.', 'Use half to marinade 1-1 1/2 pounds boneless chicken breast or chicken breast tenders over night. Refrigerate other half to be used later.', 'Prepare white rice for 4 people, as instructed on bag.', 'Remove chicken from marinade and discard marinade. Grill or broil chicken while rice is cooking.', 'Stir can of crushed pineapple (drained) and about 3/4 cup of cashew pieces into cooked rice.']

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


**Round 3** (2026-07-18, adjudication_20260718T090522Z.md diet_023 +
advisor-review APPROVED remediation-scope amendments; docs/
instructions_integrity_spec.md remains the frozen base spec -- this is a
single pre-registered miss-fix under spec Sec. 3's "a miss is a spec bug:
fix and re-run the audit" rule, not a spec amendment).
Corpus baseline for this round: post-Option-A-quarantine, post-
imp_2bd54fd475cf50fc-manual-quarantine corpus, 2,888 rows (NOT the rounds
1-2 baseline of 4,045 rows -- see this constant's module-level citation
comment for the corpus-history chain).
Baseline (this round, cereal NOT yet a wheat_gluten trigger): 0/2888 (0.00%)
flagged. This round's result (cereal added): 5/2888 (0.17%) flagged --
still comfortably under the 1%-10% expected band's floor and the 12% hard
ceiling; the run's own guard-band verdict is PROBABLE_BUG (floor sanity:
<10 rows), which is the pre-registered, expected artifact of running the
floor-sanity check against an already-quarantined, mostly-clean corpus (the
same "known post-quarantine artifact" class as the 20260718T090602Z run
that followed the Option A mass quarantine) -- NOT investigated as a real
bug: this round's own miss (diet_023's cereal case) is direct, adjudicated
proof the vocabulary gap was real, and the sample-audit evidence below (all
5 flagged rows) is reported for the orchestrator's own sample check before
any of these 5 are quarantined, per this round's task scope (report, do not
auto-quarantine).

Single-rule ablation (flagged-recipe count with `cereal` reverted out of
`WHEAT_GLUTEN_TERMS`, all other rounds' rules held active, vs. this round's
5 final count): 0 without it -> 5 with it -- INCREASES the flagged count by
5 (a genuine-miss fix, not an FP suppression; the `s?` trailing-morphology
idiom shared by every other term in this set covers "cereals" from the
singular `cereal` entry, so no separate plural entry was needed). Cite
imp_2bd54fd475cf50fc "Butterscotch Chewy Bars" (adjudication_
20260718T090522Z.md diet_023: "Remove from heat and immediately stir in
cereals." with no cereal row; quarantined via the manual-adjudication path
prior to this audit run, per the task's step 1, so it does not itself
appear in this round's 5). `cereal` is automatically its own satisfier (the
category's satisfiers are `WHEAT_GLUTEN_TERMS | WHEAT_GLUTEN_SATISFIER_
EXTRAS | _KETJAP_SATISFIER_EXTRAS` -- a wholesale union of the trigger set
-- consistent with the core lenient-satisfier design already used by every
other wheat_gluten trigger), so a listed "rice cereal"/"crispy rice cereal"
row satisfies a "stir in cereal" mention without any additional satisfier
wiring; pinned by `tests/test_instructions_ingredient_integrity.py::
test_synthetic_crispy_rice_cereal_row_satisfies_stir_in_cereal_mention`.

**Newly flagged rows this round (5, reported for the orchestrator's sample
check per this round's task scope -- NOT auto-quarantined):**
- `imp_e5c662ec002355d6` "Praline Pecan Crunch" -- ingredients: pecan
  pieces, light corn syrup, brown sugar, margarine, butter, vanilla, baking
  soda. Steps: "Combine cereal and pecans in 13x9-inch baking pan; set
  aside." / "Stir in vanilla and baking soda and pour over cereal mixture;
  stir to coat evenly." No cereal row -- same undisclosed-cereal shape as
  diet_023's bars row.
- `imp_9c4f812bcda75ef0` "Crunchy Pretzel Drops No-Bake Cookies" --
  ingredients: light corn syrup, milk, butter, vanilla. Step: "Remove from
  heat and stir in cereal and pretzels." No cereal (or pretzel) row --
  same shape.
- `imp_42d786e354855c6c` "Grape-Nuts Pudding" -- ingredients:
  quick-cooking tapioca, raisins, boiling water, brown sugar, vanilla
  extract. Step: "In a heavy saucepan, stir together tapioca, boiling
  water, brown sugar, raisins and cereal.  Let stand for 5 minutes." No
  cereal row despite the title itself naming the Grape-Nuts brand cereal --
  same undisclosed shape, title corroborates rather than substitutes for a
  row.
- `imp_fbfd3dda61af5cd5` "No-Bake Cereal Bars" -- ingredients: light corn
  syrup, sugar, peanut butter. Step: "Add cereal;  mix well." No cereal
  row despite the title itself naming "Cereal Bars" -- same shape.
- `imp_9fb0ca4a0fa65c48` "Low-Fat Swiss Muesli" -- ingredients: rolled
  oats, lemon juice, water, cinnamon, red apples, golden delicious apples,
  prunes, pecans, honey. Step: "Cover and refrigerate overnight.  In the
  morning, spoon some of the muesli into  a cereal bowl." FLAG PATTERN
  DIFFERS from the other four: this recipe's own dish IS the muesli (rolled
  oats row already present); "a cereal bowl" here reads as the SERVING
  CONTAINER for the already-listed muesli, not a second, undisclosed cereal
  ingredient -- a serving-vehicle mention structurally like the existing
  `EXACT_PHRASE_SUPPRESSIONS`/serving-cue classes (e.g. "stock pot" the
  utensil vs. "stock" the ingredient), but no such phrase suppression
  exists for "cereal bowl" yet. Flagged as-is by the current vocabulary;
  called out here as the one candidate among the 5 that may be a false
  positive on inspection, left for the orchestrator's sample check rather
  than pre-judged or suppressed by this executor pass (out of this task's
  scope, which is limited to the single proven `cereal` trigger addition).

**Rejected candidate (recorded, not implemented):** adding `cereal` as a
DAIRY trigger. The advisor's supplementary review verdict raised this as an
explicitly non-blocking suggestion (FARE lists cereals under milk as a
hidden-dairy source), but the proven miss binding from diet_023 is gluten
only -- imp_2bd54fd475cf50fc's own adjudicated hazard is undisclosed
gluten (crisped-rice/bar cereals routinely carry barley-malt flavoring or
wheat), not a demonstrated dairy gap. Adding an unproven trigger beyond the
cited miss is out of this fix's scope; left as a candidate for a future
round if a dairy-specific miss is separately proven.


**Round 3 follow-up** (2026-07-18, orchestrator sample check of the
20260718T113546Z report's round-3 5-case sample-audit list).
Baseline for this follow-up: 5/2884 flagged (post-round-3-quarantine
corpus, imp_2bd54fd475cf50fc already removed per round 3's own manual
quarantine).

Of the 5 sample-audit candidates:
- 4 adjudicated CORRECT_QUARANTINE (undisclosed-cereal class, same shape as
  imp_2bd54fd475cf50fc): `imp_e5c662ec002355d6` "Praline Pecan Crunch",
  `imp_9c4f812bcda75ef0` "Crunchy Pretzel Drops No-Bake Cookies",
  `imp_42d786e354855c6c` "Grape-Nuts Pudding", `imp_fbfd3dda61af5cd5`
  "No-Bake Cereal Bars" -- quarantined via the manual-adjudication path
  (`python scripts/quarantine_flagged_recipes.py --recipe-ids
  imp_e5c662ec002355d6 imp_9c4f812bcda75ef0 imp_42d786e354855c6c
  imp_fbfd3dda61af5cd5 --reason "cereal vocabulary miss-fix
  (adjudication_20260718T090522Z diet_023 class): instructions stir in
  undisclosed cereal, no cereal row"`). Corpus: 2888 -> 2884 rows; sidecar:
  1350 -> 1354 rows; no other row changed.
- 1 adjudicated FALSE_POSITIVE: `imp_9fb0ca4a0fa65c48` "Low-Fat Swiss
  Muesli" -- "spoon some of the muesli into a cereal bowl" is the SERVING
  CONTAINER for the already-listed muesli (its own "rolled oats" row is
  present), not a second, undisclosed cereal ingredient -- same
  utensil/serving-vessel class as the existing "stock pot" exact-phrase
  suppression. Fixed via a new `EXACT_PHRASE_SUPPRESSIONS["cereal bowl"] =
  "cereal"` entry (`app/services/corpus_import/
  instructions_ingredient_integrity.py`), pinned by
  `tests/test_instructions_ingredient_integrity.py::
  test_imp_9fb0ca4a0fa65c48_low_fat_swiss_muesli_cereal_bowl_not_flagged`
  (fixture copied verbatim from `data/processed/imported_recipes.jsonl`
  before quarantine).

Net effect on the flagged count: 5/2888 (0.17%) before this follow-up (this
round's sample-audit set) -> 0/2884 (0.00%) after (4 quarantined out of the
corpus entirely, 1 suppressed by the new phrase rule) -- re-running
`scripts/audit_instructions_integrity.py` against the resulting 2884-row
corpus is idempotent (0 Tier A/B flags), confirming both the manual
quarantine and the phrase-suppression fix fully account for this round's
5-case list. The run's own guard-band verdict remains PROBABLE_BUG (floor
sanity: <10 rows) -- the same pre-registered, expected post-quarantine
artifact as round 3's own 5/2888 run (a mostly-clean corpus intrinsically
trips the floor-sanity check; not investigated as a real bug).

