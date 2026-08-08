"""Tests for GET /recipes/{recipe_id} -- Interactive Plan Recipes (clickable
recipe names in day/week plans) roadmap item.

Pure lookup-by-id endpoint: no safety decision, no nutrition computation.
It reuses `app.services.recipe_retriever.get_recipe_by_id`, which resolves
against `app.rag.loaders.load_corpus()` (seed UNION imported -- fixed
2026-08-07, previously the seed-25-only `recipes_by_id()`, see that
function's docstring) -- already covered elsewhere (see
`tests/test_recipe_retriever.py`, `tests/test_retriever_corpus.py`). These
tests only check this route's own plumbing: 200 with the full `Recipe` body
for a known id, 404 for an unknown one.
"""

import pytest
from fastapi.testclient import TestClient

import app.api.routes_recommendations as routes_recommendations_module
from app.main import create_app
from app.schemas.recipe import Recipe


def _client() -> TestClient:
    return TestClient(create_app())


def _recipe(**overrides) -> Recipe:
    fields = {
        "recipe_id": "seed_1",
        "title": "Test Recipe",
        "ingredients": [{"name": "rice", "amount": 100, "unit": "g"}],
        "instructions": ["Cook rice."],
        "allergens": [],
        "diet_tags": [],
    }
    fields.update(overrides)
    return Recipe(**fields)


def test_get_recipe_by_id_returns_full_recipe(monkeypatch: pytest.MonkeyPatch) -> None:
    recipe = _recipe()
    monkeypatch.setattr(
        routes_recommendations_module,
        "get_recipe_by_id",
        lambda recipe_id: recipe if recipe_id == "seed_1" else None,
    )

    response = _client().get("/recipes/seed_1")

    assert response.status_code == 200
    body = response.json()
    assert body["recipe_id"] == "seed_1"
    assert body["title"] == "Test Recipe"
    assert body["ingredients"] == [{"name": "rice", "amount": 100, "unit": "g", "preparation": None}]
    assert body["instructions"] == ["Cook rice."]


def test_get_recipe_by_id_unknown_id_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_recommendations_module, "get_recipe_by_id", lambda recipe_id: None)

    response = _client().get("/recipes/does-not-exist")

    assert response.status_code == 404
