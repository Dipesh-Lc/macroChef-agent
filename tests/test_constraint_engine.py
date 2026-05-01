from app.schemas.recipe import Recipe
from app.schemas.user import MacroTargets, UserProfile
from app.services.constraint_engine import validate_recipe


def _profile(**kwargs) -> UserProfile:
    return UserProfile(user_id="u", macro_targets=MacroTargets(), **kwargs)


def _recipe(**kwargs) -> Recipe:
    defaults = {
        "recipe_id": "r",
        "title": "Test Recipe",
        "ingredients": ["rice", "spinach"],
        "instructions": ["Cook."],
        "allergens": [],
        "diet_tags": ["gluten-free"],
        "cook_time_min": 20,
    }
    defaults.update(kwargs)
    return Recipe(**defaults)


def test_rejects_peanut_recipe_for_peanut_allergy() -> None:
    recipe = _recipe(ingredients=["tofu", "peanut butter"], allergens=["peanut"])
    result = validate_recipe(recipe, _profile(allergies=["peanut"]))

    assert not result.is_valid
    assert "allergen" in result.rejection_reason.lower()


def test_rejects_dairy_recipe_for_dairy_allergy() -> None:
    recipe = _recipe(ingredients=["Greek yogurt", "berries"], allergens=["dairy"])
    result = validate_recipe(recipe, _profile(allergies=["dairy"]))

    assert not result.is_valid


def test_rejects_milk_alias_for_parmesan() -> None:
    recipe = _recipe(ingredients=["zucchini noodles", "parmesan"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["milk"]))

    assert not result.is_valid


def test_rejects_tree_nut_alias_for_almond_flour() -> None:
    recipe = _recipe(ingredients=["ground turkey", "almond flour"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["tree nut"]))

    assert not result.is_valid


def test_rejects_seafood_alias_for_salmon() -> None:
    recipe = _recipe(ingredients=["salmon", "rice", "cucumber"], allergens=[])
    result = validate_recipe(recipe, _profile(allergies=["seafood"]))

    assert not result.is_valid


def test_rejects_disliked_ingredient() -> None:
    recipe = _recipe(ingredients=["rice", "mushroom"])
    result = validate_recipe(recipe, _profile(disliked_ingredients=["mushroom"]))

    assert not result.is_valid
    assert "disliked" in result.rejection_reason.lower()


def test_rejects_over_max_cook_time() -> None:
    recipe = _recipe(cook_time_min=45)
    result = validate_recipe(recipe, _profile(max_cook_time_min=30))

    assert not result.is_valid
    assert "time" in result.rejection_reason.lower()


def test_allows_safe_recipe() -> None:
    recipe = _recipe()
    result = validate_recipe(recipe, _profile(allergies=["peanut"], max_cook_time_min=30))

    assert result.is_valid
