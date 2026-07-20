from functools import lru_cache

from sqlalchemy.orm import Session

from app.data.db import SessionLocal, init_db
from app.data.recipe_library_repository import RecipeLibraryRepository
from app.data.repositories import FeedbackRepository, SessionMemoryRepository
from app.rag.loaders import load_corpus
from app.schemas.recipe import Recipe
from app.schemas.recommendation import FeedbackRequest, MealRecommendation, TasteProfile
from app.services.analytics import get_analytics
from app.utils.ingredient_normalizer import normalize_ingredient

# feedback_type values that map onto a thumbs up/down analytics signal.
# "cooked"/"skipped" are other feedback types this endpoint accepts but are
# not thumbs up/down, so they are not captured here.
_THUMBS_EVENT_BY_FEEDBACK_TYPE = {"liked": "thumbs_up", "disliked": "thumbs_down"}


def save_feedback(
    user_id: str, request: FeedbackRequest, db: Session | None = None
) -> dict[str, str]:
    # `user_id` is the verified session identity (see
    # app.dependencies.get_session_user), passed in by the caller --
    # `FeedbackRequest` carries no user_id field to fall back to, so both the
    # persisted row and the analytics event below use only this value, never
    # anything from `request`.
    init_db()
    owns_session = db is None
    session = db or SessionLocal()
    try:
        FeedbackRepository(session).add_feedback(user_id, request)
        thumbs_event = _THUMBS_EVENT_BY_FEEDBACK_TYPE.get(request.feedback_type)
        if thumbs_event:
            get_analytics().capture(
                user_id,
                "thumbs up/down",
                {"direction": thumbs_event, "recipe_id": request.recipe_id},
            )
        return {"status": "ok", "message": "Feedback saved"}
    finally:
        if owns_session:
            session.close()


def get_user_memory(user_id: str, db: Session | None = None) -> tuple[set[str], set[str]]:
    init_db()
    owns_session = db is None
    session = db or SessionLocal()
    try:
        repo = FeedbackRepository(session)
        return repo.get_liked_recipe_ids(user_id), repo.get_disliked_recipe_ids(user_id)
    finally:
        if owns_session:
            session.close()


def save_session_summary(
    user_id: str, recommendations: list[MealRecommendation], db: Session | None = None
) -> str:
    if not recommendations:
        return "No recommendations saved."
    init_db()
    owns_session = db is None
    session = db or SessionLocal()
    summary = "Recommended: " + ", ".join(item.recipe.title for item in recommendations)
    try:
        SessionMemoryRepository(session).add_summary(user_id=user_id, summary=summary)
        return summary
    finally:
        if owns_session:
            session.close()


# ---------------------------------------------------------------------------
# Phase 3: visible personalization loop.
#
# `get_user_memory` above only ever re-recognizes a recipe the user has
# already rated (exact recipe_id match). The functions below GENERALIZE:
# they look at what a user's liked/disliked recipes have IN COMMON
# (ingredients, cuisine) so a brand-new, never-rated recipe can still be
# nudged. This is a ranking/UX signal only -- it is never consulted by
# app.services.constraint_engine and can never turn an unsafe recipe safe
# or vice versa; app.services.nutrition_scorer.preference_score applies it
# strictly downstream of, and blind to, the safety filter's decisions.
#
# Threshold choices (deliberately simple and explainable, not tuned):
# - Minimum sample floor (3 disliked / 3 liked recipes) -- one or two data
#   points is a coincidence, not a pattern; 3 is the smallest floor that
#   requires a signal to have recurred rather than resting on a single
#   recipe, without demanding an unrealistic amount of feedback from a demo
#   user.
# - Minimum recurrence within the user's own history (an ingredient/cuisine
#   must appear in >=2 of the user's disliked/liked recipes, not just 1) --
#   guards against one disliked recipe's rare ingredient (which would blow
#   up the ratio below purely because the corpus baseline for it is tiny)
#   being wrongly generalized into "avoided".
# - Frequency-ratio threshold vs. the corpus baseline (>=3x for avoided
#   ingredients, >=2x for preferred cuisines; ingredients get the higher bar
#   because an ingredient recipe corpus has many more distinct ingredients
#   than cuisines, so a random ingredient is more likely to look
#   disproportionate by chance) -- "appears in disliked/liked recipes at a
#   materially higher rate than in the corpus at large", not just "appears
#   at all".
# - Laplace (add-one) smoothing on the baseline rate so an ingredient/cuisine
#   absent from the (large but finite) corpus baseline doesn't produce a
#   divide-by-zero or an artificially infinite ratio.
# ---------------------------------------------------------------------------

