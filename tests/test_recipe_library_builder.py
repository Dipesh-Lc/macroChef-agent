import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.data.recipe_library_repository as repo_module
from app.data.db import Base
from app.graph.library_builder import run_library_discovery_graph
from app.schemas.library import RecipeDiscoveryRequest
from app.schemas.recipe_candidate import RecipeCandidate
from app.services.recipe_discovery_service import RecipeDiscoveryService
from app.services.recipe_generation_service import RecipeGenerationService


@pytest.fixture(autouse=True)
def _isolated_library_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """The library discovery graph's deduplication_node reads/writes via
    RecipeLibraryRepository, which lazily opens SessionLocal() against
    `app.data.db`'s module-level, real on-disk engine (default
    sqlite:///./macrochef.db) unless overridden. run_library_discovery_graph
    is called directly here (no FastAPI app, so init_db() -- only ever
    invoked from the startup hook -- never fires), so on a genuinely fresh
    checkout (no pre-existing macrochef.db, exactly what CI's `test` job
    starts from) this raises `OperationalError: no such table:
    user_saved_recipes`. This was previously masked on a dev machine only
    because a real macrochef.db with that table already happens to exist on
    disk.

    Point the repository at a fresh in-memory SQLite DB instead, mirroring
    the same pattern tests/test_recipe_library_isolation.py and
    tests/test_rate_limiting.py already use for the same reason.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(repo_module, "SessionLocal", test_session_local)


def test_mock_discovery_returns_requested_count() -> None:
    request = RecipeDiscoveryRequest(
        cuisines=["Japanese", "Indian"],
        meal_type="dinner",
        diet_type="high-protein",
        max_cook_time_min=35,
        count=10,
        allergies=["peanut"],
    )

    candidates = RecipeDiscoveryService().discover(request, "library_test_user")

    assert len(candidates) == 10
    assert all(candidate.title for candidate in candidates)
    assert all(candidate.ingredients for candidate in candidates)
    assert all(candidate.instructions for candidate in candidates)


def test_library_discovery_graph_multiple_cuisines_and_constraints() -> None:
    request = RecipeDiscoveryRequest(
        cuisines=["Japanese", "Indian"],
        meal_type="dinner",
        diet_type="high-protein",
        max_cook_time_min=35,
        difficulty="easy",
        count=8,
        allergies=["peanut"],
        excluded_ingredients=["mushroom"],
    )

    response = run_library_discovery_graph(request, "library_graph_user")

    assert response.candidates
    assert len(response.candidates) <= 8
    assert {candidate.cuisine for candidate in response.candidates}.issubset(
        {"Japanese", "Indian"}
    )
    assert all(candidate.cook_time_min <= 35 for candidate in response.candidates)
    assert all(
        "peanut" not in [item.lower() for item in candidate.allergens]
        for candidate in response.candidates
    )
    assert response.debug_trace


def test_llm_discovery_falls_back_to_mock_when_generation_fails() -> None:
    class BrokenGenerationService:
        def generate(self, request):
            raise ValueError("model returned prose instead of JSON")

    request = RecipeDiscoveryRequest(
        cuisines=["Japanese"],
        meal_type="dinner",
        count=3,
        source_mode="llm",
    )
    service = RecipeDiscoveryService(generation_service=BrokenGenerationService())

    candidates = service.discover(request, "fallback_user")

    assert len(candidates) == 3
    assert service.warnings
    assert all(candidate.source_type == "mock" for candidate in candidates)


def test_external_discovery_uses_llm_before_mock_when_import_is_empty() -> None:
    class FakeGenerationService:
        def generate(self, request):
            return [
                RecipeDiscoveryService()
                ._mock_candidates(request, "external_user")[0]
                .model_copy(update={"source_type": "ai_generated"})
            ]

    request = RecipeDiscoveryRequest(
        cuisines=["Mexican"],
        meal_type="dinner",
        count=1,
        source_mode="external",
    )
    service = RecipeDiscoveryService(generation_service=FakeGenerationService())

    candidates = service.discover(request, "external_user")

    assert len(candidates) == 1
    assert service.warnings
    assert candidates[0].source_type == "ai_generated"


def test_external_discovery_falls_back_to_mock_after_llm_failure() -> None:
    class BrokenGenerationService:
        def generate(self, request):
            raise ValueError("llm unavailable")

    request = RecipeDiscoveryRequest(
        cuisines=["Mexican"],
        meal_type="dinner",
        count=4,
        source_mode="external",
    )
    service = RecipeDiscoveryService(generation_service=BrokenGenerationService())

    candidates = service.discover(request, "external_mock_user")

    assert len(candidates) == 4
    assert any("trying LLM fallback" in warning for warning in service.warnings)
    assert any("mock fallback" in warning for warning in service.warnings)
    assert all(candidate.source_type == "mock" for candidate in candidates)


def test_generation_service_extracts_json_from_markdown_fence() -> None:
    text = """
Here are recipes:
```json
{"candidates": [{"title": "A", "ingredients": [], "instructions": []}]}
```
"""

    payload = RecipeGenerationService()._extract_json(text)

    assert payload == [{"title": "A", "ingredients": [], "instructions": []}]


def test_generation_service_sanitizes_common_llm_shape_mismatches() -> None:
    service = RecipeGenerationService()
    payload = service._sanitize_candidate_payload(
        {
            "title": "Chicken Rice Bowl",
            "ingredients": [
                {"quantity": 150, "unit": "g", "name": "chicken breast"},
                "120 g cooked rice",
            ],
            "instructions": "Cook rice.\nSear chicken.",
            "cook_time_min": "25 minutes",
            "servings": "1 serving",
            "calories": "590 kcal",
            "protein_g": "48 g",
            "carbs_g": "70 g",
            "fat_g": "12 g",
            "fiber_g": "6 g",
            "home_cookable_score": 10,
        }
    )

    candidate = RecipeCandidate.model_validate(payload)

    assert candidate.home_cookable_score == 1.0
    # Structured ingredient dicts keep amount/unit instead of being flattened to strings.
    assert candidate.ingredients[0].name == "chicken breast"
    assert candidate.ingredients[0].amount == 150
    assert candidate.ingredients[0].unit == "g"
    # Quantified strings are parsed into the same structured shape.
    assert candidate.ingredients[1].name == "cooked rice"
    assert candidate.ingredients[1].amount == 120
    assert candidate.ingredients[1].unit == "g"
    assert candidate.instructions == ["Cook rice.", "Sear chicken."]
    assert candidate.calories == 590
