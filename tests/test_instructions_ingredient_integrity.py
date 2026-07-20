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
    # Deliberately NOT step-initial "Serve" (revision round 2, ruling item
    # 4, added a whole-step suppression for `^\s*serve\b` -- this step is
    # rephrased to "Top the soup..." so the fixture keeps testing the
    # exact-phrase suppression it was written for, rather than colliding
    # with the new unrelated serve-initial rule).
    recipe = _recipe(
        "syn15",
        "Synthetic",
        [{"name": "soup", "amount": 1, "unit": None}],
        ["Top the soup with oyster crackers."],
    )
    all_mismatches = find_instructions_ingredient_mismatches(recipe)
    # "Top the soup with..." contains no serving-cue phrase ("serve with"/
    # "serve over"/...) and does not begin with "serve", so the step is not
    # suppressed by either whole-step rule; "oyster" is suppressed by the
    # exact-phrase rule; "cracker" fires wheat_gluten with no satisfier.
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


# --- Revision round 1 fixtures (2026-07-18 advisor ruling on the 220709Z
# HALT report, docs/instructions_integrity_spec.md) -- verbatim from
# data/processed/imported_recipes.jsonl. -------------------------------


def test_imp_a7eb6f7b7e885e67_raised_waffles_variation_prefix_suppressed() -> None:
    recipe = _recipe(
        "imp_a7eb6f7b7e885e67",
        "Raised Waffles",
        [
            {"name": "water", "amount": 0.75, "unit": None},
            {"name": "active dry yeast", "amount": 1.5, "unit": None},
            {"name": "granulated sugar", "amount": 1.25, "unit": None},
            {"name": "water", "amount": 2.5, "unit": None},
            {"name": "butter", "amount": 1.25, "unit": None},
            {"name": "salt", "amount": 0.75, "unit": None},
            {"name": "flour", "amount": 1.25, "unit": None},
            {"name": "eggs", "amount": 3.0, "unit": None},
            {"name": "baking soda", "amount": 3.0, "unit": None},
            {"name": "pure maple syrup", "amount": 0.5, "unit": None},
        ],
        [
            "* Flour may be any of or any combination of white, whole wheat, rye, oat, buckwheat, "
            "yellow cornmeal, or blue cornmeal.",
            "Put the 3/4 cup water into a large bowl and  sprinkle in the yeast and sugar.  Let "
            "dissolve for  5 minutes.",
            "Add the 2 1/2 cups water, the milk, butter, salt,  and flour(s) to the yeast mixture "
            "and whisk until smooth and blended.",
            "Cover the  bowl with plastic wrap and let stand overnight at room  temperature. (The  "
            "batter will rise to double its  original volume.)  Before baking the waffles,  beat "
            "in the eggs, then add the baking soda and stir until well combined.",
            "(The  batter will be thin.)  Pour 1/2 to 3/4 cup batter into a very hot waffle iron "
            "and  bake until golden and crisp.  Serve immediately with the warm syrup.",
            "Variation:  Top with fresh strawberries and whipped cream or sliced bananas, toasted "
            "coconut, and sliced roasted almonds.  Dust with confectioner's  sugar.",
        ],
        allergens=["dairy", "egg", "eggs", "gluten", "milk", "wheat"],
    )
    # The "Variation:" step-prefix suppresses the whole step, so the
    # otherwise-unlisted "roasted almonds" never contributes a tree_nut flag.
    assert tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)) == []


def test_imp_0d20dbf56b3b55fa_cantaloupe_melba_menu_featuring_suppressed() -> None:
    recipe = _recipe(
        "imp_0d20dbf56b3b55fa",
        "Cantaloupe Melba",
        [
            {"name": "fresh raspberries", "amount": 2.0, "unit": None},
            {"name": "sugar", "amount": 0.3333333333333333, "unit": None},
            {"name": "cantaloupe", "amount": 2.0, "unit": None},
        ],
        [
            "In a blender or food processor, whirl raspberries until pureed.",
            "Pour through a sieve to remove seeds.",
            "Stir sugar and liqueur (if used) into puree and mix well; cover and chill.",
            "Halve cantaloupes and remove seeds; peel and cut into thin slices.",
            "Line each of 8 small dessert bowls or goblets with 3 or 4 melon slices.",
            "Top melon with a scoop of sherbet and pour 2 tablespoons chilled raspberry sauce "
            "over sherbet.",
            "Raspberry sherbet in goblets lined with sliced cantaloupe and topped with Melba "
            "sauce would make a memorable finale for a menu featuring an egg and cheese dish.",
        ],
        allergens=[],
    )
    # "menu featuring" suppresses the whole step, so the egg/cheese mention
    # about a DIFFERENT dish never contributes egg/dairy flags.
    assert tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)) == []


def test_imp_941617b6247054aa_sweetened_soy_sauce_same_quantities_as_suppressed() -> None:
    recipe = _recipe(
        "imp_941617b6247054aa",
        "Sweetened Soy Sauce",
        [
            {"name": "soy sauce", "amount": 1.0, "unit": None},
            {"name": "sugar", "amount": 0.6666666666666666, "unit": None},
            {"name": "sake", "amount": 0.5, "unit": None},
            {"name": "sherry wine", "amount": 1.0, "unit": None},
            {"name": "onions", "amount": 1.0, "unit": None},
            {"name": "round onion", "amount": 15.0, "unit": None},
            {"name": "ginger", "amount": 15.0, "unit": None},
            {"name": "cinnamon sticks", "amount": None, "unit": None},
            {"name": "star anise", "amount": None, "unit": None},
        ],
        [
            "Put all ingredients in pan, bring to boil, and simmer over low heat for approximately "
            "one hour, until liquid has reduced to about 2/3.",
            "Strain, cool, and store in fridge for up to one month.",
            "Use in same quantities as Oyster Sauce.",
        ],
        allergens=["soy", "soya"],
    )
    # "same quantities as" suppresses the whole step, so "Oyster" (a
    # cross-referenced DIFFERENT sauce, not this recipe's own content) never
    # contributes a mollusk flag.
    assert tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)) == []


def test_imp_28766bd14c6c5a24_onion_dip_as_desired_suppressed() -> None:
    recipe = _recipe(
        "imp_28766bd14c6c5a24",
        "Onion Dip, Low Cal",
        [
            {"name": "cottage cheese", "amount": 1.0, "unit": None},
            {"name": "lemon juice", "amount": 1.0, "unit": None},
            {"name": "plain yogurt", "amount": 0.5, "unit": None},
            {"name": "green onion", "amount": 0.25, "unit": None},
            {"name": "salt", "amount": 1.0, "unit": None},
            {"name": "pepper", "amount": 1.0, "unit": None},
        ],
        [
            "Base dip.",
            "Add onion soup mix, parsley, basil, artichoke, dill, shrimp, crab, or curry as desired.",
            "In blender, process cottage cheese with lemon juice until blended.",
            "Add other ingredients.",
            "Process just until mixed.",
            "Refrigerate four hours, or overnight.",
        ],
        allergens=[],
    )
    # "as desired" suppresses the whole step, so the optional shrimp/crab
    # add-in never contributes a crustacean flag.
    assert tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)) == []


def test_imp_a52ae950e8dd5eb5_sauerbraten_roast_satisfies_meat() -> None:
    recipe = _recipe(
        "imp_a52ae950e8dd5eb5",
        "Sauerbraten & Ginger",
        [
            {"name": "rump roast", "amount": 4.0, "unit": None},
            {"name": "onions", "amount": 2.0, "unit": None},
            {"name": "peppercorns", "amount": 8.0, "unit": None},
            {"name": "4 cloves", "amount": 4.0, "unit": "clove"},
            {"name": "bay leaf", "amount": 1.0, "unit": None},
            {"name": "white vinegar", "amount": 1.0, "unit": None},
            {"name": "water", "amount": 1.0, "unit": None},
            {"name": "cider vinegar", "amount": 0.5, "unit": None},
            {"name": "salt", "amount": 0.25, "unit": None},
            {"name": "water", "amount": 0.5, "unit": None},
            {"name": "sour cream", "amount": 2.0, "unit": None},
            {"name": "unbleached flour", "amount": 10.0, "unit": None},
        ],
        [
            "Place the beef roast in a deep ceramic or glass bowl.",
            "Add onions, peppercorns, cloves, and bay leaf.",
            "Pour white vinegar and cider vinegar over the meat; chill, covered, for 4 days.",
            "Turn meat twice each day.",
            "Remove the meat from the marinade, dry it well with paper towels, and strain the "
            "marinade into a bowl.",
            "Reserve onions and 1 cup marinade.",
            "In a Dutch oven brown the meat on all sides in hot vegetable oil.",
            "Sprinkle meat with salt.",
            "Pour boiling water around the meat. sprinkle in crushed gingersnaps, and simmer "
            "covered for 1 1/2 hours.",
            "Turn often.",
            "Add 1 cup of reserved marinade and cook meat 2 hours or more, until tender.",
            "Remove the meat and keep it warm.",
            "Strain the cooking juices into a large saucepan.",
            "In a small bowl mix sour cream with flour.",
            "Stir it into the cooking juices and cook, stirring, until sauce is thickened and smooth.",
            "Slice meat in 1/4 inch slices; add to hot gravy.",
            "Arrange meat on a heated plater and pour extra sauce over it.",
        ],
        allergens=[],
    )
    # "rump roast" satisfies the "beef" mention via the new "roast" satisfier.
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "meat" not in categories


