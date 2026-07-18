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
via production's `ingredient_matches`, exact cuisine match, exact meal_type
match). So keyword's near-1.0 score on those three categories is an ORACLE
UPPER BOUND -- it is measuring "does the label-generating predicate match
itself", not evidence the keyword path handles real user queries well. The
`dish`, `dietary`, and `paraphrase_syn`/`paraphrase_oov` categories
(title-substring match, diet-tag match, and a canonical-ingredient predicate
paired with colloquial/synonym query text respectively) are genuinely
method-independent for BOTH keyword and semantic -- see
scripts/evaluate_retrieval.py's methodology note and gate definition.

GROUND-TRUTH MATCHING PREDICATE -- Phase 1.5 closeout decontamination:

Ground truth here does NOT use `app.utils.ingredient_normalizer.ingredient_matches`
(the function production `keyword_search` and every other consumer uses).
That function is unsuitable for GROUND TRUTH -- as opposed to a live search
result a human can see and discard -- because of two compounding effects:

  1. Raw substring containment (`left in right or right in left`), which
     matches "egg" inside "eggplant", "onion" inside "green onion", "pea"
     inside "chickpea" purely at the character level, not the word level.
  2. `normalize_ingredient`'s trailing fuzzy fallback
     (`fuzzy_normalize_ingredient`, rapidfuzz `token_sort_ratio >= 85`),
     which can fold an unrelated ingredient onto a `CANONICAL_INGREDIENTS`
     entry when nothing else in normalization matched.

On this corpus that inflated some single-ingredient relevant sets by
10-40x -- e.g. "eggplant" matched 1,197 of 4,263 recipes via
`ingredient_matches` (nearly every recipe that happens to contain "egg"
somewhere), collapsing to 31 under the strict predicate below. See
docs/phase-1.5-closeout.md for the full before/after table.
`ingredient_matches` itself is UNCHANGED here and remains in production use
(disliked-ingredient filtering, recipe discovery, procurement,
recipe_validation_service) -- fixing it there is a separately tracked
backlog item (see the closeout doc), out of scope for this eval-only pass.

This generator instead uses its own `_strict_ingredient_match`, used ONLY to
compute the pinned ground truth below:

  - Both sides are normalized with `normalize_ingredient` (dict synonyms +
    descriptor stripping + plural stripping + fuzzy fallback -- the same
    normalization keyword_search itself performs on each side individually,
    so reusing it here is mechanical name-cleanup, not a new judgment call).
  - Matching is then WORD-BOUNDARY TOKEN containment: the (whitespace-split)
    token set of one normalized name must be a subset of the other's -- NOT
    a raw substring check, and NO additional fuzzy step at the matching
    stage. This alone kills the raw-substring false positives above, since
    e.g. {"egg"} is never a subset of {"eggplant"} as *token sets* (they are
    different single-word tokens), even though the characters "egg" are a
    substring of "eggplant".
  - Token-set subset containment is still too permissive for a small set of
    single-word ingredient names that are also the HEAD of a longer
    canonical name for a materially different ingredient: "onion" (tokens
    {"onion"}) is a token-subset of "green onion" ({"green", "onion"}), and
    "pepper" is a token-subset of "bell pepper". `AMBIGUOUS_HEADS` forces
    EXACT normalized-string equality for these four terms -- a plain
    "onion" query no longer counts a "green onion" recipe as relevant (and
    vice versa), same for "pepper"/"bell pepper", "egg"/"eggplant" (and
    "egg"/"egg white"), and "pea"/"chickpea" (killed by tokenization alone,
    but kept in the set for symmetry/defense-in-depth since "pea" is also a
    head of other two-word canonical peas dishes should the corpus grow one).

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
from app.utils.ingredient_normalizer import normalize_ingredient  # noqa: E402

OUTPUT_PATH = ROOT / "app" / "evaluation" / "data" / "retrieval_eval_queries.jsonl"

# Single-word ingredient names that are also the head of a longer canonical
# name for a materially different ingredient. See the module docstring's
# "GROUND-TRUTH MATCHING PREDICATE" section for the full rationale.
AMBIGUOUS_HEADS = {"egg", "onion", "pepper", "pea"}


def _strict_ingredient_match(query_name: str, inventory_name: str) -> bool:
    """Ground-truth-only ingredient match. NOT `ingredient_matches` -- see
    the module docstring. Normalize both sides, then require word-boundary
    token containment, with `AMBIGUOUS_HEADS` forcing exact equality."""
    query_norm = normalize_ingredient(query_name).lower().strip()
    inventory_norm = normalize_ingredient(inventory_name).lower().strip()
    if not query_norm or not inventory_norm:
        return False
    if query_norm == inventory_norm:
        return True
    if query_norm in AMBIGUOUS_HEADS or inventory_norm in AMBIGUOUS_HEADS:
        return False
    query_tokens = set(query_norm.split())
    inventory_tokens = set(inventory_norm.split())
    return query_tokens <= inventory_tokens or inventory_tokens <= query_tokens


