from collections import Counter
from typing import Any

from app.config import get_settings
from app.data.recipe_library_repository import RecipeLibraryRepository
from app.rag.loaders import load_corpus, recipes_by_id
from app.rag.vector_store import get_vector_store
from app.schemas.recipe import Recipe
from app.utils.ingredient_normalizer import ingredient_matches, normalize_ingredient
from app.utils.logging import get_logger

logger = get_logger(__name__)


def build_metadata_filter(
    cuisine_preference: str | None, meal_type: str | None
) -> dict[str, Any] | None:
    """Vector-store `where` clause for exact cuisine/meal_type metadata
    filtering (supported identically by both the Chroma and pgvector
    backends -- see `app.rag.pgvector_store`'s where-clause translator).

    Module-level (not just RecipeRetriever._build_metadata_filter) so
    callers that query the vector store directly -- e.g. the retrieval eval in
    app.evaluation.eval_retrieval, which measures the semantic path in
    isolation from the keyword-fallback mixing in .retrieve() -- can still
    apply the same metadata pre-filter production actually uses, rather than
    an unfiltered pure-embedding search that understates real semantic
    quality on cuisine/meal_type queries.
    """
    clauses: list[dict[str, str]] = []
    if cuisine_preference:
        clauses.append({"cuisine": cuisine_preference})
    if meal_type:
        clauses.append({"meal_type": meal_type})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


