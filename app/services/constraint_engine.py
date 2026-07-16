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
    # Satay/saté sauce is a peanut-based sauce (ground peanuts, oil, and
    # aromatics) in its standard Southeast Asian preparations -- by
    # definition, not a sourced claim. Peanut is a major allergen designated
    # by FALCPA (21 U.S.C. Sec. 321(qq)) and by EU Regulation 1169/2011,
    # Annex II, point 5 ("Peanuts") -- those two statute/regulation cites are
    # verified. "sate"/"saté" are accepted alternate transliterations of the
    # same dish/sauce.
    "peanut": {
        "groundnut",
        "peanut",
        "peanut butter",
        "peanut oil",
        "peanuts",
        "sate",
        "satay",
        "satay sauce",
        "saté",
    },
    "peanuts": {
        "groundnut",
        "peanut",
        "peanut butter",
        "peanut oil",
        "peanuts",
        "sate",
        "satay",
        "satay sauce",
        "saté",
    },
    "tree nut": {
        "almond",
        "almonds",
        # Amaretti (Italian almond macaroons), marzipan, frangipane, praline,
        # nougat, and gianduja are almond- and/or hazelnut-based confections
        # or pastes by definition (not merely "may contain" products), so
        # they are sourceable additions rather than a general/unsourced
        # audit expansion.
        "amaretti",
        # Amaretto (the liqueur): the dominant commercial brand (Disaronno)
        # is apricot-kernel-based and marketed as nut-free, but some other
        # amaretto brands/recipes are almond-based, and AAAAI guidance notes
        # post-distillation nut infusions/flavorings can still trigger
        # reactions; FARE's "foods and ingredients to avoid" guidance for
        # tree-nut allergy includes nut extracts and nut-flavored
        # distillates generally. Given that ambiguity, this project's policy
        # (see the nougat/Worcestershire over-blocking notes below) resolves
        # toward blocking rather than excluding by base rate. Note: because
        # matching is substring-based, "amaretti" above does NOT also match
        # "amaretto" -- it is listed here as its own explicit entry.
        "amaretto",
        # Brazil nut is a tree nut explicitly named alongside almond,
        # hazelnut, walnut, cashew, pecan, pistachio, and macadamia in EU
        # Regulation 1169/2011, Annex II, point 8 ("Nuts"), and in FDA's
        # FALCPA tree-nut guidance.
        "brazil nut",
        "brazil nuts",
        "cashew",
        # Frangipane is, by definition, an almond-cream pastry filling
        # (ground almonds, butter, sugar, egg) -- not a source-verified
        # claim; FARE's published tree-nut hidden-sources list does not
        # currently name frangipane explicitly.
        "frangipane",
        # Gianduja is, by definition, a hazelnut-and-chocolate paste (the
        # base of Nutella-style spreads) -- FARE's tree-nut hidden-sources
        # guidance lists it explicitly.
        "gianduja",
        "hazelnut",
        "macadamia",
        # Marzipan is almond paste (ground almonds + sugar) by definition;
        # FARE's tree-nut hidden-sources guidance names marzipan as a common
        # concealed tree-nut source.
        "marzipan",
        # Traditional nougat (e.g. nougat de Montelimar, and the nougat in
        # many chocolate bars) contains almonds and/or hazelnuts by
        # definition. FARE's PEANUT page (not the tree-nut page) lists
        # "Nougat and marzipan" as possible peanut sources; the tree-nut
        # classification here rests on the definitional almond/hazelnut
        # content, not on that peanut-page citation. This over-blocks the
        # rarer nut-free nougat -- an accepted tradeoff for an
        # anaphylaxis-class allergen (see the Worcestershire/fish note below
        # for the same reasoning applied to fish).
        "nougat",
        "pecan",
        # Pine nut is retained as a tree nut in FDA's January 2025 Edition 5
        # "Questions and Answers Regarding Food Allergens" guidance, which
        # narrowed the previously ~23-item tree-nut list to 12 named tree
        # nuts and kept "Pine nut (Pinon nut)" among them.
        "pine nut",
        "pine nuts",
        "pistachio",
        # Praline paste (French/Belgian confectionery) is traditionally
        # almond- and/or hazelnut-based; American-style pralines are
        # pecan-based. Either way it is tree-nut derived -- FARE's tree-nut
        # hidden-sources guidance lists praline.
        "praline",
        "walnut",
    },
    # "nuts" mirrors both the "tree nut" and "peanut" alias vocabularies
    # above (see those sets' inline comments for the citation behind each
    # addition); no new citations are introduced here.
    "nuts": {
        "almond",
        "almonds",
        "amaretti",
        "amaretto",
        "brazil nut",
        "brazil nuts",
        "cashew",
        "frangipane",
        "gianduja",
        "groundnut",
        "hazelnut",
        "macadamia",
        "marzipan",
        "nougat",
        "peanut",
        "peanut butter",
        "peanut oil",
        "pecan",
        "pine nut",
        "pine nuts",
        "pistachio",
        "praline",
        "sate",
        "satay",
        "satay sauce",
        "saté",
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
        # Traditional Worcestershire sauce is fermented with anchovies, a
        # fish allergen under FALCPA and under EU Regulation 1169/2011,
        # Annex II, point 4 ("Fish"); FARE (Food Allergy Research &
        # Education)'s fish page lists Worcestershire sauce as a common
        # hidden source of fish. Anchovy-free "vegan" Worcestershire-style
        # sauces do exist, so this over-blocks them -- an accepted tradeoff
        # for an anaphylaxis-class allergen, where a false positive costs
        # one recipe and a false negative can be fatal. "worcestershire"
        # already appears in MEAT_ALIASES below for the unrelated
        # vegetarian/vegan diet-type check; this is an additive, independent
        # entry in the allergen table and does not change that path.
        "worcestershire",
        "worcestershire sauce",
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
        # Worcestershire sauce is fish-derived (fermented anchovies) -- see
        # the "fish" set's citation above for the FALCPA/EU/FARE basis.
        # "seafood" is a superset covering fish + shellfish, so it needs the
        # same entry to avoid a gap where "fish" blocks it but "seafood"
        # does not.
        "worcestershire",
        "worcestershire sauce",
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
