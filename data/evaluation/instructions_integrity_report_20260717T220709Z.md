# Instructions/ingredient integrity audit -- 20260717T220709Z

Dry run only -- this report never mutated `data/processed/imported_recipes.jsonl` or any quarantine sidecar. See `docs/instructions_integrity_spec.md` for the full rule set and guard-band pre-registration.

## Guard-band verdict

**HALT**: Hard ceiling breach: 1197/4045 = 29.59% flagged (> 12%). HALT per spec Sec. 3: analyze the false-positive classes in this report, add suppressions (each cited with a real example), and re-run. Maximum two revision rounds; if still above the ceiling, this is a HUMAN GATE -- the corpus is majority-defective for safety purposes and replacing/re-importing it is a product decision, not an automated purge.

- Corpus size: 4045
- Flagged (Tier A+B, quarantine-worthy): 1197 (29.59%)
- Tier A: 1236
- Tier B: 222
- Tier C (report-only, never quarantines): 1084 recipes, 1246 mismatch pairs

## Per-category counts (Tier A/B, quarantine-worthy)

- `wheat_gluten` (tier A): 372
- `stock` (tier B): 222
- `egg` (tier A): 210
- `meat` (tier A): 157
- `nut` (tier A): 135
- `dairy` (tier A): 120
- `tree_nut` (tier A): 113
- `fish` (tier A): 42
- `sesame` (tier A): 34
- `peanut` (tier A): 24
- `crustacean` (tier A): 15
- `soy` (tier A): 13
- `mollusk` (tier A): 1

## Per-category counts (Tier C, report-only)

- `oil`: 645
- `sauce`: 406
- `meat_generic`: 101
- `gravy`: 61
- `dough`: 29
- `batter`: 4

## Out-of-scope boundary (spec Sec. 1)

Non-safety-vocabulary omissions (e.g. the imp_f9cc221553155bfc 'orange juice' class) are explicitly out of scope: hidden orange juice cannot produce an engine-visible allergy/diet violation. Title-side bare meat/fish word checking remains unchanged (proven unsafe to do deterministically, per the existing title module and `docs/BACKLOG.md`).

## Sample-audit candidate list (n=40, seed 20260717)

Stratified by category (largest-remainder proportional allocation, min 3 per non-empty category), population unit = one (recipe, category) Tier A/B mismatch case. For the orchestrator/advisor to write per-case CORRECT_QUARANTINE / FALSE_POSITIVE adjudication against (acceptance: <=2/40 false positives, i.e. >=95% precision). Full evidence in the sidecar JSON.

- `imp_f26d5c5093e25ac7` 'Amazing Nasi Goreng' -- category `crustacean` (tier A)
  - matched terms: ['shrimp']
  - ingredient names: ['long grain rice', 'smoked bacon', 'chicken', 'onion', 'garlic cloves', 'carrot', 'cabbage', 'water', 'leek', 'trassi oedang', 'ketjap manis', 'cumin', 'curcumae', 'sambal oelek', 'salt']
  - quoted step ('shrimp'): 'NOTES : Trassi is a shrimp paste found in Asian grocery stores. If you do  not have any, you can either use peeled shrimp mixed in with the other  meat, or leave it out all together.'
- `imp_bca827b64d08523e` 'Beef Shreds with Green Pepper' -- category `crustacean` (tier A)
  - matched terms: ['shrimp']
  - ingredient names: ['bell peppers', 'garlic', 'salt', 'thin soy sauce', 'sherry wine', 'thin cornstarch paste']
  - quoted step ('shrimp'): 'Garnishing note: Time and inclination permitting, deep-fry about 12 shrimp chips.'
- `imp_28766bd14c6c5a24` 'Onion Dip, Low Cal' -- category `crustacean` (tier A)
  - matched terms: ['crab', 'shrimp']
  - ingredient names: ['cottage cheese', 'lemon juice', 'plain yogurt', 'green onion', 'salt', 'pepper']
  - quoted step ('shrimp'): 'Add onion soup mix, parsley, basil, artichoke, dill, shrimp, crab, or curry as desired.'
  - quoted step ('crab'): 'Add onion soup mix, parsley, basil, artichoke, dill, shrimp, crab, or curry as desired.'
- `imp_0d20dbf56b3b55fa` 'Cantaloupe Melba' -- category `dairy` (tier A)
  - matched terms: ['cheese']
  - ingredient names: ['fresh raspberries', 'sugar', 'cantaloupe']
  - quoted step ('cheese'): 'Raspberry sherbet in goblets lined with sliced cantaloupe and topped with Melba sauce would make a memorable finale for a menu featuring an egg and cheese dish.'
- `imp_956259b2ddf05c8f` 'Beef Crumble' -- category `dairy` (tier A)
  - matched terms: ['butter', 'cheese']
  - ingredient names: ['beef', 'onion', 'celery', 'mushroom', 'carrot', 'flour', 'Worcestershire sauce']
  - quoted step ('cheese'): 'TOPPING 3/4 cup wholemeal flour 1/3 cup rolled oats 1 oz butter 1/3 cup grated cheese 1/2 tsp dried mixed herbs Fry mince over a medium heat in its own fat, turning, until evenly browned.'
  - quoted step ('butter'): 'TOPPING 3/4 cup wholemeal flour 1/3 cup rolled oats 1 oz butter 1/3 cup grated cheese 1/2 tsp dried mixed herbs Fry mince over a medium heat in its own fat, turning, until evenly browned.'
  - quoted step ('butter'): 'Rub in the butter until mixture resembles coarse breadcrumbs.'
  - quoted step ('cheese'): 'Stir in the cheese, herbs and salt and pepper to taste.  Transfer the meat to a greased casserole and spoon topping over.'
