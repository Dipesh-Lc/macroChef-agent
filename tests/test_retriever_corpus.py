"""Regression test for the "retriever only sees the 25 seed recipes" bug.

Before this fix, RecipeRetriever._base_recipes was built from
`load_recipes(self.recipe_path)` -- only the 25 hand-curated seed recipes
(`data/processed/sample_recipes.jsonl`). The ~4,238 imported Food.com recipes
(`data/processed/imported_recipes.jsonl`) were embedded in Chroma, but
`retrieve()`'s `recipes_by_id` lookup (built from `_base_recipes`) filtered
every one of them back out, so they could never actually surface to a user.

Post-2026-07-18 corpus quarantine: the imported corpus is now ~2,889 rows
(down from ~4,238 due to instructions-integrity issues), plus 25 seeds.

`RecipeRetriever` now builds `_base_recipes` from
`app.rag.loaders.load_corpus()` (seed UNION imported, deduped by id, seeds
win) instead. This test proves, at full corpus scale:
  (a) an imported (non-seed) recipe CAN surface in `retrieve()` results, and
  (b) allergy filtering (the `retrieve()` -> `validate_recipe` path) still
      rejects unsafe recipes once the retriever is backed by the full corpus.

Deterministic in CI: the vector store's `count()` is monkeypatched to 0 so
`retrieve()` falls through to the pure-Python `keyword_search` path,
independent of Chroma/pgvector/embedding-provider state (ROADMAP 5.2 made
the backend swappable -- see `app.rag.vector_store`).
"""

from app.agent.tools import ToolContext, dispatch_tool_call
from app.rag.loaders import load_corpus
from app.schemas.user import MacroTargets, UserProfile
from app.services import recipe_retriever as retriever_module
from app.services.constraint_engine import validate_recipe
from app.services.recipe_retriever import RecipeRetriever, get_recipe_by_id


class FakeLibraryRepository:
    def list_user_recipes(self, user_id: str) -> list:
        return []


class _EmptyVectorStore:
    def count(self) -> int:
        return 0


def _retriever(monkeypatch) -> RecipeRetriever:
    monkeypatch.setattr(retriever_module, "get_vector_store", lambda: _EmptyVectorStore())
    return RecipeRetriever(library_repository=FakeLibraryRepository())


def test_get_recipe_by_id_resolves_an_imported_corpus_recipe() -> None:
    """Regression test for the exact same class of bug this file exists for
    (see the module docstring), found again 2026-08-07 one function over:
    `get_recipe_by_id` (used by `app.agent.tools._resolve_recipe`, and by
    `GET /recipes/{recipe_id}`) called `app.rag.loaders.recipes_by_id()`,
    which loads ONLY the 25 seed recipes -- not `load_corpus()`'s seed-union-
    imported set `RecipeRetriever` itself already used. So `search_recipes`
    could surface an `imp_*` id that no other tool could ever resolve. See
    `get_recipe_by_id`'s docstring (app/services/recipe_retriever.py) for
    the fix."""
    imported = next(recipe for recipe in load_corpus() if recipe.recipe_id.startswith("imp_"))

    resolved = get_recipe_by_id(imported.recipe_id)

    assert resolved is not None
    assert resolved.recipe_id == imported.recipe_id


def test_check_recipe_safety_resolves_an_imported_corpus_recipe_end_to_end() -> None:
    """Same bug, exercised through the actual tool a chat turn calls: before
    the fix, `check_recipe_safety` reported "Recipe not found" for every
    imported recipe id `search_recipes` could ever return, even though
    `validate_recipe` itself was never broken -- `_resolve_recipe` just
    could never find the recipe to hand it."""
    imported = next(recipe for recipe in load_corpus() if recipe.recipe_id.startswith("imp_"))
    ctx = ToolContext(user_id="user_corpus_safety_check", user_profile=UserProfile())

    result = dispatch_tool_call(ctx, "check_recipe_safety", {"recipe_ids": [imported.recipe_id]})

    assert result.ok is True
    rejection_reasons = [
        entry["result"].get("rejection_reason") for entry in result.raw["results"]
    ]
    assert "Recipe not found" not in rejection_reasons


def test_full_corpus_is_loaded_seed_union_imported(monkeypatch) -> None:
    retriever = _retriever(monkeypatch)

    recipe_ids = {recipe.recipe_id for recipe in retriever.all_recipes()}

    # 25 hand-curated seed recipes + the full ~2,889-recipe imported corpus after 2026-07-18 quarantine.
    assert len(recipe_ids) > 2900
    assert any(recipe_id.startswith("imp_") for recipe_id in recipe_ids)
    assert any(recipe_id.startswith("r_") for recipe_id in recipe_ids)


def test_imported_recipe_can_surface_in_retrieve_results(monkeypatch) -> None:
    retriever = _retriever(monkeypatch)

    recipes = retriever.retrieve(["peanut butter", "whole wheat flour"], limit=10)

    assert any(recipe.recipe_id.startswith("imp_") for recipe in recipes), (
        "No imported (non-seed) recipe surfaced in retrieve() results even though "
        "the corpus contains several matching imported recipes -- the retriever "
        "may be filtering imported recipes back out again."
    )


def test_allergy_filtering_rejects_unsafe_recipes_at_full_corpus_scale(monkeypatch) -> None:
    retriever = _retriever(monkeypatch)

    # "peanut butter" surfaces many peanut-containing imported recipes
    # (Pork Satay, Fudge Drops, Peanut Butter Bread, Peanut Butter Pie, ...).
    candidates = retriever.retrieve(["peanut butter", "sugar", "butter"], limit=30)
    assert candidates, "Expected retrieve() to surface candidates for this query."

    profile = UserProfile(user_id="allergy_test", macro_targets=MacroTargets(), allergies=["peanut"])
    validated = [recipe for recipe in candidates if validate_recipe(recipe, profile).is_valid]

    peanut_terms = ("peanut",)
    for recipe in validated:
        ingredient_names = " ".join(item.name.lower() for item in recipe.ingredients)
        assert not any(term in ingredient_names for term in peanut_terms), (
            f"Recipe {recipe.recipe_id!r} ({recipe.title!r}) contains peanut but "
            "passed validate_recipe for a peanut-allergic user."
        )

    # Sanity check: the corpus-scale candidate set actually contained at
    # least one peanut recipe that got rejected -- otherwise this test would
    # trivially pass without exercising the filter at all.
    rejected_for_peanut = [
        recipe
        for recipe in candidates
        if recipe not in validated
        and any("peanut" in item.name.lower() for item in recipe.ingredients)
    ]
    assert rejected_for_peanut, (
        "Expected at least one peanut-containing candidate to be rejected -- "
        "otherwise this test isn't exercising the allergy filter."
    )
