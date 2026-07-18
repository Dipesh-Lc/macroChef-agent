# Instructions/ingredient integrity audit -- 20260717T231309Z

Dry run only -- this report never mutated `data/processed/imported_recipes.jsonl` or any quarantine sidecar. See `docs/instructions_integrity_spec.md` for the full rule set and guard-band pre-registration.

## Guard-band verdict

**HALT**: Hard ceiling breach: 1130/4045 = 27.94% flagged (> 12%). HALT per spec Sec. 3: analyze the false-positive classes in this report, add suppressions (each cited with a real example), and re-run. Maximum two revision rounds; if still above the ceiling, this is a HUMAN GATE -- the corpus is majority-defective for safety purposes and replacing/re-importing it is a product decision, not an automated purge.

- Corpus size: 4045
- Flagged (Tier A+B, quarantine-worthy): 1130 (27.94%)
- Tier A: 1168
- Tier B: 177
- Tier C (report-only, never quarantines): 1075 recipes, 1233 mismatch pairs

## Per-category counts (Tier A/B, quarantine-worthy)

- `wheat_gluten` (tier A): 364
- `egg` (tier A): 206
- `stock` (tier B): 177
- `meat` (tier A): 152
- `nut` (tier A): 125
- `dairy` (tier A): 104
- `tree_nut` (tier A): 104
- `fish` (tier A): 39
- `sesame` (tier A): 34
- `peanut` (tier A): 22
- `crustacean` (tier A): 11
- `soy` (tier A): 7

## Per-category counts (Tier C, report-only)

- `oil`: 642
- `sauce`: 401
- `meat_generic`: 100
- `gravy`: 57
- `dough`: 29
- `batter`: 4

## Out-of-scope boundary (spec Sec. 1)

Non-safety-vocabulary omissions (e.g. the imp_f9cc221553155bfc 'orange juice' class) are explicitly out of scope: hidden orange juice cannot produce an engine-visible allergy/diet violation. Title-side bare meat/fish word checking remains unchanged (proven unsafe to do deterministically, per the existing title module and `docs/BACKLOG.md`).

## Sample-audit candidate list (n=40, seed 20260718)

Stratified by category (largest-remainder proportional allocation, min 3 per non-empty category), population unit = one (recipe, category) Tier A/B mismatch case. For the orchestrator/advisor to write per-case CORRECT_QUARANTINE / FALSE_POSITIVE adjudication against (acceptance: <=2/40 false positives, i.e. >=95% precision). Full evidence in the sidecar JSON.

- `imp_e7fb53c18ced5dc0` 'Beer Batter' -- category `crustacean` (tier A)
  - matched terms: ['shrimp']
  - ingredient names: ['beer', 'flour', 'seasoning salt', 'pepper', 'eggs']
  - quoted step ('shrimp'): 'Dip fresh shrimp, mushrooms or veggies.'
- `imp_9b2c1d45a9f55ef1` 'Alfredo Sauce' -- category `crustacean` (tier A)
  - matched terms: ['shrimp']
  - ingredient names: ['sweet butter', 'heavy cream', 'parmesan cheese', 'salt', 'pepper']
  - quoted step ('shrimp'): 'Add salt and pepper to taste. (If serving with shrimp, you might not need much salt.).'
- `imp_2380cadece955cc7` 'Alfredo Sauce with Pasta' -- category `crustacean` (tier A)
  - matched terms: ['crab', 'shrimp']
  - ingredient names: ['butter', 'margarine', 'heavy cream', 'parmesan cheese', 'salt', 'pepper', 'fettuccine']
  - quoted step ('shrimp'): 'Sprinkle  with remaining  cheese. Variation: Add cooked shrimp, crab or mushrooms.'
  - quoted step ('crab'): 'Sprinkle  with remaining  cheese. Variation: Add cooked shrimp, crab or mushrooms.'
- `imp_13e739367b505085` 'Spiced Pear Butter' -- category `dairy` (tier A)
  - matched terms: ['cheese']
  - ingredient names: ['pears', 'cinnamon sticks', 'allspice', '2 cloves', 'sugar']
  - quoted step ('cheese'): 'Tie broken cinnamon  spices, gingerroot, allspice and cloves in a piece of cheese cloth; add  to pear mixture. Bring to a boil; cover, reduce heat, and simmer for 45  minutes to 1 hour or until pears are tender.'
