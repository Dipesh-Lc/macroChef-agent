"""Tests for POST /recipes/search (deterministic corpus search/filter,
NOT the generative /library/discover endpoint).

THE SINGLE MOST IMPORTANT TEST IN THIS FILE:
test_allergic_users_excluded_recipe_never_appears_even_as_a_perfect_fit --
proves app.services.constraint_engine.contains_allergen actually runs inside
the route BEFORE a recipe can appear in `results`. A recipe containing the
user's allergen is engineered to be a "perfect fit" on every other filter
(cuisine + every macro range); if the safety filter were ever skipped,
bypassed, or reordered, this test fails. Mirrors
tests/test_day_planner_endpoint.py's identically-named/-intentioned test.
"""

import pytest
from fastapi.testclient import TestClient

import app.api.routes_recommendations as routes_recommendations_module
from app.config import get_settings
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token
from app.main import create_app
from app.schemas.nutrition import FoodMacros, GroundingStatus, RecipeNutrition
from app.schemas.recipe import Recipe
from app.services.rate_limiter import get_rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    get_rate_limiter().reset()
    yield
    get_rate_limiter().reset()


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SESSION_SECRET", "recipe-search-route-test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _headers(user_id: str) -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: mint_session_token(user_id, get_settings())}


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


def _recipe(recipe_id: str, **overrides) -> Recipe:
    defaults = {
        "title": recipe_id,
        "ingredients": [{"name": "rice", "amount": 100, "unit": "g"}],
        "instructions": ["Cook."],
        "allergens": [],
    }
    defaults.update(overrides)
    return Recipe(recipe_id=recipe_id, **defaults)


def _search(client: TestClient, payload: dict, user_id: str = "search_user"):
    return client.post("/recipes/search", json=payload, headers=_headers(user_id))


# ---------------------------------------------------------------------------
# Cuisine filter.
# ---------------------------------------------------------------------------


