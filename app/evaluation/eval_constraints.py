from app.schemas.recipe import Recipe
from app.schemas.user import UserProfile
from app.services.constraint_engine import validate_recipe


def evaluate_constraint_set(recipes: list[Recipe], user_profile: UserProfile) -> dict[str, int]:
    results = [validate_recipe(recipe, user_profile) for recipe in recipes]
    return {
        "valid": sum(1 for result in results if result.is_valid),
        "rejected": sum(1 for result in results if not result.is_valid),
    }
