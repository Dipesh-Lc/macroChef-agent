"""Roadmap item "Shareable plan URLs" (Phase 4 item 4) -- THE LOAD-BEARING
TESTS for this FULL TREATMENT item.

For each of the four shareable types, constructs an input object with every
sensitive field populated with an obviously-sentinel value, runs it through
the corresponding `app.services.share_service` mapping function, and
asserts the resulting `Public*` object:

  (a) has none of the stripped field NAMES at all (checked both against the
      `Public*` schema's own declared fields and against the actual
      serialized JSON's keys), and
  (b) never contains the sentinel VALUE anywhere in its serialized output
      (a belt-and-suspenders string scan of the full JSON dump, not just a
      schema check).

See `app.services.share_service`'s module docstring for why this is the
single most important property of this feature: `Recipe.owner_user_id` is a
field ON THE RECIPE OBJECT ITSELF, and if it were ever echoed verbatim, a
share link would leak the sharer's session identity.
"""

import json

from app.schemas.batch_plan import BatchPlan, RecipeFit
from app.schemas.day_plan import DayPlan, PlanItem
from app.schemas.recipe import Recipe
from app.schemas.share import PublicBatchPlan, PublicDayPlan, PublicRecipe, PublicWeeklyPlan
from app.schemas.weekly_plan import WeeklyPlan
from app.services.share_service import (
    batch_plan_to_public,
    day_plan_to_public,
    recipe_to_public,
    weekly_plan_to_public,
)

OWNER_SENTINEL = "secret-user-12345"
IMAGE_PATH_SENTINEL = "/srv/secret/local/path/only-the-owner-can-see.jpg"


# ---------------------------------------------------------------------------
# PublicRecipe
# ---------------------------------------------------------------------------


def _sentinel_recipe() -> Recipe:
    return Recipe(
        recipe_id="recipe_share_test_1",
        title="Sentinel Recipe",
        cuisine="test-cuisine",
        meal_type="dinner",
        ingredients=[{"name": "rice", "amount": 100, "unit": "g"}],
        instructions=["Cook the rice."],
        allergens=["gluten"],
        diet_tags=["vegetarian"],
        cook_time_min=20,
        # nutrition deliberately left None here so the sentinel numeric
        # scan below can't collide with a legitimate nested
        # RecipeNutrition.per_serving/total protein_g/etc figure.
        nutrition=None,
        description="A recipe used only to prove the allowlist strips fields.",
        difficulty="easy",
        servings=2,
        equipment=["pan"],
        image_url="https://example.com/public-image.jpg",
        image_path=IMAGE_PATH_SENTINEL,
        source_type="base",
        source_name="Test Source",
        source_url="https://example.com/source",
        owner_user_id=OWNER_SENTINEL,
        is_user_saved=True,
        is_active=False,
        restored_from_quarantine=True,
        substitution_note="Swapped X -> Y",
    )


def test_recipe_to_public_strips_owner_and_private_fields() -> None:
    recipe = _sentinel_recipe()
    public = recipe_to_public(recipe)

    assert isinstance(public, PublicRecipe)

    stripped_field_names = {
        "owner_user_id",
        "is_user_saved",
        "image_path",
        "is_active",
        "restored_from_quarantine",
        "calories",
        "protein_g",
        "carbs_g",
        "fat_g",
        "fiber_g",
    }
    # (a) the PublicRecipe schema itself declares none of these fields.
    assert stripped_field_names.isdisjoint(PublicRecipe.model_fields.keys())

    dumped = public.model_dump()
    # (a) none of the stripped field names appear as a top-level JSON key.
    assert stripped_field_names.isdisjoint(dumped.keys())

    serialized = public.model_dump_json()
    # (b) belt-and-suspenders: the sentinel VALUES do not appear ANYWHERE
    # in the serialized output.
    assert OWNER_SENTINEL not in serialized
    assert IMAGE_PATH_SENTINEL not in serialized
    # Kept fields survive the trip (proves this isn't an empty/broken map).
    assert public.recipe_id == "recipe_share_test_1"
    assert public.title == "Sentinel Recipe"
    assert public.substitution_note == "Swapped X -> Y"


def test_recipe_to_public_strips_self_reported_tag_macros() -> None:
    recipe = _sentinel_recipe().model_copy(
        update={
            "calories": 918273.0,
            "protein_g": 918273.0,
            "carbs_g": 918273.0,
            "fat_g": 918273.0,
            "fiber_g": 918273.0,
        }
    )
    public = recipe_to_public(recipe)
    serialized = public.model_dump_json()

    assert "918273" not in serialized


# ---------------------------------------------------------------------------
# PublicDayPlan
# ---------------------------------------------------------------------------

_DAY_TRUSTED_POOL_SENTINEL = 424242


def _sentinel_day_plan() -> DayPlan:
    return DayPlan(
        items=[PlanItem(recipe_id="r1", title="Recipe One", servings=2)],
        meals_planned=2,
        trusted_pool_size=_DAY_TRUSTED_POOL_SENTINEL,
        total_calories=500,
        total_protein_g=40,
        total_carbs_g=50,
        total_fat_g=15,
        total_fiber_g=8,
        target_calories=520,
        target_protein_g=42,
        calories_relative_error=0.04,
        protein_relative_error=0.05,
        carbs_relative_error=0.02,
        fat_relative_error=0.01,
        fiber_relative_error=0.03,
        within_tolerance=True,
    )