- `imp_61a95036c54f5583` 'Chocolate Tortoni' -- category `dairy` (tier A)
  - matched terms: ['whipped cream']
  - ingredient names: ['cream of tartar', 'salt', 'sugar', 'sugar', 'vanilla']
  - quoted step ('whipped cream'): 'Fold the beaten egg whites, the chopped cherries, toasted almonds and the melted semi-sweet chocolate into the whipped cream mixture.'
- `imp_a99116c82ed05dc1` 'Lemon Bundt Cake' -- category `egg` (tier A)
  - matched terms: ['egg']
  - ingredient names: ['butter', 'sugar', 'flour', 'baking powder', 'salt', 'milk', 'vanilla', 'lemon, rind of']
  - quoted step ('egg'): 'Beat egg yolks in separate bowl until light and lemon colored.'
- `imp_d126b4b4d0b451c9` 'Tiramisu' -- category `egg` (tier A)
  - matched terms: ['egg']
  - ingredient names: ['sugar', 'cream cheese', 'mascarpone', 'marsala wine', 'heavy whipping cream', 'marsala', 'sugar', 'water', 'french-style ladyfinger cookies']
  - quoted step ('egg'): 'In an electric mixer, prepare cream mixture by whipping sugar and egg yolks on high speed until pale yellow and thick.'
- `imp_1c4cfb66fdb557ee` 'Mongolian Beef' -- category `egg` (tier A)
  - matched terms: ['egg']
  - ingredient names: ['green onion tops', 'ginger', 'water chestnut flour', 'salt', 'cornstarch paste', 'dark soy sauce', 'sugar', 'dry sherry']
  - quoted step ('egg'): 'In bowl big enough to hold meat, combine egg whites, salt & water chestnut flour.'
- `imp_95baba4df49c5225` 'Sweet Coating for Fried Crappie (Fried Fish)' -- category `fish` (tier A)
  - matched terms: ['fish']
  - ingredient names: ['12 clove', 'golden dry ginger ale', 'pale dry ginger ale', 'egg', 'flour']
  - quoted step ('fish'): 'Presoak Fish in a large baggie in the ginger ale. ( about 4 hours), then drain  and wash.'
  - quoted step ('fish'): 'Dip fish in beaten egg and then roll in the dry mix.'
  - quoted step ('fish'): 'Place fish  in a Hot skillet cook each side until lightly golden brown.'
- `imp_2e2c3891144e5c07` 'Orange Roughy With Vegetables' -- category `fish` (tier A)
  - matched terms: ['fish']
  - ingredient names: ['lemon juice', 'stewed tomatoes', 'celery', 'onion', 'bell pepper', 'mushroom', 'thyme', 'garlic powder']
  - quoted step ('fish'): 'Arrange fish in a single layer and sprinkle  with 1 tablespoon lemon juice.'
  - quoted step ('fish'): 'Combine remaining ingredients and spoon over fish.'
  - quoted step ('fish'): 'Bake uncovered in a 350°F oven for 25-30 minutes, until fish flakes and sauce is thick.'
- `imp_a22b3c09a6b25bb5` 'Crispy Baked Fish & Herbs' -- category `fish` (tier A)
  - matched terms: ['fish']
  - ingredient names: ['water', 'lemon pepper', 'fresh parsley', 'low-fat margarine']
  - quoted step ('fish'): 'Rinse fish and pat dry.'
  - quoted step ('fish'): 'Dip fish in egg white, then roll in crumbs.'
  - quoted step ('fish'): 'Arrange fish in baking pan.'
  - quoted step ('fish'): 'Bake uncovered 20 min or until fish flakes easily.'
- `imp_ce64651a221b54d3` 'Italian Sausage, Sicilian Style' -- category `meat` (tier A)
  - matched terms: ['sausage']
  - ingredient names: ['fennel seed', 'bay leaves', 'dried parsley', 'garlic cloves', 'salt', 'fresh ground black pepper', 'dry white wine']
  - quoted step ('sausage'): "Column: 'Sausages like Mama used to make'  Frugal Gourmet News column."
- `imp_a52ae950e8dd5eb5` 'Sauerbraten &amp; Ginger' -- category `meat` (tier A)
  - matched terms: ['beef']
  - ingredient names: ['rump roast', 'onions', 'peppercorns', '4 cloves', 'bay leaf', 'white vinegar', 'water', 'cider vinegar', 'salt', 'water', 'sour cream', 'unbleached flour']
  - quoted step ('beef'): 'Place the beef roast in a deep ceramic or glass bowl.'