- `imp_a07efbc761c35e16` 'Chocolate-Cinnamon Cake Roll' -- category `dairy` (tier A)
  - matched terms: ['whipped cream']
  - ingredient names: ['eggs', 'salt', 'sugar', 'water', 'unbleached flour', 'cake flour', 'powdered sugar', 'baking powder', 'ground cinnamon']
  - quoted step ('whipped cream'): 'Sprinkle 2 tb of the liqueur over the cake spread with Cinnamon Whipped Cream; roll up.'
  - quoted step ('whipped cream'): 'CINNAMON WHIPPED CREAM:'
- `imp_41bfceea6ba65b47` 'Corn Chowder' -- category `dairy` (tier A)
  - matched terms: ['milk']
  - ingredient names: ['bacon', '-3 potatoes', 'onion', '-3 celery ribs', 'water', 'bacon']
  - quoted step ('milk'): 'Then add can cream style corn and can of milk.'
- `imp_903a53ccc0b55219` 'Chocolate Rice Ruination' -- category `egg` (tier A)
  - matched terms: ['egg']
  - ingredient names: ['unsalted butter', 'milk', 'vanilla extract', 'long-grain rice', "confectioners' sugar", 'heavy cream']
  - quoted step ('egg'): 'Beat in the egg yolks and 2 teaspoons of the vanilla.'
- `imp_0c0b6207064c5d15` 'Flowerpots (Baked Alaska)' -- category `egg` (tier A)
  - matched terms: ['egg', 'meringue']
  - ingredient names: ['ice cream', 'sugar', 'vanilla']
  - quoted step ('meringue'): 'Pile meringue around the inside of the pot, leaving s over the soda straw open.'
  - quoted step ('meringue'): 'Bake at 400 degrees until the meringue turn brown, (about 5 minutes).'
  - quoted step ('meringue'): 'For the Meringue:'
  - quoted step ('egg'): 'Beat the egg whites until foamy before slowly adding the sugar, beat well after each addition.'
  - quoted step ('meringue'): 'Each flowerpot requires about a third of a cup of meringue'
- `imp_b8e878e91861543a` 'Bearnaise Sauce' -- category `egg` (tier A)
  - matched terms: ['egg']
  - ingredient names: ['white wine vinegar', 'dry white wine', 'vermouth', 'tarragon leaves', 'shallots', 'butter']
  - quoted step ('egg'): 'Strain mixture into small bowl; whisk in egg yolks.'
  - quoted step ('egg'): 'Whisk egg yolk mixture into butter.'
- `imp_58d0ea05ba705823` 'Deep Fried Fish' -- category `fish` (tier A)
  - matched terms: ['fish']
  - ingredient names: ['plain flour', 'self raising flour', 'salt', 'egg', 'butter', 'milk', 'lemon wedge']
  - quoted step ('fish'): 'Coat 2  pieces of fish with batter.'
  - quoted step ('fish'): 'Repeat with the remaining fish.'
- `imp_6cf61d5aa17d5f52` 'Peppered Fish in Herbed Butter' -- category `fish` (tier A)
  - matched terms: ['fish']
  - ingredient names: ['pepper', 'butter', 'lemon juice', 'parsley', 'thyme']
  - quoted step ('fish'): 'Sprinkle fish with pepper.'
  - quoted step ('fish'): 'Add the fish in a single layer, cover and cook on HIGH for 5 minutes or until fish is tender.'
- `imp_d3a91c593c3d55b2` 'Green and Gold Chowder' -- category `fish` (tier A)
  - matched terms: ['fish']
  - ingredient names: ['milk', 'bay leaf', 'butter', 'flour', 'onions', 'frozen green beans']
  - quoted step ('fish'): 'Arrange fish in a shallow dish in a single layer.'
  - quoted step ('fish'): 'Flake fish, discarding skin and bones.'
  - quoted step ('fish'): 'Stir in the flour and whisk in the fish cooking liquid and the remaining milk, a little at a time, until mixture is smooth.'
  - quoted step ('fish'): 'Mix the vegetables into the sauce.  Cover and cook on HIGH for 6 1/2 minutes, stir in fish and pepper to taste and cook for a further 2 minutes, until vegetables are cooked, stirring twice.'
- `imp_ba2c9449969156af` 'A Real Philly Cheesesteak' -- category `meat` (tier A)
  - matched terms: ['steak']
  - ingredient names: ['onion', 'mushroom', 'provolone cheese', 'Cheese Whiz']
  - quoted step ('steak'): 'Cooking the steak: In a cast iron frying pan, or a grill pan heat some oil.  Saute toppings until pliable - make them however you like them.  Remove them from pan and set aside.'
- `imp_caea496900545f7f` 'Tagliolini with Butter and White Truffles' -- category `meat` (tier A)
  - matched terms: ['chicken']
  - ingredient names: ['salt', 'butter', 'white truffle']
  - quoted step ('chicken'): 'Cook the fresh tagliolini in fresh Chicken Stock, not in water. Add a bit of salt to the stock.'
