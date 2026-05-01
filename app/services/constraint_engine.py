from app.schemas.recommendation import ValidationResult
from app.schemas.recipe import Recipe
from app.schemas.user import UserProfile
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
        "lactose",
        "milk",
        "mozzarella",
        "paneer",
        "parmesan",
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
        "lactose",
        "milk",
        "mozzarella",
        "paneer",
        "parmesan",
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
        "bread",
        "bulgur",
        "couscous",
        "farro",
        "flour",
        "pasta",
        "rye",
        "seitan",
        "tortilla",
        "wheat",
        "whole wheat pasta",
    },
    "wheat": {
        "bread",
        "bulgur",
        "couscous",
        "farro",
        "flour",
        "pasta",
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
    "fish": {"anchovy", "cod", "fish", "salmon", "sardine", "tuna", "white fish"},
    "seafood": {
        "anchovy",
        "clam",
        "cod",
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

DIET_BLOCKERS = {
    "vegetarian": {"chicken", "beef", "pork", "turkey", "salmon", "shrimp", "tuna", "fish"},
    "vegan": {
        "chicken",
        "beef",
        "pork",
        "turkey",
        "salmon",
        "shrimp",
        "tuna",
        "fish",
        "egg",
        "eggs",
        "yogurt",
        "Greek yogurt",
        "cheese",
        "milk",
        "honey",
    },
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
    return _normalized_terms([*recipe.ingredients, *recipe.allergens])


def contains_allergen(recipe: Recipe, allergies: list[str]) -> bool:
    allergy_terms = _expand_allergen_terms(allergies)
    recipe_terms = _recipe_safety_terms(recipe)
    for allergy_term in allergy_terms:
        if allergy_term in recipe_terms:
            return True
        if any(ingredient_matches(allergy_term, recipe_term) for recipe_term in recipe_terms):
            return True
    return False


def contains_disliked_ingredient(recipe: Recipe, disliked_ingredients: list[str]) -> bool:
    for disliked in disliked_ingredients:
        if any(ingredient_matches(disliked, ingredient) for ingredient in recipe.ingredients):
            return True
    return False


def violates_diet_type(recipe: Recipe, diet_type: str | None) -> bool:
    if not diet_type or diet_type.lower() in {"none", "omnivore", "no restriction"}:
        return False

    requested = diet_type.lower()
    recipe_tags = {tag.lower() for tag in recipe.diet_tags}
    if requested in recipe_tags:
        return False

    if requested == "gluten-free":
        return "gluten" in {item.lower() for item in recipe.allergens}
    if requested == "dairy-free":
        return "dairy" in {item.lower() for item in recipe.allergens}
    if requested in DIET_BLOCKERS:
        blockers = DIET_BLOCKERS[requested]
        return any(ingredient_matches(blocker, ingredient) for blocker in blockers for ingredient in recipe.ingredients)

    return False


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
