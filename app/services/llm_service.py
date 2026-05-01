from app.schemas.recipe import Recipe
from app.schemas.recommendation import RecipeScore
from app.services.model_provider import (
    generate_explanation_with_provider_chain,
    template_explanation,
)


def explain_recommendation(recipe: Recipe, score: RecipeScore, allergy_safe: bool = True) -> str:
    return generate_explanation_with_provider_chain(recipe, score, allergy_safe)


__all__ = ["explain_recommendation", "template_explanation"]