def _has_ingredient(recipe: Recipe, name: str) -> bool:
    return any(_strict_ingredient_match(name, item.name) for item in recipe.ingredients)


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
    # Each entry is (description, structured `ingredients` field, [optional]
    # ground-truth match terms if they must differ from the structured field).
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
        # Ground truth intentionally drops "potato" from the match terms
        # here (structured `ingredients` field keeps all 3, unaffected):
        # `normalize_ingredient`'s naive plural-stripping turns "potatoes"
        # into "potatoe" (off-by-one, not "potato") on many corpus items
        # like "-12 mashed potatoes", so a bare "potato" match term fails to
        # find them even though they're clearly potato recipes. That is a
        # pre-existing `ingredient_normalizer` bug (see BACKLOG in
        # docs/phase-1.5-closeout.md), out of scope for this eval-only pass
        # -- worked around here the same way the paraphrase category already
        # decouples its colloquial `ingredients` field from the canonical
        # match predicate.
        ("bacon, cheddar cheese, and potato", ["bacon", "cheddar cheese", "potato"], ["bacon", "cheddar cheese"]),
        ("pumpkin and cream cheese", ["pumpkin", "cream cheese"]),
        ("mushroom, spinach, and garlic", ["mushroom", "spinach", "garlic"]),
    ]
    for i, combo in enumerate(ingredient_combos, start=1):
        if len(combo) == 3:
            desc, ings, match_ings = combo
        else:
            desc, ings = combo
            match_ings = ings
        add(
            f"ing_{i:02d}", "ingredient", f"What can I make with {desc}?",
            ingredients=ings,
            predicate=lambda r, names=match_ings: _has_all_ingredients(r, names),
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

    # --- paraphrase queries: the method-independent vocabulary-bridging test,
    # split into two subcategories (Phase 1.5 closeout respecification -- see
    # scripts/evaluate_retrieval.py's methodology note and gate definition):
    #
    # `paraphrase_syn`: the colloquial anchor IS resolvable by
    # `app.utils.ingredient_normalizer.SYNONYMS` (directly, or after
    # descriptor-stripping/plural-stripping feeds back into a SYNONYMS hit --
    # verified per-term below). This means keyword_search's own normalization
    # also resolves these, so it is a SYNONYM-TABLE REGRESSION test (keyword
    # is expected to do fine here too) rather than a semantic-vs-keyword
    # embedding-value test. Reported, not gated against semantic.
    #
    # `paraphrase_oov`: the colloquial/regional anchor is verifiably ABSENT
    # from SYNONYMS and out of `fuzzy_normalize_ingredient`'s reach (verified
    # per-term below: `normalize_ingredient(term)` does NOT resolve to the
    # canonical anchor via SYNONYMS/fuzzy -- 8 of the 9 terms pass through
    # normalization completely unchanged; the exception is "garbanzos",
    # where mechanical plural-stripping alone turns it into "garbanzo"
    # without SYNONYMS or the fuzzy fallback ever firing, so it still does
    # NOT resolve to the canonical "chickpea" anchor either way), with a
    # canonical anchor that has real corpus recipes. This is the TRUE
    # embedding-value test --
    # whether semantic search can bridge vocabulary a literal keyword lookup
    # cannot. Reported honestly whichever way it lands; see
    # scripts/evaluate_retrieval.py for why an OOV loss does not fail the
    # Phase 1.5 gate.
    #
    # Ground truth for both subcategories uses `_has_all_ingredients` over
    # CANONICAL corpus ingredient names -- same predicate as the `ingredient`
    # category above -- paired with colloquial/synonym query text a real user
    # might type instead of the canonical name. This isolates vocabulary
    # bridging independent of which method is under test, since the ground
    # truth never touches either method's matching logic.
    #
    # NOTE on combo sizes: several canonical terms ("green onion", "bell
    # pepper", "eggplant") were historically prone to spurious matches via
    # short-substring overlap under the OLD ground-truth predicate (e.g.
    # "onion" matching "green onion", "egg" matching "eggplant") -- the
    # `_strict_ingredient_match`/`AMBIGUOUS_HEADS` predicate above now
    # prevents that. Queries still pair those terms with a second/third
    # co-occurring canonical ingredient (mirroring the `ingredient` category's
    # 2-3 term AND-predicates) to keep relevant-set sizes reasonable, not to
    # work around a substring bug.
    paraphrase_syn_queries = [
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
        (
            "courgette and parmesan",
            ["zucchini", "parmesan"],
            "a dish with courgette and parmesan",
            ["courgette", "parmesan"],
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
    for i, (_label, canonical, desc, colloquial_ings) in enumerate(paraphrase_syn_queries, start=1):
        add(
            f"para_syn_{i:02d}", "paraphrase_syn", desc,
            ingredients=colloquial_ings,
            predicate=lambda r, names=canonical: _has_all_ingredients(r, names),
        )

    paraphrase_oov_queries = [
        (
            "leftover roast chicken with ginger",
            ["chicken breast", "ginger"],
            "a way to use up leftover roast chicken with some fresh ginger",
            ["leftover roast chicken", "ginger"],
        ),
        ("bean curd", ["tofu"], "a recipe using bean curd", ["bean curd"]),
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
            "double cream and sugar",
            ["heavy cream", "sugar"],
            "a dessert using double cream and sugar",
            ["double cream", "sugar"],
        ),
        (
            "streaky bacon and eggs",
            ["bacon", "egg"],
            "streaky bacon and eggs for breakfast",
            ["streaky bacon", "eggs"],
        ),
        (
            "mince and onion",
            ["ground beef", "onion"],
            "mince and onion for dinner",
            ["mince", "onion"],
        ),
        (
            "gammon and potato",
            ["ham", "potato"],
            "a gammon and potato bake",
            ["gammon", "potato"],
        ),
        (
            "rotisserie chicken and rice",
            ["chicken breast", "rice"],
            "a quick meal with rotisserie chicken and rice",
            ["rotisserie chicken", "rice"],
        ),
    ]
    for i, (_label, canonical, desc, colloquial_ings) in enumerate(paraphrase_oov_queries, start=1):
        add(
            f"para_oov_{i:02d}", "paraphrase_oov", desc,
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
