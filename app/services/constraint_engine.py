from app.schemas.recommendation import ValidationResult
from app.schemas.recipe import Recipe
from app.schemas.user import NO_RESTRICTION_DIET_TYPES, UserProfile
from app.utils.ingredient_normalizer import ingredient_matches, normalize_ingredient


ALLERGEN_ALIASES = {
    "dairy": {
        "butter",
        "casein",
        "cheddar",
        "cheese",
        "cream",
        "feta",
        "ghee",
        "Greek yogurt",
        "half and half",
        "half-and-half",
        "lactose",
        "mascarpone",
        "milk",
        "mozzarella",
        "paneer",
        "parmesan",
        "ricotta",
        "whey",
        "yogurt",
    },
    "milk": {
        "butter",
        "casein",
        "cheddar",
        "cheese",
        "cream",
        "feta",
        "ghee",
        "Greek yogurt",
        "half and half",
        "half-and-half",
        "lactose",
        "mascarpone",
        "milk",
        "mozzarella",
        "paneer",
        "parmesan",
        "ricotta",
        "whey",
        "yogurt",
    },
    "peanut": {"groundnut", "peanut", "peanut butter", "peanut oil", "peanuts"},
    "peanuts": {"groundnut", "peanut", "peanut butter", "peanut oil", "peanuts"},
    "tree nut": {
        "almond",
        "almonds",
        "cashew",
        "hazelnut",
        "macadamia",
        "pecan",
        "pistachio",
        "walnut",
    },
    "nuts": {
        "almond",
        "almonds",
        "cashew",
        "hazelnut",
        "macadamia",
        "peanut",
        "peanut butter",
        "pecan",
        "pistachio",
        "walnut",
    },
    "gluten": {
        "barley",
        "biscuit",
        "bread",
        "bulgur",
        "couscous",
        "cracker",
        "crouton",
        "farro",
        "fettuccine",
        "filo",
        "flour",
        "graham cracker",
        "lasagna",
        "linguine",
        "macaroni",
        # "malt" (barley-derived) is gluten but not wheat -- listed here only,
        # not in the "wheat" set below.
        "malt",
        "pasta",
        "pastry",
        "phyllo",
        "semolina",
        # "spaghetti" also substring-matches "spaghetti squash" (a vegetable,
        # gluten-free in reality) -- accepted as an over-cautious false
        # positive rather than a missed detection, consistent with existing
        # "cornflour"/"eggplant" substring trade-offs elsewhere in this file.
        "spaghetti",
        "rye",
        "seitan",
        "tortilla",
        "wheat",
        "whole wheat pasta",
    },
    "wheat": {
        "biscuit",
        "bread",
        "bulgur",
        "couscous",
        "cracker",
        "crouton",
        "farro",
        "fettuccine",
        "filo",
        "flour",
        "graham cracker",
        "lasagna",
        "linguine",
        "macaroni",
        "pasta",
        "pastry",
        "phyllo",
        "semolina",
        "spaghetti",
        "seitan",
        "tortilla",
        "wheat",
        "whole wheat pasta",
    },
    "soy": {"edamame", "miso", "soy", "soy sauce", "soya", "tamari", "tempeh", "tofu"},
    "soya": {"edamame", "miso", "soy", "soy sauce", "soya", "tamari", "tempeh", "tofu"},
    "egg": {"egg", "egg whites", "eggs", "mayonnaise"},
    "eggs": {"egg", "egg whites", "eggs", "mayonnaise"},
    "shellfish": {
        "clam",
        "crab",
        "crayfish",
        "lobster",
        "mussel",
        "oyster",
        "prawn",
        "scallop",
        "shellfish",
        "shrimp",
    },
    "crustacean": {"crab", "crayfish", "lobster", "prawn", "shrimp"},
    "fish": {
        "anchovy",
        "cod",
        "fish",
        "flounder",
        "haddock",
        "halibut",
        "salmon",
        "sardine",
        "snapper",
        "sole",
        "trout",
        "tuna",
        "white fish",
    },
    "seafood": {
        "anchovy",
        "clam",
        "cod",
        "flounder",
        "haddock",
        "halibut",
        "snapper",
        "sole",
        "trout",
        "crab",
        "fish",
        "lobster",
        "mussel",
        "oyster",
        "salmon",
        "sardine",
        "scallop",
        "shellfish",
        "shrimp",
        "tuna",
    },
    "sesame": {"sesame", "sesame oil", "sesame seeds", "tahini"},
}