- `imp_f8b65c2dfc1255c4` 'Dill Pickle Soup' -- category `meat` (tier A)
  - matched terms: ['beef', 'chicken', 'veal']
  - ingredient names: ['sour dill pickle', 'onion', 'garlic', 'carrot', 'butter', 'flour', 'fresh dill', 'dried dill', 'heavy cream', 'lemon juice', 'sour cream']
  - quoted step ('chicken'): 'Stock: this can be a well-flavored chicken or veal, or a brown stock.'
  - quoted step ('veal'): 'Stock: this can be a well-flavored chicken or veal, or a brown stock.'
  - quoted step ('chicken'): 'The author notes that using all beef stock makes the soup a bit too strong, and usually substitute half of the brown stock for chicken or veal.'
  - quoted step ('veal'): 'The author notes that using all beef stock makes the soup a bit too strong, and usually substitute half of the brown stock for chicken or veal.'
  - quoted step ('beef'): 'The author notes that using all beef stock makes the soup a bit too strong, and usually substitute half of the brown stock for chicken or veal.'
- `imp_941617b6247054aa` 'Sweetened Soy Sauce' -- category `mollusk` (tier A)
  - matched terms: ['oyster']
  - ingredient names: ['soy sauce', 'sugar', 'sake', 'sherry wine', 'onions', 'round onion', 'ginger', 'cinnamon sticks', 'star anise']
  - quoted step ('oyster'): 'Use in same quantities as Oyster Sauce.'
- `imp_ea00f5dfa0435e19` 'Chocolate Mint Sticks' -- category `nut` (tier A)
  - matched terms: ['nuts']
  - ingredient names: ['eggs', 'butter', 'sugar', 'flour', 'butter', 'heavy cream', "confectioners' sugar", 'butter']
  - quoted step ('nuts'): 'Add flour and nuts.'
- `imp_c846d8efd9895c8d` 'Pineapple Cranberry Bread' -- category `nut` (tier A)
  - matched terms: ['nuts']
  - ingredient names: ['cranberry juice', 'crushed pineapple', 'butter', 'margarine', 'salt', 'oats', 'bread flour', 'cranberries']
  - quoted step ('nuts'): 'Add cranberries and nuts at the tone indicating the end of the raisin/mix cycle. (Coconut is also a great addition).'
- `imp_0201dbcec6b15a84` 'Nutty Chocolate Mint Fudge' -- category `nut` (tier A)
  - matched terms: ['nuts']
  - ingredient names: ['marshmallow cream', 'salt', 'sugar', 'evaporated milk', 'butter', 'vanilla extract']
  - quoted step ('nuts'): 'Add nuts and vanilla extract.'
- `imp_bca827b64d08523e` 'Beef Shreds with Green Pepper' -- category `peanut` (tier A)
  - matched terms: ['peanut']
  - ingredient names: ['bell peppers', 'garlic', 'salt', 'thin soy sauce', 'sherry wine', 'thin cornstarch paste']
  - quoted step ('peanut'): 'Peel and quarter garlic clove; add to peanut oil.'
- `imp_d34a2ab621245cba` 'Unusual Chicken' -- category `peanut` (tier A)
  - matched terms: ['ground nut']
  - ingredient names: ['chicken piece', 'chili powder', 'ginger', 'salt', 'garam masala', 'soy sauce', 'plain yogurt', 'curry leaf', 'ginger', 'garlic', 'green chili', 'spring onion', 'coriander leaves']
  - quoted step ('ground nut'): 'Add one beaten egg and corn flour to cover. Place some ground nut oil in a wok heat oil and deep fry on a low heat. The meat is now ready to eat.'
- `imp_9f1663ef59e7595a` 'Comforting Barbecue Sauce' -- category `peanut` (tier A)
  - matched terms: ['peanut']
  - ingredient names: ['onions', 'celery', 'bell pepper', 'fresh parsley', 'garlic', 'ketchup', 'salt']
  - quoted step ('peanut'): 'In a large skillet, saute onions, celery, bell pepper and parsley in peanut oil until onions are clear or tender.'
- `imp_f6b3377bf2445dda` "General Tso's Chicken" -- category `sesame` (tier A)
  - matched terms: ['sesame']
  - ingredient names: ['boneless chicken breast', 'dark soy sauce', 'gingerroot', 'cornstarch', 'roasted sichuan peppercorn', 'dark soy sauce', 'salt', 'sugar']
  - quoted step ('sesame'): 'Put it  into a bowl together with the soy sauce, ginger, cornstarch and 1 teaspoon  sesame oil.'
- `imp_450843d2ead35afd` 'Chinese Style Shrimp' -- category `sesame` (tier A)
  - matched terms: ['sesame']
  - ingredient names: ['shrimp', 'salt', 'sugar', 'soya sauce', 'white mushrooms', 'oyster sauce', 'green onion', 'cornstarch', 'gingerroot', 'water', 'white pepper', 'Chinese wine']
  - quoted step ('sesame'): 'Add sesame oil and white pepper to taste.'
- `imp_aecd551de6055303` 'Tofu "Turkey" with Stuffing' -- category `sesame` (tier A)
  - matched terms: ['sesame']
  - ingredient names: ['firm tofu', 'tofu', 'onion', 'celery', 'mushroom', 'garlic', '-4 sage', 'marjoram', 'thyme', 'winter savory', 'summer savory', 'rosemary', 'celery seeds', 'soy sauce', 'tamari', 'Pepperidge Farm Herb Stuffing', '- 1/3 soy sauce', 'tamari', 'miso', 'mustard']
  - quoted step ('sesame'): "Saute' the onions, celery and mushrooms in the 2 tablespoons sesame oil."