- `imp_3233766015ca524d` 'Buttermilk Jalapeno Cornbread' -- category `meat` (tier A)
  - matched terms: ['bacon']
  - ingredient names: ['all-purpose flour', 'yellow cornmeal', 'sugar', 'baking powder', 'salt', 'eggs', 'milk', 'buttermilk', 'shortening']
  - quoted step ('bacon'): 'Can add drained corn, bacon,  finely chopped jalapeno peppers etc. for a different taste.'
- `imp_d4597ae869735e8e` 'Layer Cookies (Magic Layer Bars)' -- category `nut` (tier A)
  - matched terms: ['nuts']
  - ingredient names: ['butter', 'graham cracker', 'flaked coconut', 'chocolate chips', 'sweetened condensed milk']
  - quoted step ('nuts'): 'Layer the coconut and chips in order given. Pour sweetened condensed milk over all. Top with nuts. DO NOT mix together.'
- `imp_aeb6d9f6f5c55903` 'Deluxe Brownies' -- category `nut` (tier A)
  - matched terms: ['nuts']
  - ingredient names: ['butter', 'margarine', 'sugar', 'vanilla', 'eggs', 'flour']
  - quoted step ('nuts'): 'Stir in nuts.'
- `imp_121294a381be5535` 'Wonderful Microwave Honey Roasted Nuts' -- category `nut` (tier A)
  - matched terms: ['nut', 'nuts']
  - ingredient names: ['butter', 'honey', 'orange zest', 'cinnamon']
  - quoted step ('nuts'): 'To toast nuts, heat and stir over medium heat till toasted.'
  - quoted step ('nuts'): 'Nuts tend to burn easily so toast with caution and stir and turn frequently.'
  - quoted step ('nuts'): 'Then stir nuts with remainder of ingredients and mix well.'
  - quoted step ('nut'): 'Break up nut mixture and stir in a cool dry place.'
- `imp_8c7176ba96a35dce` 'Chewy Chocolate Cookies' -- category `peanut` (tier A)
  - matched terms: ['peanut']
  - ingredient names: ['butter', 'margarine', 'sugar', 'eggs', 'vanilla extract', 'all-purpose flour', 'baking soda', 'salt']
  - quoted step ('peanut'): 'Combine flour, cocoa, baking soda and salt; gradually blend into creamed mixture. Stir in peanut butter or chocolate chips.'
- `imp_73834906f18e553a` 'Andouille in Comforting Barbecue Sauce' -- category `peanut` (tier A)
  - matched terms: ['peanut']
  - ingredient names: ['onions', 'celery', 'bell pepper', 'parsley', 'garlic', 'ketchup', 'cayenne pepper', 'salt', 'andouille sausage']
  - quoted step ('peanut'): 'Saute onions, celery, bell pepper, and parsley in peanut oil until the onions are clear or tender.'
- `imp_bca827b64d08523e` 'Beef Shreds with Green Pepper' -- category `peanut` (tier A)
  - matched terms: ['peanut']
  - ingredient names: ['bell peppers', 'garlic', 'salt', 'thin soy sauce', 'sherry wine', 'thin cornstarch paste']
  - quoted step ('peanut'): 'Peel and quarter garlic clove; add to peanut oil.'
- `imp_216295e7e97b5bdc` 'Bean Curd With Broccoli' -- category `sesame` (tier A)
  - matched terms: ['sesame']
  - ingredient names: ['cornstarch', 'dry sherry', 'soy sauce', 'scallion', 'gingerroot', 'garlic cloves', 'broccoli', 'salt', 'medium firm tofu']
  - quoted step ('sesame'): 'Add wine, soy sauce and  sesame oil.'
- `imp_fbf6565762c0590d` 'Mabo Dofu - Tofu with Beef' -- category `sesame` (tier A)
  - matched terms: ['sesame']
  - ingredient names: ['ground beef', 'minced beef', 'garlic', 'chili peppers', 'leek', 'soy sauce', 'sugar', 'cornstarch', 'water', 'broth']
  - quoted step ('sesame'): 'Turn out into serving dish, sprinkle with the  sesame oil and serve hot. EmmaDeer'
- `imp_119bba669dca593d` 'Fried Szechuan Chicken' -- category `sesame` (tier A)
  - matched terms: ['sesame']
  - ingredient names: ['chicken', 'salt', 'five-spice powder', 'water', 'cornstarch', 'light soy sauce', 'Chinese wine', 'sherry wine', 'black pepper', 'garlic cloves', 'green ginger', 'scallion']
  - quoted step ('sesame'): 'Marinate chicken with salt, five- spice powder and sesame oil, set  aside. Mix water, light soy sauce, wine and pepper in a separate  bowl.'