def test_imp_2391b489ec6459e3_haddock_chowder_water_plus_fish_satisfies_stock() -> None:
    recipe = _recipe(
        "imp_2391b489ec6459e3",
        "Down East Haddock Chowder",
        [
            {"name": "haddock fillets", "amount": 1.0, "unit": None},
            {"name": "water", "amount": 4.0, "unit": None},
            {"name": "salt", "amount": 1.0, "unit": None},
            {"name": "potatoes", "amount": 3.0, "unit": None},
            {"name": "onion", "amount": 1.0, "unit": None},
            {"name": "celery", "amount": 1.0, "unit": None},
            {"name": "pepper", "amount": 1.0, "unit": None},
            {"name": "evaporated milk", "amount": 1.0, "unit": None},
            {"name": "butter", "amount": 2.0, "unit": None},
        ],
        [
            "Place fish, water and salt in large saucepan.",
            "Bring to boil, reduce heat and  simmer gently, uncovered, for 8 to 10 minutes.",
            "Fish is done when flesh is  opaque. Remove immediately and when cool enough to "
            "handle, break into  bite-size pieces.",
            "Reserve until rest of soup is ready.",
            "Skim  any foam off fish stock.",
            "Add potatoes, onion, celery and pepper; cover  and bring to boil.",
            "Reduce heat and simmer until tender.",
            "Return fish to pan.",
            "Pour in milk and heat through without boiling.",
            "Taste and adjust seasoning.",
            "Swirl in butter.",
            "Transfer to heated tureen or soup bowls and serve  immediately.",
        ],
        allergens=["dairy", "milk"],
    )
    # water row + haddock (a FISH_TERMS row) satisfies the Tier B stock
    # composite -- the "fish stock" mention is no longer treated as hidden.
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "stock" not in categories


def test_imp_54fefa2b200d50a7_pancit_water_plus_pork_shrimp_satisfies_stock() -> None:
    recipe = _recipe(
        "imp_54fefa2b200d50a7",
        "Pancit",
        [
            {"name": "onion", "amount": 1.0, "unit": None},
            {"name": "garlic", "amount": 4.0, "unit": None},
            {"name": "shrimp", "amount": 1.0, "unit": None},
            {"name": "pork", "amount": 1.0, "unit": None},
            {"name": "cabbage", "amount": 1.0, "unit": None},
            {"name": "carrots", "amount": 2.0, "unit": None},
            {"name": "soy sauce", "amount": 4.0, "unit": None},
            {"name": "water", "amount": 1.0, "unit": None},
            {"name": "lemon wedge", "amount": 1.0, "unit": None},
        ],
        [
            "Using a large skillet, lightly saute in a small amount of oil, the onions and garlic.",
            "Add the pork and shrimp.",
            "Add cabbage, carrots, soy sauce and 1 cup water.",
            "Turn heat to medium and simmer for 5 minutes.",
            "Stir and simmer until carrots are cooked.",
            "Place noodles on top of mixture and spoon vegetables and broth over the noodles.",
            "You might have to add a little more water if the noodles have not wilted.",
            "Cover and allow to steam for about 2 minutes.",
            "Turn out on a platter and garnish with lemon wedges.",
            "The recipe can be varied with chicken leftovers,",
            "bean sprouts or green onions.",
            "Squeeze the lemon wedges over Pancit before eating.",
        ],
        allergens=["crustacean", "seafood", "shellfish", "soy", "soya"],
    )
    # water row + pork/shrimp (MEAT_FLESH_TERMS/CRUSTACEAN_TERMS rows)
    # satisfies the Tier B stock composite -- the "broth" mention is no
    # longer treated as hidden.
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "stock" not in categories


def test_imp_787ec005979550d2_fra_diavolo_mollusk_row_satisfies_stock_but_may_flag_others() -> None:
    recipe = _recipe(
        "imp_787ec005979550d2",
        "Mussels Fra Diavolo",
        [
            {"name": "mussels", "amount": 2.0, "unit": None},
            {"name": "onion", "amount": 2.0, "unit": None},
            {"name": "green pepper", "amount": 1.0, "unit": None},
            {"name": "garlic", "amount": 1.0, "unit": None},
            {"name": "tomatoes", "amount": 1.0, "unit": None},
            {"name": "dry white wine", "amount": 1.0, "unit": None},
            {"name": "tomato paste", "amount": 1.0, "unit": None},
            {"name": "parsley", "amount": 0.3333333333333333, "unit": None},
            {"name": "salt", "amount": 3.0, "unit": None},
            {"name": "-3 sugar", "amount": 2.0, "unit": None},
            {"name": "red pepper flakes", "amount": 1.5, "unit": None},
            {"name": "basil", "amount": 1.0, "unit": None},
            {"name": "- 1 oregano", "amount": 0.5, "unit": None},
            {"name": "linguine", "amount": 0.5, "unit": None},
        ],
        [
            "Scrub the mussels under running cold water making sure they are closed tight and "
            "remove the beards.",
            'In a large pot over high heat bring to a boil about 1" of water.',
            "Reduce the heat to low and add the mussels-cover and cook until the shells open "
            "about 5 minutes.",
            "Discard any that do not open.",
            "Discard the top shell from each mussel; rinse the mussel in the broth left in the "
            "pot to remove any left over s and.",
            "Let broth stand awhile to let the sand settle in the bottom of the pot. Pour 3/4 "
            "cup of the broth into a measuring cup and discard any remaining broth being careful "
            "not to pour any sand into the cup.",
            "In a large skillet over med.",
            "heat, heat the oil and Saute onions, green pepper and garlic until tender but not "
            "brown.",
            'Prepare the pasta as directed on the package. Cut the fish into 1" chunks.',
            "Into the onion mixture, add toma toes with the liquid from the can, all remaining "
            "ingredients, except mussels- the fish and mussel broth.",
            "(If you are adding more seafood add it now). Turn the heat to high and bring to a "
            "boil-when this comes to a boil, reduce heat to low-cover and simmer 5-7 minutes or "
            "until fish is cooked through.",
            "Add the mussels on the half shell and heated through.",
            "To serve, put the pasta onto plates or a large platter, spoon the fish/mussel "
            "mixture over and top with fresh grated Parmesan cheese.",
        ],
        allergens=["gluten", "seafood", "shellfish", "wheat"],
    )
    # The mussels row (a mollusk term) satisfies the Tier B stock composite's
    # arm 1 -- "stock" must be ABSENT from the flagged categories. This is
    # deliberately an category-absence assertion, NOT an empty-result
    # assertion: the recipe may still flag OTHER categories (e.g. dairy, via
    # "Parmesan cheese" with no dairy ingredient row) that this ruling does
    # not touch.
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "stock" not in categories


def test_imp_f26d5c5093e25ac7_nasi_goreng_flags_exactly_egg() -> None:
    recipe = _recipe(
        "imp_f26d5c5093e25ac7",
        "Amazing Nasi Goreng",
        [
            {"name": "long grain rice", "amount": 1.25, "unit": None},
            {"name": "smoked bacon", "amount": 3.0, "unit": None},
            {"name": "chicken", "amount": 6.0, "unit": None},
            {"name": "onion", "amount": 1.5, "unit": None},
            {"name": "garlic cloves", "amount": 1.0, "unit": None},
            {"name": "carrot", "amount": 2.0, "unit": None},
            {"name": "cabbage", "amount": 1.0, "unit": None},
            {"name": "water", "amount": 2.0, "unit": None},
            {"name": "leek", "amount": 4.0, "unit": None},
            {"name": "trassi oedang", "amount": 1.0, "unit": None},
            {"name": "ketjap manis", "amount": 1.0, "unit": None},
            {"name": "cumin", "amount": 1.0, "unit": None},
            {"name": "curcumae", "amount": 0.25, "unit": None},
            {"name": "sambal oelek", "amount": 0.25, "unit": None},
            {"name": "salt", "amount": 0.25, "unit": None},
        ],
        [
            "Boil the rice according to the instructions on the package. Make sure that  the "
            "rice is fluffy.",
            "In a wok or large skillet, heat the vegetable oil and fry the smoked bacon and pork "
            "or chicken until done.",
            "Add the onion and garlic.",
            "Turn the heat to medium and simmer for about 5 minutes.",
            "Meanwhile, in a separate large saucepan, bring the carrot and cabbage to a  boil in "
            "about 4 cups of water. Boil for 3 minutes; drain.",
            "Add the leek and trassi oedang to the meat mixture; simmer for 3 minutes.",
            "Add the cooked cabbage and carrot mixture.",
            "Keep the entire mixture on low heat and stir in the beaten eggs until they are well "
            "incorporated.",
            "Add the ketjap manis, cumin, curcumae, coriander, and sambal oelek if  using.",
            "Stir well and add the fluffy white rice.",
            "Mix well and serve warm.",
            "Serving Ideas:",
            "May serve with sate (peanut sauce) on the side.",
            "NOTES : Trassi is a shrimp paste found in Asian grocery stores. If you do  not have "
            "any, you can either use peeled shrimp mixed in with the other  meat, or leave it "
            "out all together.",
        ],
        allergens=[],
    )
    # meat: satisfied (smoked bacon/chicken rows). crustacean: the "NOTES :"
    # step is suppressed AND "trassi" is now a crustacean satisfier
    # (trassi oedang row). peanut: "May serve with..." is a serving-cue
    # step. egg: unsatisfied (no egg ingredient row, no egg allergen) --
    # the ONE residual genuine flag.
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert categories == {"egg"}


