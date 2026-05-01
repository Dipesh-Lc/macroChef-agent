from app.schemas.recipe import Recipe
from app.services import recipe_retriever as retriever_module
from app.services.recipe_retriever import RecipeRetriever


class FakeLibraryRepository:
    def __init__(self, recipes_by_user: dict[str, list[Recipe]] | None = None):
        self.recipes_by_user = recipes_by_user or {}

    def list_user_recipes(self, user_id: str) -> list[Recipe]:
        return self.recipes_by_user.get(user_id, [])


def test_retrieves_recipes_from_sample_data(monkeypatch) -> None:
    monkeypatch.setattr(retriever_module, "collection_count", lambda: 0)
    retriever = RecipeRetriever(library_repository=FakeLibraryRepository())

    recipes = retriever.retrieve(["chicken breast", "rice", "spinach"], limit=5)

    assert recipes
    assert any("Chicken" in recipe.title for recipe in recipes)


def test_applies_metadata_preferences_in_fallback(monkeypatch) -> None:
    monkeypatch.setattr(retriever_module, "collection_count", lambda: 0)
    retriever = RecipeRetriever(library_repository=FakeLibraryRepository())

    recipes = retriever.retrieve(
        ["chicken breast", "rice"],
        cuisine_preference="Japanese",
        meal_type="dinner",
        limit=3,
    )

    assert recipes[0].cuisine == "Japanese"


def test_has_fallback_behavior(monkeypatch) -> None:
    monkeypatch.setattr(retriever_module, "collection_count", lambda: 0)
    retriever = RecipeRetriever(library_repository=FakeLibraryRepository())

    recipes = retriever.retrieve(["unlikely mystery ingredient"], limit=4)

    assert len(recipes) == 4


def test_user_saved_recipes_can_be_retrieved(monkeypatch) -> None:
    monkeypatch.setattr(retriever_module, "collection_count", lambda: 0)
    saved = Recipe(
        recipe_id="user_r1",
        title="User Teriyaki Chicken Rice Bowl",
        cuisine="Japanese",
        meal_type="dinner",
        ingredients=["chicken breast", "rice", "spinach"],
        instructions=["Cook rice.", "Cook chicken."],
        owner_user_id="alice",
        is_user_saved=True,
    )
    retriever = RecipeRetriever(
        library_repository=FakeLibraryRepository({"alice": [saved], "bob": []})
    )

    recipes = retriever.retrieve(
        ["chicken breast", "rice"],
        cuisine_preference="Japanese",
        meal_type="dinner",
        limit=5,
        user_id="alice",
    )

    assert any(recipe.recipe_id == "user_r1" for recipe in recipes)


def test_user_cannot_retrieve_another_users_private_recipes(monkeypatch) -> None:
    monkeypatch.setattr(retriever_module, "collection_count", lambda: 0)
    private = Recipe(
        recipe_id="user_private",
        title="Private Chicken Bowl",
        cuisine="Japanese",
        meal_type="dinner",
        ingredients=["chicken breast", "rice"],
        instructions=["Cook rice.", "Cook chicken."],
        owner_user_id="alice",
        is_user_saved=True,
    )
    retriever = RecipeRetriever(library_repository=FakeLibraryRepository({"alice": [private]}))

    recipes = retriever.retrieve(["chicken breast", "rice"], limit=10, user_id="bob")

    assert all(recipe.recipe_id != "user_private" for recipe in recipes)
