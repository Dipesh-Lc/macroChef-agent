"""Diet-leak audit: for vegan/vegetarian/gluten-free/dairy-free, measure what
fraction of the recipes app.services.constraint_engine.validate_recipe marks
"safe" for that diet actually still contain an excluded ingredient.

Deliberately independent of constraint_engine's own term tables (MEAT_ALIASES,
ALLERGEN_ALIASES, DIET_TYPE_EXCLUDED_TERMS). If this script imported those and
matched against them, a "leak" would be structurally impossible to find --
this would just be re-running the production code against itself. The term
lists below are hand-authored separately, from the same kind of general
food-vocabulary knowledge a human auditor would use, precisely so this can
catch cases where the production tables are wrong or incomplete.

Usage: python scripts/audit_diet_leaks.py [path/to/imported_recipes.jsonl]
Exits nonzero if any diet type has a nonzero leak rate, so this can be wired
into CI directly as a release gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets, UserProfile
from app.services.constraint_engine import validate_recipe
from app.utils.ingredient_normalizer import normalize_ingredient

DEFAULT_CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "imported_recipes.jsonl"

# --- Independent ground-truth vocabulary (NOT shared with constraint_engine) ---

GROUND_TRUTH_MEAT_POULTRY_FISH = {
    "anchovy", "anchovies", "bacon", "beef", "beef broth", "beef stock", "bologna",
    "bratwurst", "brisket", "calamari", "capon", "catfish", "caviar", "chicken",
    "chicken broth", "chicken stock", "chorizo", "clam", "clams", "cod", "crab",
    "crabmeat", "crawfish", "crayfish", "duck", "fish", "fish sauce", "flounder",
    "gelatin", "goose", "grouper", "haddock", "halibut", "ham", "hamburger",
    "hot dog", "lamb", "lard", "lobster", "mackerel", "meatball", "mussel",
    "mussels", "octopus", "oyster", "oysters", "pancetta", "pepperoni", "perch",
    "pheasant", "pork", "prawn", "prawns", "prosciutto", "quail", "rabbit",
    "salami", "salmon", "sardine", "sardines", "sausage", "scallop", "scallops",
    "shrimp", "sirloin", "snapper", "sole", "squid", "steak", "suet", "swordfish",
    "tilapia", "tripe", "trout", "tuna", "turkey", "veal", "venison",
    "white fish", "worcestershire",
}

GROUND_TRUTH_DAIRY = {
    "brie", "butter", "buttermilk", "camembert", "casein", "cheddar", "cheese",
    "cottage cheese", "cream", "cream cheese", "creme fraiche", "curd", "custard",
    "feta", "ghee", "gouda", "gruyere", "half and half", "heavy cream", "ice cream",
    "kefir", "lactose", "mascarpone", "milk", "mozzarella", "paneer", "parmesan",
    "provolone", "queso", "ricotta", "sour cream", "swiss cheese", "whey",
    "whipped cream", "whipping cream", "yogurt", "yoghurt",
}

GROUND_TRUTH_EGG = {"egg", "eggs", "egg white", "egg whites", "egg yolk", "mayonnaise", "meringue"}
GROUND_TRUTH_HONEY = {"honey"}
GROUND_TRUTH_GLUTEN = {
    "barley", "biscuit", "bread", "breadcrumb", "breadcrumbs", "bulgur", "cake flour",
    "couscous", "cracker", "crackers", "croutons", "farro", "flour",
    "graham cracker", "malt", "orzo", "pasta", "pastry",
    "pita", "pretzel", "rye", "seitan", "semolina", "spaghetti", "tortilla",
    "wheat", "wheat germ",
    # Deliberately NOT bare "noodle"/"noodles": cellophane/rice noodles are
    # genuinely gluten-free, and that generic a term would false-flag them.
    # Deliberately NOT "durum": bidirectional substring matching makes it
    # collide with the common ingredient "rum" ("rum" is a substring of
    # "durum"), a false positive with no real durum-vocabulary payoff --
    # "wheat"/"semolina"/"flour" already catch genuine durum-wheat products.
}

DIET_GROUND_TRUTH = {
    "vegetarian": GROUND_TRUTH_MEAT_POULTRY_FISH,
    "vegan": GROUND_TRUTH_MEAT_POULTRY_FISH | GROUND_TRUTH_DAIRY | GROUND_TRUTH_EGG | GROUND_TRUTH_HONEY,
    "gluten-free": GROUND_TRUTH_GLUTEN,
    "dairy-free": GROUND_TRUTH_DAIRY,
}


def _load_corpus(path: Path) -> list[Recipe]:
    recipes = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            recipes.append(Recipe.model_validate(json.loads(line)))
    return recipes


def _recipe_ingredient_terms(recipe: Recipe) -> set[str]:
    terms: set[str] = set()
    for item in recipe.ingredients:
        raw = item.name.lower().strip()
        if raw:
            terms.add(raw)
        normalized = normalize_ingredient(item.name).lower().strip()
        if normalized:
            terms.add(normalized)
    return terms


def _ground_truth_violates(recipe: Recipe, excluded_terms: set[str]) -> bool:
    # One-directional on purpose: does a known excluded word appear WITHIN an
    # ingredient's name (e.g. "milk" in "buttermilk")? The reverse direction
    # (ingredient name is a substring of the excluded word) isn't needed for a
    # fixed, already-specific ground-truth vocabulary, and it actively causes
    # false positives for short ingredient words that happen to appear inside
    # an unrelated longer excluded word (e.g. "rum" in "breadcrumb").
    ingredient_terms = _recipe_ingredient_terms(recipe)
    for excluded in excluded_terms:
        for ingredient_term in ingredient_terms:
            if excluded in ingredient_term:
                return True
    return False


def audit(corpus: list[Recipe], diet_type: str) -> dict:
    profile = UserProfile(user_id="audit", macro_targets=MacroTargets(), diet_type=diet_type)
    ground_truth_terms = DIET_GROUND_TRUTH[diet_type]

    passed = [r for r in corpus if validate_recipe(r, profile).is_valid]
    leaking = [r for r in passed if _ground_truth_violates(r, ground_truth_terms)]

    return {
        "diet_type": diet_type,
        "corpus_size": len(corpus),
        "passed_filter": len(passed),
        "leaking": len(leaking),
        "leak_rate": (len(leaking) / len(passed)) if passed else 0.0,
        "sample_leaks": [{"recipe_id": r.recipe_id, "title": r.title} for r in leaking[:10]],
    }


def main() -> int:
    corpus_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CORPUS_PATH
    corpus = _load_corpus(corpus_path)

    print(f"Loaded {len(corpus)} recipes from {corpus_path}")
    print()

    any_leak = False
    for diet_type in ["vegan", "vegetarian", "gluten-free", "dairy-free"]:
        result = audit(corpus, diet_type)
        any_leak = any_leak or result["leaking"] > 0
        print(f"=== {diet_type} ===")
        print(f"  passed filter: {result['passed_filter']} / {result['corpus_size']}")
        print(f"  leaking:       {result['leaking']}")
        print(f"  leak rate:     {result['leak_rate']:.1%}")
        if result["sample_leaks"]:
            print("  sample leaks:")
            for leak in result["sample_leaks"]:
                print(f"    - {leak['title']} ({leak['recipe_id']})")
        print()

    return 1 if any_leak else 0


if __name__ == "__main__":
    raise SystemExit(main())