- `imp_3787a22d065b5c3d` '&quot;any&quot; Muffins' -- category `soy` (tier A)
  - matched terms: ['soy']
  - ingredient names: ['white flour', 'milk', 'egg', 'sugar', 'baking powder', 'salt', 'milk']
  - quoted step ('soy'): 'substitute 1 heaping Tbsp of soy flour and 1 Tbsp of water.'
- `imp_b3f19d74632257ba` 'Trifle' -- category `soy` (tier A)
  - matched terms: ['soy']
  - ingredient names: ['egg white substitute', 'granulated sugar', 'soymilk', 'lemon juice', 'whole wheat pastry flour', 'baking powder', 'salt', 'cornstarch', 'granulated sugar', 'soymilk', 'vanilla extract', 'lemon juice', 'sweet sherry', 'port wine', 'pear']
  - quoted step ('soy'): 'Pour in  enough soy milk to dissolve them.'
- `imp_3e5cbefd62c05ed8` 'Pumpkin Au Gratin' -- category `soy` (tier A)
  - matched terms: ['soy']
  - ingredient names: ['pumpkin', 'soymilk', 'garlic clove', 'olive oil', 'salt']
  - quoted step ('soy'): 'Pour the soy milk  little by little while stirring.'
  - quoted step ('soy'): 'NB: if you like almonds, you can add 1 tea spoon ground almonds in the mixture  before adding the soy milk.'
- `imp_2391b489ec6459e3` 'Down East Haddock Chowder' -- category `stock` (tier B)
  - matched terms: ['stock']
  - ingredient names: ['haddock fillets', 'water', 'salt', 'potatoes', 'onion', 'celery', 'pepper', 'evaporated milk', 'butter']
  - quoted step ('stock'): 'Skim  any foam off fish stock.'
- `imp_54fefa2b200d50a7` 'Pancit' -- category `stock` (tier B)
  - matched terms: ['broth']
  - ingredient names: ['onion', 'garlic', 'shrimp', 'pork', 'cabbage', 'carrots', 'soy sauce', 'water', 'lemon wedge']
  - quoted step ('broth'): 'Place noodles on top of mixture and spoon vegetables and broth over the noodles.'
- `imp_787ec005979550d2` 'Mussels Fra Diavolo' -- category `stock` (tier B)
  - matched terms: ['broth']
  - ingredient names: ['mussels', 'onion', 'green pepper', 'garlic', 'tomatoes', 'dry white wine', 'tomato paste', 'parsley', 'salt', '-3 sugar', 'red pepper flakes', 'basil', '- 1 oregano', 'linguine']
  - quoted step ('broth'): 'Discard the top shell from each mussel; rinse the mussel in the broth left in the pot to remove any left over s and.'
  - quoted step ('broth'): 'Let broth stand awhile to let the sand settle in the bottom of the pot. Pour 3/4 cup of the broth into a measuring cup and discard any remaining broth being careful not to pour any sand into the cup.'
  - quoted step ('broth'): 'Into the onion mixture, add toma toes with the liquid from the can, all remaining ingredients, except mussels- the fish and mussel broth.'
- `imp_9159af8f00af5725` "Helen's Light Fruitcake" -- category `tree_nut` (tier A)
  - matched terms: ['almonds']
  - ingredient names: ['sultanas', 'flour', 'baking powder', 'butter', 'sugar', 'nutmeg', 'eggs', 'lemon', 'orange', 'rose extract']
  - quoted step ('almonds'): 'Split almonds and add to mixture, saving some whole for top.'
- `imp_a7eb6f7b7e885e67` 'Raised Waffles' -- category `tree_nut` (tier A)
  - matched terms: ['almonds']
  - ingredient names: ['water', 'active dry yeast', 'granulated sugar', 'water', 'butter', 'salt', 'flour', 'eggs', 'baking soda', 'pure maple syrup']
  - quoted step ('almonds'): "Variation:  Top with fresh strawberries and whipped cream or sliced bananas, toasted coconut, and sliced roasted almonds.  Dust with confectioner's  sugar."
- `imp_de9f4959d0855804` 'Cream Puff Paste' -- category `tree_nut` (tier A)
  - matched terms: ['almonds', 'praline']
  - ingredient names: ['all-purpose flour', 'water', 'sweet unsalted butter', 'salt', 'eggs', 'egg']
  - quoted step ('almonds'): 'Brush the whole thing with beaten egg, and  sprinkle a handful of thinly sliced almonds all over the top of the ring.'
  - quoted step ('praline'): 'Fill the bottom with praline cream (or coffee cream, or  chocolate cream) filling.'
  - quoted step ('praline'): 'use a nozzle with a zigzag edge (like pinking shears) to squeeze out a  layer of fancy puff-balls of whipped cream all over the layer of praline  cream filling.'
  - quoted step ('almonds'): "Keep the cream puff ring in a cool dry  place until serving time.                  - - - - - - - - - - - - - - - - - -                     *  Exported from  MasterCook  *                            PRALINE FILLING Recipe By     : Homemade Good News (Vol 3 No 3) Serving Size  : 1    Preparation Time :0:00 Categories    : Pastries Amount  Measure       Ingredient -- Preparation Method --------  ------------  --------------------------------  1      cup           10X powdered confectioners' sugar    1/2  cup           almonds Make the vanilla custard cream."
  - quoted step ('praline'): "Keep the cream puff ring in a cool dry  place until serving time.                  - - - - - - - - - - - - - - - - - -                     *  Exported from  MasterCook  *                            PRALINE FILLING Recipe By     : Homemade Good News (Vol 3 No 3) Serving Size  : 1    Preparation Time :0:00 Categories    : Pastries Amount  Measure       Ingredient -- Preparation Method --------  ------------  --------------------------------  1      cup           10X powdered confectioners' sugar    1/2  cup           almonds Make the vanilla custard cream."
  - quoted step ('praline'): 'Fold the praline powder into the vanilla  custard cream.'
