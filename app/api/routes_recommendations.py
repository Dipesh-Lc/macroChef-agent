from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.dependencies import require_recommend_rate_limit
from app.graph.builder import run_recommendation_graph
from app.rag.loaders import load_corpus
from app.schemas.instructions import DetailedInstructionsRequest, DetailedInstructionsResponse
from app.schemas.recipe import Recipe
from app.schemas.recipe_search import RecipeSearchRequest, RecipeSearchResponse
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.services.constraint_engine import contains_allergen, violates_diet_type
from app.services.model_provider import generate_detailed_instructions_with_provider_chain
from app.services.nutrition_view import trusted_per_serving
from app.services.recipe_retriever import get_recipe_by_id

router = APIRouter(prefix="/recipes", tags=["recommendations"])


def _macro_filters_active(request: RecipeSearchRequest) -> bool:
    return any(
        value is not None
        for value in (
            request.calorie_min,
            request.calorie_max,
            request.protein_min,
            request.protein_max,
            request.carbs_min,
            request.carbs_max,
            request.fat_min,
            request.fat_max,
        )
    )


def _within_macro_ranges(macros, request: RecipeSearchRequest) -> bool:  # type: ignore[no-untyped-def]
    if request.calorie_min is not None and macros.calories < request.calorie_min:
        return False
    if request.calorie_max is not None and macros.calories > request.calorie_max:
        return False
    if request.protein_min is not None and macros.protein_g < request.protein_min:
        return False
    if request.protein_max is not None and macros.protein_g > request.protein_max:
        return False
    if request.carbs_min is not None and macros.carbs_g < request.carbs_min:
        return False
    if request.carbs_max is not None and macros.carbs_g > request.carbs_max:
        return False
    if request.fat_min is not None and macros.fat_g < request.fat_min:
        return False
    if request.fat_max is not None and macros.fat_g > request.fat_max:
        return False
    return True


