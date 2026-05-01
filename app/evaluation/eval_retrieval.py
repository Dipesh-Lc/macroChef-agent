from app.services.recipe_retriever import RecipeRetriever


def evaluate_retrieval_smoke(query_ingredients: list[str]) -> dict[str, object]:
    retriever = RecipeRetriever()
    recipes = retriever.retrieve(query_ingredients, limit=5)
    return {"count": len(recipes), "titles": [recipe.title for recipe in recipes]}
