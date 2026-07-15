from app.schemas.nutrition import FoodMacros, GroundingStatus, RecipeNutrition
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
    # The search document indexes ingredient names (quantities are retrieval noise).
    assert "chicken breast" in document
    assert "high-protein" in document


def test_metadata_includes_user_fields_and_allergens() -> None:
    metadata = recipe_index_metadata(_recipe())

    assert metadata["owner_user_id"] == "u1"
    assert metadata["is_user_saved"] is True
    assert metadata["source_type"] == "mock"
    assert metadata["contains_soy"] is True


# --- Phase 1.5 item 3: index computed-or-unknown macros, not tag macros ----
#
# Prior behavior embedded recipe.calories/protein_g/... (self-reported tag
# metadata, e.g. an imported dataset's own unverified numbers) directly into
# the search document and metadata. Both must now come from
# app.services.nutrition_view (the same source the scorer/frontend/
# explanation layer trust), never the tag fields.


def _grounded_nutrition(coverage: float = 1.0, status: GroundingStatus = GroundingStatus.GROUNDED) -> RecipeNutrition:
    macros = FoodMacros(calories=321, protein_g=28, carbs_g=19, fat_g=11, fiber_g=4)
    return RecipeNutrition(
        status=status,
        servings=1,
        total=macros,
        per_serving=macros,
        coverage=coverage,
    )


def test_search_document_does_not_embed_unverified_tag_macros() -> None:
    # Tag macros (calories=560 etc.) are self-reported and recipe.nutrition is
    # unset (grounding job hasn't run) -- the document must say so, never
    # silently embed the tag numbers as if they were verified.
    document = build_recipe_search_document(_recipe())

    assert "Macros: Macros have not been verified for this recipe yet." in document
    assert "560" not in document
    assert "45" not in document.split("Macros:")[1]


def test_search_document_embeds_grounded_computed_macros() -> None:
    recipe = _recipe()
    recipe.nutrition = _grounded_nutrition()

    document = build_recipe_search_document(recipe)

    assert "calories 321" in document
    assert "protein 28g" in document
    # The self-reported tag macro (560) must not appear anywhere in the document.
    assert "560" not in document


def test_search_document_flags_partial_grounding_as_undercount() -> None:
    recipe = _recipe()
    recipe.nutrition = _grounded_nutrition(coverage=0.5, status=GroundingStatus.PARTIAL)

    document = build_recipe_search_document(recipe)

    assert "partial" in document
    assert "50% of ingredients" in document
    assert "undercount" in document


def test_metadata_excludes_unverified_tag_macros() -> None:
    # recipe.nutrition unset -> macros must be entirely absent from metadata,
    # never fall back to the self-reported tag fields.
    metadata = recipe_index_metadata(_recipe())

    for key in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g"):
        assert key not in metadata


def test_metadata_uses_grounded_computed_macros() -> None:
    recipe = _recipe()
    recipe.nutrition = _grounded_nutrition()

    metadata = recipe_index_metadata(recipe)

    assert metadata["calories"] == 321
    assert metadata["protein_g"] == 28


def test_metadata_excludes_partial_macros_as_untrusted() -> None:
    # PARTIAL undercounts by definition -- excluded from numeric metadata the
    # same way nutrition_scorer.macro_fit_score excludes it from scoring.
    recipe = _recipe()
    recipe.nutrition = _grounded_nutrition(coverage=0.5, status=GroundingStatus.PARTIAL)

    metadata = recipe_index_metadata(recipe)

    for key in ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g"):
        assert key not in metadata


def test_rebuild_index_clean_removes_stale_macro_metadata(monkeypatch) -> None:
    """Real Chroma `collection.upsert(...)` MERGES the new metadata dict into
    whatever metadata already exists for that id -- a key simply absent from
    the new payload (e.g. `calories`, omitted here because a recipe went from
    "was indexed with old self-reported tag macros" to "ungrounded, macros
    unknown") is NOT deleted by a plain upsert; the stale numeric value
    survives. Found live while re-indexing the corpus for this fix: recipes
    with UNGROUNDED nutrition kept their old, no-longer-embedded calorie
    metadata after a plain `rebuild_index`. `rebuild_index_clean` (drop +
    recreate the collection, then index from scratch) is the only path that
    actually clears it -- this is why the reindex command for this change
    must be rebuild_index_clean, not the upsert-only rebuild_index."""

    class MergingFakeCollection:
        """Mimics chromadb's real upsert-merges-metadata semantics."""

        def __init__(self):
            self.metadata_by_id: dict[str, dict] = {}

        def upsert(self, ids, documents, metadatas):
            for recipe_id, metadata in zip(ids, metadatas):
                existing = self.metadata_by_id.setdefault(recipe_id, {})
                existing.update(metadata)

    store = {"collection": MergingFakeCollection()}
    monkeypatch.setattr(recipe_indexing_service, "get_chroma_collection", lambda: store["collection"])
    monkeypatch.setattr(
        recipe_indexing_service, "reset_chroma_collection", lambda: store.__setitem__("collection", MergingFakeCollection()) or store["collection"]
    )

    grounded_recipe = _recipe()
    grounded_recipe.nutrition = _grounded_nutrition()
    monkeypatch.setattr(recipe_indexing_service, "load_corpus", lambda: [grounded_recipe])

    service = RecipeIndexingService(repository=None)
    service.rebuild_index(include_base=True, include_user=False)
    assert store["collection"].metadata_by_id["user_test_recipe"]["calories"] == 321

    # Recipe becomes ungrounded (e.g. a corrected grounding run) -- calories
    # must disappear from the index, not linger from the prior upsert.
    ungrounded_recipe = _recipe()
    ungrounded_recipe.nutrition = None
    monkeypatch.setattr(recipe_indexing_service, "load_corpus", lambda: [ungrounded_recipe])

    # A plain (non-clean) rebuild leaves the stale value behind -- documents
    # the hazard rather than asserting it's fine.
    service.rebuild_index(include_base=True, include_user=False)
    assert store["collection"].metadata_by_id["user_test_recipe"]["calories"] == 321

    # rebuild_index_clean drops and recreates the collection first, so the
    # stale key cannot survive.
    service.rebuild_index_clean(include_base=True, include_user=False)
    assert "calories" not in store["collection"].metadata_by_id["user_test_recipe"]


def test_indexing_uses_collection_without_crashing(monkeypatch) -> None:
    captured = {}

    class FakeCollection:
        def upsert(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(recipe_indexing_service, "get_chroma_collection", lambda: FakeCollection())

    count = RecipeIndexingService(repository=None).index_recipes([_recipe()])

    assert count == 1
    assert captured["ids"] == ["user_test_recipe"]
