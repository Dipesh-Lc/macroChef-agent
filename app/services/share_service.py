"""Roadmap item "Shareable plan URLs" (Phase 4 item 4, docs/ROADMAP.md).

THE LOAD-BEARING SAFETY PROPERTY OF THIS MODULE (do not weaken without a
fresh advisor FULL TREATMENT review): `Recipe.owner_user_id`
(`app/schemas/recipe.py`) is a field ON THE RECIPE OBJECT ITSELF, set by
`RecipeLibraryRepository._row_to_recipe` to the owning user's session
`user_id`. If a client's `Recipe`/`DayPlan`/`BatchPlan`/`WeeklyPlan` object
were ever persisted or echoed verbatim on this path, the sharer's session
identity would leak in-band to anyone who opens the resulting share link.

The four `*_to_public` functions below are therefore an explicit,
FIELD-LEVEL ALLOWLIST -- each one is built by naming every field it copies
out of the source object, never by `model_dump()`-then-strip and never by
constructing the target from `**source.model_dump()`. A new field added to
`Recipe`/`DayPlan`/`BatchPlan`/`WeeklyPlan` in the future is therefore
excluded from the public payload BY DEFAULT (it simply won't appear on the
matching `Public*` schema in `app/schemas/share.py` either) unless someone
deliberately adds it to both the schema and the mapping function here --
the safe failure mode for a share surface.

No LLM anywhere on this path -- this module does not import
`app.services.model_provider` or any chat/vision provider; see
`tests/test_share_no_llm_import.py`, which asserts that statically so this
can never silently regress.
"""

import json
import secrets

from app.data.share_repository import ShareRepository
from app.schemas.batch_plan import BatchPlan
from app.schemas.day_plan import DayPlan
from app.schemas.recipe import Recipe
from app.schemas.share import (
    PlanType,
    PublicBatchPlan,
    PublicDayPlan,
    PublicRecipe,
    PublicWeeklyPlan,
    ShareCreateRequest,
    ShareCreateResponse,
    SharedPlanView,
)
from app.schemas.weekly_plan import WeeklyPlan

# Opaque share id length -- 128 bits (secrets.token_urlsafe(16) produces
# ~22 URL-safe characters), matching the house pattern already used for
# anonymous session identity (frontend/session_client.py's
# `secrets.token_urlsafe(32)`). Deliberately NOT a sequential integer (would
# let a caller enumerate other users' share links) and NOT UUID4 (weaker,
# non-cryptographic randomness guarantee than `secrets`).
_SHARE_ID_BYTES = 16

# Sourced verbatim from frontend/streamlit_app.py's existing st.warning
# disclaimer (lines ~358-366 as of this task) so the share-link experience
# carries the exact same honest-scope numbers as the main app -- judge-
# flagged count (16/259) ALWAYS reported alongside the adjudicated-true
# count (0/259), per CLAUDE.md's "Honest scope" rule; the judge-flagged
# number is never dropped even though it is currently higher than the
# adjudicated one. Do not edit this string in response to a new benchmark
# run without re-reading the live streamlit_app.py text first -- see
# docs/BACKLOG.md for the follow-up to dedupe this constant into one shared
# location (out of scope for this task, per its spec).
SHARE_DISCLAIMER = (
    "Hobby project — not medical advice. MacroChef is an unpaid personal "
    "project, not a certified nutrition or allergy-safety product. On its "
    "259-case adversarial allergy benchmark, the deterministic judge flagged "
    "16/259 recipes; written per-case adjudication found 0 true violations "
    "(all 16 were judge false positives). "
    "If you have a food allergy, you must independently verify every "
    "ingredient before you eat anything suggested here."
)


def recipe_to_public(recipe: Recipe) -> PublicRecipe:
    """The allowlist for a shared single recipe. See `PublicRecipe`'s
    docstring (app/schemas/share.py) for exactly which `Recipe` fields are
    excluded and why -- `owner_user_id` above all."""
    return PublicRecipe(
        recipe_id=recipe.recipe_id,
        title=recipe.title,
        cuisine=recipe.cuisine,
        meal_type=recipe.meal_type,
        ingredients=list(recipe.ingredients),
        instructions=list(recipe.instructions),
        allergens=list(recipe.allergens),
        diet_tags=list(recipe.diet_tags),
        cook_time_min=recipe.cook_time_min,
        nutrition=recipe.nutrition,
        description=recipe.description,
        difficulty=recipe.difficulty,
        servings=recipe.servings,
        equipment=list(recipe.equipment),
        image_url=recipe.image_url,
        source_type=recipe.source_type,
        source_name=recipe.source_name,
        source_url=recipe.source_url,
        substitution_note=recipe.substitution_note,
    )


