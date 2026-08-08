"""The 7 Chef-agent tools (ROADMAP.md Phase 3, Step 3.3).

Every function here is a THIN, Pydantic-in/out wrapper over an already
safety-approved `app.services.*` function -- none reimplements service
logic (mirrors `app/api/routes_safety_tools.py`'s "thin pass-through" house
style, see that module's own docstring). `ToolContext.user_id`/`.user_profile`
are the ONLY source of identity/allergy data a tool ever consults -- both
are bound once (session-verified `user_id`; `user_profile` bound at thread
creation, see `app.data.models.ChatThread`) by the graph, never an
LLM-supplied tool-call argument. No tool's `Args` schema below has a
`user_id` or `user_profile` field for this reason (CLAUDE.md invariant #3).

`dispatch_tool_call` never raises for an ordinary tool-usage failure (a bad
diet_type, a missing recipe_id, a malformed args payload) -- it always
returns a `ToolResult` with `ok=False` and a human `error`/`summary`, since a
raised exception mid-agent-loop is a dead end for a turn (mirrors
`app/api/routes_safety_tools.py`'s ValueError-to-structured-response
handling for `violates_diet_type`). A genuinely unexpected exception is
still caught at the dispatch boundary for the same reason.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, model_validator

from app.data.agent_note_repository import AgentNoteRepository
from app.data.db import SessionLocal
from app.data.recipe_library_repository import RecipeLibraryRepository
from app.data.repositories import FeedbackRepository
from app.schemas.ingredient import Ingredient
from app.schemas.recipe import Recipe
from app.schemas.user import UserProfile
from app.services.constraint_engine import validate_recipe
from app.services.day_planner import assemble_plan
from app.services.memory_service import derive_taste_profile
from app.services.nutrition_grounding import compute_recipe_macros_async
from app.services.nutrition_view import macro_display_state, trusted_per_serving
from app.services.rate_limiter import get_rate_limiter
from app.services.recipe_retriever import RecipeRetriever, get_recipe_by_id
from app.services.substitution_service import generate_safe_variants
from app.services.usda_client import UsdaClient
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Q4 (advisor-reviewed): account-wide, not per-user -- USDA FDC's real
# ceiling is ~1000 req/hr per key, shared with the offline batch grounding
# job (app.services.grounding_job); 300/hr leaves headroom for that job.
_GROUND_NUTRITION_RATE_LIMIT_KEY = "ground_nutrition:global"
_GROUND_NUTRITION_RATE_LIMIT_MAX = 300
_GROUND_NUTRITION_RATE_LIMIT_WINDOW_SECONDS = 3600.0
# Local to this call site ONLY -- deliberately NOT Settings.llm_max_
# concurrency (that sizes the offline grounding job's fan-out; sharing it
# would silently couple two unrelated budgets, see the task spec's Q4).
_GROUND_NUTRITION_CONCURRENCY = 3
_GROUND_NUTRITION_TIMEOUT_SECONDS = 6.0


@dataclass(frozen=True)
class ToolContext:
    """Session-bound context every tool handler closes over. NEVER
    constructed from LLM-controlled data -- `user_id` comes from the
    verified session token, `user_profile` from the thread's stored,
    bind-once `ChatThread.user_profile` (see that model's docstring)."""

    user_id: str
    user_profile: UserProfile


class ToolResult(BaseModel):
    """Uniform tool-call outcome, always returned (never raised) by
    `dispatch_tool_call`. `raw` is a small JSON-serializable dict --  the
    thing `app.agent.prompts.wrap_tool_output` wraps in `<tool_output>`
    delimiters for the model's next turn. `recipe_ids_covered` is set ONLY
    by `check_recipe_safety` (the sole tool the response gate trusts for
    safety coverage, see `app.agent.chef_agent.evaluate_response_gate`'s
    docstring for why this is deliberately conservative)."""

    tool: str
    ok: bool
    summary: str
    raw: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    recipe_ids_covered: list[str] = Field(default_factory=list)


def _resolve_recipe(recipe_id: str, user_id: str) -> Recipe | None:
    """Resolve `recipe_id` against the base corpus first, then this user's
    saved-recipe library -- mirrors the spec table's `search_recipes` row
    ("a tool resolving a recipe_id must check both")."""
    recipe = get_recipe_by_id(recipe_id)
    if recipe is not None:
        return recipe
    return RecipeLibraryRepository().get_recipe(user_id, recipe_id)


# ---------------------------------------------------------------------------
# 1. search_recipes
# ---------------------------------------------------------------------------


class SearchRecipesArgs(BaseModel):
    tool: Literal["search_recipes"] = "search_recipes"
    ingredients: list[str] = Field(default_factory=list)
    cuisine_preference: str | None = None
    meal_type: str | None = None
    limit: int = Field(default=8, ge=1, le=20)

    @model_validator(mode="after")
    def _require_some_search_criteria(self) -> SearchRecipesArgs:
        """Defense-in-depth for the 2026-08-07 incident (see `app.agent.
        chef_agent.ChefStep.tool_args`'s docstring for the root cause): every
        field here defaults to empty/None, so a malformed or degenerate
        `{}` payload used to validate silently into a no-op search --
        `RecipeRetriever._build_query` would embed the literal string
        "available ingredients: " and return whatever the index considers
        closest to that boilerplate, with no visible error anywhere. Now a
        payload with nothing to search on (no ingredients, no cuisine, no
        meal type) raises here instead, so `dispatch_tool_call` returns
        `ok=False` with a real error the model can see and retry against --
        NOT a `min_length=1` on `ingredients` alone, which would wrongly
        reject a legitimate cuisine-only/meal-type-only query like "suggest
        an Italian dinner"."""
        if not self.ingredients and not self.cuisine_preference and not self.meal_type:
            raise ValueError(
                "search_recipes needs at least one of ingredients, "
                "cuisine_preference, or meal_type -- an empty payload can't "
                "produce a meaningful search."
            )
        return self


def _search_recipes(ctx: ToolContext, args: SearchRecipesArgs) -> ToolResult:
    recipes = RecipeRetriever().retrieve(
        ingredients=args.ingredients,
        cuisine_preference=args.cuisine_preference,
        meal_type=args.meal_type,
        limit=args.limit,
        user_id=ctx.user_id,
    )
    raw = {
        "recipes": [
            {
                "recipe_id": recipe.recipe_id,
                "title": recipe.title,
                "cuisine": recipe.cuisine,
                "meal_type": recipe.meal_type,
            }
            for recipe in recipes
        ]
    }
    titles = ", ".join(recipe.title for recipe in recipes[:3])
    summary = f"Found {len(recipes)} recipe(s)" + (f": {titles}." if titles else ".")
    return ToolResult(tool="search_recipes", ok=True, raw=raw, summary=summary)


# ---------------------------------------------------------------------------
# 2. check_recipe_safety (batch-capable -- advisor Q1)
# ---------------------------------------------------------------------------


class CheckRecipeSafetyArgs(BaseModel):
    tool: Literal["check_recipe_safety"] = "check_recipe_safety"
    recipe_ids: list[str] = Field(min_length=1)


def _check_recipe_safety(ctx: ToolContext, args: CheckRecipeSafetyArgs) -> ToolResult:
    results: list[dict[str, Any]] = []
    covered: list[str] = []
    valid_count = 0

    for recipe_id in args.recipe_ids:
        recipe = _resolve_recipe(recipe_id, ctx.user_id)
        if recipe is None:
            results.append(
                {
                    "recipe_id": recipe_id,
                    "result": {"is_valid": False, "rejection_reason": "Recipe not found"},
                }
            )
            continue
        try:
            verdict = validate_recipe(recipe, ctx.user_profile)
        except ValueError as exc:
            # Mirrors app/api/routes_safety_tools.py's ValueError handling
            # for an unrecognized diet_type: a structured tool-error result,
            # never a raised exception mid-loop.
            results.append(
                {
                    "recipe_id": recipe_id,
                    "result": {"is_valid": False, "rejection_reason": f"Could not validate: {exc}"},
                }
            )
            continue
        results.append({"recipe_id": recipe_id, "result": verdict.model_dump()})
        covered.append(recipe_id)
        if verdict.is_valid:
            valid_count += 1

    rejected_count = len(covered) - valid_count
    summary = (
        f"Checked {len(args.recipe_ids)} recipe(s): {valid_count} safe, "
        f"{rejected_count} rejected."
    )
    return ToolResult(
        tool="check_recipe_safety",
        ok=True,
        raw={"results": results},
        summary=summary,
        recipe_ids_covered=covered,
    )


# ---------------------------------------------------------------------------
# 3. ground_nutrition (advisor Q4 -- rate-limit slicing, bounded concurrency,
#    bounded timeout; never a hard tool failure)
# ---------------------------------------------------------------------------


class GroundNutritionArgs(BaseModel):
    tool: Literal["ground_nutrition"] = "ground_nutrition"
    recipe_id: str | None = None
    ingredients: list[Ingredient] | None = None
    servings: int = Field(default=1, ge=1)


def _ground_nutrition(ctx: ToolContext, args: GroundNutritionArgs) -> ToolResult:
    servings = args.servings
    if args.recipe_id:
        recipe = _resolve_recipe(args.recipe_id, ctx.user_id)
        if recipe is None:
            return ToolResult(
                tool="ground_nutrition",
                ok=False,
                error="recipe not found",
                summary=f"No recipe found for id {args.recipe_id!r}.",
            )
        ingredients = list(recipe.ingredients)
        servings = recipe.servings or servings
    else:
        ingredients = list(args.ingredients or [])

    if not ingredients:
        return ToolResult(
            tool="ground_nutrition",
            ok=False,
            error="no ingredients given",
            summary="No ingredients were given to ground.",
        )

    # Gate at INGREDIENT-request granularity (advisor Q4), not tool-call
    # granularity: FdcCache means a repeat ingredient is free, so only
    # NOVEL ingredients should cost quota. Anything beyond the affordable
    # slice goes straight to `ungrounded_ingredients` -- never a hard
    # failure.
    limiter = get_rate_limiter()
    affordable: list[Ingredient] = []
    over_budget_names: list[str] = []
    for ingredient in ingredients:
        if limiter.allow(
            _GROUND_NUTRITION_RATE_LIMIT_KEY,
            _GROUND_NUTRITION_RATE_LIMIT_MAX,
            _GROUND_NUTRITION_RATE_LIMIT_WINDOW_SECONDS,
        ):
            affordable.append(ingredient)
        else:
            over_budget_names.append(ingredient.name)

    nutrition = None
    timed_out_names: list[str] = []
    if affordable:
        client = UsdaClient()
        semaphore = asyncio.Semaphore(_GROUND_NUTRITION_CONCURRENCY)
        try:
            # Safe ONLY when called from a context with no already-running
            # event loop (a plain sync test, or the worker thread
            # `app.agent.chef_agent.run_chef_turn` always runs in via
            # `asyncio.to_thread`) -- see this tool's module docstring.
            nutrition = asyncio.run(
                asyncio.wait_for(
                    compute_recipe_macros_async(
                        affordable, servings, client=client, semaphore=semaphore
                    ),
                    timeout=_GROUND_NUTRITION_TIMEOUT_SECONDS,
                )
            )
        except TimeoutError:
            # Whatever didn't complete in time also becomes ungrounded --
            # USDA slowness must never hang or fail a chat turn.
            timed_out_names = [ingredient.name for ingredient in affordable]
            logger.warning(
                "ground_nutrition tool timed out after %.1fs grounding %d ingredient(s); "
                "treating them as ungrounded.",
                _GROUND_NUTRITION_TIMEOUT_SECONDS,
                len(affordable),
            )

    ungrounded_extra = over_budget_names + timed_out_names

    if nutrition is None:
        raw = {
            "status": "unknown",
            "verified": False,
            "per_serving": None,
            "ungrounded_ingredients": [ingredient.name for ingredient in ingredients],
        }
        summary = (
            "Nutrition could not be verified for these ingredients right now "
            "(rate limit or timeout) -- treat as unknown, not zero."
        )
        return ToolResult(tool="ground_nutrition", ok=True, raw=raw, summary=summary)

    # Mandate (spec section 2.2): report verified/estimated status via
    # nutrition_view's single source of truth, never re-derive it from raw
    # RecipeNutrition fields. Wrapped in a throwaway Recipe so those
    # functions (which read `Recipe.nutrition`) can be reused as-is.
    display_recipe = Recipe(
        recipe_id="_adhoc_ground_nutrition", title="_adhoc", nutrition=nutrition
    )
    status = macro_display_state(display_recipe)
    trusted = trusted_per_serving(display_recipe)
    combined_ungrounded = list(nutrition.ungrounded_ingredients) + ungrounded_extra

    raw = {
        "status": status,
        "verified": status == "grounded",
        "per_serving": (trusted or nutrition.per_serving).model_dump(),
        "ungrounded_ingredients": combined_ungrounded,
    }
    summary = f"Nutrition status: {status}."
    if combined_ungrounded:
        summary += f" {len(combined_ungrounded)} ingredient(s) unverified."
    return ToolResult(tool="ground_nutrition", ok=True, raw=raw, summary=summary)


# ---------------------------------------------------------------------------
# 4. propose_substitutions
# ---------------------------------------------------------------------------


class ProposeSubstitutionsArgs(BaseModel):
    tool: Literal["propose_substitutions"] = "propose_substitutions"
    recipe_id: str


def _propose_substitutions(ctx: ToolContext, args: ProposeSubstitutionsArgs) -> ToolResult:
    recipe = _resolve_recipe(args.recipe_id, ctx.user_id)
    if recipe is None:
        return ToolResult(
            tool="propose_substitutions",
            ok=False,
            error="recipe not found",
            summary=f"No recipe found for id {args.recipe_id!r}.",
        )
    variants = generate_safe_variants(recipe, ctx.user_profile)
    raw = {
        "variants": [
            {
                "recipe_id": variant.recipe.recipe_id,
                "title": variant.recipe.title,
                "original_ingredient": variant.original_ingredient_name,
                "substitution_note": variant.recipe.substitution_note,
            }
            for variant in variants
        ]
    }
    summary = (
        f"Found {len(variants)} safe substitution variant(s) for {recipe.title}."
        if variants
        else f"No safe substitution variant found for {recipe.title}."
    )
    return ToolResult(tool="propose_substitutions", ok=True, raw=raw, summary=summary)


# ---------------------------------------------------------------------------
# 5. build_day_plan -- the tool wrapper, NOT assemble_plan, is responsible
#    for ensuring candidates are already safety-filtered this turn.
# ---------------------------------------------------------------------------


class BuildDayPlanArgs(BaseModel):
    tool: Literal["build_day_plan"] = "build_day_plan"
    recipe_ids: list[str] = Field(min_length=1)
    calories: int | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    fiber_g: float | None = Field(default=None, ge=0)
    meals: int = Field(default=3, ge=1, le=8)


def _build_day_plan(
    ctx: ToolContext, args: BuildDayPlanArgs, *, verified_safe_recipe_ids: frozenset[str]
) -> ToolResult:
    from app.schemas.recommendation import MacroTargets

    safe_ids = [rid for rid in args.recipe_ids if rid in verified_safe_recipe_ids]
    skipped_ids = [rid for rid in args.recipe_ids if rid not in verified_safe_recipe_ids]
    candidates = [
        recipe
        for recipe in (_resolve_recipe(rid, ctx.user_id) for rid in safe_ids)
        if recipe is not None
    ]

    if not candidates:
        return ToolResult(
            tool="build_day_plan",
            ok=False,
            error="no safety-verified candidates",
            summary=(
                "None of the given recipe_ids were verified safe via "
                "check_recipe_safety this turn -- call that tool first."
            ),
        )

    target = MacroTargets(
        calories=args.calories,
        protein_g=args.protein_g,
        carbs_g=args.carbs_g,
        fat_g=args.fat_g,
        fiber_g=args.fiber_g,
    )
    try:
        plan = assemble_plan(candidates, target, args.meals)
    except ValueError as exc:
        return ToolResult(
            tool="build_day_plan",
            ok=False,
            error=str(exc),
            summary=f"Could not build a day plan: {exc}",
        )

    raw = {
        "within_tolerance": plan.within_tolerance,
        "items": [item.model_dump() for item in plan.items],
        "total_calories": plan.total_calories,
        "total_protein_g": plan.total_protein_g,
        "skipped_unverified_recipe_ids": skipped_ids,
    }
    summary = (
        f"Built a day plan from {len(plan.items)} recipe-serving(s) "
        f"({'within' if plan.within_tolerance else 'outside'} tolerance)."
    )
    if skipped_ids:
        summary += f" Skipped {len(skipped_ids)} unverified recipe_id(s)."
    return ToolResult(tool="build_day_plan", ok=True, raw=raw, summary=summary)


# ---------------------------------------------------------------------------
# 6. get_user_context -- user_id is session-bound, NEVER an LLM argument
#    (the schema below has no such field at all).
# ---------------------------------------------------------------------------


class GetUserContextArgs(BaseModel):
    tool: Literal["get_user_context"] = "get_user_context"


def _get_user_context(ctx: ToolContext, args: GetUserContextArgs) -> ToolResult:
    del args  # no fields -- kept for a uniform handler signature
    taste_profile = derive_taste_profile(ctx.user_id)
    saved_recipes = RecipeLibraryRepository().list_user_recipes(ctx.user_id)

    db = SessionLocal()
    try:
        feedback_rows = FeedbackRepository(db).get_feedback_for_user(ctx.user_id)
    finally:
        db.close()

    notes = AgentNoteRepository().list_active(ctx.user_id)

    raw = {
        "taste_profile": taste_profile.model_dump(),
        "saved_recipes": [
            {"recipe_id": recipe.recipe_id, "title": recipe.title} for recipe in saved_recipes[:20]
        ],
        "recent_feedback": [
            {"recipe_id": row.recipe_id, "feedback_type": row.feedback_type}
            for row in feedback_rows[-10:]
        ],
        "notes": [note.note for note in notes],
    }
    summary = f"{len(saved_recipes)} saved recipe(s), {len(notes)} remembered note(s)."
    return ToolResult(tool="get_user_context", ok=True, raw=raw, summary=summary)


# ---------------------------------------------------------------------------
# 7. remember -- the ONLY LLM-facing note-writing tool (advisor Q2).
# ---------------------------------------------------------------------------


class RememberArgs(BaseModel):
    tool: Literal["remember"] = "remember"
    note: str = Field(min_length=1)


def _remember(ctx: ToolContext, args: RememberArgs) -> ToolResult:
    row = AgentNoteRepository().remember(ctx.user_id, args.note)
    return ToolResult(tool="remember", ok=True, raw={"note": row.note}, summary="Noted.")


# ---------------------------------------------------------------------------
# Registry + dispatch
# ---------------------------------------------------------------------------

ToolArgs = Annotated[
    SearchRecipesArgs
    | CheckRecipeSafetyArgs
    | GroundNutritionArgs
    | ProposeSubstitutionsArgs
    | BuildDayPlanArgs
    | GetUserContextArgs
    | RememberArgs,
    Field(discriminator="tool"),
]

_TOOL_ARGS_ADAPTER: TypeAdapter[ToolArgs] = TypeAdapter(ToolArgs)

TOOL_NAMES = (
    "search_recipes",
    "check_recipe_safety",
    "ground_nutrition",
    "propose_substitutions",
    "build_day_plan",
    "get_user_context",
    "remember",
)


def dispatch_tool_call(
    ctx: ToolContext,
    tool: str,
    args_dict: dict[str, Any],
    *,
    verified_safe_recipe_ids: frozenset[str] = frozenset(),
) -> ToolResult:
    """Validate `args_dict` against the named tool's own args schema and
    run its handler -- the single entry point `app.agent.chef_agent.
    tools_node` calls. Never raises: an unknown tool name, a malformed args
    payload, or an unexpected exception inside a handler all become a
    `ToolResult(ok=False, ...)` instead, since a raised exception mid-loop
    is a dead end for an agent turn (see this module's docstring)."""
    if tool not in TOOL_NAMES:
        return ToolResult(
            tool=tool, ok=False, error="unknown tool", summary=f"Unknown tool {tool!r}."
        )

    try:
        parsed = _TOOL_ARGS_ADAPTER.validate_python({**args_dict, "tool": tool})
    except ValidationError as exc:
        return ToolResult(
            tool=tool,
            ok=False,
            error=f"invalid arguments: {exc}",
            summary=f"{tool} was called with invalid arguments.",
        )

    try:
        if isinstance(parsed, SearchRecipesArgs):
            return _search_recipes(ctx, parsed)
        if isinstance(parsed, CheckRecipeSafetyArgs):
            return _check_recipe_safety(ctx, parsed)
        if isinstance(parsed, GroundNutritionArgs):
            return _ground_nutrition(ctx, parsed)
        if isinstance(parsed, ProposeSubstitutionsArgs):
            return _propose_substitutions(ctx, parsed)
        if isinstance(parsed, BuildDayPlanArgs):
            return _build_day_plan(ctx, parsed, verified_safe_recipe_ids=verified_safe_recipe_ids)
        if isinstance(parsed, GetUserContextArgs):
            return _get_user_context(ctx, parsed)
        if isinstance(parsed, RememberArgs):
            return _remember(ctx, parsed)
    except Exception as exc:  # noqa: BLE001 - never let a tool crash the agent loop
        logger.exception("Chef agent tool %s raised unexpectedly", tool)
        return ToolResult(tool=tool, ok=False, error=str(exc), summary=f"{tool} failed: {exc}")

    # Unreachable: TOOL_NAMES/ToolArgs enumerate the same 7 tools above.
    return ToolResult(tool=tool, ok=False, error="dispatch fell through", summary="Internal error.")
