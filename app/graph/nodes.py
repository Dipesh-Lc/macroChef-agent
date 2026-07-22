from app.config import get_settings
from app.data.recipe_library_repository import RecipeLibraryRepository
from app.graph.state import MacroChefState, ensure_state, state_update
from app.rag.loaders import load_recipes
from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recommendation import MealRecommendation, RejectedRecipe
from app.services.constraint_engine import validate_recipe
from app.services.llm_service import explain_recommendation, template_explanation
from app.services.memory_service import derive_taste_profile, get_user_memory, save_session_summary
from app.services.nutrition_scorer import score_recipe
from app.services.procurement_service import build_shopping_list_for_recipe, merge_shopping_lists
from app.services.ranking_service import rank_recipes
from app.services.recipe_retriever import RecipeRetriever
from app.services.substitution_service import generate_safe_variants
from app.services.text_inventory_parser import merge_inventory_observations, parse_typed_inventory
from app.services.vision_service import extract_inventory_from_image
from app.services.waste_tracking import build_waste_nudges

# Retrieval-stage candidate count (recipe_retriever_node). Widened from 14 so
# that after safety_filter_node removes unsafe/disliked/over-time candidates,
# roughly MAX_RECOMMENDATIONS can still survive to be ranked.
RETRIEVAL_CANDIDATE_LIMIT = 40

# Ranked recommendations returned by meal_ranking_node. Widened from 3 so the
# frontend can paginate (top 5 shown, then "See more" reveals more, up to
# this cap) instead of a fixed top-3.
MAX_RECOMMENDATIONS = 20

# Real per-recipe LLM chef-explanation calls (chef_explanation_node) are
# capped at this count, independent of MAX_RECOMMENDATIONS, because each
# one is a live network call to the configured LLM provider (see
# app.services.model_provider) -- letting this scale with
# MAX_RECOMMENDATIONS (20) turned a 3-call step into a 20-call one last
# session, which plausibly exceeded the frontend's 90s recommend timeout.
# Recommendations beyond this cap get the deterministic
# template_explanation fallback instead (instant, no network call). Matches
# web/src/pages/HomePage.tsx's INITIAL_VISIBLE_COUNT (5) -- the number of
# recommendations shown before the user clicks "see more".
LLM_EXPLANATION_LIMIT = 5


def _trace(state: MacroChefState, message: str) -> list[str]:
    return [*state.debug_trace, message]


def _inventory_from_observations(state: MacroChefState) -> list[ConfirmedIngredient]:
    return [
        ConfirmedIngredient(
            name=observation.normalized_name,
            quantity=observation.quantity,
            amount=observation.amount,
            unit=observation.unit,
        )
        for observation in state.raw_inventory_observations
    ]


def intake_node(state: MacroChefState | dict):
    current = ensure_state(state)
    observations = list(current.raw_inventory_observations)

    if current.confirmed_inventory:
        debug = _trace(
            current,
            (
                "intake_node: using "
                f"{len(current.confirmed_inventory)} pre-confirmed ingredients."
            ),
        )
        return state_update(current, debug_trace=debug)

    text_observations = parse_typed_inventory(current.typed_ingredients)
    image_observations = []
    vision_skipped = False
    if current.image_path and current.input_type in {"image", "mixed"}:
        if get_settings().enable_vision:
            image_observations = extract_inventory_from_image(current.image_path)
        else:
            vision_skipped = True
    observations = merge_inventory_observations(observations, text_observations, image_observations)

    if not observations:
        return state_update(
            current,
            errors=[
                "No ingredients were detected. Add typed ingredients or upload a clearer image."
            ],
            debug_trace=_trace(current, "intake_node: no ingredients detected."),
        )

    low_confidence = [item.normalized_name for item in observations if item.needs_confirmation]
    vision_note = " Vision disabled; uploaded image was not processed." if vision_skipped else ""
    message = (
        f"intake_node: extracted {len(observations)} ingredients"
        + (f"; low confidence: {', '.join(low_confidence)}." if low_confidence else ".")
        + vision_note
    )
    return state_update(
        current,
        raw_inventory_observations=observations,
        debug_trace=_trace(current, message),
    )