- `imp_ab6b542e34555631` 'The Bottomless Chicken Soup Pot' -- category `soy` (tier A)
  - matched terms: ['soy sauce']
  - ingredient names: ['chicken', 'chicken parts', 'water', 'carrots', 'onions', 'celery', 'chicken bouillon cubes', 'salt']
  - quoted step ('soy sauce'): 'San Francisco:  3 cup fine egg noodles, 2 cup frozen green peas, 2 tablespoons soy sauce, 1/2 teaspoons ground ginger. Just before serving, whisk in 1 beaten egg. Sprinkle with sliced scallions.'
- `imp_068b162ec1445581` 'Pasta Soup Mix' -- category `soy` (tier A)
  - matched terms: ['soy sauce']
  - ingredient names: ['shell macaroni', 'dried lentils', 'dried mushroom', 'parmesan cheese', 'instant chicken bouillon granules', 'dried parsley flakes', 'dried oregano', 'garlic powder']
  - quoted step ('soy sauce'): 'Stir in 3 oz. frozen pea pods, halved crosswise and 2 tsps. soy sauce.'
- `imp_d287af8d742e5d44` 'Katjang Sauce: Peanut Sauce' -- category `soy` (tier A)
  - matched terms: ['soy sauce']
  - ingredient names: ['onion', 'garlic cloves', 'brown sugar', 'sambal oelek', 'mild paprika', 'ginger powder', 'crunchy peanut butter', 'ketjap manis', 'milk', 'lemon juice']
  - quoted step ('soy sauce'): '*Ketjap manis is a sweet Indonesian soy sauce. It may be found in  Dutch stores, some Chinese stores or maybe European Delis. It is worth  looking for as it is just delicious!'
- `imp_00efafa3c86e5b9e` 'Beef Stroganoff with Dill' -- category `stock` (tier B)
  - matched terms: ['stock']
  - ingredient names: ['butter', 'mushroom', 'onion', 'cornstarch', 'water', 'sour cream', 'dill weed', 'butter', 'paprika']
  - quoted step ('stock'): 'In a separate pan, saute mushrooms and add to meat. In the separate pan, saute onions and add to meat mixture. Add beef stock.'
  - quoted step ('stock'): 'Toss gently with chicken stock base, butter, and paprika.'
- `imp_a76aa35639d85deb` 'Borscht II' -- category `stock` (tier B)
  - matched terms: ['broth']
  - ingredient names: ['beef stew meat', 'beets', 'onion', 'tomatoes', 'lime, juice of', '-2 sugar', 'sour cream']
  - quoted step ('broth'): 'Half an hour before serving, remove beets, keeping the broth at a simmer.'
- `imp_2020aaedc3cf532a` 'Lasagna Rollups with Bechamel Sauce' -- category `stock` (tier B)
  - matched terms: ['broth']
  - ingredient names: ['-15 beef', '- 2 parmesan cheese', 'bay leaf', 'milk', 'butter', 'pepper', 'salt', 'nutmeg']
  - quoted step ('broth'): 'Stir in scalded milk, instant chicken broth, salt, pepper and nutmeg.'
- `imp_6b64b4caa0125a71` 'Baked Acorn or Hubbard Squash With Orange Sauce' -- category `tree_nut` (tier A)
  - matched terms: ['almonds']
  - ingredient names: ['acorn squash', 'margarine', 'butter', 'brown sugar', '- 1/2 cinnamon', 'nutmeg', 'tangerines']
  - quoted step ('almonds'): 'Sprinkle with almonds.'
