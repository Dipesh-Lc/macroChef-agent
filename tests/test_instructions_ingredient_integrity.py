"""Unit tests for app.services.corpus_import.instructions_ingredient_integrity
-- the shared detection logic behind the instructions/ingredient integrity
check (spec: docs/instructions_integrity_spec.md).

Planted-fault fixtures are copied VERBATIM (title, ingredients, instructions,
allergens) from the real corpus rows so these tests don't depend on live
data files -- 7 from the quarantine sidecar
(data/processed/quarantined_recipes.jsonl), 3 still live in
data/processed/imported_recipes.jsonl, and 3 curated seeds from
data/processed/sample_recipes.jsonl (the actual path -- the spec's
"data/recipes/sample_recipes.jsonl" does not exist in this repo).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.schemas.ingredient import Ingredient
from app.schemas.recipe import Recipe
from app.services import constraint_engine
from app.services.corpus_import.instructions_ingredient_integrity import (
    MEAT_FLESH_TERMS,
    Mismatch,
    build_quarantine_record,
    find_instructions_ingredient_mismatches,
    tier_ab_mismatches,
    tier_c_mismatches,
)


def _recipe(
    recipe_id: str,
    title: str,
    ingredients: list[dict],
    instructions: list[str],
    allergens: list[str] | None = None,
) -> Recipe:
    return Recipe(
        recipe_id=recipe_id,
        title=title,
        ingredients=[Ingredient(**item) for item in ingredients],
        instructions=instructions,
        allergens=allergens or [],
    )


def _categories(mismatches: list[Mismatch]) -> set[str]:
    return {m.category for m in mismatches}


# --- Planted-fault fixtures (must flag), verbatim from the corpus ----------


def test_imp_348d24dd1f4d5284_prize_butter_tarts_flags_wheat() -> None:
    # pecans ARE present (satisfies "nut"/"tree_nut"), so the negated
    # "without the raisins or nuts" step is not needed to pass -- the wheat
    # flag comes from "pastry"/"pastry dough", never listed as an ingredient.
    recipe = _recipe(
        "imp_348d24dd1f4d5284",
        "Prize Butter Tarts",
        [
            {"name": "brown sugar", "amount": 1.0, "unit": None},
            {"name": "seedless raisins", "amount": 0.5, "unit": None},
            {"name": "pecans", "amount": 0.3333333333333333, "unit": None},
            {"name": "butter", "amount": 1.0, "unit": None},
            {"name": "margarine", "amount": 2.0, "unit": None},
            {"name": "egg", "amount": 1.0, "unit": None},
            {"name": "milk", "amount": 1.0, "unit": None},
            {"name": "vanilla", "amount": None, "unit": None},
        ],
        [
            "Preheat oven to 375F.",
            "Prepare pastry dough; cut in circles and line 3-inch tart pans with pastry circles.",
            "Combine balance of ingredients.",
            "Spoon mixture into unbaked pastry lined pans, filling each no more than 2/3 full "
            "(if the filling bubbles over it makes one heck of a mess!). Bake for 20 minutes or "
            "until filling has cooked and pastry is golden.",
            "Notes: This can be made without the raisins or nuts, but  they are very plain.",
            "Craisins can be substituted for the raisins.",
            "For Jam Tarts: Line tart pan cups with pastry.",
            "Fill cups 1/2 full with your choice of jam.",
            "Bake at 400F for 20 minutes or until pastry is golden.",
        ],
        allergens=["dairy", "egg", "eggs", "milk", "nuts", "tree nut"],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert "wheat_gluten" in categories
    assert "nut" not in categories
    assert "tree_nut" not in categories


def test_imp_6ab74a6c238451a3_banana_nut_muffins_flags_nut_not_ground_nutmeg() -> None:
    recipe = _recipe(
        "imp_6ab74a6c238451a3",
        "Banana-Nut Muffins",
        [
            {"name": "white flour", "amount": 2.0, "unit": None},
            {"name": "baking powder", "amount": 3.0, "unit": None},
            {"name": "salt", "amount": 0.5, "unit": None},
            {"name": "ground cinnamon", "amount": 1.0, "unit": None},
            {"name": "ground nutmeg", "amount": 0.25, "unit": None},
            {"name": "butter", "amount": 0.5, "unit": None},
            {"name": "- 1 margarine", "amount": 0.6666666666666666, "unit": None},
            {"name": "sugar", "amount": 2.0, "unit": None},
            {"name": "eggs", "amount": 1.0, "unit": None},
            {"name": "vanilla extract", "amount": 1.5, "unit": None},
            {"name": "bananas", "amount": 1.0, "unit": None},
        ],
        [
            "Sift together flour, baking powder, salt and spices; set aside.",
            "Cream together butter and sugar in bowl until light and fluffy, using electric "
            "mixer at medium speed.",
            "Beat in eggs, one at a time, blending well after each addition.",
            "Stir in mashed bananas.   Add vanilla to banana mixture.",
            "Mix nuts with flour and add all at once to banana mixture, stirring gently to just combine",
            "Spoon batter into 6 greased 3-inch muffin-pan cups.",
            "Batter will be thick.",
            "Bake in 375 degree F. oven 20-30 minutes or until golden brown.",
            "Serve hot with homemade jam or jelly.",
        ],
        allergens=["dairy", "egg", "eggs", "milk"],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert "nut" in categories
    # "ground nutmeg" (\bnutmeg\b, not \bnut\b -- no word boundary inside it)
    # must NOT satisfy the "nut" category.
    nut_mismatch = next(m for m in mismatches if m.category == "nut")
    assert "nutmeg" not in nut_mismatch.matched_terms


def test_imp_78c1d567c07b545a_chinese_beef_and_broccoli_flags_meat() -> None:
    recipe = _recipe(
        "imp_78c1d567c07b545a",
        "Chinese Beef and Broccoli",
        [
            {"name": "soy sauce", "amount": 1.0, "unit": None},
            {"name": "dry sherry", "amount": 2.0, "unit": None},
            {"name": "cornstarch", "amount": 1.0, "unit": None},
            {"name": "frozen broccoli", "amount": 0.5, "unit": None},
            {"name": "garlic clove", "amount": 1.0, "unit": None},
            {"name": "fresh ginger", "amount": 1.0, "unit": None},
            {"name": "salt", "amount": 1.0, "unit": None},
        ],
        [
            "Slice the steak against the grain into very thin slices.",
            "Combine the soy sauce, sherry, and cornstarch and pour this mixture over the steak.",
            "Marinate the meat for 15 minutes.",
            "While the meat is marinating, slice the broccoli at a diagonal and mince garlic and ginger.",
            "Heat a wok or large frying pan for 30 seconds, add oil, wait about 20 seconds, and add "
            "minced garlic and ginger root. Fry over high heat, stirring constantly for about 20 "
            "seconds more, then add the beef.",
            "Stir-fry, stirring constantly, for about 1 minute. Add broccoli and stir-fry for "
            "another 4 to 6 minutes, until the broccoli is cooked but still crisp and still dark green.",
            "Serve hot. This is low in carbohydrates.",
        ],
        allergens=["soy", "soya"],
    )
    all_mismatches = find_instructions_ingredient_mismatches(recipe)
    ab = tier_ab_mismatches(all_mismatches)
    categories = _categories(ab)
    assert categories == {"meat"}
    meat_mismatch = next(m for m in ab if m.category == "meat")
    assert {"beef", "steak"} <= set(meat_mismatch.matched_terms)
    # "soy sauce" is already a listed ingredient -- wheat_gluten AND soy must
    # both be SATISFIED (not flagged), even though "soy sauce" is a trigger
    # phrase for both categories.
    assert "wheat_gluten" not in categories
    assert "soy" not in categories
    # Bare "meat" is Tier C (report-only), never gates the decision.
    assert "meat_generic" in _categories(tier_c_mismatches(all_mismatches))


def test_imp_997819df41245ec6_banana_bread_flags_tree_nut_via_unsuppressed_step() -> None:
    recipe = _recipe(
        "imp_997819df41245ec6",
        "Perfectly Spiced Banana Bread",
        [
            {"name": "all-purpose flour", "amount": 1.75, "unit": None},
            {"name": "baking powder", "amount": 2.0, "unit": None},
            {"name": "baking soda", "amount": 0.5, "unit": None},
            {"name": "salt", "amount": 0.5, "unit": None},
            {"name": "ginger", "amount": 0.5, "unit": None},
            {"name": "allspice", "amount": 0.25, "unit": None},
            {"name": "nutmeg", "amount": 0.25, "unit": None},
            {"name": "lemon zest", "amount": 1.0, "unit": None},
            {"name": "butter", "amount": 0.25, "unit": None},
            {"name": "margarine", "amount": 0.5, "unit": None},
            {"name": "sugar", "amount": 0.75, "unit": None},
            {"name": "eggs", "amount": 2.0, "unit": None},
            {"name": "bananas", "amount": 1.5, "unit": None},
        ],
        [
            "Preheat oven to 350F.",
            "Grease 9 x 5 inch loaf pan.",
            "Sift flour,baking powder,  baking soda, salt, ginger, allspice and nutmeg together in bowl.",
            "Add lemon zest and almonds.",
            "Stir until combined.",
            "Set aside. Beat butter in large mixing bowl until soft and creamy.",
            "Beat in sugar until light and fluffy.",
            "Add eggs and beat until thoroughly blended.",
            "Beat in flour mixture alternately with bananas until mixture is well blended.",
            "Pour into prepared pan.",
            "Bake in center of oven 1 hour to 1 hour 5 minutes, or until toothpick inserted in "
            "center comes out clean.",
            "Cool in pan on wire rack 10 minutes.",
            "Invert from pan and cool completely on rack.",
            "Variation: Banana-walnut or -pecan bread: Omit almonds.",
            "Add 3/4 cup coarsely chopped walnuts or pecans with bananas.",
        ],
        allergens=["dairy", "egg", "eggs", "milk"],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    tree_nut = next(m for m in mismatches if m.category == "tree_nut")
    # The "Add lemon zest and almonds." step has no negation cue -> flags.
    assert "almonds" in tree_nut.matched_terms
    # The negated "Omit almonds." step must not be the ONLY source of the
    # flag (it is suppressed) -- covered by the assertion above, since
    # "almonds" only appears unnegated in the earlier step.
    negated_step_terms = {
        term
        for entry in tree_nut.evidence
        if "Omit almonds" in entry["quoted_step"]
        for term in [entry["term"]]
    }
    assert negated_step_terms == set(), "the negated 'Omit almonds.' step must not contribute evidence"


def test_imp_9e0a542fc2195d5b_bananas_baked_with_custard_flags_wheat_bread() -> None:
    recipe = _recipe(
        "imp_9e0a542fc2195d5b",
        "Bananas Baked With Custard",
        [
            {"name": "butter", "amount": 1.0, "unit": None},
            {"name": "bananas", "amount": 4.0, "unit": None},
            {"name": "sultanas", "amount": 6.0, "unit": None},
            {"name": "milk", "amount": 2.0, "unit": None},
            {"name": "eggs", "amount": 1.0, "unit": None},
            {"name": "brown sugar", "amount": 2.0, "unit": None},
            {"name": "nutmeg", "amount": 2.0, "unit": None},
        ],
        [
            "Grease a med-sized baking dish with butter.",
            "Peel the  bananas and cut into rounds.",
            "Halve the bread slices  Put layers of the bread, bananas and sultanas in the baking  "
            "dish, ending with a layer of bread.",
            "In a small pan heat milk over moderate heat. Beat the  eggs, egg-yolks and sugar together.",
            "Slowly pour in the milk,  stirring continuously.",
            "Pour the milk-egg mixture into the  baking dish and leave to stand 30 minutes.",
            "Dust the pudding with  nutmeg.",
            "Cook in at 190 C for 30 minutes.",
            "Serve hot or cold.",
        ],
        allergens=["dairy", "egg", "eggs", "milk"],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert "wheat_gluten" in categories
    bread_mismatch = next(m for m in mismatches if m.category == "wheat_gluten")
    assert "bread" in bread_mismatch.matched_terms


def test_imp_9ff0ac08d2b353ca_banana_bran_muffins_flags_nut_pastry_blender_suppressed() -> None:
    recipe = _recipe(
        "imp_9ff0ac08d2b353ca",
        "Banana Bran Muffins with Strawberry Butter",
        [
            {"name": "all-purpose flour", "amount": 1.6666666666666665, "unit": None},
            {"name": "baking powder", "amount": 1.0, "unit": None},
            {"name": "butter", "amount": 0.5, "unit": None},
            {"name": "baking soda", "amount": 1.0, "unit": None},
            {"name": "egg", "amount": 0.6666666666666666, "unit": None},
            {"name": "banana", "amount": 0.5, "unit": None},
            {"name": "plain yogurt", "amount": 1.0, "unit": None},
            {"name": "brown sugar", "amount": 0.6666666666666666, "unit": None},
            {"name": "molasses", "amount": 0.5, "unit": None},
            {"name": "butter", "amount": 0.5, "unit": None},
        ],
        [
            "Preheat oven to 375F (190C). In a large bowl, combine flour, baking powder and baking soda.",
            "Cut in butter with pastry blender or two knives until mixture is crumbly.",
            "Stir in bran and nuts.",
            "In a medium bowl, lightly beat egg; stir in banana, yogurt, brown sugar and molasses.",
            "Add to dry ingredients, all at once, stirring just until moistened.",
            "Divide batter evenly among 12 medium greased muffin cups.",
            "Bake 20 minutes or until toothpick inserted in centre comes out clean.",
            "Cool 10 minutes in cups on wire racks.",
            "Remove from cups and let cool completely.",
            "Serve with Strawberry Butter.",
            "Straw berry Butter: Cream together 1/2 cup (125 mL) softened butter and 1/2 cup (125 mL) "
            "strawberry jam.  Makes about 1 cup (250 mL).",
            "TIP: Add a topping treat to your muffins before you bake them.  Over batter in muffin "
            "cups, sprinkle quick-cooking rolled oats, cinnamon and sugar, sesame seeds or chopped nuts.",
        ],
        allergens=["dairy", "egg", "eggs", "milk"],
    )
    all_mismatches = find_instructions_ingredient_mismatches(recipe)
    ab = tier_ab_mismatches(all_mismatches)
    categories = _categories(ab)
    assert "nut" in categories
    # "pastry blender" is a tool, not a wheat mention -- must not appear as a
    # matched term anywhere (whether or not wheat_gluten happens to also be
    # satisfied via the flour ingredient).
    for mismatch in all_mismatches:
        assert "pastry" not in mismatch.matched_terms


def test_imp_ffba7239b17c5b29_spicy_fish_cakes_flags_fish() -> None:
    recipe = _recipe(
        "imp_ffba7239b17c5b29",
        "Spicy Fish Cakes",
        [
            {"name": "spring onions", "amount": 3.0, "unit": None},
            {"name": "red capsicum", "amount": 0.5, "unit": None},
            {"name": "potatoes", "amount": 2.0, "unit": None},
            {"name": "eggs", "amount": 1.0, "unit": None},
            {"name": "flour", "amount": 375.0, "unit": None},
            {"name": "salt", "amount": 2.0, "unit": None},
            {"name": "parsley", "amount": 1.0, "unit": None},
            {"name": "butter", "amount": 1.0, "unit": None},
        ],
        [
            "Slice onions finely.",
            "Chop the flesh of the capsicum finely.",
            "Cut the potatoes into 1cm cubes.",
            "Place all into a bowl with the Creole seasoning.",
            "Cut the fish into small pieces and mix through the potato mixture with the eggs, "
            "flour, salt and parsley.",
            "Heat frypan and add oil and butter.",
            "Cook 1 Tbs of the mixture, turning to brown both sides.",
            "Place fritters on absorbent paper.",
            "Serve with Corn Salsa, relish or a fruit chutney.",
            "Cheers,  Doreen Doreen Randal,  Wanganui.",
            "New Zealand.",
        ],
        allergens=["dairy", "egg", "eggs", "gluten", "milk", "wheat"],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert categories == {"fish"}


def test_imp_d34a2ab621245cba_unusual_chicken_flags_egg_and_peanut() -> None:
    recipe = _recipe(
        "imp_d34a2ab621245cba",
        "Unusual Chicken",
        [
            {"name": "chicken piece", "amount": None, "unit": None},
            {"name": "chili powder", "amount": None, "unit": None},
            {"name": "ginger", "amount": None, "unit": None},
            {"name": "salt", "amount": None, "unit": None},
            {"name": "garam masala", "amount": None, "unit": None},
            {"name": "soy sauce", "amount": None, "unit": None},
            {"name": "plain yogurt", "amount": None, "unit": None},
            {"name": "curry leaf", "amount": None, "unit": None},
            {"name": "ginger", "amount": None, "unit": None},
            {"name": "garlic", "amount": None, "unit": None},
            {"name": "green chili", "amount": None, "unit": None},
            {"name": "spring onion", "amount": None, "unit": None},
            {"name": "coriander leaves", "amount": None, "unit": None},
        ],
        [
            "Mix together and marinate chicken for about 5 to 6 hours or overnight in a covered "
            "dish in the refrigerator.",
            "Add one beaten egg and corn flour to cover. Place some ground nut oil in a wok heat "
            "oil and deep fry on a low heat. The meat is now ready to eat.",
            "If a hotter dish is required: Take some curry leaves, ginger, garlic, green chilies, "
            "spring onions, coriander leaves. Place all the above in a wok with hot oil and fry "
            "for a couple of minutes.",
            "Add some yogurt and tomato sauce and stir. Now add the chicken and some red food "
            "coloring and stir fry again to cover all the meat with the sauce.",
        ],
        allergens=["soy", "soya"],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    # Resolves review finding 4: still live in the corpus.
    assert categories == {"egg", "peanut"}
    peanut_mismatch = next(m for m in mismatches if m.category == "peanut")
    assert "ground nut" in peanut_mismatch.matched_terms
    # meat is satisfied (chicken piece is listed) -- must not also flag.
    assert "meat" not in categories


def test_imp_acd7c3ec0ed35a51_rice_apple_raisin_dressing_flags_tier_b_stock() -> None:
    recipe = _recipe(
        "imp_acd7c3ec0ed35a51",
        "Rice, Apple and Raisin Dressing",
        [
            {"name": "salt", "amount": 2.0, "unit": None},
            {"name": "white pepper", "amount": 1.5, "unit": None},
            {"name": "garlic powder", "amount": 1.0, "unit": None},
            {"name": "dry mustard", "amount": 1.0, "unit": None},
            {"name": "cayenne pepper", "amount": 1.0, "unit": None},
            {"name": "black pepper", "amount": 0.5, "unit": None},
            {"name": "onion", "amount": 0.25, "unit": None},
            {"name": "green bell pepper", "amount": 1.0, "unit": None},
            {"name": "pecan halves", "amount": 1.0, "unit": None},
            {"name": "raisins", "amount": 0.5, "unit": None},
            {"name": "unsalted butter", "amount": 0.5, "unit": None},
            {"name": "rice", "amount": 4.0, "unit": None},
            {"name": "apples", "amount": 1.5, "unit": None},
        ],
        [
            "Combine the seasoning mix ingredients in a small bowl and set aside.",
            "In a 2-quart saucepan, heat the oil over high heat until very hot, about 2 minutes.",
            "Add the onions and bell peppers; saute about 2 minutes, stirring occasionally.",
            "Add the pecans and continue cooking for about 3 minutes, stirring occasionally.",
            "Add the raisins and butter (these are added together so the raisins will absorb as "
            "much butter as possible).",
            "Stir until butter is melted, then cook until raisins are plump, about 4 minutes, "
            "stirring occasionally.",
            'Add the rice and seasoning mix and cook until rice starts looking frizzly (a bit '
            'like ce Krispies) Chef Prudhomme recommended using converted rice.',
            'This will require about 2 to 3 minutes, stirring almost constantly before the rice '
            'looks "frizzly".',
            "Stir in the stock, scraping pan bottom well, then stir in the apples.",
            "Cover pan and bring to boil; lower heat and simmer covered for 5 minutes.",
        ],
        allergens=[],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert categories == {"stock"}
    stock_mismatch = next(m for m in mismatches if m.category == "stock")
    assert stock_mismatch.tier == "B"


def test_imp_ece8c7dd17b95468_dirty_rice_flags_tier_b_stock_pork_satisfies_meat() -> None:
    recipe = _recipe(
        "imp_ece8c7dd17b95468",
        "Dirty Rice",
        [
            {"name": "chicken fat", "amount": 2.0, "unit": None},
            {"name": "black pepper", "amount": 1.0, "unit": None},
            {"name": "chicken gizzard", "amount": 0.5, "unit": None},
            {"name": "paprika", "amount": 2.0, "unit": None},
            {"name": "pork", "amount": 0.25, "unit": None},
            {"name": "dry mustard", "amount": 1.0, "unit": None},
            {"name": "bay leaf", "amount": 1.0, "unit": None},
            {"name": "cumin", "amount": 1.0, "unit": None},
            {"name": "yellow onion", "amount": 1.0, "unit": None},
            {"name": "thyme", "amount": 0.5, "unit": None},
            {"name": "celery", "amount": 1.5, "unit": None},
            {"name": "oregano", "amount": 0.5, "unit": None},
            {"name": "bell pepper", "amount": 0.5, "unit": None},
            {"name": "butter", "amount": 2.0, "unit": None},
            {"name": "garlic clove", "amount": 1.0, "unit": None},
            {"name": "Tabasco sauce", "amount": 2.0, "unit": None},
            {"name": "chicken liver", "amount": 1.0, "unit": None},
            {"name": "salt", "amount": 0.5, "unit": None},
            {"name": "rice", "amount": 1.0, "unit": None},
        ],
        [
            "Mince onion, bell pepper, celery and garlic.",
            "Grind livers and gizzards.",
            "Place fat, gizzards, pork and bay leaves in large heavy skillet over high heat; cook "
            "until meat is thoroughly browned, about 6 minutes, stirring occasionally.",
            "Stir in the onion, celery, bell pepper, garlic, Tabasco, salt, pepper, paprika, "
            "mustard, cumin, thyme, and oregano; stir thoroughly, scraping pan bottom well.",
            "Add the butter and stir until melted.",
            "Reduce heat to medium and cook about 8 minutes, stirring constantly and scraping "
            "pan bottom well.",
            "Add the stock or water and stir until any mixture sticking to the pan bottom comes "
            "loose; cook about 8 minutes over high heat, stirring once.",
            "Then stir in the chicken livers and cook about 2 minutes.",
            "Add the rice and stir thoroughly; cover pan and turn heat to very low; cook about "
            "5 minutes.",
            "Remove from heat and leave covered until rice is tender, about 10 minutes.",
            "Remove bay leaves and serve immediately.",
        ],
        allergens=["dairy", "milk"],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    # "or water" does NOT suppress the stock mention.
    assert categories == {"stock"}
    # pork/chicken rows already satisfy meat -- must not also flag.
    assert "meat" not in categories


# --- Must-NOT-flag fixtures -------------------------------------------------


def test_imp_e8b6568570965387_fish_marinade_serving_cue_suppressed() -> None:
    recipe = _recipe(
        "imp_e8b6568570965387",
        "Fish Marinade",
        [
            {"name": "lemon juice", "amount": 2.0, "unit": None},
            {"name": "salt", "amount": 2.0, "unit": None},
            {"name": "creole mustard", "amount": 2.0, "unit": None},
            {"name": "cayenne pepper", "amount": 2.0, "unit": None},
        ],
        [
            "Mix all ingredients together and stir well.",
            "Use as a marinade, Then as a basting sauce when you cook fish.",
        ],
        allergens=[],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_imp_f9cc221553155bfc_mallow_topped_sweet_potatoes_orange_juice_out_of_scope() -> None:
    # Documents the deliberate boundary (spec Sec. 1): hidden "orange juice"
    # cannot produce an engine-visible allergy/diet violation, so this
    # module has no vocabulary for it at all and correctly produces zero
    # mismatches despite the instructions naming an ingredient
    # ("orange  juice") absent from the ingredient list.
    recipe = _recipe(
        "imp_f9cc221553155bfc",
        "Mallow Topped Sweet Potatoes",
        [
            {"name": "sweet potatoes", "amount": 3.0, "unit": None},
            {"name": "butter", "amount": 0.25, "unit": None},
            {"name": "margarine", "amount": 0.25, "unit": None},
            {"name": "brown sugar", "amount": 0.25, "unit": None},
            {"name": "salt", "amount": 0.5, "unit": None},
            {"name": "cinnamon", "amount": 1.0, "unit": None},
            {"name": "nutmeg", "amount": 0.25, "unit": None},
            {"name": "marshmallows", "amount": 25.0, "unit": None},
        ],
        [
            "Heat oven to 350 degrees.",
            'Pour sweet potatoes in a 10x6" (1 1/2 quart) baking  dish coated with cooking spray.',
            "In a separate bowl, combine butter, orange  juice, brown sugar, salt and spices.",
            "Mix thoroughly.",
            "Pour mixture over sweet  potatoes.",
            "Top with marshmallows.",
            "Bake for 18-20 min.",
            "or until hot and  marshmallows are lightly browned.",
        ],
        allergens=["dairy", "milk"],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_seed_r_007_coconut_milk_does_not_fire_dairy() -> None:
    recipe = _recipe(
        "r_007",
        "Indian Chickpea Spinach Curry",
        [
            {"name": "chickpeas", "amount": 150, "unit": "g", "preparation": "canned"},
            {"name": "spinach", "amount": 60, "unit": "g"},
            {"name": "tomato", "amount": 1, "unit": None},
            {"name": "onion", "amount": 0.5, "unit": None},
            {"name": "garlic", "amount": 2, "unit": "clove"},
            {"name": "ginger", "amount": 5, "unit": "g"},
            {"name": "coconut milk", "amount": 100, "unit": "ml", "preparation": "canned"},
            {"name": "basmati rice", "amount": 150, "unit": "g", "preparation": "cooked"},
        ],
        [
            "Saute onion, garlic, and ginger.",
            "Add tomato and spices and simmer.",
            "Stir in chickpeas, spinach, and coconut milk.",
            "Serve with basmati rice.",
        ],
        allergens=[],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_seed_r_009_dairy_free_chicken_fajita_plate_clean() -> None:
    recipe = _recipe(
        "r_009",
        "Dairy-Free Chicken Fajita Plate",
        [
            {"name": "chicken breast", "amount": 180, "unit": "g", "preparation": "raw"},
            {"name": "bell pepper", "amount": 1, "unit": None},
            {"name": "onion", "amount": 1, "unit": None},
            {"name": "brown rice", "amount": 150, "unit": "g", "preparation": "cooked"},
            {"name": "black beans", "amount": 100, "unit": "g", "preparation": "canned"},
            {"name": "lime", "amount": 15, "unit": "g"},
            {"name": "avocado", "amount": 0.5, "unit": None},
            {"name": "coriander", "amount": 5, "unit": "g"},
        ],
        [
            "Cook brown rice.",
            "Sear sliced chicken with peppers and onion.",
            "Warm black beans.",
            "Serve with avocado, lime, and coriander.",
        ],
        allergens=[],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_seed_r_012_american_turkey_sweet_potato_chili_clean() -> None:
    recipe = _recipe(
        "r_012",
        "American Turkey Sweet Potato Chili",
        [
            {"name": "ground turkey", "amount": 170, "unit": "g", "preparation": "raw"},
            {"name": "sweet potato", "amount": 150, "unit": "g"},
            {"name": "black beans", "amount": 130, "unit": "g", "preparation": "canned"},
            {"name": "tomato", "amount": 2, "unit": None},
            {"name": "onion", "amount": 0.5, "unit": None},
            {"name": "chili powder", "amount": 5, "unit": "g"},
            {"name": "spinach", "amount": 40, "unit": "g"},
        ],
        [
            "Brown ground turkey with onion.",
            "Add sweet potato, tomato, beans, and chili powder.",
            "Simmer until sweet potato is tender.",
            "Stir in spinach before serving.",
        ],
        allergens=[],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


# --- Synthetic units ---------------------------------------------------


def test_synthetic_nutmeg_doughnut_butternut_coconut_no_word_boundary_false_positive() -> None:
    recipe = _recipe(
        "syn1",
        "Synthetic",
        [{"name": "sugar", "amount": 1, "unit": None}, {"name": "flour", "amount": 1, "unit": None}],
        [
            "Add a pinch of ground nutmeg.",
            "Serve with butternut squash and a doughnut on the side.",
            "Top with coconut flakes.",
        ],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_cream_the_butter_and_sugar_is_a_verb_not_a_trigger() -> None:
    recipe = _recipe(
        "syn2",
        "Synthetic",
        [{"name": "butter", "amount": 1, "unit": None}, {"name": "sugar", "amount": 1, "unit": None}],
        ["Cream the butter and sugar until fluffy."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_grease_and_flour_the_pan_satisfied_by_flour_row() -> None:
    recipe = _recipe(
        "syn3",
        "Synthetic",
        [{"name": "flour", "amount": 1, "unit": None}, {"name": "butter", "amount": 1, "unit": None}],
        ["Grease and flour the pan."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_coconut_milk_row_satisfies_bare_milk_mention() -> None:
    recipe = _recipe(
        "syn4",
        "Synthetic",
        [{"name": "coconut milk", "amount": 1, "unit": None}],
        ["Stir in the milk and simmer."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_margarine_row_satisfies_melt_the_butter() -> None:
    recipe = _recipe(
        "syn5",
        "Synthetic",
        [{"name": "margarine", "amount": 1, "unit": None}],
        ["Melt the butter in a pan."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_rice_flour_row_satisfies_add_the_flour() -> None:
    recipe = _recipe(
        "syn6",
        "Synthetic",
        [{"name": "rice flour", "amount": 1, "unit": None}],
        ["Add the flour and mix well."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_stock_pot_phrase_is_not_tier_b() -> None:
    recipe = _recipe(
        "syn7",
        "Synthetic",
        [{"name": "water", "amount": 1, "unit": None}, {"name": "salt", "amount": 1, "unit": None}],
        ["Heat the stock pot over medium heat."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_scalloped_potatoes_is_not_mollusk() -> None:
    recipe = _recipe(
        "syn8",
        "Synthetic",
        [
            {"name": "potatoes", "amount": 1, "unit": None},
            {"name": "milk", "amount": 1, "unit": None},
            {"name": "cheese", "amount": 1, "unit": None},
        ],
        ["Layer the scalloped potatoes in a dish."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_only_negated_mention_does_not_flag() -> None:
    recipe = _recipe(
        "syn9",
        "Synthetic",
        [{"name": "flour", "amount": 1, "unit": None}, {"name": "sugar", "amount": 1, "unit": None}],
        ["Omit walnuts if allergic."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_pastry_blender_suppressed_even_with_no_flour_row() -> None:
    # No flour/bread/wheat ingredient at all -- if "pastry blender" weren't
    # suppressed, this would incorrectly flag wheat_gluten.
    recipe = _recipe(
        "syn10",
        "Synthetic",
        [{"name": "butter", "amount": 1, "unit": None}, {"name": "sugar", "amount": 1, "unit": None}],
        ["Cut in butter with pastry blender until crumbly."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_gluten_free_negation_suffix_disclaims_wheat() -> None:
    recipe = _recipe(
        "syn11",
        "Synthetic",
        [{"name": "rice flour", "amount": 1, "unit": None}],
        ["Use gluten-free bread for this recipe."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_no_nuts_negation_disclaims_nut() -> None:
    recipe = _recipe(
        "syn12",
        "Synthetic",
        [{"name": "flour", "amount": 1, "unit": None}],
        ["This is a no nuts recipe, safe for school lunches."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_water_chestnut_preceding_token_suppression() -> None:
    recipe = _recipe(
        "syn13",
        "Synthetic",
        [{"name": "celery", "amount": 1, "unit": None}],
        ["Add sliced water chestnuts to the stir-fry."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_cape_cod_place_name_suppressed() -> None:
    recipe = _recipe(
        "syn14",
        "Synthetic",
        [{"name": "cranberries", "amount": 1, "unit": None}],
        ["This is a Cape Cod specialty."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_oyster_crackers_suppresses_oyster_not_cracker() -> None:
    # "oyster crackers" (no oyster ingredient) must not flag mollusk, but
    # bare "cracker" is still a wheat trigger with no flour/cracker row.
    recipe = _recipe(
        "syn15",
        "Synthetic",
        [{"name": "soup", "amount": 1, "unit": None}],
        ["Serve the soup topped with oyster crackers."],
    )
    all_mismatches = find_instructions_ingredient_mismatches(recipe)
    # "Serve the soup topped with..." contains "serve" but not one of the
    # exact serving-cue phrases ("serve with"/"serve over"/...), so the step
    # is NOT suppressed by the serving-cue rule; "oyster" is suppressed by
    # the exact-phrase rule; "cracker" fires wheat_gluten with no satisfier.
    categories = _categories(tier_ab_mismatches(all_mismatches))
    assert "mollusk" not in categories
    assert "wheat_gluten" in categories


def test_synthetic_fish_out_idiom_suppressed() -> None:
    recipe = _recipe(
        "syn16",
        "Synthetic",
        [{"name": "bay leaves", "amount": 1, "unit": None}, {"name": "stew", "amount": 1, "unit": None}],
        ["Fish out the bay leaves before serving."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_eggplant_hyphenated_idiom_suppressed() -> None:
    recipe = _recipe(
        "syn17",
        "Synthetic",
        [{"name": "eggplant", "amount": 1, "unit": None}],
        ["Slice the egg-plant into rounds."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_mock_prefix_disclaims_per_step() -> None:
    recipe = _recipe(
        "syn18",
        "Synthetic",
        [{"name": "pinto beans", "amount": 1, "unit": None}],
        ["Mock pecan pie: no actual pecans, just pinto beans and sugar."],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_synthetic_tier_c_bare_oil_dough_batter_sauce_gravy_never_gate() -> None:
    recipe = _recipe(
        "syn19",
        "Synthetic",
        [{"name": "water", "amount": 1, "unit": None}],
        [
            "Heat the oil in a pan.",
            "Pour the batter into the pan.",
            "Knead the dough for 5 minutes.",
            "Add the sauce and simmer.",
            "Top with gravy before serving.",
        ],
    )
    all_mismatches = find_instructions_ingredient_mismatches(recipe)
    assert tier_ab_mismatches(all_mismatches) == []
    c_categories = _categories(tier_c_mismatches(all_mismatches))
    assert c_categories == {"oil", "batter", "dough", "sauce", "gravy"}


def test_synthetic_dual_category_soy_sauce_fires_both_wheat_and_soy() -> None:
    recipe = _recipe(
        "syn20",
        "Synthetic",
        [{"name": "chicken", "amount": 1, "unit": None}],
        ["Marinate in soy sauce overnight."],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert categories == {"wheat_gluten", "soy"}


def test_synthetic_negation_is_occurrence_local_across_steps() -> None:
    # A negated mention in one step must not suppress an UNnegated mention
    # of the same term in a different step.
    recipe = _recipe(
        "syn21",
        "Synthetic",
        [{"name": "flour", "amount": 1, "unit": None}],
        ["Variation: omit almonds if allergic.", "Add lemon zest and almonds."],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert "tree_nut" in categories


# --- Structural tests --------------------------------------------------


def test_meat_terms_are_superset_of_meat_alias_flesh_words() -> None:
    # constraint_engine.MEAT_ALIASES also carries non-flesh hazard words
    # (different classes, per that module's own inline comments): gelatin
    # and worcestershire are independently fish-side allergens; marshmallow,
    # suet, and lard are animal-derived but not flesh words. Excluding
    # exactly these five and nothing else must leave a set this module's
    # MEAT_FLESH_TERMS fully contains -- if constraint_engine.MEAT_ALIASES
    # ever gains a new flesh word without a matching addition here, this
    # test fails loudly instead of the two vocabularies silently drifting.
    non_flesh_exclusions = {"gelatin", "worcestershire", "marshmallow", "suet", "lard"}
    flesh_subset = constraint_engine.MEAT_ALIASES - non_flesh_exclusions
    assert flesh_subset <= MEAT_FLESH_TERMS


def test_module_imports_no_llm_or_provider_modules() -> None:
    """Mirrors tests/test_safety_judge_import_ban.py's AST-based approach:
    this module must be pure deterministic regex, never an LLM/provider
    call, so the "LLM never enforces allergies" invariant is executable,
    not just documented."""
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "corpus_import"
        / "instructions_ingredient_integrity.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)

    banned_substrings = ("openai", "anthropic", "langchain", "llm", "provider")
    offenders = [
        name
        for name in imported_names
        if any(banned in name.lower() for banned in banned_substrings)
    ]
    assert offenders == [], f"unexpected LLM/provider-shaped import(s): {offenders}"
    # Sanity: the module does import something real (pydantic-backed
    # Recipe schema, stdlib re/dataclasses/datetime), so this isn't a
    # vacuous pass on an empty import list.
    assert imported_names


def test_module_has_no_file_io_and_never_references_sample_recipes() -> None:
    """The check operates purely on an in-memory `Recipe` object passed in
    by the caller -- it is structurally incapable of reading
    sample_recipes.jsonl (or any file), which is what actually protects the
    curated seeds, not any pass/fail behavior of the check itself."""
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "services"
        / "corpus_import"
        / "instructions_ingredient_integrity.py"
    )
    source = module_path.read_text(encoding="utf-8")
    assert "sample_recipes" not in source
    for io_primitive in ("open(", ".read_text(", "Path(", "import json"):
        assert io_primitive not in source, f"unexpected file I/O primitive {io_primitive!r} found"


def test_idempotency_reflagging_a_clean_recipe_yields_zero() -> None:
    """A recipe that has already survived (or been quarantined and
    conceptually repaired) with no remaining safety-relevant mismatch must
    yield zero mismatches on any subsequent run -- re-running this check
    against a cleaned corpus produces no new flags."""
    recipe = _recipe(
        "clean1",
        "Clean Recipe",
        [
            {"name": "chicken breast", "amount": 1, "unit": None},
            {"name": "flour", "amount": 1, "unit": None},
            {"name": "butter", "amount": 1, "unit": None},
        ],
        ["Cook the chicken.", "Coat in flour.", "Fry in butter."],
    )
    first_run = find_instructions_ingredient_mismatches(recipe)
    second_run = find_instructions_ingredient_mismatches(recipe)
    assert first_run == [] == second_run


def test_quarantine_record_shape() -> None:
    recipe = _recipe(
        "shape1",
        "Shape Test",
        [{"name": "onion", "amount": 1, "unit": None}],
        ["Add the peanut oil and steak and fry until browned."],
    )
    mismatches = find_instructions_ingredient_mismatches(recipe)
    assert mismatches  # sanity: this recipe should indeed be flagged (meat)

    record = build_quarantine_record(recipe, mismatches)
    assert record["recipe"]["recipe_id"] == "shape1"
    assert record["quarantine_reason"]["check"] == "instructions_ingredient_integrity"
    assert "quarantined_at_utc" in record
    for entry in record["quarantine_reason"]["mismatches"]:
        assert entry["category"]
        assert entry["tier"] in ("A", "B")
        assert entry["matched_terms"]
        assert entry["evidence"]
        for ev in entry["evidence"]:
            assert "term" in ev and "quoted_step" in ev


def test_build_quarantine_record_never_includes_tier_c_only_findings() -> None:
    # A recipe with ONLY a Tier C finding (bare "oil") must produce a
    # quarantine record with an EMPTY mismatches list -- Tier C never gates.
    recipe = _recipe(
        "tierc1",
        "Tier C Only",
        [{"name": "water", "amount": 1, "unit": None}],
        ["Heat the oil in a pan."],
    )
    mismatches = find_instructions_ingredient_mismatches(recipe)
    assert {m.category for m in mismatches} == {"oil"}
    record = build_quarantine_record(recipe, mismatches)
    assert record["quarantine_reason"]["mismatches"] == []