def inventory_confirmation_node(state: MacroChefState | dict):
    current = ensure_state(state)
    if current.errors:
        return current.model_dump()

    if current.confirmed_inventory:
        return state_update(
            current,
            debug_trace=_trace(
                current,
                (
                    "inventory_confirmation_node: kept "
                    f"{len(current.confirmed_inventory)} user-confirmed ingredients."
                ),
            ),
        )

    confirmed = _inventory_from_observations(current)
    if not confirmed:
        return state_update(
            current,
            errors=["No confirmed ingredients are available for recipe planning."],
            debug_trace=_trace(current, "inventory_confirmation_node: no confirmed inventory."),
        )

    low_confidence = [
        item.normalized_name
        for item in current.raw_inventory_observations
        if item.needs_confirmation
    ]
    message = (
        f"inventory_confirmation_node: auto-confirmed {len(confirmed)} ingredients"
        + (f"; needs review: {', '.join(low_confidence)}." if low_confidence else ".")
    )
    return state_update(
        current,
        confirmed_inventory=confirmed,
        debug_trace=_trace(current, message),
    )


def constraint_builder_node(state: MacroChefState | dict):
    current = ensure_state(state)
    profile = current.user_profile
    if profile is None:
        return state_update(
            current,
            errors=["Missing user profile."],
            debug_trace=_trace(current, "constraint_builder_node: missing profile."),
        )

    constraints = {
        "allergies": profile.allergies,
        "disliked_ingredients": profile.disliked_ingredients,
        "diet_type": profile.diet_type,
        "preferred_cuisines": profile.preferred_cuisines,
        "macro_targets": profile.macro_targets.model_dump(),
        "max_cook_time_min": profile.max_cook_time_min,
    }
    return state_update(
        current,
        constraints=constraints,
        debug_trace=_trace(current, "constraint_builder_node: built deterministic constraints."),
    )


def recipe_retriever_node(state: MacroChefState | dict):
    current = ensure_state(state)
    if current.errors:
        return current.model_dump()
    ingredients = [item.name for item in current.confirmed_inventory]
    retriever = RecipeRetriever()
    recipes = retriever.retrieve(
        ingredients=ingredients,
        cuisine_preference=current.cuisine_preference,
        meal_type=current.meal_type,
        limit=RETRIEVAL_CANDIDATE_LIMIT,
        user_id=current.user_id,
        include_user_recipes=True,
        include_base_recipes=True,
    )
    return state_update(
        current,
        candidate_recipes=recipes,
        debug_trace=_trace(
            current,
            f"recipe_retriever_node: retrieved {len(recipes)} candidate recipes.",
        ),
    )


def safety_filter_node(state: MacroChefState | dict):
    current = ensure_state(state)
    if current.errors or current.user_profile is None:
        return current.model_dump()

    valid = []
    rejected = list(current.rejected_recipes)
    # See MacroChefState.rejected_recipe_objects -- kept in lockstep with
    # `rejected` so substitution_node can recover the full Recipe later.
    rejected_objects = dict(current.rejected_recipe_objects)
    for recipe in current.candidate_recipes:
        result = validate_recipe(recipe, current.user_profile)
        if result.is_valid:
            valid.append(recipe)
        else:
            rejected.append(
                RejectedRecipe(
                    recipe_id=recipe.recipe_id,
                    title=recipe.title,
                    reason=result.rejection_reason or "Rejected by hard constraint",
                )
            )
            rejected_objects[recipe.recipe_id] = recipe

    return state_update(
        current,
        candidate_recipes=valid,
        rejected_recipes=rejected,
        rejected_recipe_objects=rejected_objects,
        debug_trace=_trace(
            current,
            f"safety_filter_node: {len(valid)} valid, {len(rejected)} total rejected.",
        ),
    )