- `imp_de9f4959d0855804` 'Cream Puff Paste' -- category `tree_nut` (tier A)
  - matched terms: ['almonds', 'praline']
  - ingredient names: ['all-purpose flour', 'water', 'sweet unsalted butter', 'salt', 'eggs', 'egg']
  - quoted step ('almonds'): 'Brush the whole thing with beaten egg, and  sprinkle a handful of thinly sliced almonds all over the top of the ring.'
  - quoted step ('praline'): 'Fill the bottom with praline cream (or coffee cream, or  chocolate cream) filling.'
  - quoted step ('praline'): 'use a nozzle with a zigzag edge (like pinking shears) to squeeze out a  layer of fancy puff-balls of whipped cream all over the layer of praline  cream filling.'
  - quoted step ('praline'): "Keep the cream puff ring in a cool dry  place until serving time.                  - - - - - - - - - - - - - - - - - -                     *  Exported from  MasterCook  *                            PRALINE FILLING Recipe By     : Homemade Good News (Vol 3 No 3) Serving Size  : 1    Preparation Time :0:00 Categories    : Pastries Amount  Measure       Ingredient -- Preparation Method --------  ------------  --------------------------------  1      cup           10X powdered confectioners' sugar    1/2  cup           almonds Make the vanilla custard cream."
  - quoted step ('almonds'): "Keep the cream puff ring in a cool dry  place until serving time.                  - - - - - - - - - - - - - - - - - -                     *  Exported from  MasterCook  *                            PRALINE FILLING Recipe By     : Homemade Good News (Vol 3 No 3) Serving Size  : 1    Preparation Time :0:00 Categories    : Pastries Amount  Measure       Ingredient -- Preparation Method --------  ------------  --------------------------------  1      cup           10X powdered confectioners' sugar    1/2  cup           almonds Make the vanilla custard cream."
  - quoted step ('praline'): 'Fold the praline powder into the vanilla  custard cream.'
- `imp_7895384b27835dfa` 'Apple Strudel' -- category `tree_nut` (tier A)
  - matched terms: ['almonds']
  - ingredient names: ['apples', 'raisins', 'lemon, rind of', 'sugar', 'cinnamon', 'phyllo pastry', 'butter']
  - quoted step ('almonds'): 'Mix apples with raisins, lemon rind, sugar, cinnamon, and almonds; set aside.'
- `imp_329270d2ee78560a` 'German Stuffed Veal Breast' -- category `wheat_gluten` (tier A)
  - matched terms: ['bread']
  - ingredient names: ['beef', 'pork', 'egg', 'lemon juice', 'nutmeg', 'salt', 'pepper', 'shortening', 'paprika', 'bay leaves', '2 cloves', 'rosemary', 'basil', 'water']
  - quoted step ('bread'): 'Mix ground meats, egg, bread crumbs, lemon juice, netmeg, salt, and pepper for stuffing.'
- `imp_748b6422ecbb5c7d` 'Polish Sausage and Peppers' -- category `wheat_gluten` (tier A)
  - matched terms: ['bread']
  - ingredient names: ['Polish sausage', 'green peppers', 'onions', '-3 beer']
  - quoted step ('bread'): 'Serve the sausage and peppers and onions on French bread.'
- `imp_654b6348a151563b` 'Appetizer Sweet and Sour Meatballs' -- category `wheat_gluten` (tier A)
  - matched terms: ['bread']
  - ingredient names: ['jellied cranberry sauce', 'brown sugar', 'onion', 'water', 'egg']
  - quoted step ('bread'): 'Soak the bread in water until it is soggy but not overly soggy. Remove and place in a mixing bowl.'
- `imp_de9fdd7638765fc8` 'Cooked Salad Dressing' -- category `egg` (tier A)
  - matched terms: ['egg', 'eggs']
  - ingredient names: ['sugar', 'flour', 'dry mustard', 'salt', 'black pepper', 'cider vinegar', 'margarine']
  - quoted step ('eggs'): 'Beat the egg yolks slightly then stir 3  tablespoons of the hot mixture into the eggs.'
  - quoted step ('egg'): 'Beat the egg yolks slightly then stir 3  tablespoons of the hot mixture into the eggs.'
  - quoted step ('egg'): 'Immediately  blend the egg mixture into the mixture in the top of the double boiler.'
- `imp_1b3530039f7a5ca3` 'Crock Pot Pork and Capsicum Pepper Casserole' -- category `meat` (tier A)
  - matched terms: ['pork']
  - ingredient names: ['green capsicum', 'onions', 'mushrooms', 'flour', 'dry white wine', 'tomato puree', 'sage', 'tomatoes']
  - quoted step ('pork'): 'Cut the pork into cubes and brown lightly in the oil.'
- `imp_4206dd29ea5550fb` 'Escalope of Salmon With Chanterelles' -- category `stock` (tier B)
  - matched terms: ['stock']
  - ingredient names: ['salmon', 'canned chanterelles', 'Noilly Prat', 'broad beans', 'peas', 'butter', 'shallots', 'lemon juice', 'sea salt']
  - quoted step ('stock'): 'Make a space for the salmon in the pan,  add wine and fish stock.'