def test_imp_b3f19d74632257ba_trifle_flags_tree_nut_not_soy_or_dairy() -> None:
    recipe = _recipe(
        "imp_b3f19d74632257ba",
        "Trifle",
        [
            {"name": "egg white substitute", "amount": 3.0, "unit": None},
            {"name": "granulated sugar", "amount": 0.5, "unit": None},
            {"name": "soymilk", "amount": 0.25, "unit": None},
            {"name": "lemon juice", "amount": 2.0, "unit": None},
            {"name": "whole wheat pastry flour", "amount": 1.0, "unit": None},
            {"name": "baking powder", "amount": 1.0, "unit": None},
            {"name": "salt", "amount": 0.25, "unit": None},
            {"name": "cornstarch", "amount": 0.3333333333333333, "unit": None},
            {"name": "granulated sugar", "amount": 0.5, "unit": None},
            {"name": "soymilk", "amount": 2.0, "unit": None},
            {"name": "vanilla extract", "amount": 2.0, "unit": None},
            {"name": "lemon juice", "amount": 2.0, "unit": None},
            {"name": "sweet sherry", "amount": 0.3333333333333333, "unit": None},
            {"name": "port wine", "amount": 1.0, "unit": None},
            {"name": "pear", "amount": 0.25, "unit": None},
        ],
        [
            "Preheat the oven to 350 degrees.",
            "Beat the egg white substitutes until stiff  with an electric mixer.",
            "Fold in the sugar, milk, and lemon juice and beat again.",
            "Combine the flour, baking powder, and salt in a small mixing bowl.",
            "Sprinkle into  the egg white mixture, a bit at a time, beating in each time with "
            "the mixer  until velvety smooth.",
            "Pour into a lightly oiled, 9- by 13-inch baking pan.",
            "Bake  for 25 minutes, or until the top is golden and a knife inserted into the "
            "center  tests clean.",
            "This cake may be made well ahead of time; let it cool completely,  then store in "
            "an airtight container or proceed with the remaining steps.",
            "For  the custard, combine the cornstarch and sugar in a heavy saucepan.",
            "Pour in  enough soy milk to dissolve them.",
            "Whisk in the remaining milk.",
            "Place over  moderate heat and bring to a simmer, whisking almost continuously, so "
            "that the  cornstarch does not lump on the bottom.",
            "Let the mixture simmer gently, whisking  frequently, until thick.",
            "Remove from the heat. Stir in the vanilla and lemon  juice. Let the custard cool to "
            "room temperature.  Before assembling the trifle, cut the cake base into 4 to 6 "
            "sections, then  carefully split the sections in half through the center so that "
            "they are half  the thickness.",
            "Spread the bottom halves with the raspberry preserves , then  cover with the tops.",
            "Cut the sandwiched cake into approximately 1- by 2-inch  fingers.",
            "Assemble the trifle in a trifle dish or a IO-inch round, preferably  clear-glass "
            "casserole dish at least 3 to 4 inches deep: half the cake fingers,  sprinkled with "
            "half of the sherry or port, half of the custard, the pear s  lices, the remaining "
            "cake fingers, the remaining sherry or port, the remaining  custard.",
            "Sprinkle the top with the sliced almonds and decorate with small dots  of raspberry "
            "jam, either in an irregular or regular pattern.",
            "Chill thoroughly  before serving.",
        ],
        allergens=[],
    )
    # "soy milk"/"milk" mentions are satisfied by the "soymilk" ingredient
    # rows (new satisfier-only extras); "almonds" (sliced almonds, no
    # almond/nut ingredient row) is the residual genuine tree_nut flag.
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "tree_nut" in categories
    assert "soy" not in categories
    assert "dairy" not in categories