@router.get("/{recipe_id}", response_model=Recipe)
def get_recipe(recipe_id: str) -> Recipe:
    """Public call: no session bootstrap, no rate limit -- this is a pure
    lookup by id into the already-loaded corpus (`app.services.
    recipe_retriever.get_recipe_by_id`), the same lookup POST /plan/day and
    friends already do server-side to resolve a `PlanItem.recipe_id` back to
    its full `Recipe`. It computes nothing (no nutrition math, no allergy
    decision) and makes no safety decision of its own -- it only returns
    already-computed, already-grounded data the frontend can't otherwise
    reach from a `PlanItem` (which only carries `{recipe_id, title,
    servings}`, see `app.schemas.day_plan.PlanItem`). Used by the day/week
    plan views' "click a recipe name" detail modal."""
    recipe = get_recipe_by_id(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.post("/search", response_model=RecipeSearchResponse)
def search_recipes(
    request: RecipeSearchRequest,
    session_user_id: str = Depends(require_recommend_rate_limit),
) -> RecipeSearchResponse:
    """Deterministic search/filter over the existing static corpus (loaded
    via `app.rag.loaders.load_corpus`) -- NOT the generative `/library/
    discover` endpoint. Rate-limited the same way as POST /recipes/recommend
    and POST /recipes/instructions above (this file's existing pattern for a
    non-personalized-write, corpus-scale endpoint); see
    `require_recommend_rate_limit`'s own docstring. `session_user_id` is
    otherwise unused: this endpoint reads/writes no per-user data, exactly
    like /recipes/instructions.

    SAFETY (mandatory, verifiable): allergen exclusion and diet-type
    exclusion are each decided by calling `app.services.constraint_engine`'s
    `contains_allergen`/`violates_diet_type` DIRECTLY -- the same
    deterministic, substring-matching primitives `validate_recipe` itself
    calls -- never an LLM, and never `recipe.allergens`/`recipe.diet_tags`
    tag metadata alone. `validate_recipe` itself is deliberately NOT used
    here: it also enforces `contains_disliked_ingredient`/
    `violates_cook_time`, which have no meaning for a search/browse request
    and would require synthesizing dummy values on a fake `UserProfile`.

    Calorie/macro range filtering reads ONLY
    `app.services.nutrition_view.trusted_per_serving` -- never
    `recipe.calories`/`recipe.protein_g` (self-reported tag fields, never
    trusted for scoring/filtering per that model's own docstring). When at
    least one calorie/macro filter is supplied and `trusted_per_serving`
    returns `None` for a recipe (ungrounded/partial/flagged nutrition), that
    recipe is excluded and counted in `macro_unavailable_excluded`. When NO
    calorie/macro filter is supplied, nutrition groundedness is never
    checked and nothing is excluded on that basis -- a cuisine/allergen/diet
    -only search must not silently drop ungrounded recipes.

    Cuisine matching mirrors `RecipeRetriever._keyword_score`'s existing
    convention (app.services.recipe_retriever): case-insensitive exact
    match against `recipe.cuisine`, not a substring/fuzzy match.

    Linear scan over `load_corpus()`, no index/cache -- the same performance
    posture POST /plan/day, /plan/batch, and /plan/week already use
    (app.api.routes_day_planner) at this corpus size.
    """
    requested_cuisines = (
        {cuisine.lower() for cuisine in request.cuisines} if request.cuisines else None
    )
    allergies = request.allergies or []
    macro_filters_active = _macro_filters_active(request)

    total_matched = 0
    macro_unavailable_excluded = 0
    matched_recipes: list[Recipe] = []

    for recipe in load_corpus():
        if requested_cuisines is not None:
            if not recipe.cuisine or recipe.cuisine.lower() not in requested_cuisines:
                continue
        if contains_allergen(recipe, allergies):
            continue
        if violates_diet_type(recipe, request.diet_type):
            continue
        if macro_filters_active:
            macros = trusted_per_serving(recipe)
            if macros is None:
                macro_unavailable_excluded += 1
                continue
            if not _within_macro_ranges(macros, request):
                continue

        total_matched += 1
        matched_recipes.append(recipe)

    return RecipeSearchResponse(
        results=matched_recipes[: request.limit],
        total_matched=total_matched,
        macro_unavailable_excluded=macro_unavailable_excluded,
    )


@router.post("/recommend", response_model=RecommendationResponse)
def recommend_recipes(
    request: RecommendationRequest,
    session_user_id: str = Depends(require_recommend_rate_limit),
) -> RecommendationResponse:
    # `session_user_id` is the verified session identity (see
    # app.dependencies.get_session_user, which require_recommend_rate_limit
    # resolves internally before keying the rate limit on it). It is now also
    # the ONLY identity used for this request -- there is no client-supplied
    # `user_id` on `RecommendationRequest` to fall back to or be confused
    # with. This is what list_user_recipes/get_user_memory/
    # save_session_summary key personalization and saved-library reads on
    # inside the recommendation graph (see app.graph.builder).
    return run_recommendation_graph(request, session_user_id)


@router.post("/instructions", response_model=DetailedInstructionsResponse)
def get_detailed_instructions(
    request: DetailedInstructionsRequest,
    session_user_id: str = Depends(require_recommend_rate_limit),
) -> DetailedInstructionsResponse:
    # Session-gated and rate-limited the exact same way as POST
    # /recipes/recommend (require_recommend_rate_limit resolves
    # app.dependencies.get_session_user internally before keying the rate
    # limit) -- this reuses that endpoint's existing, already-tested
    # session/rate-limit tier rather than inventing a new one. `session_user_id`
    # is otherwise unused here: this endpoint is a pure function of its
    # request body (it reads/writes no per-user data), so the only reason it
    # requires a session at all is to share the same abuse-guard bucket as
    # the other LLM-backed /recipes/* call.
    del session_user_id
    settings = get_settings()
    steps, generated = generate_detailed_instructions_with_provider_chain(
        title=request.title,
        ingredients=request.ingredients,
        instructions=request.instructions,
        servings=request.servings,
        cuisine=request.cuisine,
    )
    provider_note = None
    if not generated:
        if settings.model_provider == "mock":
            provider_note = "Detailed generation is unavailable in mock mode; showing the original steps."
        else:
            provider_note = (
                "Detailed generation is temporarily unavailable; showing the original steps."
            )
    return DetailedInstructionsResponse(steps=steps, generated=generated, provider_note=provider_note)