- `imp_b79a7b507fc95c78` 'Calzones II' -- category `wheat_gluten` (tier A)
  - matched terms: ['biscuit', 'floured']
  - ingredient names: ['part-skim ricotta cheese', 'mozzarella cheese', 'ham', 'ham', 'oregano leaves']
  - quoted step ('biscuit'): 'Roll  each biscuit between 2 sheets of floured wax paper, forming  four 6-inch circles.'
  - quoted step ('floured'): 'Roll  each biscuit between 2 sheets of floured wax paper, forming  four 6-inch circles.'

## Miss spot-check candidate list (n=15, seed 20260718)

15 random UNflagged rows for the orchestrator to read for any Tier A/B-class omission the check should have caught (acceptance: 0 misses; a miss is a spec bug, fix and re-run -- not an acceptance judgment call).

- `imp_0a490b0819a15b81` 'Cookie Salad'
  - ingredient names: ['instant vanilla pudding', 'buttermilk', 'Cool Whip', 'mandarin orange', 'french-style ladyfinger cookie']
  - instructions: ['Mix vanilla pudding and buttermilk.', 'Stir in Cool Whip and drained Mandarin oranges.', 'Let set overnight. Before serving, stir in the 1 cup crushed Fudge Strip cookies.']
- `imp_2f284b242a8555f4` 'Jewish Apple Cake'
  - ingredient names: ['unsifted all-purpose flour', 'sugar', 'baking powder', 'salt', 'real vanilla', 'eggs', 'apples', 'cinnamon', 'sugar']
  - instructions: ['Beat together until smooth--flour, 2 1/2 cups of sugar, baking powder, salt, vanilla, oil, eggs, and juice. Then in a separate bowl, mix apples, cinnamon, and sugar.', 'Layer the batter and apples in a greased tube pan.', '**pour some batter--then layer it with apples--then switch back and forth until it is all used up**.', 'Bake in oven at 350° for 1 1/2 hours to 1 3/4 hours.']
- `imp_635b6cd0fbd557ad` 'Hutspot'
  - ingredient names: ['carrots', 'onions', 'potatoes', 'water']
  - instructions: ['First put potatoes in kettle.', 'Add ribs, carrots and onions; salt to taste.', 'Bring to slow boil, cover and cook for about 3 hours.', 'When done take out bones and mash.']
- `imp_1b67712639485a0f` 'Crispy Potato Wedges'
  - ingredient names: ['russet potatoes', 'black pepper', 'salt', 'garlic cloves', 'reduced sodium ketchup']
  - instructions: ['Place potatoes in a large bowl; add cold water to cover and let stand 15 min      minutes.', 'Preheat oven to 425.', 'Spray a nonstick baking sheet with vegetable cooking spray.', 'Set aside.', 'Drain potatoes in colander.', 'Spread on a double layer of paper towels.', 'Cover with a second layer of paper towels.', 'Press down on the towels to dry      potatoes.', 'Transfer potatoes to a clean large bowl.', 'Sprinkle with oil, pepper, and salt;      toss gently to combine.  Arrange seasoned potatoes in a single layer on the      prepared baking sheet.', 'Bake potatoes for 20 minutes.', 'Using a spatula, turn potatoes; sprinkle with garlic.  Bake until golden, about 20 minutes, turning baking sheet after 10      minutes for even browning.', 'Serve immediately with ketchup on the side. <NOTE:  For a sweeter flavor, use sweet potatoes instead of the russet potatoes.', 'Add 1/2 teaspoon of paprika when tossing potatoes with spices.', 'Bake as previously directed.>.']
- `imp_fe5e997cb47c553c` 'Chocolate-Caramel-Pecan Cheesecake'
  - ingredient names: ['graham cracker crumbs', 'butter', 'margarine', 'evaporated milk', 'pecans', 'cream cheese', 'sugar', 'eggs', 'vanilla extract', 'pecan halves']
  - instructions: ['Combine graham cracker crumbs and butter, stirring well.', 'Press mixture evenly onto bottom and 1 inch up sides of a 9-inch springform pan.', 'Unwrap caramels; combine with milk and heat over low heat until  caramels are melted, stirring often.', 'Pour over graham cracker crust;  sprinkle chopped pecans evenly over caramel layer and set aside.', 'Beat  cream cheese at high speed until light and fluffy; gradually add  sugar, mixing well.', 'Add eggs, one at a time, mixing well after each  one. Stir in vanilla and chocolate; beat until blended.', 'Spoon over  pecan layer.', 'Bake at 350 degrees for 30 minutes.', 'Remove from oven,  and run knife around edge of pan to release sides.', 'Let cool t  o room  temperature on a wire rack; cover and chill at least 8 hours before  serving.', 'Top with pecan halves and serve.']