- `imp_e9ac590092015c96` 'Japanese Cabbage Salad' -- category `wheat_gluten` (tier A)
  - matched terms: ['noodle']
  - ingredient names: ['chicken breast', 'sesame seeds', 'head of cabbage', 'green onions', 'sugar', 'salt', 'Accent seasoning', 'black pepper', 'rice vinegar']
  - quoted step ('noodle'): 'Saute sesame seed, almonds and noodles in 2  tablespoons oil until brown.'
- `imp_9016a30d23625355` 'Puffy Cheese Bake' -- category `wheat_gluten` (tier A)
  - matched terms: ['bread']
  - ingredient names: ['butter', 'eggs', 'salt', 'pepper', 'dry mustard', 'milk']
  - quoted step ('bread'): 'At least 4 hours before cooking, trim crusts and cut bread into 1 inch squares.  Cut cheese into bite size pieces.'
  - quoted step ('bread'): 'In a large greased casserole, alternate layers of bread and cheese.  Pour melted butter over top.'
- `imp_6404a96a38aa5c12` 'Swiss Chard Dolmades' -- category `wheat_gluten` (tier A)
  - matched terms: ['bread']
  - ingredient names: ['swiss chard leaves', 'white rice', 'garlic', 'butter', 'white raisins', 'curry powder', 'salt', 'lamb shoulder', 'olive oil', 'garlic', 'white rice', 'dried dill', 'fresh dill', 'salt']
  - quoted step ('bread'): 'Suggested accompaniments:  Avegolemo soup, tossed salad with black olives and feta cheese, fresh steamed  artichokes, garlic bread.'
- `imp_8115c40a596a58a5` 'Chipotle Mussels with Orange Mayonnaise' -- category `egg` (tier A)
  - matched terms: ['egg']
  - ingredient names: ['mussels', 'garlic', 'oranges, zest of', 'chipotle chiles in adobo', 'water', 'olive oil', 'orange zest', 'fresh lime juice', 'cilantro', 'cilantro']
  - quoted step ('egg'): 'Beat the egg yolk in a glass or stainless steel bowl until light and lemon colored.'
- `imp_f7b0bfbebbba569c` 'Pork with Orange and Apricots' -- category `stock` (tier B)
  - matched terms: ['stock']
  - ingredient names: ['butter', 'orange', 'onion', 'green pepper', 'cornflour', 'watercress']
  - quoted step ('stock'): 'Add onion and pepper to the fat remaining in the pan and fry until soft.  Stir in the stock.'
- `imp_ee6f9faf16015e2e` 'All-in-One Tuna Casserole' -- category `wheat_gluten` (tier A)
  - matched terms: ['noodle']
  - ingredient names: ['- 1 milk', '- 2 tuna', 'cheddar cheese']
  - quoted step ('noodle'): 'In large bowl, blend onion soup mix with cream of mushroom soup and milk; stir in peas & carrots, cooked noodles, cheese and tuna.'

## Miss spot-check candidate list (n=15, seed 20260717)

15 random UNflagged rows for the orchestrator to read for any Tier A/B-class omission the check should have caught (acceptance: 0 misses; a miss is a spec bug, fix and re-run -- not an acceptance judgment call).

- `imp_25ff999493705583` 'Grilled Steaks with Peppery Peach Salsa'
  - ingredient names: ['boneless beef top loin steaks', 'salt', 'pepper', 'red bell pepper', 'green onion', 'fresh lemon juice', 'lemon, rind of', 'garlic', 'fresh ginger', 'salt']
  - instructions: ['Sprinkle both sides of beef steaks with 1/4 teaspoon each salt and pepper.', 'Remove seeds from bell pepper, leaving pepper whole. Place steaks and bell pepper on grid over medium, ash-covered coals.', 'Grill steaks, uncovered, 15 to 18 minutes for medium rare to medium doneness, turning once. Grill bell pepper 2 to 3 minutes, turning occasionally.', 'While steaks continue to cook, cut four 1/2-inch thick rings from bell pepper; set aside for garnish.', 'Coarsely chop enough remaining bell pepper to make 1/4 cup.', 'In small saucepan, combine the 1/4 cup chopped bell pepper with salsa ingredients.', 'Place on grid near edge of grill to heat until warm.', 'Approximately 5 minutes before steaks are done, remove 2 tablespoons salsa from saucepan and brush on both sides of steaks.', 'To serve, place 1 bell pepper ring on each steak; fill rings with warm salsa.', 'Makes 4 servings (serving size: 1/4 of recipe). Tip: To broil, place steaks and bell pepper on rack in broiler pan so surface of meat is 3 to 4 inche s from heat. Broil bell pepper 5 minutes; remove and proceed as directed above. Broil steaks 13 to 17 minutes, turning once; approx.', '5 minutes before steaks are done, brush both sides with 2 tablespoons salsa.']
