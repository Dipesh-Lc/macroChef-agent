"""Tests for POST /plan/batch (Phase 4 item 1: meal-prep batch solver).

THE SINGLE MOST IMPORTANT TEST IN THIS FILE:
test_allergic_users_excluded_recipe_never_appears_even_as_a_perfect_container_fit
-- mirrors tests/test_day_planner_endpoint.py's own critical test, proving
app.services.constraint_engine.validate_recipe actually runs inside the
route BEFORE app.services.batch_planner ever sees a candidate. A recipe
containing the user's allergen is engineered to be a mathematically
perfect per-container macro match; if the safety filter were ever skipped,
bypassed, or reordered after assembly, this test fails.
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
        "macro_targets": {},
        "max_cook_time_min": None,
    }
    profile.update(overrides)
    return profile


# ---------------------------------------------------------------------------
# THE single most important test: constraint_engine.validate_recipe actually
# gates batch-plan assembly.
# ---------------------------------------------------------------------------


def test_allergic_users_excluded_recipe_never_appears_even_as_a_perfect_container_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # This recipe is a mathematically PERFECT per-container macro match for
    # the target below (500 kcal / 40g protein) -- the most tempting
    # possible candidate for the batch solver -- but contains a milk
    # allergen ingredient.
    unsafe_perfect_fit = Recipe(
        recipe_id="unsafe_perfect_fit",
        title="Milk-Laden Perfect Container Bowl",
        ingredients=[{"name": "milk", "amount": 200, "unit": "ml"}],
        instructions=["Pour milk."],
        allergens=["dairy", "milk"],
        nutrition=_nutrition(
            GroundingStatus.GROUNDED, calories=500, protein_g=40, carbs_g=10, fat_g=8, fiber_g=0
        ),
    )
    # A safe recipe that is a much worse macro fit -- if the safety filter
    # works, this is the best (out-of-tolerance, "closest") the solver can
    # legitimately do.
    safe_far_fit = Recipe(
        recipe_id="safe_far_fit",
        title="Safe But Distant Container Fit",
        ingredients=[{"name": "rice", "amount": 150, "unit": "g"}],
        instructions=["Cook rice."],
        allergens=[],
        nutrition=_nutrition(
            GroundingStatus.GROUNDED, calories=1500, protein_g=100, carbs_g=100, fat_g=20, fiber_g=5
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
        "per_container_target_calories": 500,
        "per_container_target_protein_g": 40,
        "containers": 10,
    }

    response = client.post("/plan/batch", json=payload)

    assert response.status_code == 200
    body = response.json()

    # The unsafe recipe must never appear in the assembled batch plan...
    plan_recipe_ids = {item["recipe_id"] for item in body["plan"]["items"]}
    assert "unsafe_perfect_fit" not in plan_recipe_ids

    # ...even though, ignoring safety, it would have been a perfect
    # (0-error) per-container macro fit -- confirms this isn't a
    # coincidence of the safe recipe also fitting well (it doesn't: the
    # plan must be out of tolerance).
    assert body["plan"]["within_tolerance"] is False

    # ...and it must show up in rejected_recipes, proving the filter ran
    # (rather than the recipe simply never being loaded).
    rejected_ids = {item["recipe_id"] for item in body["rejected_recipes"]}
    assert "unsafe_perfect_fit" in rejected_ids
    rejected_entry = next(
        item for item in body["rejected_recipes"] if item["recipe_id"] == "unsafe_perfect_fit"
    )
    assert "allergen" in rejected_entry["reason"].lower()

    # The safe recipe must have been a candidate the solver was free to use.
    assert "safe_far_fit" not in rejected_ids
    assert "safe_far_fit" in plan_recipe_ids


def test_non_allergic_user_can_receive_the_same_recipe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check on the fixture itself: the same recipe IS selectable by
    a user without the allergy, proving the exclusion above is caused by
    the allergy, not by some unrelated bug (e.g. an accidental blanket
    filter)."""
    perfect_fit = Recipe(
        recipe_id="perfect_fit",
        title="Milk-Laden Perfect Container Bowl",
        ingredients=[{"name": "milk", "amount": 200, "unit": "ml"}],
        instructions=["Pour milk."],
        allergens=["dairy", "milk"],
        nutrition=_nutrition(
            GroundingStatus.GROUNDED, calories=500, protein_g=40, carbs_g=10, fat_g=8, fiber_g=0
        ),
    )
    monkeypatch.setattr(routes_day_planner_module, "load_corpus", lambda: [perfect_fit])

    client = _client()
    payload = {
        "user_profile": _base_profile(allergies=[]),
        "per_container_target_calories": 500,
        "per_container_target_protein_g": 40,
        "containers": 10,
    }

    response = client.post("/plan/batch", json=payload)

    assert response.status_code == 200
    body = response.json()
    plan_recipe_ids = {item["recipe_id"] for item in body["plan"]["items"]}
    assert "perfect_fit" in plan_recipe_ids
    assert body["plan"]["within_tolerance"] is True
    assert body["rejected_recipes"] == []


# ---------------------------------------------------------------------------
# Consolidated shopping list, built via build_shopping_list_for_items.
# ---------------------------------------------------------------------------


def test_batch_endpoint_returns_consolidated_shopping_list(monkeypatch: pytest.MonkeyPatch) -> None:
    recipe_a = Recipe(
        recipe_id="a",
        title="Recipe A",
        servings=1,
        ingredients=[{"name": "tofu", "amount": 200, "unit": "g"}],
        instructions=["Cook."],
        nutrition=_nutrition(
            GroundingStatus.GROUNDED, calories=500, protein_g=40, carbs_g=10, fat_g=8, fiber_g=0
        ),
    )
    recipe_b = Recipe(
        recipe_id="b",
        title="Recipe B",
        servings=1,
        ingredients=[{"name": "tofu", "amount": 150, "unit": "g"}],
        instructions=["Cook."],
        nutrition=_nutrition(
            GroundingStatus.GROUNDED, calories=505, protein_g=41, carbs_g=10, fat_g=8, fiber_g=0
        ),
    )
    monkeypatch.setattr(routes_day_planner_module, "load_corpus", lambda: [recipe_a, recipe_b])

    client = _client()
    payload = {
        "user_profile": _base_profile(),
        "per_container_target_calories": 500,
        "per_container_target_protein_g": 40,
        "containers": 10,
        "inventory": [{"name": "tofu", "amount": 100, "unit": "g"}],
    }

    response = client.post("/plan/batch", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert len(body["shopping_list"]) == 1
    item = body["shopping_list"][0]
    assert item["name"] == "tofu"
    assert item["unit"] == "g"
    # Both recipes selected (2 >= min_recipes default), containers=10 -> 5/5
    # split; combined need = 5*200 + 5*150 = 1750; pantry has 100 -> 1650
    # short, reconciled ONCE (not double-counted per recipe).
    assert item["amount"] == pytest.approx(1650.0)
