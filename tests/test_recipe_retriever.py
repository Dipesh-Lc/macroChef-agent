from typing import Any

from app.schemas.recipe import Recipe
from app.services import recipe_retriever as retriever_module
from app.services.recipe_retriever import RecipeRetriever


class FakeLibraryRepository:
    def __init__(self, recipes_by_user: dict[str, list[Recipe]] | None = None):
        self.recipes_by_user = recipes_by_user or {}

    def list_user_recipes(self, user_id: str) -> list[Recipe]:
        return self.recipes_by_user.get(user_id, [])


class FakeVectorStore:
    """Stand-in for `app.rag.vector_store.VectorStore` (ROADMAP 5.2) --
    `RecipeRetriever` is tested against this seam, never a Chroma-specific
    object, so these tests stay valid regardless of `VECTOR_BACKEND`."""

    def __init__(self, count: int = 0, query_fn=None):
        self._count = count
        self._query_fn = query_fn or (lambda query, n_results, where=None: [])
        self.captured_where: list[Any] = []

    def count(self) -> int:
        return self._count

    def query(self, text: str, n_results: int = 10, where=None) -> list[str]:
        self.captured_where.append(where)
        return self._query_fn(text, n_results, where=where)


def _empty_store(monkeypatch) -> None:
    monkeypatch.setattr(retriever_module, "get_vector_store", lambda: FakeVectorStore(count=0))


def test_retrieves_recipes_from_sample_data(monkeypatch) -> None:
    _empty_store(monkeypatch)
    retriever = RecipeRetriever(library_repository=FakeLibraryRepository())

    recipes = retriever.retrieve(["chicken breast", "rice", "spinach"], limit=5)

    assert recipes
    assert any("Chicken" in recipe.title for recipe in recipes)


def test_applies_metadata_preferences_in_fallback(monkeypatch) -> None:
    _empty_store(monkeypatch)
    retriever = RecipeRetriever(library_repository=FakeLibraryRepository())

    recipes = retriever.retrieve(
        ["chicken breast", "rice"],
        cuisine_preference="Japanese",
        meal_type="dinner",
        limit=3,
    )

    assert recipes[0].cuisine == "Japanese"


def test_has_fallback_behavior(monkeypatch) -> None:
    _empty_store(monkeypatch)
    retriever = RecipeRetriever(library_repository=FakeLibraryRepository())

    recipes = retriever.retrieve(["unlikely mystery ingredient"], limit=4)

    assert len(recipes) == 4


def test_user_saved_recipes_can_be_retrieved(monkeypatch) -> None:
    _empty_store(monkeypatch)
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


def test_semantic_path_does_not_hard_exclude_untagged_cuisine_recipe(monkeypatch) -> None:
    """Regression test: the corpus's dominant case is a recipe with NO
    "cuisine" key in the vector store's metadata at all (recipe_indexing_service
    drops None values before writing), because a hard equality `where` filter
    can never match an absent key. Before the fix, retrieve() passed
    cuisine_preference straight into the semantic query's `where` clause, so a
    semantic search result set containing only untagged recipes would be
    silently discarded by the backend itself -- this test exercises the
    semantic path (store.count() > 0) directly, bypassing the keyword_search
    fallback that every other test in this file uses, since the fallback
    path never had this bug.
    """
    untagged = Recipe(
        recipe_id="user_untagged",
        title="Untagged Chicken Rice Bowl",
        cuisine=None,
        meal_type="dinner",
        ingredients=["chicken breast", "rice"],
        instructions=["Cook rice.", "Cook chicken."],
        owner_user_id="alice",
        is_user_saved=True,
    )

    fake_store = FakeVectorStore(
        count=5, query_fn=lambda query, n_results, where=None: ["user_untagged"]
    )
    monkeypatch.setattr(retriever_module, "get_vector_store", lambda: fake_store)

    retriever = RecipeRetriever(
        library_repository=FakeLibraryRepository({"alice": [untagged]})
    )

    recipes = retriever.retrieve(
        ["chicken breast", "rice"],
        cuisine_preference="Thai",
        limit=5,
        user_id="alice",
        include_base_recipes=False,
    )

    assert fake_store.captured_where == [None], (
        "retrieve() must not pass cuisine/meal_type as a hard `where` filter "
        f"on the semantic path -- it should be applied as a soft re-ranking "
        f"boost instead. Got where={fake_store.captured_where!r}"
    )
    assert any(recipe.recipe_id == "user_untagged" for recipe in recipes), (
        "Untagged recipe was excluded from semantic-path results when a "
        "cuisine_preference was set -- the hard where-filter bug is back."
    )


def test_semantic_path_still_ranks_matching_cuisine_above_untagged(monkeypatch) -> None:
    """Proves the soft-boost re-ranking still works post-fix: given the
    vector store returning an untagged recipe BEFORE a cuisine-matching
    recipe (i.e. the untagged one is more semantically similar), retrieve()
    should still surface the cuisine-matching recipe first, mirroring the
    +0.75 boost keyword_search's _keyword_score already applies.
    """
    untagged = Recipe(
        recipe_id="user_untagged2",
        title="Untagged Chicken Rice Bowl",
        cuisine=None,
        meal_type="dinner",
        ingredients=["chicken breast", "rice"],
        instructions=["Cook rice.", "Cook chicken."],
        owner_user_id="alice",
    )
    thai_match = Recipe(
        recipe_id="user_thai",
        title="Thai Chicken Rice Bowl",
        cuisine="Thai",
        meal_type="dinner",
        ingredients=["chicken breast", "rice"],
        instructions=["Cook rice.", "Cook chicken."],
        owner_user_id="alice",
    )

    # The store returns the untagged recipe FIRST (more semantically
    # similar), the Thai match second.
    fake_store = FakeVectorStore(
        count=5, query_fn=lambda query, n_results, where=None: ["user_untagged2", "user_thai"]
    )
    monkeypatch.setattr(retriever_module, "get_vector_store", lambda: fake_store)

    retriever = RecipeRetriever(
        library_repository=FakeLibraryRepository({"alice": [untagged, thai_match]})
    )

    recipes = retriever.retrieve(
        ["chicken breast", "rice"],
        cuisine_preference="Thai",
        limit=5,
        user_id="alice",
        include_base_recipes=False,
    )

    ids = [recipe.recipe_id for recipe in recipes]
    assert ids.index("user_thai") < ids.index("user_untagged2"), (
        "Cuisine-matching recipe should rank above the untagged one after "
        "the soft-boost re-rank, even though the store returned it second."
    )


def test_user_cannot_retrieve_another_users_private_recipes(monkeypatch) -> None:
    _empty_store(monkeypatch)
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
