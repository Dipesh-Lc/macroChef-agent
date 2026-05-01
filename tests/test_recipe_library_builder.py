from app.graph.library_builder import run_library_discovery_graph
from app.schemas.library import RecipeDiscoveryRequest
from app.schemas.recipe_candidate import RecipeCandidate
from app.services.recipe_discovery_service import RecipeDiscoveryService
from app.services.recipe_generation_service import RecipeGenerationService


def test_mock_discovery_returns_requested_count() -> None:
    request = RecipeDiscoveryRequest(
        user_id="library_test_user",
        cuisines=["Japanese", "Indian"],
        meal_type="dinner",
        diet_type="high-protein",
        max_cook_time_min=35,
        count=10,
        allergies=["peanut"],
    )

    candidates = RecipeDiscoveryService().discover(request)

    assert len(candidates) == 10
    assert all(candidate.title for candidate in candidates)
    assert all(candidate.ingredients for candidate in candidates)
    assert all(candidate.instructions for candidate in candidates)


def test_library_discovery_graph_multiple_cuisines_and_constraints() -> None:
    request = RecipeDiscoveryRequest(
        user_id="library_graph_user",
        cuisines=["Japanese", "Indian"],
        meal_type="dinner",
        diet_type="high-protein",
        max_cook_time_min=35,
        difficulty="easy",
        count=8,
        allergies=["peanut"],
        excluded_ingredients=["mushroom"],
    )

    response = run_library_discovery_graph(request)

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
        user_id="fallback_user",
        cuisines=["Japanese"],
        meal_type="dinner",
        count=3,
        source_mode="llm",
    )
    service = RecipeDiscoveryService(generation_service=BrokenGenerationService())

    candidates = service.discover(request)

    assert len(candidates) == 3
    assert service.warnings
    assert all(candidate.source_type == "mock" for candidate in candidates)


def test_external_discovery_uses_llm_before_mock_when_import_is_empty() -> None:
    class FakeGenerationService:
        def generate(self, request):
            return [
                RecipeDiscoveryService()._mock_candidates(request)[0].model_copy(
                    update={"source_type": "ai_generated"}
                )
            ]

    request = RecipeDiscoveryRequest(
        user_id="external_user",
        cuisines=["Mexican"],
        meal_type="dinner",
        count=1,
        source_mode="external",
    )
    service = RecipeDiscoveryService(generation_service=FakeGenerationService())

    candidates = service.discover(request)

    assert len(candidates) == 1
    assert service.warnings
    assert candidates[0].source_type == "ai_generated"


def test_external_discovery_falls_back_to_mock_after_llm_failure() -> None:
    class BrokenGenerationService:
        def generate(self, request):
            raise ValueError("llm unavailable")

    request = RecipeDiscoveryRequest(
        user_id="external_mock_user",
        cuisines=["Mexican"],
        meal_type="dinner",
        count=4,
        source_mode="external",
    )
    service = RecipeDiscoveryService(generation_service=BrokenGenerationService())

    candidates = service.discover(request)

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
    assert candidate.ingredients[0] == "150 g chicken breast"
    assert candidate.instructions == ["Cook rice.", "Sear chicken."]
    assert candidate.calories == 590
