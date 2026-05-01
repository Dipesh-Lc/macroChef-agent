from app.data.recipe_library_repository import RecipeLibraryRepository
from app.graph.state import MacroChefState, ensure_state, state_update
from app.rag.loaders import load_recipes
from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recommendation import MealRecommendation, RejectedRecipe
from app.services.constraint_engine import validate_recipe
from app.services.llm_service import explain_recommendation
from app.services.memory_service import get_user_memory, save_session_summary
from app.services.nutrition_scorer import score_recipe
from app.services.procurement_service import build_shopping_list_for_recipe, merge_shopping_lists
from app.services.ranking_service import rank_recipes
from app.services.recipe_retriever import RecipeRetriever
from app.services.text_inventory_parser import merge_inventory_observations, parse_typed_inventory
from app.services.vision_service import extract_inventory_from_image


def _trace(state: MacroChefState, message: str) -> list[str]:
    return [*state.debug_trace, message]


def _inventory_from_observations(state: MacroChefState) -> list[ConfirmedIngredient]:
    return [
        ConfirmedIngredient(name=observation.normalized_name, quantity=observation.quantity)
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
    if current.image_path and current.input_type in {"image", "mixed"}:
        image_observations = extract_inventory_from_image(current.image_path)
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
    message = (
        f"intake_node: extracted {len(observations)} ingredients"
        + (f"; low confidence: {', '.join(low_confidence)}." if low_confidence else ".")
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
        limit=14,
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

    return state_update(
        current,
        candidate_recipes=valid,
        rejected_recipes=rejected,
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


def nutrition_scoring_node(state: MacroChefState | dict):
    current = ensure_state(state)
    if current.errors or current.user_profile is None:
        return current.model_dump()

    liked_ids, disliked_ids = get_user_memory(current.user_id)
    scores = [
        score_recipe(
            recipe,
            current.confirmed_inventory,
            current.user_profile,
            cuisine_preference=current.cuisine_preference,
            liked_recipe_ids=liked_ids,
            disliked_recipe_ids=disliked_ids,
        )
        for recipe in current.candidate_recipes
    ]
    return state_update(
        current,
        scored_recipes=scores,
        debug_trace=_trace(current, f"nutrition_scoring_node: scored {len(scores)} recipes."),
    )


def meal_ranking_node(state: MacroChefState | dict):
    current = ensure_state(state)
    scores_by_id = {score.recipe_id: score for score in current.scored_recipes}
    ranked = rank_recipes(current.candidate_recipes, scores_by_id, limit=3)
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
    for recommendation in current.final_recommendations:
        explanation = explain_recommendation(
            recommendation.recipe, recommendation.score, allergy_safe=True
        )
        explained.append(recommendation.model_copy(update={"explanation": explanation}))
    return state_update(
        current,
        final_recommendations=explained,
        debug_trace=_trace(current, "chef_explanation_node: generated structured explanations."),
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