- `imp_5d7345ec55cd55d3` 'Grilled Sweet Potato Salad'
  - ingredient names: ['sweet potatoes', 'olive oil', 'cherry tomatoes', 'extra virgin olive oil', 'clear honey']
  - instructions: ['Preheat grill (broiler) to a medium heat and brush the potato slices with the  olive oil.', 'Season and grill for 10 minutes on each side until tender.', 'Arrange  salad leaves, tomatoes and seeds on a platter.', 'Make the dressing by pouring into a jug and whisking well.', 'Drizzle over the salad leaves.', 'Place the hot potato  slices on the salad and serve.']
- `imp_98860ce03a2f5348` 'Grilled Salmon with Ginger-Orange Mustard Glaze'
  - ingredient names: ['tamari', 'soy sauce', 'cream sherry', 'Dijon mustard', 'fresh ginger', 'honey', 'salmon fillets', 'green onion']
  - instructions: ['Combine first 6 ingredients in a large zip-top plastic bag.', 'Add salmon to bag; seal and marinate in the refrigerator 30 minutes.', 'Remove salmon from bag, reserving marinade. Prepare grill or broiler by spraying with nonstick cooking spray.', 'Cook 6 minutes each side or until fish flakes easily when tested with a fork; basting frequently with reserved marinade. Place remaining marinade in a saucepan; bring to a boil.', 'Serve with salmon; garnish with green onion fans.']
- `imp_60980e0a847f51d4` 'Bran Muffins'
  - ingredient names: ['white flour', 'cornmeal', 'salt', 'skim milk', 'molasses', 'baking soda', 'raisins']
  - instructions: ['Dissolve baking soda in milk.', 'Mix all ingredients together and pour into a muffin tin, using either nonstick pan or paper liners.', 'Bake 325F for 25 minute.']
- `imp_15fe9cc27b96537b` 'Pumpkin-Pecan Pie'
  - ingredient names: ['canned pumpkin', 'sugar', 'ground cinnamon', 'ground ginger', 'ground cloves', 'salt', 'eggs', 'evaporated milk', 'butter', 'pecans', 'brown sugar']
  - instructions: ['Combine the pumpkin, sugar, spices and salt in a bowl mixing well.', 'Add the eggs and evaporated milk.', 'Beat until smooth, using a rotary beater or an electric mixer.', 'Pour into the unbaked pie shell.', 'Bake in a preheated oven at 425 degrees Fahrenheit for 15 minutes and then reduce the temperature to 350 degree and bake for an additional 45 minutes or until a knife inserted halfway between the center and edge comes out clean.', 'Cool on a wire rack.', 'CRUNCHY PECAN TOPPING:  Place the softened butter, brown sugar, and pecans in a bowl and mix until crumbly with a fork.  Sprinkle over the cooled pie. Place the pie under the broiler (5 inches from the heat source) until the mixture begins to bubble, about 1 minute.', 'Cool to room temperature on a wire rack.']
- `imp_d63bae35bb3a55bb` 'Austrian Sweet Cheese Crepes Baked in Custard'
  - ingredient names: ['dried currant', 'boiling water', 'cream cheese', 'eggs', 'lemon, zest of', 'vanilla', 'granulated sugar', 'eggs', 'granulated sugar', 'milk', "confectioners' sugar"]
  - instructions: ['Make filling: In a small heatproof bowl plump currants in boiling-hot water 15 minutes  and drain.', 'Pat currants dry between paper towels.', 'In a food processor or in a bowl with an electric mixer blend together well cream cheese, jam, yolks, zest, and vanilla.', 'In a bowl with an electric mixer (beaters cleaned if necessary) beat whites with a pinch of salt until they hold soft peaks.', 'Add sugar to whites and beat meringue until it holds stiff peaks.', 'Fold cheese mixture into meringue gently but thoroughly and fold in currants.', 'Preheat oven to 400F.', 'and lightly butter a 14-inch-long oval gratin dish or other 2 1/2-quart shallow baking dish.', 'Working with 1 crepe at a time, spread 2 generous tablespoons filling on  each crepe, leaving a 1/2-inch border all around, and roll up crepes  jelly-roll fashion.', 'With a sharp knife cut crepes on a diagonal in half  and arrange, overlapping slightly, in layers in baking dish.', 'Crepes may  be prepared up to this point 4 hours ahead and chilled, covered.', 'Bring  crepes to at room temperature before proceeding.', 'In a small bowl whisk together eggs, granulated sugar, and milk and pour  over crepes, letting custard seep between layers.', 'Bake crepes in middle  of oven 30 to 35 minutes, or until puffed and custard is set, and cool to warm.', "Dust crepes with confectioners' sugar and serve with apricot caramel  sauce."]
