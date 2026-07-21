"""Tests for the /tools/* safety-tools API (app/api/routes_safety_tools.py,
roadmap Phase 5).

THE LOAD-BEARING TEST CLASS: TestEndpointOutputMatchesDirectFunctionCall.
Every /tools/* endpoint is required to be a byte-for-byte pass-through to
its underlying app.services.constraint_engine function -- these tests call
BOTH the direct function and the HTTP endpoint with the same inputs and
assert identical results, proving the endpoint adds no caching,
normalization, or other transformation of its own.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.recipe import Recipe
from app.schemas.user import UserProfile
from app.services.constraint_engine import (
    contains_allergen,
    derive_allergen_labels,
    validate_recipe,
    violates_diet_type,
)
from app.services.rate_limiter import get_rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    """The rate limiter is a process-wide singleton -- reset it around every
    test so one test's calls never exhaust another's budget (mirrors
    tests/test_rate_limiting.py's fixture of the same name)."""
    get_rate_limiter().reset()
    yield
    get_rate_limiter().reset()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _peanut_recipe() -> Recipe:
    return Recipe(
        recipe_id="pb_sandwich",
        title="Peanut Butter Sandwich",
        ingredients=[
            {"name": "peanut butter", "amount": 30, "unit": "g"},
            {"name": "bread", "amount": 2, "unit": "slice"},
        ],
        instructions=["Spread peanut butter on bread."],
        allergens=["peanut", "wheat"],
    )


def _safe_recipe() -> Recipe:
    return Recipe(
        recipe_id="rice_bowl",
        title="Plain Rice Bowl",
        ingredients=[{"name": "rice", "amount": 150, "unit": "g"}],
        instructions=["Cook rice."],
    )


def _vegan_violating_recipe() -> Recipe:
    return Recipe(
        recipe_id="chicken_rice",
        title="Chicken and Rice",
        ingredients=[
            {"name": "chicken breast", "amount": 200, "unit": "g"},
            {"name": "rice", "amount": 150, "unit": "g"},
        ],
        instructions=["Cook chicken and rice."],
    )


def _profile(**overrides) -> UserProfile:
    base = {
        "allergies": [],
        "disliked_ingredients": [],
        "diet_type": None,
        "preferred_cuisines": [],
        "macro_targets": {},
        "max_cook_time_min": None,
    }
    base.update(overrides)
    return UserProfile(**base)


# ---------------------------------------------------------------------------
# Load-bearing: endpoint output == direct function call output, for every
# one of the 4 endpoints.
# ---------------------------------------------------------------------------


class TestEndpointOutputMatchesDirectFunctionCall:
    def test_validate_recipe(self, client: TestClient) -> None:
        recipe = _peanut_recipe()
        profile = _profile(allergies=["peanut"])

        direct = validate_recipe(recipe, profile)

        response = client.post(
            "/tools/validate-recipe",
            json={
                "recipe": recipe.model_dump(mode="json"),
                "user_profile": profile.model_dump(mode="json"),
            },
        )

        assert response.status_code == 200
        assert response.json() == direct.model_dump(mode="json")

    def test_check_allergen(self, client: TestClient) -> None:
        recipe = _peanut_recipe()
        allergies = ["peanut"]

        direct = contains_allergen(recipe, allergies)

        response = client.post(
            "/tools/check-allergen",
            json={"recipe": recipe.model_dump(mode="json"), "allergies": allergies},
        )

        assert response.status_code == 200
        assert response.json() == {"contains_allergen": direct}

    def test_check_diet_violation(self, client: TestClient) -> None:
        recipe = _vegan_violating_recipe()
        diet_type = "vegan"

        direct = violates_diet_type(recipe, diet_type)

        response = client.post(
            "/tools/check-diet-violation",
            json={"recipe": recipe.model_dump(mode="json"), "diet_type": diet_type},
        )

        assert response.status_code == 200
        assert response.json() == {"violates_diet_type": direct}

    def test_derive_allergen_labels(self, client: TestClient) -> None:
        ingredient_names = ["peanut butter", "milk", "shrimp"]

        direct = derive_allergen_labels(ingredient_names)

        response = client.post(
            "/tools/derive-allergen-labels",
            json={"ingredient_names": ingredient_names},
        )

        assert response.status_code == 200
        assert response.json() == {"allergens": direct}


# ---------------------------------------------------------------------------
# Real allergy/diet scenarios (not trivial always-true/always-false cases).
# ---------------------------------------------------------------------------


def test_validate_recipe_rejects_peanut_allergic_user_via_endpoint(client: TestClient) -> None:
    recipe = _peanut_recipe()
    profile = _profile(allergies=["peanut"])

    response = client.post(
        "/tools/validate-recipe",
        json={
            "recipe": recipe.model_dump(mode="json"),
            "user_profile": profile.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_valid"] is False
    assert body["rejection_reason"] == "Contains a user allergen"

    # Exactly matches the direct call, not merely "some" rejection.
    assert body == validate_recipe(recipe, profile).model_dump(mode="json")


def test_validate_recipe_admits_the_same_recipe_for_a_non_allergic_user(
    client: TestClient,
) -> None:
    """Sanity check on the fixture: the same recipe IS servable to a user
    without the allergy, proving the rejection above is caused by the
    allergy, not a blanket block."""
    recipe = _peanut_recipe()
    profile = _profile(allergies=[])

    response = client.post(
        "/tools/validate-recipe",
        json={
            "recipe": recipe.model_dump(mode="json"),
            "user_profile": profile.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"is_valid": True, "rejection_reason": None}


def test_check_allergen_true_for_peanut_recipe_and_peanut_allergy(client: TestClient) -> None:
    recipe = _peanut_recipe()

    response = client.post(
        "/tools/check-allergen",
        json={"recipe": recipe.model_dump(mode="json"), "allergies": ["peanut"]},
    )

    assert response.status_code == 200
    assert response.json() == {"contains_allergen": True}


def test_check_allergen_false_for_safe_recipe_and_peanut_allergy(client: TestClient) -> None:
    recipe = _safe_recipe()

    response = client.post(
        "/tools/check-allergen",
        json={"recipe": recipe.model_dump(mode="json"), "allergies": ["peanut"]},
    )

    assert response.status_code == 200
    assert response.json() == {"contains_allergen": False}


def test_check_diet_violation_true_for_chicken_recipe_and_vegan(client: TestClient) -> None:
    recipe = _vegan_violating_recipe()

    response = client.post(
        "/tools/check-diet-violation",
        json={"recipe": recipe.model_dump(mode="json"), "diet_type": "vegan"},
    )

    assert response.status_code == 200
    assert response.json() == {"violates_diet_type": True}


def test_check_diet_violation_false_for_safe_recipe_and_vegan(client: TestClient) -> None:
    recipe = _safe_recipe()

    response = client.post(
        "/tools/check-diet-violation",
        json={"recipe": recipe.model_dump(mode="json"), "diet_type": "vegan"},
    )

    assert response.status_code == 200
    assert response.json() == {"violates_diet_type": False}


def test_check_diet_violation_unsupported_diet_type_returns_422(client: TestClient) -> None:
    recipe = _safe_recipe()

    response = client.post(
        "/tools/check-diet-violation",
        json={"recipe": recipe.model_dump(mode="json"), "diet_type": "keto"},
    )

    assert response.status_code == 422


def test_derive_allergen_labels_real_scenario(client: TestClient) -> None:
    ingredient_names = ["peanut butter", "whole milk", "shrimp scampi"]

    response = client.post(
        "/tools/derive-allergen-labels",
        json={"ingredient_names": ingredient_names},
    )

    assert response.status_code == 200
    labels = set(response.json()["allergens"])
    assert "peanut" in labels
    assert "dairy" in labels
    assert "shellfish" in labels


# ---------------------------------------------------------------------------
# No safety logic added by this layer: constraint_engine is imported and
# called unmodified, never re-implemented in the route.
# ---------------------------------------------------------------------------


def test_routes_safety_tools_imports_constraint_engine_functions_directly() -> None:
    import app.api.routes_safety_tools as routes_safety_tools

    assert routes_safety_tools.validate_recipe is validate_recipe
    assert routes_safety_tools.contains_allergen is contains_allergen
    assert routes_safety_tools.violates_diet_type is violates_diet_type
    assert routes_safety_tools.derive_allergen_labels is derive_allergen_labels


# ---------------------------------------------------------------------------
# Rate limiting (IP-keyed -- see app/dependencies.py
# require_safety_tools_rate_limit for why this differs from the
# session-keyed pattern the other rate-limited endpoints use).
# ---------------------------------------------------------------------------


def test_safety_tools_rate_limit_nth_plus_one_request_gets_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("RATE_LIMIT_SAFETY_TOOLS_MAX", "2")
    monkeypatch.setenv("RATE_LIMIT_SAFETY_TOOLS_WINDOW_SECONDS", "3600")
    get_settings.cache_clear()

    payload = {"recipe": _safe_recipe().model_dump(mode="json"), "allergies": ["peanut"]}

    first = client.post("/tools/check-allergen", json=payload)
    second = client.post("/tools/check-allergen", json=payload)
    third = client.post("/tools/check-allergen", json=payload)

    get_settings.cache_clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


def test_safety_tools_endpoints_require_no_session_token(client: TestClient) -> None:
    """Unlike /library/*, /recipes/recommend, and /library/reindex, /tools/*
    is reachable with no X-Session-Token at all -- the whole point of this
    surface is that an external caller with no MacroChef session can use
    it."""
    response = client.post(
        "/tools/check-allergen",
        json={"recipe": _safe_recipe().model_dump(mode="json"), "allergies": []},
    )
    assert response.status_code == 200