class RecipeRetriever:
    def __init__(
        self,
        recipe_path: str | None = None,
        library_repository: RecipeLibraryRepository | None = None,
    ):
        self.settings = get_settings()
        self.recipe_path = recipe_path or str(self.settings.recipe_path)
        # Seed (hand-curated) recipes union the imported Food.com corpus, deduped
        # by recipe_id with seeds winning -- see app.rag.loaders.load_corpus.
        # Previously this loaded ONLY the 25 seed recipes via load_recipes(), so
        # the ~4,238 imported recipes embedded in Chroma were filtered out of
        # retrieve() because recipes_by_id was built from _base_recipes alone.
        self._base_recipes = load_corpus(seed_path=self.recipe_path)
        self.library_repository = library_repository or RecipeLibraryRepository()

    def retrieve(
        self,
        ingredients: list[str],
        cuisine_preference: str | None = None,
        meal_type: str | None = None,
        limit: int = 12,
        user_id: str | None = None,
        include_user_recipes: bool = True,
        include_base_recipes: bool = True,
    ) -> list[Recipe]:
        recipes = self._available_recipes(user_id, include_user_recipes, include_base_recipes)
        recipes_by_id = {recipe.recipe_id: recipe for recipe in recipes}
        query = self._build_query(ingredients, cuisine_preference, meal_type)

        try:
            store = get_vector_store()
            if store.count() > 0:
                # No `where` filter here: a hard equality filter on
                # cuisine/meal_type would exclude every recipe missing that
                # metadata key entirely (recipe_indexing_service drops None
                # values before writing to the vector store, so ~most of the
                # corpus has no "cuisine" key at all -- not cuisine=null, the
                # key is absent). A hard filter can never match an absent key,
                # which was silently collapsing cuisine-filtered search down
                # to the handful of hand-curated seed recipes that happen to
                # carry a cuisine tag. Instead, run the semantic query
                # unfiltered and apply the same soft cuisine/meal_type boost
                # keyword_search already uses (_metadata_boost) to re-rank
                # afterward -- an untagged recipe just doesn't get the boost,
                # it isn't excluded.
                recipe_ids = store.query(query, n_results=limit * 3)
                semantic = [
                    recipes_by_id[recipe_id]
                    for recipe_id in recipe_ids
                    if recipe_id in recipes_by_id
                ]
                semantic = self._rank_semantic_results(semantic, cuisine_preference, meal_type)
                if len(semantic) >= limit:
                    return semantic[:limit]
                seen = {recipe.recipe_id for recipe in semantic}
                fallback = [
                    recipe
                    for recipe in self.keyword_search(
                        ingredients,
                        cuisine_preference,
                        meal_type,
                        limit,
                        recipes=recipes,
                    )
                    if recipe.recipe_id not in seen
                ]
                if semantic or fallback:
                    return [*semantic, *fallback][:limit]
        except Exception as exc:
            logger.warning("Semantic retrieval failed, falling back to keyword search: %s", exc)

        return self.keyword_search(
            ingredients,
            cuisine_preference,
            meal_type,
            limit,
            recipes=recipes,
        )

    def keyword_search(
        self,
        ingredients: list[str],
        cuisine_preference: str | None = None,
        meal_type: str | None = None,
        limit: int = 12,
        recipes: list[Recipe] | None = None,
    ) -> list[Recipe]:
        normalized = [normalize_ingredient(item) for item in ingredients]
        scored: list[tuple[float, Recipe]] = []
        candidate_recipes = recipes or self._base_recipes
        for recipe in candidate_recipes:
            score = self._keyword_score(recipe, normalized, cuisine_preference, meal_type)
            if recipe.is_user_saved:
                score += 0.2
            if score > 0:
                scored.append((score, recipe))

        scored.sort(key=lambda item: item[0], reverse=True)
        seen = {recipe.recipe_id for _, recipe in scored}
        for recipe in candidate_recipes:
            if recipe.recipe_id not in seen:
                scored.append((0.05, recipe))
        return [recipe for _, recipe in scored[:limit]]

    def all_recipes(self) -> list[Recipe]:
        return list(self._base_recipes)

    def _available_recipes(
        self,
        user_id: str | None,
        include_user_recipes: bool,
        include_base_recipes: bool,
    ) -> list[Recipe]:
        recipes: list[Recipe] = []
        if include_base_recipes:
            recipes.extend(self._base_recipes)
        if include_user_recipes and user_id:
            recipes.extend(self.library_repository.list_user_recipes(user_id))
        return recipes

    def _rank_semantic_results(
        self,
        recipes: list[Recipe],
        cuisine_preference: str | None,
        meal_type: str | None,
    ) -> list[Recipe]:
        """Re-rank Chroma's semantic-similarity order by the same soft
        cuisine/meal_type boost `_metadata_boost` applies in keyword_search,
        plus the existing user-saved boost. `sorted` is stable, so within an
        equal (is_user_saved, metadata_boost) tier, Chroma's own relevance
        order is preserved -- an untagged recipe (no boost either way) simply
        keeps its semantic rank rather than being excluded or penalized.
        """
        return sorted(
            recipes,
            key=lambda recipe: (
                recipe.is_user_saved,
                self._metadata_boost(recipe, cuisine_preference, meal_type),
            ),
            reverse=True,
        )

    def _metadata_boost(
        self,
        recipe: Recipe,
        cuisine_preference: str | None,
        meal_type: str | None,
    ) -> float:
        boost = 0.0
        if (
            cuisine_preference
            and recipe.cuisine
            and recipe.cuisine.lower() == cuisine_preference.lower()
        ):
            boost += 0.75
        if meal_type and recipe.meal_type and recipe.meal_type.lower() == meal_type.lower():
            boost += 0.5
        return boost

    def _keyword_score(
        self,
        recipe: Recipe,
        ingredients: list[str],
        cuisine_preference: str | None,
        meal_type: str | None,
    ) -> float:
        score = 0.0
        ingredient_counter = Counter(normalize_ingredient(item.name) for item in recipe.ingredients)
        for ingredient in ingredients:
            if any(
                ingredient_matches(ingredient, recipe_ingredient)
                for recipe_ingredient in ingredient_counter
            ):
                score += 1.0

        score += self._metadata_boost(recipe, cuisine_preference, meal_type)

        return score

    def _build_query(
        self,
        ingredients: list[str],
        cuisine_preference: str | None,
        meal_type: str | None,
    ) -> str:
        parts = ["available ingredients: " + ", ".join(ingredients)]
        if cuisine_preference:
            parts.append(f"preferred cuisine: {cuisine_preference}")
        if meal_type:
            parts.append(f"meal type: {meal_type}")
        return " | ".join(parts)

    def _build_metadata_filter(
        self, cuisine_preference: str | None, meal_type: str | None
    ) -> dict[str, Any] | None:
        return build_metadata_filter(cuisine_preference, meal_type)


def get_recipe_by_id(recipe_id: str) -> Recipe | None:
    return recipes_by_id().get(recipe_id)