- `imp_6f3463afcc2f5d51` 'Pork Spareribs in Tangy Sauce'
  - ingredient names: ['tomato sauce', 'water', 'brown sugar', 'Worcestershire sauce', 'garlic', 'vinegar', 'lemon juice', 'paprika', 'ginger', 'soy sauce']
  - instructions: ['Trim spareribs of rind and excess fat, place ribs in a shallow dish.', 'Cook on HIGH 14 minutes, turning halfway through cooking time.  Drain fat from dish carefully.', 'Mix the remaining ingredients together and pour over the ribs; cook on HIGH 3 minutes or until hot. Cheers,  Doreen Doreen Randal,  Wanganui.', 'New Zealand.']
- `imp_cc133418cf78547b` 'Luscious Applesauce Bars'
  - ingredient names: ['brown sugar', 'butter', 'unsweetened applesauce', 'egg', 'flour', 'baking soda', 'cinnamon', 'salt', 'ground cloves', 'ground nutmeg', 'butter', 'brown sugar', 'powdered sugar']
  - instructions: ['Preheat oven to 350 degrees Fahrenheit.', 'Grease and flour a 13x9-inch pan.', 'In a large bowl, cream brown sugar and butter until light and fluffy.', 'Add applesauce and egg; blend well.', 'Stir in flour, baking soda, cinnamon, salt, cloves and  nutmeg until well mixed.', 'Stir in cereal.', 'Spread mixture into prepared pan.', 'Bake for 25 to 30 minutes or until toothpick inserted in center comes out  clean.', 'Prepare glaze:', 'Melt butter over low heat and stir in brown sugar.', 'Cook about 1  minute or until mixture bubbles, stirring constantly.', 'Remove from heat and stir in powdered sugar.', 'While glaze is still hot, drizzle it over warm bars.', 'Cool completely; cut into squares.']
- `imp_915061b64a0454df` 'Winter Pear Butter'
  - ingredient names: ['pears', 'sugar', 'brandy', 'water']
  - instructions: ['Peel, quarter and core the pears; chop in 1/2-inch pieces.', 'Put all the ingredients in a large heavy pot; bring to a boil.', 'Reduce the heat and cook, stirring often, for 15 minutes, or until the  pears are soft.', 'Puree the mixture in a food processor or blender.', 'Return the  puree to the pot.', 'Cook uncovered over very low heat, stirring often, for 1 to 1-1/2 hours, or until the pear butter is very thick.', 'Be careful not  to let it scorch.', 'Remove from the heat.', 'Stir the hot pear butter for a minute or two to release more heat.', 'Spoon into clean hot jars, leaving 1/4 inch of space at the top of  each jar.', 'Wipe the rim of each jar.', "Cover and allow to come to room  temperature. (You'll notice that the pear butter is a rather gray-green  color; this is the correct color.)", 'Label the jars and refrigerate for up to three weeks.', '(Remember: The label should include the name of the recipe and the  date by which it should be eaten. Be sure the recipient stores the pear butter in the refrigerator.).']
- `imp_09aa21fdc43e5392` 'Orange Tarragon Dressing'
  - ingredient names: ['garlic heads', 'Dijon mustard', 'white wine vinegar', 'cider vinegar', 'salt', 'black pepper', 'fresh tarragon']
  - instructions: ['Squeeze the garlic paste from the heads of roasted garlic into a blender.', 'Add the orange juice, mustard, vinegar, salt, and pepper and puree until smooth and creamy.', 'Add the tarragon and whirl briefly just to mix-there should be flecks of green throughout the golden dressing.', 'Set aside for at least 30 minutes to allow the flavors to marry.', 'Tightly sealed and refrigerated, the dressing will keep for about a week.']
- `imp_4b158d76b28e594d` 'Truffle-Topped Amaretto Brownies'
  - ingredient names: ['water', 'Amaretto', 'egg', 'cream cheese', 'powdered sugar', 'Amaretto']
  - instructions: ["Heat oven to 350'F Grease 13x9-inch pan.", 'In large bowl, combine all brownie ingredients. Beat 50 strokes by hand.', "Spread batter in greased pan. Bake at 350'F. for 26 to 33 minutes or until set. DO NOT OVERBAKE. Cool completely.", 'In small bowl, beat cream cheese and powdered sugar at medium speed until smooth.', 'Add melted chocolate chips and 2 to 3 tablespoons Amaretto; beat until well blended.', 'Spread filling mixture over top of cooled brownies.', 'Refrigerate at least 1 hour or until firm.', 'In small saucepan over low heat, melt l/2 cup chocolate chips and whipping cream, stirring constantly until smooth.', 'Carefully spread evenly over chilled filling.', 'Sprinkle with sliced almonds; garnish with candied cherries.', 'Refrigerate at least 1 hour or until set; cut into bars.', 'Store in refrigerator.', 'TIPS: * if using almond extract instead of Amaretto, increase water in brownies to 1/2 cup; use almond extract and 2 tablespoons milk in filling.', "** To toast almonds, spread on cookie sheet. Bake at 350'F. for 5 to 10 minutes or until light golden brown, stirring occasionally. Or, spread in thin layer in microwave-safe pie pan. Microwave on HIGH for 3 to 4 minutes or until light golden brown, stirring frequently."]