def fallback_relaxation_node(state: MacroChefState | dict):
    current = ensure_state(state)
    if current.user_profile is None:
        return current.model_dump()

    valid = []
    rejected = list(current.rejected_recipes)
    # Deliberately NOT populating rejected_recipe_objects here (unlike
    # safety_filter_node) -- see substitution_node's docstring: the task
    # spec scopes substitution to recipes "rejected BY safety_filter_node"
    # specifically, which retrieval bounds to ~14 candidates. This node's
    # own scan is over the ENTIRE recipe corpus (thousands of recipes) when
    # triggered; feeding all of those into rejected_recipe_objects would
    # make substitution_node do O(corpus) work on every such request --
    # confirmed as a real, severe slowdown during this task's own testing
    # (a single 381-case benchmark run did not complete in 20+ minutes with
    # this wired in). Bounding to safety_filter_node's own small rejected
    # set keeps substitution_node's cost independent of corpus size, at the
    # cost of never attempting a rescue for a recipe ONLY seen via this
    # broader fallback scan -- an accepted, documented scope limit (see
    # docs/BACKLOG.md), not a silent gap: this only ever means a missed
    # rescue opportunity, never an unsafe one.
    recipes = [
        *load_recipes(),
        *RecipeLibraryRepository().list_user_recipes(current.user_id),
    ]
    for recipe in recipes:
        result = validate_recipe(recipe, current.user_profile)
        if result.is_valid:
            valid.append(recipe)
        elif not any(item.recipe_id == recipe.recipe_id for item in rejected):
            rejected.append(
                RejectedRecipe(
                    recipe_id=recipe.recipe_id,
                    title=recipe.title,
                    reason=result.rejection_reason or "Rejected by hard constraint",
                )
            )

    if not valid:
        return state_update(
            current,
            rejected_recipes=rejected,
            errors=["No recipes satisfy the allergy, diet, dislike, and time constraints."],
            debug_trace=_trace(current, "fallback_relaxation_node: no safe recipes found."),
        )

    return state_update(
        current,
        candidate_recipes=valid[:12],
        rejected_recipes=rejected,
        debug_trace=_trace(
            current,
            (
                "fallback_relaxation_node: broadened retrieval and found "
                f"{len(valid[:12])} safe recipes."
            ),
        ),
    )


# RejectedRecipe.reason prefixes produced by constraint_engine.validate_recipe
# (see its ValidationResult.rejection_reason strings) that indicate an
# allergy-or-diet rejection specifically -- as opposed to "Contains a
# disliked ingredient" or "Exceeds maximum cooking time", which are not
# allergy/diet safety reasons and are deliberately excluded (see the task
# spec: substitution_node only reads recipes "rejected ... specifically for
# an allergy or diet reason (not e.g. rejected for macro/time fit)").
_ALLERGEN_REJECTION_PREFIX = "Contains a user allergen"
_DIET_REJECTION_PREFIX = "Violates diet type"


def substitution_node(state: MacroChefState | dict):
    """Deterministic substitution engine integration (Phase 3 roadmap item).

    NO SAFETY AUTHORITY of its own -- see app.services.substitution_
    service's module docstring. For every recipe in `current.rejected_
    recipes` whose rejection reason is specifically an allergy or diet
    violation, recovers the full parent Recipe from `current.rejected_
    recipe_objects` and asks `generate_safe_variants` for every candidate
    swap that PASSES `constraint_engine.validate_recipe` against the user's
    FULL profile. Only variants that already passed that re-validation are
    ever appended to `candidate_recipes`, exactly like any other recipe
    flowing into nutrition_scoring_node/meal_ranking_node downstream.
    """
    current = ensure_state(state)
    if current.errors or current.user_profile is None:
        return current.model_dump()

    existing_ids = {recipe.recipe_id for recipe in current.candidate_recipes}
    new_candidates = list(current.candidate_recipes)
    variants_added = 0

    for rejected in current.rejected_recipes:
        reason = rejected.reason or ""
        if not (reason.startswith(_ALLERGEN_REJECTION_PREFIX) or reason.startswith(_DIET_REJECTION_PREFIX)):
            continue
        parent = current.rejected_recipe_objects.get(rejected.recipe_id)
        if parent is None:
            continue
        for variant in generate_safe_variants(parent, current.user_profile):
            if variant.recipe.recipe_id in existing_ids:
                continue
            existing_ids.add(variant.recipe.recipe_id)
            new_candidates.append(variant.recipe)
            variants_added += 1

    return state_update(
        current,
        candidate_recipes=new_candidates,
        debug_trace=_trace(
            current,
            f"substitution_node: added {variants_added} safety-validated substitution variant(s).",
        ),
    )