_MIN_DISLIKED_SAMPLES = 3
_MIN_LIKED_SAMPLES = 3
_INGREDIENT_MIN_RECURRENCE = 2
_INGREDIENT_RATIO_THRESHOLD = 3.0
_CUISINE_MIN_RECURRENCE = 2
_CUISINE_RATIO_THRESHOLD = 2.0
_MAX_AVOIDED_INGREDIENTS = 5
_MAX_PREFERRED_CUISINES = 3


def _recipe_ingredient_names(recipe: Recipe) -> set[str]:
    # Deduped per recipe (a set, not a list) so a recipe using the same
    # ingredient twice can't inflate its own contribution to either the
    # baseline or the disliked/liked counts below.
    return {
        normalize_ingredient(ingredient.name)
        for ingredient in recipe.ingredients
        if ingredient.name and ingredient.name.strip()
    }


def _baseline_from_recipes(
    recipes: list[Recipe],
) -> tuple[dict[str, int], dict[str, int], int, int]:
    """Pure baseline-stats builder: how many corpus recipes contain each
    ingredient / carry each cuisine. Split out from `_corpus_baseline` (which
    caches this over the real on-disk corpus) so tests can exercise the same
    logic over a small synthetic recipe list without touching disk."""
    ingredient_counts: dict[str, int] = {}
    cuisine_counts: dict[str, int] = {}
    recipes_with_cuisine = 0
    for recipe in recipes:
        for name in _recipe_ingredient_names(recipe):
            ingredient_counts[name] = ingredient_counts.get(name, 0) + 1
        if recipe.cuisine:
            recipes_with_cuisine += 1
            key = recipe.cuisine.lower()
            cuisine_counts[key] = cuisine_counts.get(key, 0) + 1
    return ingredient_counts, cuisine_counts, len(recipes), recipes_with_cuisine


@lru_cache(maxsize=1)
def _cached_base_corpus() -> tuple[Recipe, ...]:
    # The base corpus (~4k recipes) is effectively static within a process
    # lifetime; re-walking it on every /recipes/recommend call (this ran once
    # per request before this task, via RecipeRetriever's own load_corpus()
    # call, but that copy is never reused here) would add real latency for no
    # benefit. Mirrors app.rag.embeddings' identical @lru_cache(maxsize=1)
    # pattern for a similarly process-lifetime-static resource.
    return tuple(load_corpus())


@lru_cache(maxsize=1)
def _corpus_baseline() -> tuple[dict[str, int], dict[str, int], int, int]:
    return _baseline_from_recipes(list(_cached_base_corpus()))


def _base_recipe_lookup() -> dict[str, Recipe]:
    return {recipe.recipe_id: recipe for recipe in _cached_base_corpus()}


def _recipe_lookup(user_id: str) -> dict[str, Recipe]:
    # Base corpus (cached) plus this user's own saved library recipes (never
    # cached -- per-user and small) -- mirrors RecipeRetriever._available_
    # recipes, so feedback on a self-saved custom recipe still resolves.
    lookup = dict(_base_recipe_lookup())
    for recipe in RecipeLibraryRepository().list_user_recipes(user_id):
        lookup[recipe.recipe_id] = recipe
    return lookup