def day_plan_to_public(day_plan: DayPlan) -> PublicDayPlan:
    """The allowlist for a shared `DayPlan`. Excludes `trusted_pool_size`
    (see `PublicDayPlan`'s docstring). Only the INNER plan object is ever
    snapshotted -- never `DayPlanResponse`, so `rejected_recipes` is
    structurally excluded (it lives only on the Response wrapper, never on
    `DayPlan` itself) as well as excluded here explicitly, per this
    feature's design decision Q2."""
    return PublicDayPlan(
        items=list(day_plan.items),
        meals_planned=day_plan.meals_planned,
        total_calories=day_plan.total_calories,
        total_protein_g=day_plan.total_protein_g,
        total_carbs_g=day_plan.total_carbs_g,
        total_fat_g=day_plan.total_fat_g,
        total_fiber_g=day_plan.total_fiber_g,
        target_calories=day_plan.target_calories,
        target_protein_g=day_plan.target_protein_g,
        calories_relative_error=day_plan.calories_relative_error,
        protein_relative_error=day_plan.protein_relative_error,
        carbs_relative_error=day_plan.carbs_relative_error,
        fat_relative_error=day_plan.fat_relative_error,
        fiber_relative_error=day_plan.fiber_relative_error,
        within_tolerance=day_plan.within_tolerance,
    )


def batch_plan_to_public(batch_plan: BatchPlan) -> PublicBatchPlan:
    """The allowlist for a shared `BatchPlan`. Excludes `trusted_pool_size`.
    Only the INNER plan object is ever snapshotted -- never
    `BatchPlanResponse`, so `rejected_recipes`/`shopping_list` are
    structurally excluded (they live only on the Response wrapper) as well
    as excluded here explicitly, per this feature's design decision Q2."""
    return PublicBatchPlan(
        items=list(batch_plan.items),
        containers=batch_plan.containers,
        per_container_target_calories=batch_plan.per_container_target_calories,
        per_container_target_protein_g=batch_plan.per_container_target_protein_g,
        recipes_selected=batch_plan.recipes_selected,
        within_tolerance=batch_plan.within_tolerance,
        recipe_fits=list(batch_plan.recipe_fits),
    )


def weekly_plan_to_public(weekly_plan: WeeklyPlan) -> PublicWeeklyPlan:
    """The allowlist for a shared `WeeklyPlan`. Excludes `trusted_pool_size`
    and the pantry-derived `pantry_utilization`/`uncompared_ingredient_count`
    (both would leak "here's what's in the sharer's kitchen" to an
    anonymous viewer). Each day is mapped through `day_plan_to_public`
    above, never through `WeeklyPlanResponse` (whose `rejected_recipes`/
    `shopping_list` are structurally excluded, same as the other three
    mapping functions)."""
    return PublicWeeklyPlan(days=[day_plan_to_public(day) for day in weekly_plan.days])


# ---------------------------------------------------------------------------
# Orchestration -- used by app.api.routes_share.
# ---------------------------------------------------------------------------

_MAPPERS = {
    "recipe": (lambda request: request.recipe, recipe_to_public, PublicRecipe),
    "day": (lambda request: request.day_plan, day_plan_to_public, PublicDayPlan),
    "batch": (lambda request: request.batch_plan, batch_plan_to_public, PublicBatchPlan),
    "week": (lambda request: request.weekly_plan, weekly_plan_to_public, PublicWeeklyPlan),
}


def create_share(
    request: ShareCreateRequest, owner_user_id: str, repo: ShareRepository | None = None
) -> ShareCreateResponse:
    """Builds the public snapshot from `request` via the server-side
    allowlist above (never the client object verbatim), persists it keyed
    by a freshly minted opaque id, and returns just that id -- never a full
    URL (see `ShareCreateResponse`'s docstring for why: the frontend
    composes the public hostname, this service never hardcodes one).

    `owner_user_id` MUST be the verified session identity resolved by
    `app.dependencies.get_session_user` at the route layer -- never a
    client-supplied value (same rule as every other per-user write path in
    this codebase, e.g. `app.data.recipe_library_repository.save_recipe`).
    """
    source_getter, mapper, _ = _MAPPERS[request.plan_type]
    source = source_getter(request)
    public_obj = mapper(source)
    content_json = public_obj.model_dump_json()

    share_id = secrets.token_urlsafe(_SHARE_ID_BYTES)
    repository = repo or ShareRepository()
    repository.create(share_id, request.plan_type, content_json, owner_user_id)
    return ShareCreateResponse(share_id=share_id)


def get_share(share_id: str, repo: ShareRepository | None = None) -> SharedPlanView | None:
    """Returns None for both "never existed" and "revoked" (is_active=False)
    -- `app.data.share_repository.ShareRepository.get_active` already
    collapses those two cases, and the caller (`app.api.routes_share.
    get_share_view`) must turn a None here into an identical 404 for both,
    so there is no oracle for "does this id exist but was revoked".

    Builds `SharedPlanView` from ONLY `plan_type` + the stored `content`
    JSON -- never from the ORM row's other columns, so `owner_user_id`
    never has a path into this return value even by accident."""
    repository = repo or ShareRepository()
    row = repository.get_active(share_id)
    if row is None:
        return None

    plan_type: PlanType = row.plan_type  # type: ignore[assignment]
    data = json.loads(row.content)
    public_type = _MAPPERS[plan_type][2]
    content = public_type.model_validate(data)
    return SharedPlanView(plan_type=plan_type, content=content, disclaimer=SHARE_DISCLAIMER)