- `imp_be1b297c49a357ed` 'Ham and Cheese Spread'
  - ingredient names: ['cream cheese', 'sour cream', 'ham', 'swiss cheese', 'cheddar cheese', 'fresh parsley']
  - instructions: ['In a mixing bowl, beat cream cheese, sour cream and soup mix until smooth.', 'Stir in ham and cheese. Form into ball or spoon into a plastic wrap-lined mold.', 'Roll in parsley or sprinkle parsley on top.', 'Refrigerate.']
- `imp_8c5c86275d405ce9` "Corky's Memphis-Style Coleslaw"
  - ingredient names: ['green cabbage', 'carrots', 'green bell pepper', 'onions', 'prepared mayonnaise', 'granulated sugar', 'dijon-style mustard', 'cider vinegar', 'celery seeds', 'salt', 'white pepper']
  - instructions: ['Place cabbage, carrots, green pepper and onion into a large bowl.  Set aside.', 'In another bowl, mix together all of the remaining ingredients.', 'Pour over the vegetables and toss well to combine. Cover the coleslaw and refrigerate for 3 to 4 hours for the flavors to meld.', 'Stir again before serving.']
- `imp_82d66d94df655f9b` 'Golden Peanut Bars'
  - ingredient names: ['unsifted flour', 'light brown sugar', 'egg', 'butter', 'margarine', 'peanuts', 'peanut butter', 'vanilla extract']
  - instructions: ['Preheat oven to 350.', 'combine flour, sugar and beaten egg.', 'cut in butter until crumbly.', 'stir in peanuts.', 'Reserving 2 cups crumb mixture, press remaining mixture on bottom of 13x9" baking pan.', 'Bake 15 minutes or until lightly browned.', 'Meanwhile, with mixer, beat sweetened condensed milk with peanut butter and vanilla.', 'spread over prepared crust; top with reserved crumb mixture Bake 25 minutes longer or until lightly browned.', 'Cool.', 'Cut into bars.', 'Store covered at room temperature.']
- `imp_3613ec3896ca593d` 'Garlic Mashed Potatoes'
  - ingredient names: ['baking potatoes', 'salt', 'butter', 'milk', 'buttermilk', 'nutmeg']
  - instructions: ['Peel and quarter potatoes and place in large pot with just enough cold water to cover and 1/2 teaspoon salt. Over high heat, bring to a boil; lower heat to medium low and cook, covered, until very tender, about 20 to 25 minutes.', 'Drain. Mash potatoes, working out all the lumps.', 'Add butter, 1/2 teaspoon salt and milk. Whip with a fork until smooth.', 'Add nutmeg to taste, if using, and a little more hot milk, if necessary. Serve immediately or keep warm over a pan of hot water.', 'VARIATIONS All quantities are for the basic Mashed Potatoes (recipe above):', 'HERBED: Add sprigs of fresh herbs, bay leaf or celery tops to the water while boiling potatoes, if desired add 1 tablespoon finely chopped parsley, thyme or oregano, or a combination of fresh herbs, while mashing.', 'ITALIAN: Substitute herbed olive oil for butter and use hot chicken broth instead of milk.', 'PESTO: Omit butter; add 1/4 cup grated Parmesan and 1 to 2 tablespoon basil pesto or sundried tomato pesto.', 'ROASTED GARLIC: Brush 6 to 10 unpeeled cloves garlic with olive oil and roast at 3250F for 30 minutes. When cool enough to handle, squeeze garlic out of skins and add to the potatoes while mashing. Add 1/4 cup grated Parmesan, if desired.', 'ROOT VEGETABLE: Use only 4 potatoes and add one of the following: 4 medium parsnips, peeled and diced; 2 white turnips, of equal size to the potatoes, peeled and diced; or 1 medium celery root, peeled and diced. Cook with potatoes. Add an extra pinch of nutmeg.']
- `imp_f5c9080b4b7e515b` 'Petto Di Pollo Al Limone E Zen Zaro'
  - ingredient names: ['boneless chicken breasts', 'unsalted butter', 'dry white wine', 'ginger', 'parsley']
  - instructions: ['Remove skin and fat from chicken breasts.', 'With a wooden mallet, flatten (and tenderize) chicken breasts.', 'With a sharp knife, slit the breasts through the centre, leaving a small hinge for the two halves.', 'In a heavy skillet, melt butter.', 'Add wine and heat together until bubbly.', 'Add prepared chicken breasts and cook on medium-high heat for about two minutes or until the chicken appears half cooked.', 'Add lemon juice and ginger to the chicken.', 'Reduce heat to medium-low and complete cooking, about six minutes 6.', 'Remove breasts with a slotted spoon and serve immediately on a warmed platter.', 'Garnish with lemon wedges and chopped parsley.']
