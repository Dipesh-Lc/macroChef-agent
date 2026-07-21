"""Tests for POST /plan/week (Phase 4 item 2: full weekly meal-plan solver).

THE SINGLE MOST IMPORTANT TEST IN THIS FILE:
test_allergic_users_excluded_recipe_never_appears_in_any_day_even_as_a_perfect_macro_fit
-- mirrors tests/test_day_planner_endpoint.py's and
tests/test_batch_planner_endpoint.py's own critical test, proving
app.services.constraint_engine.validate_recipe actually runs inside the
route BEFORE app.services.weekly_planner ever sees a candidate. A recipe
containing the user's allergen is engineered to be a mathematically perfect
macro match for every day of the week; if the safety filter were ever
skipped, bypassed, or reordered after assembly, this test fails.
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
# gates weekly-plan assembly, for EVERY day.
# ---------------------------------------------------------------------------


def test_allergic_users_excluded_recipe_never_appears_in_any_day_even_as_a_perfect_macro_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # WeeklyPlanRequest has no meals/meals_range override (matches
    # DayPlanRequest's "day plan" mode default sweep of K in 2/3/4 -- see
    # app.services.day_planner.DEFAULT_MEALS_RANGE), so this recipe's
    # per-serving macros are chosen (150 kcal / 10 g protein) so that TWO
    # servings (K=2) are a mathematically PERFECT match for the 300 kcal /
    # 20 g protein target below -- the most tempting possible candidate for
    # the planner, every single day -- but it contains a milk allergen
    # ingredient.
    unsafe_perfect_fit = Recipe(
        recipe_id="unsafe_perfect_fit",
        title="Milk-Laden Perfect Fit Bowl",
        ingredients=[{"name": "milk", "amount": 200, "unit": "ml"}],
        instructions=["Pour milk."],
        allergens=["dairy", "milk"],
        nutrition=_nutrition(
            GroundingStatus.GROUNDED, calories=150, protein_g=10, carbs_g=10, fat_g=8, fiber_g=0
        ),
    )
    # Safe but a much worse macro fit -- the honest "closest we could do".
    safe_far_fit = Recipe(
        recipe_id="safe_far_fit",
        title="Safe But Distant Fit",
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
        "days": 7,
    }

    response = client.post("/plan/week", json=payload)

    assert response.status_code == 200
    body = response.json()

    # The unsafe recipe must never appear in ANY day of the assembled week...
    plan_recipe_ids: set[str] = set()
    for day in body["plan"]["days"]:
        for item in day["items"]:
            plan_recipe_ids.add(item["recipe_id"])
    assert "unsafe_perfect_fit" not in plan_recipe_ids

    # ...even though, ignoring safety, K=2 servings of it would have been a
    # perfect (0-error) macro match for every day's 300 kcal / 20 g protein
    # target -- if the filter had leaked, EVERY day would show
    # within_tolerance=True. Confirms this isn't a coincidence of the safe
    # candidate also fitting well: with only the safe (far-off) recipe
    # available, no day of the week is within tolerance (mirrors
    # tests/test_day_planner_endpoint.py's own "this (or nothing) is the
    # best the planner can legitimately do" comment).
    assert all(day["within_tolerance"] is False for day in body["plan"]["days"])

    # ...and it must show up in rejected_recipes, proving the filter ran
    # (rather than the recipe simply never being loaded).
    rejected_ids = {item["recipe_id"] for item in body["rejected_recipes"]}
    assert "unsafe_perfect_fit" in rejected_ids
    rejected_entry = next(
        item for item in body["rejected_recipes"] if item["recipe_id"] == "unsafe_perfect_fit"
    )
    assert "allergen" in rejected_entry["reason"].lower()

    # The safe recipe must have been a candidate the solver was free to use
    # (not blocked by the safety filter) -- whether or not it ends up
    # actually selected is a day_planner scoring detail, not a safety
    # question (see the comment above).
    assert "safe_far_fit" not in rejected_ids
    assert len(body["plan"]["days"]) == 7


def test_non_allergic_user_can_receive_the_same_recipe_every_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check on the fixture itself: the same recipe IS selectable by
    a user without the allergy, proving the exclusion above is caused by
    the allergy, not by some unrelated bug (e.g. an accidental blanket
    filter)."""
    perfect_fit = Recipe(
        recipe_id="perfect_fit",
        title="Milk-Laden Perfect Fit Bowl",
        ingredients=[{"name": "milk", "amount": 200, "unit": "ml"}],
        instructions=["Pour milk."],
        allergens=["dairy", "milk"],
        nutrition=_nutrition(
            GroundingStatus.GROUNDED, calories=150, protein_g=10, carbs_g=10, fat_g=8, fiber_g=0
        ),
    )
    monkeypatch.setattr(routes_day_planner_module, "load_corpus", lambda: [perfect_fit])

    client = _client()
    payload = {
        "user_profile": _base_profile(allergies=[]),
        "days": 3,
    }

    response = client.post("/plan/week", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert len(body["plan"]["days"]) == 3
    for day in body["plan"]["days"]:
        recipe_ids = {item["recipe_id"] for item in day["items"]}
        assert "perfect_fit" in recipe_ids
        assert day["within_tolerance"] is True
    assert body["rejected_recipes"] == []


# ---------------------------------------------------------------------------
# Consolidated shopping list, built by ONE call to
# build_shopping_list_for_items over every day's pooled PlanItems.
# ---------------------------------------------------------------------------


def test_week_endpoint_returns_one_consolidated_shopping_list_not_double_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe = Recipe(
        recipe_id="tofu_bowl",
        title="Tofu Bowl",
        servings=1,
        ingredients=[{"name": "tofu", "amount": 200, "unit": "g"}],
        instructions=["Cook."],
        nutrition=_nutrition(
            GroundingStatus.GROUNDED, calories=150, protein_g=10, carbs_g=10, fat_g=8, fiber_g=0
        ),
    )
    monkeypatch.setattr(routes_day_planner_module, "load_corpus", lambda: [recipe])

    client = _client()
    payload = {
        "user_profile": _base_profile(macro_targets={"calories": 300, "protein_g": 20}),
        "days": 2,
        # Pantry covers exactly ONE day's worth of tofu (400 g) but not two.
        "inventory": [{"name": "tofu", "amount": 400, "unit": "g"}],
    }

    response = client.post("/plan/week", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert len(body["plan"]["days"]) == 2
    for day in body["plan"]["days"]:
        assert day["items"] == [{"recipe_id": "tofu_bowl", "title": "Tofu Bowl", "servings": 2}]

    # Hand-computed: need = 200 g * (2 servings / 1 recipe.servings) * 2
    # days = 800 g; pantry has 400 g -> true combined shortfall = 400 g,
    # reconciled ONCE (not the wrongly-zeroed per-day-then-merge result).
    assert len(body["shopping_list"]) == 1
    item = body["shopping_list"][0]
    assert item["name"] == "tofu"
    assert item["amount"] == pytest.approx(400.0)
    assert item["unit"] == "g"

    assert body["plan"]["pantry_utilization"] == pytest.approx(0.5)
    assert body["plan"]["uncompared_ingredient_count"] == 0


def test_week_endpoint_missing_macro_targets_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_day_planner_module, "load_corpus", lambda: [])
    client = _client()
    payload = {"user_profile": _base_profile(macro_targets={}), "days": 7}
    response = client.post("/plan/week", json=payload)
    assert response.status_code == 422