def test_day_plan_to_public_strips_trusted_pool_size() -> None:
    day_plan = _sentinel_day_plan()
    public = day_plan_to_public(day_plan)

    assert isinstance(public, PublicDayPlan)
    assert "trusted_pool_size" not in PublicDayPlan.model_fields
    dumped = public.model_dump()
    assert "trusted_pool_size" not in dumped

    serialized = public.model_dump_json()
    assert str(_DAY_TRUSTED_POOL_SENTINEL) not in serialized
    # Kept fields survive the trip.
    assert public.meals_planned == 2
    assert public.within_tolerance is True


# ---------------------------------------------------------------------------
# PublicBatchPlan
# ---------------------------------------------------------------------------

_BATCH_TRUSTED_POOL_SENTINEL = 535353


def _sentinel_batch_plan() -> BatchPlan:
    return BatchPlan(
        items=[PlanItem(recipe_id="r1", title="Recipe One", servings=3)],
        containers=10,
        per_container_target_calories=450,
        per_container_target_protein_g=35,
        recipes_selected=1,
        within_tolerance=True,
        trusted_pool_size=_BATCH_TRUSTED_POOL_SENTINEL,
        recipe_fits=[
            RecipeFit(
                recipe_id="r1",
                title="Recipe One",
                per_serving_calories=450,
                per_serving_protein_g=35,
                kcal_relative_error=0.02,
                protein_relative_error=0.03,
                container_count=10,
            )
        ],
    )


def test_batch_plan_to_public_strips_trusted_pool_size() -> None:
    batch_plan = _sentinel_batch_plan()
    public = batch_plan_to_public(batch_plan)

    assert isinstance(public, PublicBatchPlan)
    assert "trusted_pool_size" not in PublicBatchPlan.model_fields
    dumped = public.model_dump()
    assert "trusted_pool_size" not in dumped

    serialized = public.model_dump_json()
    assert str(_BATCH_TRUSTED_POOL_SENTINEL) not in serialized
    # Kept fields survive the trip.
    assert public.containers == 10
    assert public.recipe_fits[0].recipe_id == "r1"


# ---------------------------------------------------------------------------
# PublicWeeklyPlan
# ---------------------------------------------------------------------------

_WEEK_TRUSTED_POOL_SENTINEL = 646464
_PANTRY_UTILIZATION_SENTINEL = 0.918273
_UNCOMPARED_COUNT_SENTINEL = 758585


def _sentinel_weekly_plan() -> WeeklyPlan:
    return WeeklyPlan(
        days=[_sentinel_day_plan()],
        pantry_utilization=_PANTRY_UTILIZATION_SENTINEL,
        uncompared_ingredient_count=_UNCOMPARED_COUNT_SENTINEL,
        trusted_pool_size=_WEEK_TRUSTED_POOL_SENTINEL,
    )


def test_weekly_plan_to_public_strips_trusted_pool_and_pantry_fields() -> None:
    weekly_plan = _sentinel_weekly_plan()
    public = weekly_plan_to_public(weekly_plan)

    assert isinstance(public, PublicWeeklyPlan)
    stripped_field_names = {
        "trusted_pool_size",
        "pantry_utilization",
        "uncompared_ingredient_count",
    }
    assert stripped_field_names.isdisjoint(PublicWeeklyPlan.model_fields.keys())
    dumped = public.model_dump()
    assert stripped_field_names.isdisjoint(dumped.keys())
    # Nested per-day trusted_pool_size is stripped too (each day is mapped
    # through day_plan_to_public, not embedded raw).
    for day in dumped["days"]:
        assert stripped_field_names.isdisjoint(day.keys())

    serialized = public.model_dump_json()
    assert str(_WEEK_TRUSTED_POOL_SENTINEL) not in serialized
    assert str(_PANTRY_UTILIZATION_SENTINEL) not in serialized
    assert str(_UNCOMPARED_COUNT_SENTINEL) not in serialized
    # The nested day's own trusted_pool_size sentinel must also be gone.
    assert str(_DAY_TRUSTED_POOL_SENTINEL) not in serialized
    # Kept fields survive the trip.
    assert len(public.days) == 1
    assert public.days[0].meals_planned == 2


# ---------------------------------------------------------------------------
# Sanity: the mapping round-trips through JSON exactly as
# app.services.share_service.get_share reconstructs it (proves the stored
# `SharedPlan.content` -> SharedPlanView.content path doesn't silently
# resurrect a stripped field via some other route, e.g. an alias).
# ---------------------------------------------------------------------------


def test_public_recipe_round_trips_through_json_without_reintroducing_owner() -> None:
    public = recipe_to_public(_sentinel_recipe())
    round_tripped = PublicRecipe.model_validate(json.loads(public.model_dump_json()))
    assert "owner_user_id" not in round_tripped.model_dump()