# Meat/poultry (and their processed/derived forms) aren't in ALLERGEN_ALIASES
# because they aren't allergens, but they're what makes a recipe non-vegetarian.
# Fish/shellfish/seafood are deliberately NOT duplicated here -- vegetarian and
# vegan reuse ALLERGEN_ALIASES's fish/shellfish/seafood/crustacean sets below
# so there is exactly one, already-tested substring-matching definition of
# "does this recipe contain fish" for both allergy and diet-type checks to
# share, instead of two lists that can silently drift apart (that drift, for
# dairy/gluten, was root-cause of the 2026-07 corpus diet-leak audit).
#
# Sourced from the 2026-07 corpus diet-leak audit (43.7% vegan / 9.4%
# vegetarian leak rate against the 4,238-recipe Food.com import). Extend this
# set, not a separate list, if a future audit finds another gap. No need for
# compound entries like "chicken broth"/"beef stock": _recipe_contains_any_term
# substring-matches the bare "chicken"/"beef" against those directly.
MEAT_ALIASES = {
    "bacon",
    "beef",
    "chicken",
    "chorizo",
    "duck",
    "gelatin",
    "goose",
    "ham",
    "hot dog",
    "lamb",
    "lard",
    "pancetta",
    "pepperoni",
    "pork",
    "prosciutto",
    "rabbit",
    "sausage",
    "steak",
    "suet",
    "turkey",
    "veal",
    "worcestershire",
}
HONEY_ALIASES = {"honey"}

_VEGETARIAN_EXCLUDED_TERMS = (
    MEAT_ALIASES
    | ALLERGEN_ALIASES["fish"]
    | ALLERGEN_ALIASES["shellfish"]
    | ALLERGEN_ALIASES["seafood"]
    | ALLERGEN_ALIASES["crustacean"]
)
# Vegan = vegetarian's exclusions plus the animal products vegetarians still
# eat (dairy, eggs, honey). Dairy/egg terms come from the same ALLERGEN_ALIASES
# sets contains_allergen uses -- this is also why "butter", "parmesan", "sour
# cream", "mayonnaise", and "heavy cream" (all audit-surfaced vegan leaks) need
# no separate entry here: they already substring-match "cream"/"cheese"/"egg"
# etc. via the shared alias sets.
_VEGAN_EXCLUDED_TERMS = _VEGETARIAN_EXCLUDED_TERMS | ALLERGEN_ALIASES["dairy"] | ALLERGEN_ALIASES["egg"] | HONEY_ALIASES

DIET_TYPE_EXCLUDED_TERMS = {
    "vegetarian": _VEGETARIAN_EXCLUDED_TERMS,
    "vegan": _VEGAN_EXCLUDED_TERMS,
}


def _normalized_terms(values: list[str] | set[str]) -> set[str]:
    terms: set[str] = set()
    for value in values:
        normalized = normalize_ingredient(value)
        if normalized:
            terms.add(normalized.lower())
        if value:
            terms.add(value.lower().strip())
    return {term for term in terms if term}


def _expand_allergen_terms(allergies: list[str]) -> set[str]:
    terms = _normalized_terms(allergies)
    expanded = set(terms)
    for allergy in terms:
        expanded.update(_normalized_terms(ALLERGEN_ALIASES.get(allergy, set())))
    return expanded


def _recipe_safety_terms(recipe: Recipe) -> set[str]:
    # Safety is name-based and quantity-independent: an allergen present in any
    # amount is a violation, so only ingredient names (never amount/unit) feed
    # allergen matching.
    return _normalized_terms([*(item.name for item in recipe.ingredients), *recipe.allergens])


def derive_allergen_labels(ingredient_names: list[str]) -> list[str]:
    """Deterministically derive which ALLERGEN_ALIASES keys a set of ingredient
    names implies, using the same membership table as contains_allergen. This
    is the reverse direction: given ingredients, produce labels (used for
    imported/candidate recipes' `allergens` field and for Chroma index
    metadata) rather than given an allergy, test membership. Never trust a
    source-provided allergen field for imports — derive it here instead.

    Deliberately returns every matching ALLERGEN_ALIASES key as-is (e.g. both
    "dairy" and "milk" if either fires — their alias sets are identical, so
    they always co-match) rather than collapsing synonyms to one canonical
    label per class. Collapsing would require an opinionated synonym->label
    mapping (e.g. is a "seafood" match reported as "fish"?) that isn't implied
    by the existing table and would change which labels appear without any
    test coverage backing that choice — a needless risk in an allergen-safety
    path. Callers needing metadata-flag membership (recipe_indexing_service)
    only ever check the 8 canonical keys directly, so this is a drop-in,
    behavior-preserving replacement for the equivalent inline logic it lifts.
    """
    terms = _normalized_terms(ingredient_names)
    labels: set[str] = set()
    for allergen_key, aliases in ALLERGEN_ALIASES.items():
        alias_terms = _normalized_terms(aliases)
        if allergen_key in terms or terms & alias_terms:
            labels.add(allergen_key)
    return sorted(labels)