def nutrition_scoring_node(state: MacroChefState | dict):
    current = ensure_state(state)
    if current.errors or current.user_profile is None:
        return current.model_dump()

    liked_ids, disliked_ids = get_user_memory(current.user_id)
    # Phase 3 (visible personalization loop): a GENERALIZING signal derived
    # from the same feedback history `get_user_memory` above reads exactly --
    # see app.services.memory_service.derive_taste_profile. Deterministic,
    # never LLM-authored, never consulted by the safety filter (which already
    # ran, upstream of this node -- see safety_filter_node/
    # fallback_relaxation_node above).
    taste_profile = derive_taste_profile(current.user_id)
    scores = [
        score_recipe(
            recipe,
            current.confirmed_inventory,
            current.user_profile,
            cuisine_preference=current.cuisine_preference,
            liked_recipe_ids=liked_ids,
            disliked_recipe_ids=disliked_ids,
            taste_profile=taste_profile,
        )
        for recipe in current.candidate_recipes
    ]
    # Phase 4 (expiry/waste tracking): deterministic, display-only "use your
    # X today" nudges for whatever in confirmed_inventory is expiring soon --
    # see app.services.waste_tracking.build_waste_nudges. Placed here (not a
    # dedicated node) because it needs nothing this node doesn't already
    # have (confirmed_inventory) and produces no safety-relevant output.
    waste_nudges = build_waste_nudges(current.confirmed_inventory)
    return state_update(
        current,
        scored_recipes=scores,
        taste_profile=taste_profile,
        waste_nudges=waste_nudges,
        debug_trace=_trace(current, f"nutrition_scoring_node: scored {len(scores)} recipes."),
    )


def meal_ranking_node(state: MacroChefState | dict):
    current = ensure_state(state)
    scores_by_id = {score.recipe_id: score for score in current.scored_recipes}
    ranked = rank_recipes(current.candidate_recipes, scores_by_id, limit=MAX_RECOMMENDATIONS)
    recommendations = [
        MealRecommendation(
            recipe=recipe,
            score=score,
            explanation="",
            shopping_list=score.missing_ingredients,
        )
        for recipe, score in ranked
    ]
    return state_update(
        current,
        final_recommendations=recommendations,
        debug_trace=_trace(
            current,
            f"meal_ranking_node: selected {len(recommendations)} top recipes.",
        ),
    )


def chef_explanation_node(state: MacroChefState | dict):
    current = ensure_state(state)
    explained = []
    llm_calls = 0
    for index, recommendation in enumerate(current.final_recommendations):
        if index < LLM_EXPLANATION_LIMIT:
            explanation = explain_recommendation(
                recommendation.recipe, recommendation.score, allergy_safe=True
            )
            llm_calls += 1
        else:
            # Beyond LLM_EXPLANATION_LIMIT: skip the live LLM call and use the
            # deterministic template fallback directly (see the constant's
            # comment above) -- keeps this node's latency bounded regardless
            # of MAX_RECOMMENDATIONS.
            explanation = template_explanation(
                recommendation.recipe, recommendation.score, allergy_safe=True
            )
        explained.append(recommendation.model_copy(update={"explanation": explanation}))
    return state_update(
        current,
        final_recommendations=explained,
        debug_trace=_trace(
            current,
            (
                "chef_explanation_node: generated structured explanations "
                f"({llm_calls} via live LLM, {len(explained) - llm_calls} via template fallback)."
            ),
        ),
    )


def procurement_node(state: MacroChefState | dict):
    current = ensure_state(state)
    all_items = []
    updated_recommendations = []
    for recommendation in current.final_recommendations:
        items = build_shopping_list_for_recipe(recommendation.recipe, current.confirmed_inventory)
        all_items.extend(items)
        updated_recommendations.append(
            recommendation.model_copy(update={"shopping_list": [item.name for item in items]})
        )
    shopping_list = merge_shopping_lists(all_items)
    return state_update(
        current,
        final_recommendations=updated_recommendations,
        shopping_list=shopping_list,
        debug_trace=_trace(
            current,
            f"procurement_node: produced {len(shopping_list)} shopping items.",
        ),
    )


def memory_update_node(state: MacroChefState | dict):
    current = ensure_state(state)
    summary = save_session_summary(current.user_id, current.final_recommendations)
    return state_update(
        current,
        memory_update=summary,
        debug_trace=_trace(current, "memory_update_node: saved lightweight session memory."),
    )
