"""Tests for POST /plan/day (roadmap item B3).

THE SINGLE MOST IMPORTANT TEST IN THIS FILE:
test_allergic_users_excluded_recipe_never_appears_even_as_a_perfect_macro_fit
-- proves app.services.constraint_engine.validate_recipe actually runs
inside the route BEFORE app.services.day_planner ever sees a candidate. A
recipe containing the user's allergen is engineered to be a mathematically
perfect macro match; if the safety filter were ever skipped, bypassed, or
reordered after assembly, this test fails.
"""

import pytest
from fastapi.testclient import TestClient

import app.api.routes_day_planner as routes_day_planner_module
from app.main import create_app
from app.schemas.nutrition import FoodMacros, GroundingStatus, RecipeNutrition
from app.schemas.recipe import Recipe


def _nutrition(status: GroundingStatus, *, flags: list[str] | None = None, **per_serving) -> RecipeNutrition:
    macros = FoodMacros(**per_serving)
    return RecipeNutrition(
        status=status,
        servings=1,
        total=macros,
        per_serving=macros,
        coverage=1.0 if status == GroundingStatus.GROUNDED else 0.5,
        flags=flags or [],
    )


def _client() -> TestClient:
    return TestClient(create_app())


def _base_profile(**overrides) -> dict:
    profile = {
        "allergies": [],
        "disliked_ingredients": [],
        "diet_type": None,
        "preferred_cuisines": [],
        "macro_targets": {"calories": 300, "protein_g": 20},
        "max_cook_time_min": None,
    }
    profile.update(overrides)
    return profile


# ---------------------------------------------------------------------------
# THE single most important test: constraint_engine.validate_recipe actually
# gates day-plan assembly.
# ---------------------------------------------------------------------------


def test_allergic_users_excluded_recipe_never_appears_even_as_a_perfect_macro_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # This recipe is a mathematically PERFECT macro match for the target
    # below (300 kcal / 20g protein, K=1) -- the most tempting possible
    # candidate for the planner -- but contains a milk-allergen ingredient.
    unsafe_perfect_fit = Recipe(
        recipe_id="unsafe_perfect_fit",
        title="Milk-Laden Perfect Fit Bowl",
        ingredients=[{"name": "milk", "amount": 200, "unit": "ml"}],
        instructions=["Pour milk."],
        allergens=["dairy", "milk"],
        nutrition=_nutrition(
            GroundingStatus.GROUNDED, calories=300, protein_g=20, carbs_g=10, fat_g=8, fiber_g=0
        ),
    )
    # A safe recipe that is a much worse macro fit -- if the safety filter
    # works, this (or nothing) is the best the planner can legitimately do.
    safe_far_fit = Recipe(
        recipe_id="safe_far_fit",
        title="Safe But Distant Fit",
        ingredients=[{"name": "rice", "amount": 150, "unit": "g"}],
        instructions=["Cook rice."],
        allergens=[],
        nutrition=_nutrition(
            GroundingStatus.GROUNDED, calories=900, protein_g=90, carbs_g=100, fat_g=20, fiber_g=5
        ),
    )

    monkeypatch.setattr(
        routes_day_planner_module,
        "load_corpus",
        lambda: [unsafe_perfect_fit, safe_far_fit],
    )

    client = _client()
    payload = {
        "user_profile": _base_profile(allergies=["milk"]),
        "meals": 1,
    }

    response = client.post("/plan/day", json=payload)

    assert response.status_code == 200
    body = response.json()

    # The unsafe recipe must never appear in the assembled plan...
    plan_recipe_ids = {item["recipe_id"] for item in body["plan"]["items"]}
    assert "unsafe_perfect_fit" not in plan_recipe_ids

    # ...even though, ignoring safety, it would have been a perfect
    # (0-error) macro fit -- confirms this isn't a coincidence of the
    # safe recipe also fitting well.
    assert body["plan"]["within_tolerance"] is False
    assert body["plan"]["calories_relative_error"] > 0.0

    # ...and it must show up in rejected_recipes, proving the filter ran
    # (rather than the recipe simply never being loaded).
    rejected_ids = {item["recipe_id"] for item in body["rejected_recipes"]}
    assert "unsafe_perfect_fit" in rejected_ids
    rejected_entry = next(
        item for item in body["rejected_recipes"] if item["recipe_id"] == "unsafe_perfect_fit"
    )
    assert "allergen" in rejected_entry["reason"].lower()

    # The safe recipe must have been a candidate the planner was free to use.
    assert "safe_far_fit" not in rejected_ids