def _derive_avoided_ingredients(
    disliked_recipes: list[Recipe],
    ingredient_baseline_counts: dict[str, int],
    baseline_total_recipes: int,
) -> list[str]:
    if len(disliked_recipes) < _MIN_DISLIKED_SAMPLES or baseline_total_recipes == 0:
        return []

    disliked_counts: dict[str, int] = {}
    for recipe in disliked_recipes:
        for name in _recipe_ingredient_names(recipe):
            disliked_counts[name] = disliked_counts.get(name, 0) + 1

    n_disliked = len(disliked_recipes)
    ranked: list[tuple[float, str]] = []
    for name, count in disliked_counts.items():
        if count < _INGREDIENT_MIN_RECURRENCE:
            continue
        dislike_rate = count / n_disliked
        # +1 / +1 Laplace smoothing -- see module-level rationale comment.
        baseline_rate = (ingredient_baseline_counts.get(name, 0) + 1) / (baseline_total_recipes + 1)
        ratio = dislike_rate / baseline_rate
        if ratio >= _INGREDIENT_RATIO_THRESHOLD:
            ranked.append((ratio, name))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [name for _, name in ranked[:_MAX_AVOIDED_INGREDIENTS]]


def _derive_preferred_cuisines(
    liked_recipes: list[Recipe],
    cuisine_baseline_counts: dict[str, int],
    baseline_total_with_cuisine: int,
) -> list[str]:
    if len(liked_recipes) < _MIN_LIKED_SAMPLES or baseline_total_with_cuisine == 0:
        return []

    liked_counts: dict[str, int] = {}
    liked_with_cuisine = 0
    for recipe in liked_recipes:
        if not recipe.cuisine:
            continue
        liked_with_cuisine += 1
        key = recipe.cuisine.lower()
        liked_counts[key] = liked_counts.get(key, 0) + 1
    if liked_with_cuisine == 0:
        return []

    ranked: list[tuple[float, str]] = []
    for cuisine, count in liked_counts.items():
        if count < _CUISINE_MIN_RECURRENCE:
            continue
        like_rate = count / liked_with_cuisine
        baseline_rate = (cuisine_baseline_counts.get(cuisine, 0) + 1) / (baseline_total_with_cuisine + 1)
        ratio = like_rate / baseline_rate
        if ratio >= _CUISINE_RATIO_THRESHOLD:
            ranked.append((ratio, cuisine))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [cuisine.title() for _, cuisine in ranked[:_MAX_PREFERRED_CUISINES]]


def derive_taste_profile(
    user_id: str,
    db: Session | None = None,
    *,
    recipe_lookup: dict[str, Recipe] | None = None,
    corpus_recipes: list[Recipe] | None = None,
) -> TasteProfile:
    """Derive a generalizing taste profile from `user_id`'s own feedback
    history -- see the module-level comment above for the threshold
    rationale. `recipe_lookup`/`corpus_recipes` are injectable purely for
    tests (a synthetic recipe set / lookup) -- production call sites
    (app.graph.nodes.nutrition_scoring_node) always omit them and get the
    real corpus + this user's saved library.
    """
    init_db()
    owns_session = db is None
    session = db or SessionLocal()
    try:
        repo = FeedbackRepository(session)
        disliked_ids = repo.get_disliked_recipe_ids(user_id)
        liked_ids = repo.get_liked_recipe_ids(user_id)
    finally:
        if owns_session:
            session.close()

    lookup = recipe_lookup if recipe_lookup is not None else _recipe_lookup(user_id)
    disliked_recipes = [lookup[recipe_id] for recipe_id in disliked_ids if recipe_id in lookup]
    liked_recipes = [lookup[recipe_id] for recipe_id in liked_ids if recipe_id in lookup]

    if corpus_recipes is not None:
        ingredient_counts, cuisine_counts, total_recipes, total_with_cuisine = (
            _baseline_from_recipes(corpus_recipes)
        )
    else:
        ingredient_counts, cuisine_counts, total_recipes, total_with_cuisine = _corpus_baseline()

    return TasteProfile(
        avoided_ingredients=_derive_avoided_ingredients(
            disliked_recipes, ingredient_counts, total_recipes
        ),
        preferred_cuisines=_derive_preferred_cuisines(
            liked_recipes, cuisine_counts, total_with_cuisine
        ),
    )