def test_cuisine_filter_narrows_results(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    italian = _recipe("italian_1", cuisine="Italian")
    mexican = _recipe("mexican_1", cuisine="Mexican")
    monkeypatch.setattr(routes_recommendations_module, "load_corpus", lambda: [italian, mexican])

    response = _search(client, {"cuisines": ["italian"]})

    assert response.status_code == 200
    body = response.json()
    result_ids = {item["recipe_id"] for item in body["results"]}
    assert result_ids == {"italian_1"}
    assert body["total_matched"] == 1


# ---------------------------------------------------------------------------
# THE single most important test: allergen exclusion actually gates results.
# ---------------------------------------------------------------------------


def test_allergic_users_excluded_recipe_never_appears_even_as_a_perfect_fit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    unsafe_perfect_fit = _recipe(
        "unsafe_perfect_fit",
        cuisine="Italian",
        ingredients=[{"name": "milk", "amount": 200, "unit": "ml"}],
        allergens=["dairy", "milk"],
        nutrition=_nutrition(GroundingStatus.GROUNDED, calories=300, protein_g=20, carbs_g=10, fat_g=8, fiber_g=0),
    )
    safe_recipe = _recipe(
        "safe_recipe",
        cuisine="Italian",
        nutrition=_nutrition(GroundingStatus.GROUNDED, calories=305, protein_g=21, carbs_g=11, fat_g=9, fiber_g=1),
    )
    monkeypatch.setattr(
        routes_recommendations_module, "load_corpus", lambda: [unsafe_perfect_fit, safe_recipe]
    )

    payload = {
        "cuisines": ["Italian"],
        "allergies": ["milk"],
        "calorie_min": 250,
        "calorie_max": 350,
        "protein_min": 15,
        "protein_max": 25,
    }
    response = _search(client, payload)

    assert response.status_code == 200
    body = response.json()
    result_ids = {item["recipe_id"] for item in body["results"]}
    assert "unsafe_perfect_fit" not in result_ids
    assert "safe_recipe" in result_ids


def test_non_allergic_user_can_receive_the_same_recipe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = _recipe(
        "milk_recipe",
        ingredients=[{"name": "milk", "amount": 200, "unit": "ml"}],
        allergens=["dairy", "milk"],
    )
    monkeypatch.setattr(routes_recommendations_module, "load_corpus", lambda: [recipe])

    response = _search(client, {"allergies": []})

    assert response.status_code == 200
    result_ids = {item["recipe_id"] for item in response.json()["results"]}
    assert "milk_recipe" in result_ids


# ---------------------------------------------------------------------------
# diet_type filter.
# ---------------------------------------------------------------------------


def test_diet_type_filter_excludes_violating_recipes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    meat_recipe = _recipe("meat_recipe", ingredients=[{"name": "chicken", "amount": 150, "unit": "g"}])
    veg_recipe = _recipe("veg_recipe", ingredients=[{"name": "rice", "amount": 150, "unit": "g"}])
    monkeypatch.setattr(
        routes_recommendations_module, "load_corpus", lambda: [meat_recipe, veg_recipe]
    )

    response = _search(client, {"diet_type": "vegetarian"})

    assert response.status_code == 200
    result_ids = {item["recipe_id"] for item in response.json()["results"]}
    assert result_ids == {"veg_recipe"}


def test_invalid_diet_type_returns_422_via_shared_validator(client: TestClient) -> None:
    response = _search(client, {"diet_type": "halal"})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Calorie/macro range filtering, grounded via trusted_per_serving only.
# ---------------------------------------------------------------------------


def test_ungrounded_recipe_excluded_and_counted_when_macro_filter_active(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    grounded = _recipe(
        "grounded_recipe",
        nutrition=_nutrition(GroundingStatus.GROUNDED, calories=300, protein_g=20, carbs_g=10, fat_g=8, fiber_g=0),
    )
    partial = _recipe(
        "partial_recipe",
        nutrition=_nutrition(GroundingStatus.PARTIAL, calories=300, protein_g=20, carbs_g=10, fat_g=8, fiber_g=0),
    )
    ungrounded_no_nutrition = _recipe("no_nutrition_recipe")
    monkeypatch.setattr(
        routes_recommendations_module,
        "load_corpus",
        lambda: [grounded, partial, ungrounded_no_nutrition],
    )

    response = _search(client, {"calorie_min": 100, "calorie_max": 500})

    assert response.status_code == 200
    body = response.json()
    result_ids = {item["recipe_id"] for item in body["results"]}
    assert result_ids == {"grounded_recipe"}
    assert body["macro_unavailable_excluded"] == 2
    assert body["total_matched"] == 1


def test_no_macro_filter_does_not_exclude_ungrounded_recipes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ungrounded_no_nutrition = _recipe("no_nutrition_recipe")
    monkeypatch.setattr(
        routes_recommendations_module, "load_corpus", lambda: [ungrounded_no_nutrition]
    )

    response = _search(client, {})

    assert response.status_code == 200
    body = response.json()
    result_ids = {item["recipe_id"] for item in body["results"]}
    assert result_ids == {"no_nutrition_recipe"}
    assert body["macro_unavailable_excluded"] == 0


# ---------------------------------------------------------------------------
# limit truncates results; total_matched reflects the pre-truncation count.
# ---------------------------------------------------------------------------


def test_limit_truncates_results_but_total_matched_reflects_full_count(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipes = [_recipe(f"recipe_{i}") for i in range(5)]
    monkeypatch.setattr(routes_recommendations_module, "load_corpus", lambda: recipes)

    response = _search(client, {"limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 2
    assert body["total_matched"] == 5


# ---------------------------------------------------------------------------
# Session/rate-limit gating (mirrors tests/test_routes_instructions.py).
# ---------------------------------------------------------------------------


def test_missing_session_token_is_rejected_401(client: TestClient) -> None:
    response = client.post("/recipes/search", json={})

    assert response.status_code == 401