def test_non_allergic_user_can_receive_the_same_recipe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check on the fixture itself: the same recipe IS selectable by
    a user without the allergy, proving the exclusion above is caused by the
    allergy, not by some unrelated bug (e.g. an accidental blanket filter)."""
    perfect_fit = Recipe(
        recipe_id="perfect_fit",
        title="Milk-Laden Perfect Fit Bowl",
        ingredients=[{"name": "milk", "amount": 200, "unit": "ml"}],
        instructions=["Pour milk."],
        allergens=["dairy", "milk"],
        nutrition=_nutrition(
            GroundingStatus.GROUNDED, calories=300, protein_g=20, carbs_g=10, fat_g=8, fiber_g=0
        ),
    )
    monkeypatch.setattr(routes_day_planner_module, "load_corpus", lambda: [perfect_fit])

    client = _client()
    payload = {"user_profile": _base_profile(allergies=[]), "meals": 1}

    response = client.post("/plan/day", json=payload)

    assert response.status_code == 200
    body = response.json()
    plan_recipe_ids = {item["recipe_id"] for item in body["plan"]["items"]}
    assert "perfect_fit" in plan_recipe_ids
    assert body["plan"]["within_tolerance"] is True
    assert body["rejected_recipes"] == []


# ---------------------------------------------------------------------------
# meals=None (default) sweeps the day-plan range.
# ---------------------------------------------------------------------------


def test_default_meals_none_sweeps_day_plan_range(monkeypatch: pytest.MonkeyPatch) -> None:
    recipe = Recipe(
        recipe_id="a",
        title="A",
        ingredients=[{"name": "rice", "amount": 100, "unit": "g"}],
        instructions=["Cook."],
        nutrition=_nutrition(GroundingStatus.GROUNDED, calories=300, protein_g=20, carbs_g=10, fat_g=5, fiber_g=2),
    )
    monkeypatch.setattr(routes_day_planner_module, "load_corpus", lambda: [recipe])

    client = _client()
    payload = {
        "user_profile": _base_profile(macro_targets={"calories": 900, "protein_g": 60}),
        # exact fit only at K=3; default max_per_recipe=2 would make K=3
        # combinatorially infeasible with a single candidate, so raise the
        # cap to isolate what this test is actually checking (the meals=None
        # sweep, not max_per_recipe behavior -- that's covered separately in
        # tests/test_day_planner.py).
        "max_per_recipe": 3,
    }

    response = client.post("/plan/day", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["within_tolerance"] is True
    assert body["plan"]["meals_planned"] == 3
    assert body["plan"]["trusted_pool_size"] == 1


# ---------------------------------------------------------------------------
# Missing calories/protein_g target -> explicit 422, never a silent guess.
# ---------------------------------------------------------------------------


def test_missing_macro_targets_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    recipe = Recipe(
        recipe_id="a",
        title="A",
        ingredients=[{"name": "rice", "amount": 100, "unit": "g"}],
        instructions=["Cook."],
        nutrition=_nutrition(GroundingStatus.GROUNDED, calories=300, protein_g=20, carbs_g=10, fat_g=5, fiber_g=2),
    )
    monkeypatch.setattr(routes_day_planner_module, "load_corpus", lambda: [recipe])

    client = _client()
    payload = {"user_profile": _base_profile(macro_targets={})}

    response = client.post("/plan/day", json=payload)

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /plan/shopping-list (roadmap item B4).
# ---------------------------------------------------------------------------


def test_shopping_list_endpoint_aggregates_across_plan_items(monkeypatch: pytest.MonkeyPatch) -> None:
    recipe_a = Recipe(
        recipe_id="a",
        title="Recipe A",
        servings=1,
        ingredients=[{"name": "tofu", "amount": 200, "unit": "g"}],
        instructions=["Cook."],
    )
    recipe_b = Recipe(
        recipe_id="b",
        title="Recipe B",
        servings=1,
        ingredients=[{"name": "tofu", "amount": 150, "unit": "g"}],
        instructions=["Cook."],
    )
    monkeypatch.setattr(routes_day_planner_module, "load_corpus", lambda: [recipe_a, recipe_b])

    client = _client()
    payload = {
        "plan": {
            "items": [
                {"recipe_id": "a", "title": "Recipe A", "servings": 1},
                {"recipe_id": "b", "title": "Recipe B", "servings": 2},
            ],
            "meals_planned": 3,
            "trusted_pool_size": 2,
            "total_calories": 0,
            "total_protein_g": 0,
            "total_carbs_g": 0,
            "total_fat_g": 0,
            "total_fiber_g": 0,
            "target_calories": 0,
            "target_protein_g": 0,
            "calories_relative_error": 0,
            "protein_relative_error": 0,
            "within_tolerance": True,
        },
        "inventory": [{"name": "tofu", "amount": 100, "unit": "g"}],
    }

    response = client.post("/plan/shopping-list", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert len(body["shopping_list"]) == 1
    item = body["shopping_list"][0]
    assert item["name"] == "tofu"
    assert item["amount"] == pytest.approx(400.0)  # (200 + 2*150) - 100
    assert item["unit"] == "g"


# ---------------------------------------------------------------------------
# POST /plan/shopping-list-for-items (recipe search / plan-builder follow-up).
# ---------------------------------------------------------------------------


def test_shopping_list_for_items_aggregates_across_two_items_sharing_an_ingredient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirms the aggregate-then-reconcile-once behavior of
    `build_shopping_list_for_items` isn't bypassed for this endpoint: two
    PlanItems sharing an ingredient (tofu) must be summed BEFORE the pantry
    is subtracted, exactly once -- mirroring
    test_shopping_list_endpoint_aggregates_across_plan_items above."""
    recipe_a = Recipe(
        recipe_id="a",
        title="Recipe A",
        servings=1,
        ingredients=[{"name": "tofu", "amount": 200, "unit": "g"}],
        instructions=["Cook."],
    )
    recipe_b = Recipe(
        recipe_id="b",
        title="Recipe B",
        servings=1,
        ingredients=[{"name": "tofu", "amount": 150, "unit": "g"}],
        instructions=["Cook."],
    )
    monkeypatch.setattr(routes_day_planner_module, "load_corpus", lambda: [recipe_a, recipe_b])

    client = _client()
    payload = {
        "items": [
            {"recipe_id": "a", "title": "Recipe A", "servings": 1},
            {"recipe_id": "b", "title": "Recipe B", "servings": 2},
        ],
        "inventory": [{"name": "tofu", "amount": 100, "unit": "g"}],
    }

    response = client.post("/plan/shopping-list-for-items", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert len(body["shopping_list"]) == 1
    item = body["shopping_list"][0]
    assert item["name"] == "tofu"
    assert item["amount"] == pytest.approx(400.0)  # (200 + 2*150) - 100
    assert item["unit"] == "g"


def test_shopping_list_for_items_empty_items_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe = Recipe(
        recipe_id="a",
        title="Recipe A",
        servings=1,
        ingredients=[{"name": "tofu", "amount": 200, "unit": "g"}],
        instructions=["Cook."],
    )
    monkeypatch.setattr(routes_day_planner_module, "load_corpus", lambda: [recipe])

    client = _client()
    payload = {"items": [], "inventory": []}

    response = client.post("/plan/shopping-list-for-items", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["shopping_list"] == []
