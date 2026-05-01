from app.schemas.recipe import Recipe
from app.services import recipe_indexing_service
from app.services.recipe_indexing_service import (
    RecipeIndexingService,
    build_recipe_search_document,
    recipe_index_metadata,
)


def _recipe() -> Recipe:
    return Recipe(
        recipe_id="user_test_recipe",
        title="Japanese Chicken Rice Bowl",
        cuisine="Japanese",
        meal_type="dinner",
        description="A user-saved bowl.",
        ingredients=["150 g chicken breast", "150 g rice", "20 g soy sauce"],
        instructions=["Cook rice.", "Sear chicken."],
        allergens=["soy"],
        diet_tags=["high-protein", "dairy-free"],
        cook_time_min=25,
        calories=560,
        protein_g=45,
        carbs_g=60,
        fat_g=12,
        fiber_g=6,
        owner_user_id="u1",
        is_user_saved=True,
        source_type="mock",
    )


def test_recipe_search_document_contains_structured_fields() -> None:
    document = build_recipe_search_document(_recipe())

    assert "Japanese Chicken Rice Bowl" in document
    assert "Cuisine: Japanese" in document
    assert "150 g chicken breast" in document
    assert "high-protein" in document


def test_metadata_includes_user_fields_and_allergens() -> None:
    metadata = recipe_index_metadata(_recipe())

    assert metadata["owner_user_id"] == "u1"
    assert metadata["is_user_saved"] is True
    assert metadata["source_type"] == "mock"
    assert metadata["contains_soy"] is True


def test_indexing_uses_collection_without_crashing(monkeypatch) -> None:
    captured = {}

    class FakeCollection:
        def upsert(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(recipe_indexing_service, "get_chroma_collection", lambda: FakeCollection())

    count = RecipeIndexingService(repository=None).index_recipes([_recipe()])

    assert count == 1
    assert captured["ids"] == ["user_test_recipe"]