- `imp_76c9764c715b5af8` 'Sugar-Free Pumpkin Pie'
  - ingredient names: ['pumpkin', 'egg substitute', 'artificial sweetener', 'cinnamon', 'allspice', 'ginger', 'salt', 'reduced-fat graham cracker crumbs']
  - instructions: ['In a mixing bowl, combine the pumpkin, milk, egg substitute, egg whites and sweetener, beat until smooth.', 'Add the spices and salt, beat until well mixed.', 'Stir in graham cracker crumbs.', 'Pour into a 9-in. pie plate that has been coated with nonstick cooking spray.', "Bake at 325'F for 50-55 minutes or until a knife inserted near the center comes out clean.", 'Cool.', 'If desired, garnish with a dollop of whipped topping and sprinkling of cinnamon.', 'Store in the refrigerator.', "Sweet 'N Low or Sweet One are recommended for baking."]
- `imp_3aee17154e8c59e9` 'Apple Raisin Cobbler Pie'
  - ingredient names: ['raisins', 'nutmeg', 'all-purpose flour', 'brown sugar', 'butter', 'margarine', 'walnuts']
  - instructions: ['Heat oven to 375.', 'Combine apple filling, raisins and nutmeg.', 'Spoon into crust.  Combine flour and sugar.', 'Cut in butter using a pastry blender, fork or two  knives in a scissors motion.', 'until crumbly.', 'Stir in walnuts, sprinkle over  filling.', 'Bake 30-45 minutes or until topping is golden']
- `imp_16baa175074c5e58` 'Chocolate Cheesecake Brownies'
  - ingredient names: ['unsalted butter', 'instant coffee', 'eggs', 'sugar', 'flour', 'salt', 'vanilla', 'cream cheese', 'unsalted butter', 'sugar', 'eggs', 'flour']
  - instructions: ['Brownie batter - preheat oven to 350~. Butter 13"x9"x2" baking pan.', 'Combine chocolate, butter, and coffee powder in heavy small saucepan. Stir over low heat until melted and smooth.', 'Remove from heat; cool slightly.', 'In lg. bowl, beat eggs until frothy. Gradually add sugar and beat until mixture is pale yellow and slightly thickened.', 'Stir in flour, cocoa, and salt. Add vanilla, liqueur, and melted chocolate mixture; stir until well blended.', 'Cream cheese mixture - using electric mixer, beat cream cheese and butter in lg. bowl until smooth.', 'Add sugar and beat until fluffy. Beat in eggs, flour, and coffee liqueur.', 'Set aside 1/2 cup brownie batter for topping.', 'Pour remaining batter into prepared pan.  Carefully spoon cream cheese mixture over batter, covering completely. Sprinkle chocolate chips evenly over cream cheese layer.', 'Drop reserved batter by spoonfuls over cream cheese layer.', 'Using small knife, swirl batter into cream cheese mixture to resemble marble pattern.', 'Bake brownies until edges are light golden and toothpick inserted into center comes out with some crumbs still  attached; about 30 mins.', 'Cool completely in pan on rack; cut into squares.']
- `imp_6fbf683033c953b3` 'Versatile Salad Dressing'
  - ingredient names: ['sugar', 'all-purpose flour', 'salt', 'mustard', 'eggs', 'vinegar', 'water', 'mayonnaise']
  - instructions: ['In a saucepan, combine sugar, flour, salt and mustard; stir in eggs.', 'Gradually stir in vinegar and water until smooth.', 'Bring to a boil over  medium heat, stirring constantly; cook and stir for 2 minutes.', 'Cover and  refrigerate. Just before serving, combine desired amount of base with an  equal amount of mayonnaise. Serve as a dressing for potato salad,  coleslaw or salad greens.', 'Refrigerate leftovers.']
- `imp_72681c74734b550b` 'Sweet Pumpkin Pickles'
  - ingredient names: ['prepared pumpkin', 'white vinegar', 'sugar', 'cinnamon sticks']
  - instructions: ['Prepare pumpkin by peeling, cubing and discarding seeds and inner pulp.', 'Place pumpkin  cubes in colander and set over boiling water. Make sure water does not touch pumpkin. Cover and steam until just tender, 5 to 7 minutes. Drain.', 'Simmer vinegar, sugar and cinnamon for 15 minutes.', 'Add pumpkin and simmer 3 minutes.', 'Set aside for 24 hours.', 'Heat and simmer 5 minutes more. Remove cinnamon sticks.', 'Pack boiling hot in hot canning jars, leaving 1/2-inch headroom.', 'Adjust lids and process in hot water bath for 10 minutes.']

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

