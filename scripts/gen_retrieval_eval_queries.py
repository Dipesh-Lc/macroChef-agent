"""Generator for app/evaluation/data/retrieval_eval_queries.jsonl.

Computes `relevant_recipe_ids` for each hand-authored query (category,
description, structured ingredients/cuisine/meal_type) against the current
corpus, then writes the result out. The output is a FROZEN/PINNED
ground-truth file checked into the repo -- scripts/evaluate_retrieval.py
loads that file rather than recomputing ground truth live, so retrieval
scores stay comparable across runs even if the corpus is later re-imported
or re-grounded. Re-run this script deliberately (and re-review the diff)
if the query set itself needs to change; a corpus change alone should NOT
regenerate the file on every eval run.

Each query's ground truth is defined independently of the SEMANTIC retrieval
method under test (title-substring match / structured ingredient-membership
match / cuisine or meal_type or diet_tag field match) -- the same
"independent ground truth" principle scripts/audit_diet_leaks.py uses,
otherwise a "relevant" set built from the retriever under test would make
that arm of the eval circular.

CORRECTION: this independence does NOT hold for the KEYWORD baseline.
`RecipeRetriever.keyword_search` (app/services/recipe_retriever.py) scores
recipes by literally the same predicates used here to build ground truth for
the `ingredient`, `cuisine`, and `meal_type` categories (ingredient-membership
via `ingredient_matches`, exact cuisine match, exact meal_type match). So
keyword's near-1.0 score on those three categories is an ORACLE UPPER BOUND
-- it is measuring "does the label-generating predicate match itself",
not evidence the keyword path handles real user queries well. The `dish`,
`dietary`, and `paraphrase` categories (title-substring match, diet-tag
match, and a canonical-ingredient predicate paired with colloquial/synonym
query text respectively) are genuinely method-independent for BOTH keyword
and semantic, and are the meaningful comparison categories --
see scripts/evaluate_retrieval.py's methodology note and gate definition.

BACKLOG (not implemented here): corpus metadata enrichment. `cuisine`,
`meal_type`, and `diet_tags` are populated for the 25 hand-curated seed
recipes but almost entirely absent on the ~4,238 imported Food.com recipes,
which is why the `cuisine` and `dietary` categories' ground truth is
seed-only. An ML auto-tagger (classifier over title/ingredients) is a
candidate to backfill this metadata at scale, but per CLAUDE.md any such
model is advisory-only: it may suggest/rank tags, and MUST NEVER feed the
deterministic allergy/diet safety filter (app.services.constraint_engine)
-- that filter's tag/ingredient inputs must remain from grounded,
non-learned sources.

Usage: python scripts/gen_retrieval_eval_queries.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag.loaders import load_corpus  # noqa: E402
from app.schemas.recipe import Recipe  # noqa: E402
from app.utils.ingredient_normalizer import ingredient_matches  # noqa: E402

OUTPUT_PATH = ROOT / "app" / "evaluation" / "data" / "retrieval_eval_queries.jsonl"


def _has_ingredient(recipe: Recipe, name: str) -> bool:
    return any(ingredient_matches(name, item.name) for item in recipe.ingredients)


def _has_all_ingredients(recipe: Recipe, names: list[str]) -> bool:
    return all(_has_ingredient(recipe, name) for name in names)


def _has_diet_tag(recipe: Recipe, tag: str) -> bool:
    return tag in recipe.diet_tags


def _title_contains(recipe: Recipe, keyword: str) -> bool:
    return keyword.lower() in recipe.title.lower()


def build_queries(recipes: list[Recipe]) -> list[dict]:
    queries: list[dict] = []

    def add(query_id, category, description, *, ingredients=None, cuisine_preference=None,
            meal_type=None, predicate) -> None:
        relevant = [r.recipe_id for r in recipes if predicate(r)]
        queries.append(
            {
                "query_id": query_id,
                "category": category,
                "description": description,
                "ingredients": ingredients or [],
                "cuisine_preference": cuisine_preference,
                "meal_type": meal_type,
                "relevant_recipe_ids": relevant,
            }
        )

    # --- 25 ingredient-based queries (pantry-style: "what can I make with X, Y?") ---
    ingredient_combos = [
        ("chicken breast and mushroom", ["chicken breast", "mushroom"]),
        ("chicken breast, soy sauce, and ginger", ["chicken breast", "soy sauce", "ginger"]),
        ("beef, carrot, and celery", ["beef", "carrot", "celery"]),
        ("salmon and lemon juice", ["salmon", "lemon juice"]),
        ("shrimp, garlic, and lemon juice", ["shrimp", "garlic", "lemon juice"]),
        ("tofu and soy sauce", ["tofu", "soy sauce"]),
        ("cream cheese and chocolate chips", ["cream cheese", "chocolate chip"]),
        ("banana and walnut", ["banana", "walnut"]),
        ("pecan and corn syrup", ["pecan", "corn syrup"]),
        ("apple, cinnamon, and oats", ["apple", "cinnamon", "oats"]),
        ("black beans, corn, and cumin", ["black bean", "corn", "cumin"]),
        ("spinach and feta", ["spinach", "feta"]),
        ("quinoa and chickpeas", ["quinoa", "chickpea"]),
        ("lentils, carrot, and onion", ["lentil", "carrot", "onion"]),
        ("basil, parmesan, and tomato", ["basil", "parmesan", "tomato"]),
        ("oregano, mozzarella, and tomato sauce", ["oregano", "mozzarella", "tomato sauce"]),
        ("coconut milk and curry powder", ["coconut milk", "curry powder"]),
        ("peanut butter and chocolate chips", ["peanut butter", "chocolate chip"]),
        ("cranberry and orange", ["cranberry", "orange"]),
        ("zucchini and parmesan", ["zucchini", "parmesan"]),
        ("sweet potato and black beans", ["sweet potato", "black bean"]),
        ("ginger, garlic, and soy sauce", ["ginger", "garlic", "soy sauce"]),
        ("bacon, cheddar cheese, and potato", ["bacon", "cheddar cheese", "potato"]),
        ("pumpkin and cream cheese", ["pumpkin", "cream cheese"]),
        ("mushroom, spinach, and garlic", ["mushroom", "spinach", "garlic"]),
    ]
    for i, (desc, ings) in enumerate(ingredient_combos, start=1):
        add(
            f"ing_{i:02d}", "ingredient", f"What can I make with {desc}?",
            ingredients=ings,
            predicate=lambda r, ings=ings: _has_all_ingredients(r, ings),
        )

    # --- 10 dish/title queries ("I want to make X") -- ground truth is a title
    # match, independent of the ingredients list below. The ingredients are the
    # signature items a user might type if searching by ingredient rather than
    # dish name; they give the keyword baseline something structured to match
    # on, while the semantic path gets the free-text `description` (see
    # scripts/evaluate_retrieval.py for how each method consumes these fields).
    dish_queries = [
        ("chicken parmesan", "chicken parmesan", ["chicken breast", "parmesan", "tomato sauce"]),
        ("banana bread", "banana bread", ["banana", "flour", "baking soda"]),
        ("chocolate chip cookies", "chocolate chip cookie", ["chocolate chip", "flour", "butter"]),
        ("beef stew", "beef stew", ["beef", "carrot", "potato"]),
        ("apple pie", "apple pie", ["apple", "cinnamon", "pie crust"]),
        ("meatloaf", "meatloaf", ["ground beef", "breadcrumb", "ketchup"]),
        ("lasagna", "lasagna", ["lasagna noodle", "ricotta", "tomato sauce"]),
        ("chili", "chili", ["ground beef", "kidney bean", "chili powder"]),
        ("carrot cake", "carrot cake", ["carrot", "cream cheese", "flour"]),
        ("potato salad", "potato salad", ["potato", "mayonnaise", "celery"]),
    ]
    for i, (desc, kw, ings) in enumerate(dish_queries, start=1):
        add(
            f"dish_{i:02d}", "dish", f"I want to make {desc}.",
            ingredients=ings,
            predicate=lambda r, kw=kw: _title_contains(r, kw),
        )

    # --- 5 cuisine queries ---
    cuisines = ["Mediterranean", "Mexican", "Italian", "Thai", "Japanese"]
    for i, cuisine in enumerate(cuisines, start=1):
        add(
            f"cuisine_{i:02d}", "cuisine", f"I'm in the mood for {cuisine} food.",
            ingredients=[], cuisine_preference=cuisine,
            predicate=lambda r, cuisine=cuisine: r.cuisine == cuisine,
        )

    # --- 5 meal-type queries ---
    meal_type_queries = [
        ("mt_01", "a breakfast with eggs", "breakfast", ["egg"]),
        ("mt_02", "a dessert with chocolate", "dessert", ["chocolate"]),
        ("mt_03", "a dessert with apples", "dessert", ["apple"]),
        ("mt_04", "something for dinner tonight", "dinner", []),
        ("mt_05", "something quick for lunch", "lunch", []),
    ]
    for query_id, desc, meal_type, ings in meal_type_queries:
        add(
            query_id, "meal_type", f"I want {desc}.",
            ingredients=ings, meal_type=meal_type,
            predicate=lambda r, mt=meal_type, ings=ings: r.meal_type == mt and _has_all_ingredients(r, ings),
        )

    # --- 5 dietary queries ---
    dietary_queries = [
        ("diet_01", "vegan", "a vegan dinner with lentils", ["lentil"]),
        ("diet_02", "vegetarian", "a vegetarian meal with chickpeas", ["chickpea"]),
        ("diet_03", "gluten-free", "a gluten-free chicken dish", ["chicken"]),
        ("diet_04", "dairy-free", "a dairy-free chicken dish", ["chicken"]),
        ("diet_05", "high-protein", "a high-protein chicken meal", ["chicken"]),
    ]
    for query_id, diet_tag, desc, ings in dietary_queries:
        add(
            query_id, "dietary", f"I need {desc}.",
            ingredients=ings,
            predicate=lambda r, tag=diet_tag, ings=ings: _has_diet_tag(r, tag) and _has_all_ingredients(r, ings),
        )

    # --- paraphrase queries: the method-independent vocabulary-bridging test.
    # Ground truth uses the SAME `_has_all_ingredients` predicate over
    # CANONICAL corpus ingredient names as the `ingredient` category above,
    # but the free-text `description` AND the structured `ingredients` field
    # use colloquial/synonym surface forms a real user might type instead of
    # the canonical name. This isolates whether a retrieval method can
    # bridge vocabulary a literal `ingredient_matches` lookup cannot --
    # independent of which method is under test, since the ground truth
    # never touches either method's matching logic.
    #
    # Some surface forms below (e.g. "prawns"->shrimp, "capsicum"->bell
    # pepper) ARE already resolved by
    # app.utils.ingredient_normalizer.SYNONYMS, so keyword_search's own
    # normalization will also succeed on those -- that is a legitimate
    # finding (the synonym table already covers that gap), not a broken
    # query. Others ("bean curd", "leftover roast chicken", "minced beef")
    # are genuine gaps the normalizer does not cover, which is where a
    # semantic-vs-keyword gap would be expected to show up if embeddings are
    # doing real vocabulary generalization.
    #
    # NOTE on combo sizes: several canonical terms ("green onion", "bell
    # pepper", "eggplant") are prone to spurious `ingredient_matches` hits
    # via short-substring overlap (e.g. "onion" matches "green onion",
    # "egg" matches "eggplant" -- see NOTICED-NOT-FIXED in the Phase 1.5
    # closeout report). Pairing those terms with a second/third co-occurring
    # canonical ingredient (mirroring how the `ingredient` category above
    # mostly uses 2-3 term AND-predicates) keeps ground truth reasonably
    # precise without touching `ingredient_matches` itself, which is a
    # pre-existing, separately-scoped issue.
    paraphrase_queries = [
        (
            "garbanzo beans and cumin",
            ["chickpea", "cumin"],
            "a stew with garbanzo beans and cumin",
            ["garbanzo beans", "cumin"],
        ),
        ("prawns and garlic", ["shrimp", "garlic"], "a dish with prawns and garlic", ["prawns", "garlic"]),
        (
            "scallions, tamari, and ginger",
            ["green onion", "soy sauce", "ginger"],
            "a stir fry with scallions, tamari, and fresh ginger",
            ["scallions", "tamari", "ginger"],
        ),
        (
            "leftover roast chicken with ginger",
            ["chicken breast", "ginger"],
            "a way to use up leftover roast chicken with some fresh ginger",
            ["leftover roast chicken", "ginger"],
        ),
        (
            "aubergine, garlic, and tomato",
            ["eggplant", "garlic", "tomato"],
            "a recipe with aubergine, garlic, and tomato",
            ["aubergine", "garlic", "tomato"],
        ),
        (
            "fresh cilantro and cumin",
            ["coriander", "cumin"],
            "a dish with fresh cilantro and cumin",
            ["fresh cilantro", "cumin"],
        ),
        ("bean curd", ["tofu"], "a recipe using bean curd", ["bean curd"]),
        (
            "courgette and parmesan",
            ["zucchini", "parmesan"],
            "a dish with courgette and parmesan",
            ["courgette", "parmesan"],
        ),
        (
            "garbanzos and spinach",
            ["chickpea", "spinach"],
            "garbanzos and spinach for dinner",
            ["garbanzos", "spinach"],
        ),
        (
            "minced beef and carrot",
            ["beef", "carrot"],
            "a dish with minced beef and carrot",
            ["minced beef", "carrot"],
        ),
        (
            "capsicum and cumin",
            ["bell pepper", "cumin"],
            "a recipe with capsicum and cumin",
            ["capsicum", "cumin"],
        ),
        (
            "capsicum, corn, and black beans",
            ["bell pepper", "corn", "black bean"],
            "a dish with capsicum, corn, and black beans",
            ["capsicum", "corn", "black beans"],
        ),
    ]
    for i, (_label, canonical, desc, colloquial_ings) in enumerate(paraphrase_queries, start=1):
        add(
            f"para_{i:02d}", "paraphrase", desc,
            ingredients=colloquial_ings,
            predicate=lambda r, names=canonical: _has_all_ingredients(r, names),
        )

    return queries


def main() -> None:
    recipes = load_corpus()
    queries = build_queries(recipes)

    empty = [q["query_id"] for q in queries if not q["relevant_recipe_ids"]]
    if empty:
        print(f"** WARNING: {len(empty)} quer(y/ies) have an empty relevant set: {empty} **")

    sizes = sorted(len(q["relevant_recipe_ids"]) for q in queries)
    print(f"Generated {len(queries)} queries against a {len(recipes)}-recipe corpus.")
    print(f"Relevant-set sizes: min={sizes[0]}, median={sizes[len(sizes) // 2]}, max={sizes[-1]}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        for query in queries:
            handle.write(json.dumps(query) + "\n")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
