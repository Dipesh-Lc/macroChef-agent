from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.inventory import ConfirmedIngredient, InventoryObservation
from app.schemas.recipe import Recipe
from app.schemas.recommendation import (
    MealRecommendation,
    RecipeScore,
    RejectedRecipe,
    TasteProfile,
)
from app.schemas.shopping import ShoppingItem
from app.schemas.user import UserProfile
from app.schemas.waste_tracking import WasteNudge


class MacroChefState(BaseModel):
    user_id: str = "demo_user"
    # ROADMAP.md Phase 3, Step 3.2: gates whether inventory_confirmation_node
    # is allowed to call `interrupt()` for a true HITL pause. Deliberately
    # NOT settable from RecommendationRequest's wire schema -- the only
    # writer is app.api.routes_runs's start-a-run handler, which sets this
    # directly in Python when building initial state for the checkpointed
    # graph (app.graph.builder.get_compiled_macrochef_graph). The existing
    # POST /recipes/recommend and /recipes/recommend/stream endpoints never
    # set it (default False), so they keep running the uncheckpointed graph
    # to completion exactly as before this step -- same trust-boundary shape
    # as `user_id` never coming from client-supplied data (invariant #3): a
    # flag that decides whether a safety-adjacent pause is even reachable
    # must not become client-settable, even by accident via a permissive
    # schema default.
    hitl_enabled: bool = False
    input_type: Literal["text", "image", "manual", "mixed"] = "text"
    image_path: str | None = None
    typed_ingredients: str | None = None
    user_profile: UserProfile | None = None
    raw_inventory_observations: list[InventoryObservation] = Field(default_factory=list)
    confirmed_inventory: list[ConfirmedIngredient] = Field(default_factory=list)
    cuisine_preference: str | None = None
    meal_type: str | None = None
    candidate_recipes: list[Recipe] = Field(default_factory=list)
    rejected_recipes: list[RejectedRecipe] = Field(default_factory=list)
    # Full Recipe objects for the SUBSET of `rejected_recipes` that
    # safety_filter_node itself rejected (bounded to its own small candidate
    # set, ~14 recipes) -- keyed by recipe_id. Deliberately NOT populated by
    # fallback_relaxation_node's much larger, corpus-wide scan (thousands of
    # recipes) -- see that node's own comment for why: substitution_node
    # would otherwise do O(corpus) work on every request. RejectedRecipe
    # alone (recipe_id/title/reason) doesn't carry enough to build a
    # substitution candidate; substitution_node (app.services.substitution_
    # service.generate_safe_variants) reads this to recover the complete
    # rejected recipe. Never consulted by anything safety-relevant -- see
    # substitution_node's own docstring.
    rejected_recipe_objects: dict[str, Recipe] = Field(default_factory=dict)
    scored_recipes: list[RecipeScore] = Field(default_factory=list)
    # Set by nutrition_scoring_node (app.services.memory_service.
    # derive_taste_profile) -- ranking/UX only, see TasteProfile's docstring.
    taste_profile: TasteProfile | None = None
    # Set by nutrition_scoring_node (app.services.waste_tracking.
    # build_waste_nudges) -- Phase 4 expiry/waste tracking, display/UX only,
    # see WasteNudge's docstring.
    waste_nudges: list[WasteNudge] = Field(default_factory=list)
    final_recommendations: list[MealRecommendation] = Field(default_factory=list)
    shopping_list: list[ShoppingItem] = Field(default_factory=list)
    memory_update: str | None = None
    constraints: dict[str, object] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    debug_trace: list[str] = Field(default_factory=list)


def ensure_state(state: MacroChefState | dict) -> MacroChefState:
    if isinstance(state, MacroChefState):
        return state
    return MacroChefState.model_validate(state)


def state_update(state: MacroChefState, **updates):
    data = state.model_dump()
    data.update(updates)
    return data