def _recipe_contains_any_term(recipe: Recipe, terms: set[str]) -> bool:
    # Deliberately NOT ingredient_matches(term, recipe_term) here: that function
    # re-runs normalize_ingredient on `term` internally, which re-applies
    # SYNONYMS on top of the normalization _normalized_terms already did when
    # building `terms`. For a broad category word like "chicken", SYNONYMS
    # maps it to a specific cut ("chicken breast"), which then fails to
    # substring-match every OTHER cut ("chicken drumstick", "chicken broth",
    # "chicken bouillon", ...) -- silently defeating "chicken" as an exclusion
    # term for anything but literal chicken breast. `terms` and `recipe_terms`
    # are both already fully normalized (via _normalized_terms, which keeps
    # both the raw and normalized form of each value), so a direct substring
    # test is sufficient and doesn't re-trigger that collision.
    recipe_terms = _recipe_safety_terms(recipe)
    for term in terms:
        for recipe_term in recipe_terms:
            if term == recipe_term or term in recipe_term or recipe_term in term:
                return True
    return False


def contains_allergen(recipe: Recipe, allergies: list[str]) -> bool:
    return _recipe_contains_any_term(recipe, _expand_allergen_terms(allergies))


def contains_disliked_ingredient(recipe: Recipe, disliked_ingredients: list[str]) -> bool:
    for disliked in disliked_ingredients:
        if any(ingredient_matches(disliked, item.name) for item in recipe.ingredients):
            return True
    return False


def violates_diet_type(recipe: Recipe, diet_type: str | None) -> bool:
    if not diet_type or diet_type.lower() in NO_RESTRICTION_DIET_TYPES:
        return False

    requested = diet_type.lower()
    recipe_tags = {tag.lower() for tag in recipe.diet_tags}
    if requested in recipe_tags:
        return False

    if requested == "gluten-free":
        # Same substring-matching path as contains_allergen, not recipe.allergens
        # (which derive_allergen_labels populates via exact-set membership and
        # misses compound names like "buttermilk" or "gravy" -- see audit).
        return contains_allergen(recipe, ["gluten"])
    if requested == "dairy-free":
        return contains_allergen(recipe, ["dairy"])
    if requested in DIET_TYPE_EXCLUDED_TERMS:
        return _recipe_contains_any_term(recipe, _normalized_terms(DIET_TYPE_EXCLUDED_TERMS[requested]))

    # UserProfile.diet_type is validated against SUPPORTED_DIET_TYPES at
    # intake (app.schemas.user), so an unrecognized value here means a caller
    # (e.g. RecipeDiscoveryRequest, which has its own freeform diet_type) is
    # asking about a diet_type this function was never taught to enforce.
    # Returning False would silently claim the recipe is safe for that diet;
    # fail loudly instead.
    raise ValueError(f"violates_diet_type does not enforce diet_type {diet_type!r}")


def violates_cook_time(recipe: Recipe, max_cook_time: int | None) -> bool:
    return bool(max_cook_time and recipe.cook_time_min and recipe.cook_time_min > max_cook_time)


def validate_recipe(recipe: Recipe, user_profile: UserProfile) -> ValidationResult:
    if contains_allergen(recipe, user_profile.allergies):
        return ValidationResult(is_valid=False, rejection_reason="Contains a user allergen")
    if contains_disliked_ingredient(recipe, user_profile.disliked_ingredients):
        return ValidationResult(is_valid=False, rejection_reason="Contains a disliked ingredient")
    if violates_diet_type(recipe, user_profile.diet_type):
        return ValidationResult(is_valid=False, rejection_reason=f"Violates diet type: {user_profile.diet_type}")
    if violates_cook_time(recipe, user_profile.max_cook_time_min):
        return ValidationResult(is_valid=False, rejection_reason="Exceeds maximum cooking time")
    return ValidationResult(is_valid=True)