- `imp_98c235c225f25d05` 'Bran Date Bread'
  - ingredient names: ['unbleached flour', 'baking powder', 'salt', 'buttermilk', 'pitted dates', 'lemon, rind of', 'eggs', 'brown sugar']
  - instructions: ['Sift dry ingredients together.', 'Dust dates with 1 T flour mixture, then add to the bowl.', 'Then add the brown sugar, all bran, and grated lemon peel.', 'Combine 3/4 cu buttermilk, 2 beaten eggs, 1/4 cup vegetable oil.', 'Add all once to flour mixture with the sourdough starter, stirring until well moistened.', 'Pour into greased or waxpaper lined loaf pan about 9 x 5-inches.', 'Bake at 350 degrees for 1 hour.', 'Allow to stand 10 minutes in pan and then remove from pan and cool until cold.', 'Wrap in plastic wrap or foil and place in Refrigerator.', 'Use cream cheese or home made butter on this bread for an out of this world taste.']
- `imp_8119e2fa6a7f5305` 'Lemongrass Chicken'
  - ingredient names: ['boneless skinless chicken breasts', 'honey', 'fish sauce', 'soy sauce', 'fresh lemongrass', 'canola oil', 'garlic cloves', 'onion', 'fresh cilantro', 'mint']
  - instructions: ['Wash and dry the chicken and trim off any fat. Cut the chicken breast across the grain on the diagonal into 1/8-inch strips.', 'Cut these strips into 2-inch pieces.', 'Combine the chicken, honey, and 1 tablespoon fish sauce in a bowl and stir to mix.', 'Let marinate for 5 to 10 minutes.', 'Trim the green leaves and root end off the lemongrass stalk and strip off the outside leaves.', 'What remains will be a greenish crea m-colored core 4 to 5 inches long and 1/4 to 1/2 inch thick.', "Mince the core finely: You'll need about 2 tablespoons.", 'Just before serving, heat a wok (preferably nonstick) over high heat and swirl in the oil.', 'Add the garlic and lemongrass and stir-fry until fragrant but not brown, about 15 seconds.', 'Add the chicken and stir-fry until the pieces turn white, about 1 minute. Move the chicken to the sides of the wok and add the o nion to the center.', 'Stir-fry until the onion loses its rawness, about 1 minute. Mix the chicken back in the center of the wok, add the remaining fish sauce, continue stir-frying until the chicken is cooked, 2 to 3 minutes.', 'Correct the seasoning, adding honey or fish sauce to taste. The dish should be a little sweet and salty.', 'Sprinkle the chicken with the cilantro, if desired, and serve at once.']
- `imp_429f41d1b2aa553f` 'Dark Chocolate Cake'
  - ingredient names: ['sugar', 'flour', 'baking powder', 'baking soda', 'salt', 'eggs', 'milk', 'vanilla extract', 'boiling water']
  - instructions: ['Heat oven to 350°F.', 'Grease and flour two 9 inch round baking pans or one 13x9 inch pan.', 'In large mixer bowl, stir together dry ingredients.', 'Add eggs, milk, oil, and vanilla; beat on medium speed for 2 minutes.', 'Pour into prepared pan.', 'Bake 30 to 35 minutes for round 9-inch pans, 35 to 40 minutes for rectangular pan or until wooden pick inserted in center comes out clean. (Do not use 8-inch pans or the batter will overflow.).', 'Cool 10 minutes; remove from pan to wire racks.', "Please note: baking cocoa isn't hot chocolate drink mix! Baking cocoa contains no sugar and it is found on the baking aisle. Chocolate drink mixes that you add to milk or water to drink WILL NOT work in this recipe."]
- `imp_048143cd0c5d5a4d` 'White Sauce Seafood Lasagna'
  - ingredient names: ['butter', 'flour', 'salt', 'garlic', 'milk', 'chicken broth', 'pepper', 'basil', 'mozzarella cheese', 'green onion', 'cottage cheese', 'shrimp', 'bay scallop', 'dry white wine']
  - instructions: ['Heat butter in a large saucepan over low heat until melted.', 'Add  garlic.', 'Stir in flour and salt. Cook,stirring constantly until  bubbly.', 'Remove from heat. Stir in milk, broth and white wine. Return  to stove and heat to boiling, stirring constantly.', 'Boil for 1 minute.  Add mozzarella cheese,onions, basil and pepper.', 'Cook over low heat  until cheese is melted, stirring constantly.', 'Spread about 1 1/2 cups  of the sauce in an ungreased 9X13 pan.', 'Top with UNCOOKED lasagna  noodles, overlapping as needed.', 'Spread the cottage cheese over the noodles.', 'Spread with another 1 1/2 cups of sauce and then top with another 5  lasagna noodles.', 'Spread seafood over this layer and top with another  1 1/2 cups of sauce. Cover with the last 5 lasagna noodles and top  with all of the remaining sauce. If desired, top with 1/2 cup grated  Parmesan cheese. Bake, uncovered at 350~F for 35 - 45 minutes or  until the noodles are tender.', 'Let stand for 15 minutes before  cutting.']

## Revisions

(none -- this is the first full-corpus run of this vocabulary. Per spec Sec. 0's pre-registration rule, any future vocabulary revision made after seeing a result must be documented here with before/after counts and a cited real example.)