def test_imp_6f3463afcc2f5d51_sparerib_trigger_now_flags_meat_after_worcestershire_satisfier_removed() -> None:
    # Round 1 discovered a CONFLICT here (recorded then, resolved now):
    # ruling item 6 ("must-flag: imp_6f3463afcc2f5d51 Pork Spareribs ->
    # meat") was satisfied at the TRIGGER level in round 1 -- "sparerib" was
    # already firing the meat category from "Trim spareribs..." -- but this
    # exact recipe's own "Worcestershire sauce" ingredient row was ALSO
    # satisfying the "meat" category via the then-existing satisfier design
    # (meat's satisfiers included the whole of FISH_TERMS, which contains
    # "worcestershire"). That pre-existing leniency defeated the miss fix
    # for THIS specific recipe.
    #
    # Round 2 (2026-07-18 ruling item 12) removes "worcestershire"/
    # "puttanesca" from meat's satisfiers specifically -- see the module's
    # own inline comment on `CATEGORIES["meat"]["satisfiers"]` for the
    # honest counter-argument (constraint_engine.MEAT_ALIASES already
    # treats "worcestershire" as its own condiment hazard, so this recipe
    # is ALREADY blocked at serve time regardless; the quarantine value
    # here is the untrustworthy row set, independent of that redundancy).
    # This test now asserts the FLIPPED, correctly-fixed behavior: the
    # recipe flags meat.
    recipe = _recipe(
        "imp_6f3463afcc2f5d51",
        "Pork Spareribs in Tangy Sauce",
        [
            {"name": "tomato sauce", "amount": 1.0, "unit": None},
            {"name": "water", "amount": 1.0, "unit": None},
            {"name": "brown sugar", "amount": 1.0, "unit": None},
            {"name": "Worcestershire sauce", "amount": 2.0, "unit": None},
            {"name": "garlic", "amount": 2.0, "unit": None},
            {"name": "vinegar", "amount": 1.0, "unit": None},
            {"name": "lemon juice", "amount": 1.0, "unit": None},
            {"name": "paprika", "amount": 3.0, "unit": None},
            {"name": "ginger", "amount": 1.0, "unit": None},
            {"name": "soy sauce", "amount": 1.0, "unit": None},
        ],
        [
            "Trim spareribs of rind and excess fat, place ribs in a shallow dish.",
            "Cook on HIGH 14 minutes, turning halfway through cooking time.  Drain fat from "
            "dish carefully.",
            "Mix the remaining ingredients together and pour over the ribs; cook on HIGH 3 "
            "minutes or until hot. Cheers,  Doreen Doreen Randal,  Wanganui.",
            "New Zealand.",
        ],
        allergens=["fish", "seafood", "soy", "soya"],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert "meat" in categories
    meat_mismatch = next(m for m in mismatches if m.category == "meat")
    assert "sparerib" in meat_mismatch.matched_terms


def test_synthetic_sparerib_trigger_flags_meat_without_a_fish_term_satisfier_present() -> None:
    # Isolates ruling item 6's actual, verifiable effect from the
    # imp_6f3463afcc2f5d51 conflict above: with NO Worcestershire/fish-term
    # ingredient row present, "spareribs" alone now correctly triggers and
    # flags the meat category (it did not before this revision, since bare
    # "rib"/"ribs" was deliberately never added to the vocabulary).
    recipe = _recipe(
        "syn22",
        "Synthetic",
        [
            {"name": "tomato sauce", "amount": 1.0, "unit": None},
            {"name": "brown sugar", "amount": 1.0, "unit": None},
            {"name": "vinegar", "amount": 1.0, "unit": None},
        ],
        ["Trim spareribs of rind and excess fat, place ribs in a shallow dish."],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert "meat" in categories
    meat_mismatch = next(m for m in mismatches if m.category == "meat")
    assert "sparerib" in meat_mismatch.matched_terms


def test_imp_712db6319e3957c7_apricot_basting_sauce_accepted_residual_fp_flags_meat() -> None:
    # Accepted residual FP (revision round 2, ruling item 12 -- pinned here
    # so it shows up as an intentional, documented diff rather than a
    # silent surprise): removing "worcestershire" from meat's satisfiers
    # means this sauce recipe's own "Use sauce over chicken, pork, and
    # lamb." step now flags meat, even though the sauce ITSELF plausibly
    # contains no meat (it is a basting sauce FOR meat, not a claim the
    # sauce contains it). Deliberately NOT patched with a `^use` rule per
    # the ruling -- recorded as an accepted residual in the audit report
    # instead.
    recipe = _recipe(
        "imp_712db6319e3957c7",
        "Apricot Basting Sauce",
        [
            {"name": "sugar", "amount": 1.0, "unit": None},
            {"name": "salt", "amount": 1.0, "unit": None},
            {"name": "dry white wine", "amount": 1.0, "unit": None},
            {"name": "honey", "amount": 1.0, "unit": None},
            {"name": "Worcestershire sauce", "amount": 1.0, "unit": None},
        ],
        [
            "Mix together sugar, apricot jam, salt, apricots, wine, honey and Worcestershire "
            "sauce in a saucepan.",
            "Heat over medium heat until jam has been melted.",
            "Use sauce over chicken, pork, and lamb.",
        ],
        allergens=["fish", "seafood"],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "meat" in categories


# --- Revision round 2 fixtures (2026-07-18 advisor ruling on the 231309Z
# HALT report, docs/instructions_integrity_spec.md) -- verbatim from
# data/processed/imported_recipes.jsonl. -------------------------------


def test_imp_2380cadece955cc7_alfredo_with_pasta_mid_step_variation_suppressed() -> None:
    # Ruling item 1: the commentary-prefix marker is now recognized ANYWHERE
    # in a step, not just step-initial -- "Variation:" here is the step's
    # SECOND sentence.
    recipe = _recipe(
        "imp_2380cadece955cc7",
        "Alfredo Sauce with Pasta",
        [
            {"name": "butter", "amount": 1.0, "unit": None},
            {"name": "margarine", "amount": 1.0, "unit": None},
            {"name": "heavy cream", "amount": 1.0, "unit": None},
            {"name": "parmesan cheese", "amount": 1.0, "unit": None},
            {"name": "salt", "amount": 1.0, "unit": None},
            {"name": "pepper", "amount": 1.0, "unit": None},
            {"name": "fettuccine", "amount": 1.0, "unit": None},
        ],
        [
            "Cook noodles or fettuccine according to package directions.",
            "Heat butter and  cream in saucepan until butter is melted.",
            "Remove from heat. Add 1 cup Parmesan  cheese, salt and pepper; stir until sauce "
            "is blended and fairly smooth.",
            "Add to  drained noodles and toss until they are well coated.",
            "Sprinkle  with remaining  cheese. Variation: Add cooked shrimp, crab or mushrooms.",
        ],
        allergens=["dairy", "gluten", "milk", "wheat"],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "crustacean" not in categories


def test_synthetic_mid_step_note_marker_still_flags_before_the_marker() -> None:
    recipe = _recipe(
        "syn23",
        "Synthetic",
        [{"name": "flour", "amount": 1, "unit": None}],
        ["Stir in walnuts. Note: keeps 3 days."],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert "tree_nut" in categories
    tree_nut = next(m for m in mismatches if m.category == "tree_nut")
    # TREE_NUT_TERMS registers both "walnut" and "walnuts" as separate
    # trigger entries; longest-phrase-first consumption picks the plural
    # entry for this text, so the recorded matched term is "walnuts".
    assert "walnuts" in tree_nut.matched_terms


def test_imp_3233766015ca524d_buttermilk_cornbread_can_add_suppressed_meat() -> None:
    recipe = _recipe(
        "imp_3233766015ca524d",
        "Buttermilk Jalapeno Cornbread",
        [
            {"name": "all-purpose flour", "amount": 1.0, "unit": None},
            {"name": "yellow cornmeal", "amount": 1.0, "unit": None},
            {"name": "sugar", "amount": 1.0, "unit": None},
            {"name": "baking powder", "amount": 1.0, "unit": None},
            {"name": "salt", "amount": 1.0, "unit": None},
            {"name": "eggs", "amount": 1.0, "unit": None},
            {"name": "milk", "amount": 1.0, "unit": None},
            {"name": "buttermilk", "amount": 1.0, "unit": None},
            {"name": "shortening", "amount": 1.0, "unit": None},
        ],
        [
            "Sift together flour, cornmeal, sugar, baking powder and salt.",
            "Add eggs, milk and oil or melted shortening. Beat until just smooth-do not overbeat.",
            "Turn into a greased 9x9x2 inch baking pan. Bake in a 425: oven for 20-25 minutes.",
            "Can add drained corn, bacon,  finely chopped jalapeno peppers etc. for a "
            "different taste.",
        ],
        allergens=["dairy", "egg", "eggs", "milk"],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "meat" not in categories


def test_imp_8c7176ba96a35dce_chewy_chocolate_cookies_still_flags_peanut() -> None:
    # Confirms "can add"/"can be added" is narrowly scoped -- this recipe's
    # own unrelated "Stir in peanut butter or chocolate chips" step must
    # still flag peanut.
    recipe = _recipe(
        "imp_8c7176ba96a35dce",
        "Chewy Chocolate Cookies",
        [
            {"name": "butter", "amount": 1.0, "unit": None},
            {"name": "margarine", "amount": 1.0, "unit": None},
            {"name": "sugar", "amount": 1.0, "unit": None},
            {"name": "eggs", "amount": 1.0, "unit": None},
            {"name": "vanilla extract", "amount": 1.0, "unit": None},
            {"name": "all-purpose flour", "amount": 1.0, "unit": None},
            {"name": "baking soda", "amount": 1.0, "unit": None},
            {"name": "salt", "amount": 1.0, "unit": None},
        ],
        [
            "Heat oven to 350.",
            "In large mixer bowl; cream butter and sugar until light and fluffy.",
            "Add eggs and vanilla; beat well.",
            "Combine flour, cocoa, baking soda and salt; gradually blend into creamed mixture. "
            "Stir in peanut butter or chocolate chips.",
            "Drop by teaspoonfuls onto ungreased cookie sheet. Bake 8-9 minutes. (Do not "
            "overbake; cookies will be soft. They will puff while baking and flatten while "
            "cooling.).",
            "Cool slightly; remove from cookie sheet onto wire rack. Cool completely.",
        ],
        allergens=["dairy", "egg", "eggs", "milk"],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "peanut" in categories


def test_imp_9b2c1d45a9f55ef1_alfredo_sauce_if_serving_suppressed() -> None:
    recipe = _recipe(
        "imp_9b2c1d45a9f55ef1",
        "Alfredo Sauce",
        [
            {"name": "sweet butter", "amount": 1.0, "unit": None},
            {"name": "heavy cream", "amount": 1.0, "unit": None},
            {"name": "parmesan cheese", "amount": 1.0, "unit": None},
            {"name": "salt", "amount": 1.0, "unit": None},
            {"name": "pepper", "amount": 1.0, "unit": None},
        ],
        [
            "Place butter in microwave safe pot and heat on high for 30 seconds or until melted.",
            "Add cream and warm on high for approximately 1 minute.",
            "Add Parmesan cheese and warm until cheese melts.",
            "Add salt and pepper to taste. (If serving with shrimp, you might not need much "
            "salt.).",
        ],
        allergens=["dairy", "milk"],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_imp_748b6422ecbb5c7d_polish_sausage_serve_initial_suppressed() -> None:
    recipe = _recipe(
        "imp_748b6422ecbb5c7d",
        "Polish Sausage and Peppers",
        [
            {"name": "Polish sausage", "amount": 1.0, "unit": None},
            {"name": "green peppers", "amount": 1.0, "unit": None},
            {"name": "onions", "amount": 1.0, "unit": None},
            {"name": "-3 beer", "amount": 1.0, "unit": None},
        ],
        [
            "Put all the above into a roaster.",
            "Stir occasionally  Cook at 250 - 300 deg. for most of the day (4- 5 hr.)",
            "Serve the sausage and peppers and onions on French bread.",
            "Always well liked.",
        ],
        allergens=[],
    )
    assert tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)) == []


def test_imp_fbf6565762c0590d_mabo_dofu_non_initial_serve_still_flags_sesame() -> None:
    recipe = _recipe(
        "imp_fbf6565762c0590d",
        "Mabo Dofu - Tofu with Beef",
        [
            {"name": "ground beef", "amount": 1.0, "unit": None},
            {"name": "minced beef", "amount": 1.0, "unit": None},
            {"name": "garlic", "amount": 1.0, "unit": None},
            {"name": "chili peppers", "amount": 1.0, "unit": None},
            {"name": "leek", "amount": 1.0, "unit": None},
            {"name": "soy sauce", "amount": 1.0, "unit": None},
            {"name": "sugar", "amount": 1.0, "unit": None},
            {"name": "cornstarch", "amount": 1.0, "unit": None},
            {"name": "water", "amount": 1.0, "unit": None},
            {"name": "broth", "amount": 1.0, "unit": None},
        ],
        [
            "Cut bean curd into bite-sized squares and set aside. Heat oil and fry garlic,  "
            "chili peppers and chopped leek.",
            "Add meat. When meat changes color, lightly stir  in bean curd, soy sauce and = "
            "sugar.",
            "Cover with lid and cook for 10 min.",
            "Add cornstarch mixture, allowing it  to thicken for a few minutes.",
            "Turn out into serving dish, sprinkle with the  sesame oil and serve hot. EmmaDeer",
        ],
        allergens=["soy", "soya"],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert categories == {"sesame"}


def test_imp_e7fb53c18ced5dc0_beer_batter_dip_no_in_suppressed() -> None:
    recipe = _recipe(
        "imp_e7fb53c18ced5dc0",
        "Beer Batter",
        [
            {"name": "beer", "amount": 1.0, "unit": None},
            {"name": "flour", "amount": 1.0, "unit": None},
            {"name": "seasoning salt", "amount": 1.0, "unit": None},
            {"name": "pepper", "amount": 1.0, "unit": None},
            {"name": "eggs", "amount": 1.0, "unit": None},
        ],
        [
            "Blend on high until smooth.",
            "Dip fresh shrimp, mushrooms or veggies.",
            "Put on flat pan and chill for one hour.",
            "Deep fry.",
        ],
        allergens=["egg", "eggs", "gluten", "wheat"],
    )
    assert find_instructions_ingredient_mismatches(recipe) == []


def test_imp_a22b3c09a6b25bb5_dip_fish_in_egg_white_contains_in_still_flags_fish() -> None:
    recipe = _recipe(
        "imp_a22b3c09a6b25bb5",
        "Crispy Baked Fish & Herbs",
        [
            {"name": "water", "amount": 1.0, "unit": None},
            {"name": "lemon pepper", "amount": 1.0, "unit": None},
            {"name": "fresh parsley", "amount": 1.0, "unit": None},
            {"name": "low-fat margarine", "amount": 1.0, "unit": None},
        ],
        [
            "Preheat oven 400F.",
            'Lightly spray a medium size shallow baking pan with vegetable spray.',
            "Rinse fish and pat dry.",
            "In small bowl, beat egg white with a little water.",
            "Dip fish in egg white, then roll in crumbs.",
            "Arrange fish in baking pan.",
            "Sprinkle with lemon pepper and parsley, then drizzle margarine over all.",
            "Bake uncovered 20 min or until fish flakes easily.",
        ],
        allergens=[],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    fish_mismatch = next(m for m in mismatches if m.category == "fish")
    # The "Dip fish in egg white..." step itself must have contributed
    # evidence -- i.e. NOT been suppressed by the item-5 dip-initial rule,
    # since it contains "in".
    dip_step_terms = {
        entry["term"] for entry in fish_mismatch.evidence if entry["quoted_step"].startswith("Dip fish in egg white")
    }
    assert "fish" in dip_step_terms


def test_imp_13e739367b505085_spiced_pear_butter_cheese_cloth_suppressed() -> None:
    recipe = _recipe(
        "imp_13e739367b505085",
        "Spiced Pear Butter",
        [
            {"name": "pears", "amount": 1.0, "unit": None},
            {"name": "cinnamon sticks", "amount": 1.0, "unit": None},
            {"name": "allspice", "amount": 1.0, "unit": None},
            {"name": "2 cloves", "amount": 1.0, "unit": None},
            {"name": "sugar", "amount": 1.0, "unit": None},
        ],
        [
            "Combine pears and apple juice in a large Dutch oven.",
            "Tie broken cinnamon  spices, gingerroot, allspice and cloves in a piece of cheese "
            "cloth; add  to pear mixture. Bring to a boil; cover, reduce heat, and simmer for "
            "45  minutes to 1 hour or until pears are tender.",
            "Drain pears, and discard  spice bag.",
            "Mash pears or process in food processor until smooth.",
            "Return  pear puree to Dutch oven, and add sugar.",
            "Cook, uncovered, over medium  heat for 30 to 40 minutes or until mixture thickens, "
            "stirring frequently.",
            "Remove from heat, and quickly pour hot pear mixture into hot sterilized  jars, "
            "leaving 1/4-inch headspace; wipe jar rims.",
            "Cover at once with  metal lids, and screw on bands.",
            "Process in boiling water bath for 5  minutes.",
        ],
        allergens=[],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "dairy" not in categories


def test_imp_d287af8d742e5d44_katjang_sauce_ketjap_manis_satisfies_soy_and_wheat() -> None:
    recipe = _recipe(
        "imp_d287af8d742e5d44",
        "Katjang Sauce: Peanut Sauce",
        [
            {"name": "onion", "amount": 1.0, "unit": None},
            {"name": "garlic cloves", "amount": 1.0, "unit": None},
            {"name": "brown sugar", "amount": 1.0, "unit": None},
            {"name": "sambal oelek", "amount": 1.0, "unit": None},
            {"name": "mild paprika", "amount": 1.0, "unit": None},
            {"name": "ginger powder", "amount": 1.0, "unit": None},
            {"name": "crunchy peanut butter", "amount": 1.0, "unit": None},
            {"name": "ketjap manis", "amount": 1.0, "unit": None},
            {"name": "milk", "amount": 1.0, "unit": None},
            {"name": "lemon juice", "amount": 1.0, "unit": None},
        ],
        [
            "Mix onion and garlic.",
            "Place onion mixture in a bowl; add the brown sugar.",
            "Mash with  the back of a spoon to make a paste.",
            "Brown the paste in the oil at very low heat.",
            "Stir in sambal oelek, paprika, and ginger powder.",
            "Add the peanut butter.",
            "When the sauce is brown, add the ketjap manis and the milk.",
            "Keep stirring at low heat until the sauce thickens.",
            "Finally, add the lemon  juice, salt and pepper.",
            "If the sauce is too thick, add a little more milk  until it reaches a better "
            "consistency.",
            "NOTES :",
            "*Ketjap manis is a sweet Indonesian soy sauce. It may be found in  Dutch stores, "
            "some Chinese stores or maybe European Delis. It is worth  looking for as it is "
            "just delicious!",
            "*Sambal oelek is a paste made from marinaded chili peppers.",
            "It can be  found in Chinese groceries, or Dutch stores.",
        ],
        allergens=["dairy", "milk"],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "soy" not in categories
    assert "wheat_gluten" not in categories


def test_imp_a76aa35639d85deb_borscht_pot_liquor_arm3_clears_stock() -> None:
    recipe = _recipe(
        "imp_a76aa35639d85deb",
        "Borscht II",
        [
            {"name": "beef stew meat", "amount": 1.0, "unit": None},
            {"name": "beets", "amount": 1.0, "unit": None},
            {"name": "onion", "amount": 1.0, "unit": None},
            {"name": "tomatoes", "amount": 1.0, "unit": None},
            {"name": "lime, juice of", "amount": 1.0, "unit": None},
            {"name": "-2 sugar", "amount": 1.0, "unit": None},
            {"name": "sour cream", "amount": 1.0, "unit": None},
        ],
        [
            "Combine the first five ingredients in a large non-reactive pot.  Bring to a boil, "
            "then reduce heat and allow the soup to simmer for 2= hours.",
            "Half an hour before serving, remove beets, keeping the broth at a simmer.",
            "When beets are cool enough to handle, peel and grate them (the peels should slip "
            "right off).  Then  return them to the pot.  Stir in lime juice and sugar, then "
            "season with salt and pepper.",
            "Serve, garnished with a dollop of sour cream and/or some snipped chives.",
        ],
        allergens=[],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "stock" not in categories


def test_imp_2020aaedc3cf532a_lasagna_rollups_instant_broth_kept() -> None:
    recipe = _recipe(
        "imp_2020aaedc3cf532a",
        "Lasagna Rollups with Bechamel Sauce",
        [
            {"name": "-15 beef", "amount": 1.0, "unit": None},
            {"name": "- 2 parmesan cheese", "amount": 1.0, "unit": None},
            {"name": "bay leaf", "amount": 1.0, "unit": None},
            {"name": "milk", "amount": 1.0, "unit": None},
            {"name": "butter", "amount": 1.0, "unit": None},
            {"name": "pepper", "amount": 1.0, "unit": None},
            {"name": "salt", "amount": 1.0, "unit": None},
            {"name": "nutmeg", "amount": 1.0, "unit": None},
        ],
        [
            "Preheat oven to 350.",
            "Cook noodles in salted, boiling water until just tender.  Drain and place in "
            "large bowl of cold water and drain on paper towels.",
            "Cook ground meat in microwave until done.  Mix cooked meat and breading mix from "
            "meatloaf mixture until well blended.",
            "Spread meat mixture in thin layer on noodles and roll up  jelly roll fashion "
            "(don't roll too tightly).",
            "Spread all of sauce over bottom of 9/13 baking dish and arrange roll ups, seam "
            "side down on sauce.",
            "Cover with foil and bake 30 minutes at 350*.",
            "Melt butter in medium sauce pan, stir in flour, and cook stirring constantly with "
            "wooded spoon until mixture bubbles.",
            "Stir in scalded milk, instant chicken broth, salt, pepper and nutmeg.",
            "Continue cooking and stirring until sauce thickens and bubbles (about 3 minutes), "
            "and remove from stove.",
            "After rollups have baked 30 minutes, remove  foil and spoon bechamel sauce over "
            "top and sprinkle with parmesan cheese.",
            "Bake 10 minutes more or until bubbly hot and sauce is golden.",
            "It's not nearly as hard to make as it sounds, and the results are wonderful! All "
            "you need to round out  the meal is a salad, and garlic bread if desired.",
        ],
        allergens=["dairy", "milk"],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "stock" in categories


def test_imp_4206dd29ea5550fb_escalope_of_salmon_add_fish_stock_kept() -> None:
    recipe = _recipe(
        "imp_4206dd29ea5550fb",
        "Escalope of Salmon With Chanterelles",
        [
            {"name": "salmon", "amount": 1.0, "unit": None},
            {"name": "canned chanterelles", "amount": 1.0, "unit": None},
            {"name": "Noilly Prat", "amount": 1.0, "unit": None},
            {"name": "broad beans", "amount": 1.0, "unit": None},
            {"name": "peas", "amount": 1.0, "unit": None},
            {"name": "butter", "amount": 1.0, "unit": None},
            {"name": "shallots", "amount": 1.0, "unit": None},
            {"name": "lemon juice", "amount": 1.0, "unit": None},
            {"name": "sea salt", "amount": 1.0, "unit": None},
        ],
        [
            "Add 25g of Butter to a small sauti pan.",
            "Add Chanterelles and shallots, cover  with a lid and sweat for a few minutes.",
            "Make a space for the salmon in the pan,  add wine and fish stock.",
            "Poach for 4-5 minutes, take out fish and keep warm.",
            "Reduce cooking liquid by two thirds, take out mushrooms.",
            "Cut butter into small  cubes and whisk in to make sauce. Add lemon juice abd peas.",
            "Return mushrooms,  add broad beans and peas, check seasoning.",
        ],
        allergens=["dairy", "fish", "milk", "seafood"],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "stock" in categories
    assert "fish" not in categories


def test_imp_00efafa3c86e5b9e_stroganoff_no_animal_row_arm3_inapplicable_kept() -> None:
    recipe = _recipe(
        "imp_00efafa3c86e5b9e",
        "Beef Stroganoff with Dill",
        [
            {"name": "butter", "amount": 1.0, "unit": None},
            {"name": "mushroom", "amount": 1.0, "unit": None},
            {"name": "onion", "amount": 1.0, "unit": None},
            {"name": "cornstarch", "amount": 1.0, "unit": None},
            {"name": "water", "amount": 1.0, "unit": None},
            {"name": "sour cream", "amount": 1.0, "unit": None},
            {"name": "dill weed", "amount": 1.0, "unit": None},
            {"name": "butter", "amount": 1.0, "unit": None},
            {"name": "paprika", "amount": 1.0, "unit": None},
        ],
        [
            'Cut meat into 1/4" strips and brown in butter.',
            "In a separate pan, saute mushrooms and add to meat. In the separate pan, saute "
            "onions and add to meat mixture. Add beef stock.",
            "Cover and simmer 1 hour.",
            "At about 40 min., begin to cook noodles.",
            "Mix corn starch and water in small container and add, stirring rapidly until "
            "sauce is thickened.",
            "Stir in sour cream and dill weed.",
            "Serve over Paprika Noodles: Drain noodles and p ut in bowl.",
            "Toss gently with chicken stock base, butter, and paprika.",
            "Note: Chicken stock base or granular boullion may be very salty.",
            "Let diners salt and pepper to their own tastes.",
            "Robert Boston http://home.earthlink.net/~bboston/",
        ],
        allergens=["dairy", "milk"],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "stock" in categories


def test_imp_635b6cd0fbd557ad_hutspot_bare_rib_flags_meat() -> None:
    recipe = _recipe(
        "imp_635b6cd0fbd557ad",
        "Hutspot",
        [
            {"name": "carrots", "amount": 1.0, "unit": None},
            {"name": "onions", "amount": 1.0, "unit": None},
            {"name": "potatoes", "amount": 1.0, "unit": None},
            {"name": "water", "amount": 1.0, "unit": None},
        ],
        [
            "First put potatoes in kettle.",
            "Add ribs, carrots and onions; salt to taste.",
            "Bring to slow boil, cover and cook for about 3 hours.",
            "When done take out bones and mash.",
        ],
        allergens=[],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert "meat" in categories
    meat_mismatch = next(m for m in mismatches if m.category == "meat")
    assert "rib" in meat_mismatch.matched_terms


def test_imp_41bfceea6ba65b47_corn_chowder_celery_ribs_row_does_not_flag_meat() -> None:
    recipe = _recipe(
        "imp_41bfceea6ba65b47",
        "Corn Chowder",
        [
            {"name": "bacon", "amount": 1.0, "unit": None},
            {"name": "-3 potatoes", "amount": 1.0, "unit": None},
            {"name": "onion", "amount": 1.0, "unit": None},
            {"name": "-3 celery ribs", "amount": 1.0, "unit": None},
            {"name": "water", "amount": 1.0, "unit": None},
            {"name": "bacon", "amount": 1.0, "unit": None},
        ],
        [
            "Dice  bacon, fry until crisp; drain and set aside, reserving 3 tablespoons of "
            "grease.",
            "Stir diced potatoes,  diced onion, and celery into the grease.",
            "Add water, salt and pepper to taste.",
            "Cook until soft.",
            "Then add can cream style corn and can of milk.",
            "Heat to desired temperature.",
            "Dish up into soup bowls and garnish with crumbled bacon.",
        ],
        allergens=[],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "meat" not in categories


def test_imp_0ea6e8bb1fd85633_pickled_tomato_parcels_seeds_and_ribs_suppressed() -> None:
    recipe = _recipe(
        "imp_0ea6e8bb1fd85633",
        "Pickled Tomato Parcels",
        [
            {"name": "green tomatoes", "amount": 1.0, "unit": None},
            {"name": "coarse salt", "amount": 1.0, "unit": None},
            {"name": "head of cabbage", "amount": 1.0, "unit": None},
            {"name": "whole mustard seeds", "amount": 1.0, "unit": None},
            {"name": "1/4 clove", "amount": 1.0, "unit": None},
            {"name": "allspice", "amount": 1.0, "unit": None},
            {"name": "white vinegar", "amount": 1.0, "unit": None},
            {"name": "chipotle chiles", "amount": 1.0, "unit": None},
            {"name": "garlic", "amount": 1.0, "unit": None},
        ],
        [
            "Remove a slice at the stem end of tomato.",
            "With a melon baller remove seeds and ribs, leaving outer wall intact. Sprinkle "
            "inside of each tomato with 1 tsp salt.  Place tomatoes upright in a glass or "
            "plastic container with enough room to hold the tomatoes in one layer with the "
            "top slices next to them.",
            "Cover with cold water and soak 24 hours.",
            "The next day take the tomatoes out and drain upside down.",
            "While they are draining, shred cabbage into a large glass or crockery bowl.",
            "Toss the cabbage with rest of the salt, and set aside for 30 minutes until it "
            "gives off moisture. Cover the cabbage with cold water, swish to remove salt and "
            "drain it in a colander.",
            "Rinse and dry the bowl.",
            "Squeeze handfuls of the cabbage to remove as much liquid as you can and place the "
            "cabbage back in the bowl.",
            "Toss cabbage with mustard, cloves and allspice and pack gently into the tomatoes.",
            "Replace the tops and tie in place with kitchen twine. Scald the tomato container "
            "and place tomatoes in it upright. Cover tomatoes with the vinegar, add peppers "
            "and garlic, and place a scalded plate over the toma toes.",
            "Weight the plate so that the plate is under the vinegar level but does not crush "
            "the tomatoes.",
            "Cover the container with plastic wrap.",
            "Let the tomatoes sit in a cool place for 1 week.",
        ],
        allergens=[],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "meat" not in categories


def test_imp_06f98881ebf05a75_pork_loin_crust_verb_use_suppressed() -> None:
    recipe = _recipe(
        "imp_06f98881ebf05a75",
        "Roasted Pork Loin with Bacon and Onion Spaetzle",
        [
            {"name": "olive oil", "amount": 1.0, "unit": None},
            {"name": "cracked black pepper", "amount": 1.0, "unit": None},
            {"name": "bacon", "amount": 1.0, "unit": None},
            {"name": "yellow onions", "amount": 1.0, "unit": None},
            {"name": "red wine", "amount": 1.0, "unit": None},
            {"name": "shallots", "amount": 1.0, "unit": None},
            {"name": "garlic", "amount": 1.0, "unit": None},
        ],
        [
            "Prehaet the oven to 400 degrees.",
            "For pork loin: Season the entire loin  with olive oil and salt. In a hot saute "
            "pan, sear the loin for 1-2  minnutes on each side. Remove from pan and crust the "
            "loin with cracked  black pepper.",
            "Place in a roasting pan.",
            "Roast the loin for 25 to 30  minutes for medium.",
            "Remove from the oven and allow to rest for 10  minutes.",
            "For the spaetzle: In a hot large pan, render the bacon until  crispy, remove the "
            "bacon from the pan.",
            "In the bacon fat, saute the  onions for 2-3 minutes.",
            "Stir in the bacon.",
            "Season.",
        ],
        allergens=[],
    )
    assert tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)) == []


def test_imp_968a7fa664885493_emerald_fried_rice_crepe_pan_suppressed() -> None:
    recipe = _recipe(
        "imp_968a7fa664885493",
        "Emerald Fried Rice",
        [
            {"name": "salt", "amount": 1.0, "unit": None},
            {"name": "eggs", "amount": 1.0, "unit": None},
            {"name": "spring onions", "amount": 1.0, "unit": None},
            {"name": "rice", "amount": 1.0, "unit": None},
            {"name": "msg", "amount": 1.0, "unit": None},
            {"name": "ham", "amount": 1.0, "unit": None},
        ],
        [
            "Sprinkle the finely shredded greens with 1 teaspoon salt and leave for 10  "
            "minutes, then squeeze out the liquid and chop finely.",
            "Heat 1 tablespoon of oil  in a frying-pan or crepe pan.",
            "Pur in the beaten egg and allow to spread thinly  over with a palette knife and "
            "cook the other side gently.",
            "Remove the omelette  and cut into fine shreds.",
            "Heat another tablespoon of oil in the frying-pan and  add the finely chopped "
            "greens.",
            "Stir-fry for about 30 seconds, then remove from  the pan.",
            "Heat the remaining oil in a wok until it is smoking.",
            "Add the spring  onions, then the rice, and toss well together until the rice is "
            "heated through.",
            "Add the remaining salt with the MSG, greens, omelette shreds and ham.",
            "Toss all  together and serve hot on a serving dish.",
        ],
        allergens=["egg", "eggs"],
    )
    assert tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)) == []


def test_imp_15fe9cc27b96537b_pumpkin_pecan_pie_flags_wheat_gluten_pie_shell() -> None:
    # Pecan rows must NOT satisfy "pie shell" (only "crust" gets the
    # nut/coconut composite arm).
    recipe = _recipe(
        "imp_15fe9cc27b96537b",
        "Pumpkin-Pecan Pie",
        [
            {"name": "canned pumpkin", "amount": 1.0, "unit": None},
            {"name": "sugar", "amount": 1.0, "unit": None},
            {"name": "ground cinnamon", "amount": 1.0, "unit": None},
            {"name": "ground ginger", "amount": 1.0, "unit": None},
            {"name": "ground cloves", "amount": 1.0, "unit": None},
            {"name": "salt", "amount": 1.0, "unit": None},
            {"name": "eggs", "amount": 1.0, "unit": None},
            {"name": "evaporated milk", "amount": 1.0, "unit": None},
            {"name": "butter", "amount": 1.0, "unit": None},
            {"name": "pecans", "amount": 1.0, "unit": None},
            {"name": "brown sugar", "amount": 1.0, "unit": None},
        ],
        [
            "Combine the pumpkin, sugar, spices and salt in a bowl mixing well.",
            "Add the eggs and evaporated milk.",
            "Beat until smooth, using a rotary beater or an electric mixer.",
            "Pour into the unbaked pie shell.",
            "Bake in a preheated oven at 425 degrees Fahrenheit for 15 minutes and then reduce "
            "the temperature to 350 degree and bake for an additional 45 minutes or until a "
            "knife inserted halfway between the center and edge comes out clean.",
            "Cool on a wire rack.",
            "CRUNCHY PECAN TOPPING:  Place the softened butter, brown sugar, and pecans in a "
            "bowl and mix until crumbly with a fork.  Sprinkle over the cooled pie. Place the "
            "pie under the broiler (5 inches from the heat source) until the mixture begins "
            "to bubble, about 1 minute.",
            "Cool to room temperature on a wire rack.",
        ],
        allergens=["dairy", "egg", "eggs", "milk", "nuts", "tree nut"],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert "wheat_gluten" in categories
    wheat_mismatch = next(m for m in mismatches if m.category == "wheat_gluten")
    assert "pie shell" in wheat_mismatch.matched_terms


def test_imp_d63bae35bb3a55bb_austrian_crepes_flags_wheat_gluten() -> None:
    recipe = _recipe(
        "imp_d63bae35bb3a55bb",
        "Austrian Sweet Cheese Crepes Baked in Custard",
        [
            {"name": "dried currant", "amount": 1.0, "unit": None},
            {"name": "boiling water", "amount": 1.0, "unit": None},
            {"name": "cream cheese", "amount": 1.0, "unit": None},
            {"name": "eggs", "amount": 1.0, "unit": None},
            {"name": "lemon, zest of", "amount": 1.0, "unit": None},
            {"name": "vanilla", "amount": 1.0, "unit": None},
            {"name": "granulated sugar", "amount": 1.0, "unit": None},
            {"name": "eggs", "amount": 1.0, "unit": None},
            {"name": "granulated sugar", "amount": 1.0, "unit": None},
            {"name": "milk", "amount": 1.0, "unit": None},
            {"name": "confectioners' sugar", "amount": 1.0, "unit": None},
        ],
        [
            "Make filling: In a small heatproof bowl plump currants in boiling-hot water 15 "
            "minutes  and drain.",
            "Pat currants dry between paper towels.",
            "In a food processor or in a bowl with an electric mixer blend together well cream "
            "cheese, jam, yolks, zest, and vanilla.",
            "In a bowl with an electric mixer (beaters cleaned if necessary) beat whites with "
            "a pinch of salt until they hold soft peaks.",
            "Add sugar to whites and beat meringue until it holds stiff peaks.",
            "Fold cheese mixture into meringue gently but thoroughly and fold in currants.",
            "Preheat oven to 400F.",
            "and lightly butter a 14-inch-long oval gratin dish or other 2 1/2-quart shallow "
            "baking dish.",
            "Working with 1 crepe at a time, spread 2 generous tablespoons filling on  each "
            "crepe, leaving a 1/2-inch border all around, and roll up crepes  jelly-roll "
            "fashion.",
            "With a sharp knife cut crepes on a diagonal in half  and arrange, overlapping "
            "slightly, in layers in baking dish.",
            "Crepes may  be prepared up to this point 4 hours ahead and chilled, covered.",
            "Bring  crepes to at room temperature before proceeding.",
            "In a small bowl whisk together eggs, granulated sugar, and milk and pour  over "
            "crepes, letting custard seep between layers.",
            "Bake crepes in middle  of oven 30 to 35 minutes, or until puffed and custard is "
            "set, and cool to warm.",
            "Dust crepes with confectioners' sugar and serve with apricot caramel  sauce.",
        ],
        allergens=["dairy", "egg", "eggs", "milk"],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert "wheat_gluten" in categories
    wheat_mismatch = next(m for m in mismatches if m.category == "wheat_gluten")
    assert "crepe" in wheat_mismatch.matched_terms


def test_imp_fe5e997cb47c553c_chocolate_caramel_pecan_cheesecake_crust_satisfied() -> None:
    recipe = _recipe(
        "imp_fe5e997cb47c553c",
        "Chocolate-Caramel-Pecan Cheesecake",
        [
            {"name": "graham cracker crumbs", "amount": 1.0, "unit": None},
            {"name": "butter", "amount": 1.0, "unit": None},
            {"name": "margarine", "amount": 1.0, "unit": None},
            {"name": "evaporated milk", "amount": 1.0, "unit": None},
            {"name": "pecans", "amount": 1.0, "unit": None},
            {"name": "cream cheese", "amount": 1.0, "unit": None},
            {"name": "sugar", "amount": 1.0, "unit": None},
            {"name": "eggs", "amount": 1.0, "unit": None},
            {"name": "vanilla extract", "amount": 1.0, "unit": None},
            {"name": "pecan halves", "amount": 1.0, "unit": None},
        ],
        [
            "Combine graham cracker crumbs and butter, stirring well.",
            "Press mixture evenly onto bottom and 1 inch up sides of a 9-inch springform pan.",
            "Unwrap caramels; combine with milk and heat over low heat until  caramels are "
            "melted, stirring often.",
            "Pour over graham cracker crust;  sprinkle chopped pecans evenly over caramel "
            "layer and set aside.",
            "Beat  cream cheese at high speed until light and fluffy; gradually add  sugar, "
            "mixing well.",
            "Add eggs, one at a time, mixing well after each  one. Stir in vanilla and "
            "chocolate; beat until blended.",
            "Spoon over  pecan layer.",
            "Bake at 350 degrees for 30 minutes.",
            "Remove from oven,  and run knife around edge of pan to release sides.",
            "Let cool t  o room  temperature on a wire rack; cover and chill at least 8 hours "
            "before  serving.",
            "Top with pecan halves and serve.",
        ],
        allergens=["dairy", "egg", "eggs", "milk", "nuts", "tree nut"],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "wheat_gluten" not in categories


def test_synthetic_crust_nut_or_coconut_composite_satisfies_crust_not_pie_shell() -> None:
    # Isolates the nut/coconut composite arm from any pre-existing
    # "cracker"/"graham" satisfier -- ingredient rows here are ONLY
    # coconut+pecans (no flour/cracker/cookie row at all), same shape as
    # imp_21d303d861785454 "Cocoa-Nut Meringue Cheesecake": "Combine
    # coconut, pecans, and margarine, press onto bottom of 9-inch springform
    # pan" / "...pour over crust."
    recipe_crust = _recipe(
        "syn24",
        "Synthetic Crust",
        [
            {"name": "flaked coconut", "amount": 1, "unit": None},
            {"name": "pecans", "amount": 1, "unit": None},
            {"name": "margarine", "amount": 1, "unit": None},
        ],
        ["Combine coconut, pecans, and margarine, press onto bottom of pan.", "Pour over crust."],
    )
    assert tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe_crust)) == []

    recipe_pie_shell = _recipe(
        "syn25",
        "Synthetic Pie Shell",
        [
            {"name": "flaked coconut", "amount": 1, "unit": None},
            {"name": "pecans", "amount": 1, "unit": None},
            {"name": "margarine", "amount": 1, "unit": None},
        ],
        ["Pour filling into the unbaked pie shell."],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe_pie_shell))
    categories = _categories(mismatches)
    assert "wheat_gluten" in categories


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
    #
    # 2026-07-20 (systematic ground-truth-vs-production vocabulary diff
    # closure, docs/BACKLOG.md) added 8 more fish/seafood-domain terms to
    # MEAT_ALIASES: "calamari"/"octopus"/"squid" (cephalopod mollusk meat)
    # and "caviar" (fish roe, not muscle flesh at all -- same non-flesh
    # class as gelatin/worcestershire) and "grouper"/"mackerel"/"perch"/
    # "tilapia" (fish species). Same "different hazard class, fish-side"
    # reasoning as the pre-existing gelatin/worcestershire exclusions above:
    # this module already models fish/mollusk/crustacean vocabulary
    # separately and independently via its own FISH_TERMS/MOLLUSK_TERMS/
    # CRUSTACEAN_TERMS constants (deliberately NOT imported from
    # constraint_engine, per this module's own independence rationale), so
    # these 8 terms belong in that separate domain, not MEAT_FLESH_TERMS.
    # The remaining 8 new MEAT_ALIASES additions this same change made ARE
    # genuinely land-animal/poultry flesh ("brisket", "capon", "meatball",
    # "pheasant", "quail", "salami", "tripe", "venison") and are added to
    # MEAT_FLESH_TERMS below instead.
    non_flesh_exclusions = {
        "gelatin",
        "worcestershire",
        "marshmallow",
        "suet",
        "lard",
        "calamari",
        "caviar",
        "grouper",
        "mackerel",
        "octopus",
        "perch",
        "squid",
        "tilapia",
    }
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


# --- Revision round 3: "cereal" wheat_gluten trigger (adjudication_
# 20260718T090522Z.md diet_023, advisor-reviewed/APPROVED 2026-07-18) -------


def test_imp_2bd54fd475cf50fc_butterscotch_chewy_bars_flags_wheat_gluten_cereal() -> None:
    # Fixture copied verbatim from the quarantine sidecar payload
    # (data/processed/quarantined_recipes.jsonl, quarantined via
    # scripts/quarantine_flagged_recipes.py --recipe-ids
    # imp_2bd54fd475cf50fc, reason: adjudication_20260718T090522Z.md
    # diet_023: instructions "stir in cereals" with no cereal row).
    recipe = _recipe(
        "imp_2bd54fd475cf50fc",
        "Butterscotch Chewy Bars",
        [
            {"name": "butter", "amount": 3.0, "unit": None},
            {"name": "margarine", "amount": 0.5, "unit": None},
            {"name": "brown sugar", "amount": 2.0, "unit": None},
            {"name": "miniature marshmallows", "amount": 4.0, "unit": None},
        ],
        [
            "Using a large saucepan, melt butter over medium heat.",
            "Slowly add sugar and stir well.",
            "Add marshmallows; stirring constantly until marshmallows melt.",
            "Remove from  heat and immediately stir in cereals.",
            "Coat a 13 x 9 x 2 inch pan with cooking spray; press chewy mixture evenly into "
            "bottom of pan.",
            "it's a lot easier if your  hands are wet.",
            "Let cool for 60 minutes and cut.",
        ],
        allergens=["dairy", "milk"],
    )
    mismatches = tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe))
    categories = _categories(mismatches)
    assert "wheat_gluten" in categories
    wheat_mismatch = next(m for m in mismatches if m.category == "wheat_gluten")
    assert "cereal" in wheat_mismatch.matched_terms


def test_synthetic_crispy_rice_cereal_row_satisfies_stir_in_cereal_mention() -> None:
    # Must-NOT-flag counterpart to the fixture above: a recipe whose
    # ingredient list DOES name a cereal row (lenient satisfier side, spec
    # Sec. 2's core asymmetry -- `cereal` is its own satisfier since
    # WHEAT_GLUTEN_TERMS is unioned wholesale into the category's
    # satisfiers) must not flag on the same instruction wording.
    recipe = _recipe(
        "syn_cereal1",
        "Synthetic Crispy Rice Treats",
        [
            {"name": "butter", "amount": 3.0, "unit": None},
            {"name": "miniature marshmallows", "amount": 4.0, "unit": None},
            {"name": "crispy rice cereal", "amount": 6.0, "unit": None},
        ],
        [
            "Melt butter and marshmallows together over low heat.",
            "Remove from heat and immediately stir in cereal.",
            "Press into a greased pan and let cool.",
        ],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "wheat_gluten" not in categories


# --- Revision round 3 follow-up: "cereal bowl" exact-phrase suppression
# (orchestrator sample check of the 20260718T113546Z report's round-3 5-case
# list, adjudicated FALSE_POSITIVE 2026-07-18) -----------------------------


def test_imp_9fb0ca4a0fa65c48_low_fat_swiss_muesli_cereal_bowl_not_flagged() -> None:
    # Fixture copied verbatim from data/processed/imported_recipes.jsonl.
    # "spoon some of the muesli into a cereal bowl" is the SERVING
    # CONTAINER for the already-listed muesli (rolled oats row present),
    # not a second, undisclosed cereal ingredient -- same utensil/
    # serving-vessel class as "stock pot" the utensil vs. "stock" the
    # ingredient.
    recipe = _recipe(
        "imp_9fb0ca4a0fa65c48",
        "Low-Fat Swiss Muesli",
        [
            {"name": "rolled oats", "amount": 1.5, "unit": None},
            {"name": "lemon juice", "amount": 2.0, "unit": None},
            {"name": "water", "amount": 1.5, "unit": None},
            {"name": "cinnamon", "amount": 0.5, "unit": None},
            {"name": "red apples", "amount": 2.0, "unit": None},
            {"name": "golden delicious apples", "amount": 1.5, "unit": None},
            {"name": "prunes", "amount": 2.0, "unit": None},
            {"name": "pecans", "amount": None, "unit": None},
            {"name": "honey", "amount": None, "unit": None},
        ],
        [
            "Combine oats, water, shredded apples, prunes, honey, lemon juice and cinnamon.",
            "Cover and refrigerate overnight.  In the morning, spoon some of the muesli into "
            " a cereal bowl.",
            "Top with your choice of fresh fruits and nuts.",
            "Serve with a  dollop of plain yogurt or milk, if desired.",
            "Muesli can be stored in covered  container in refrigerator for several days.",
        ],
        allergens=["nuts", "tree nut"],
    )
    categories = _categories(tier_ab_mismatches(find_instructions_ingredient_mismatches(recipe)))
    assert "wheat_gluten" not in categories
