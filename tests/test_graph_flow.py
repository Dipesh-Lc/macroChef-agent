import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.data.recipe_library_repository as repo_module
from app.config import get_settings
from app.data.db import Base
from app.graph.builder import run_recommendation_graph
from app.graph.nodes import MAX_RECOMMENDATIONS
from app.schemas.recommendation import RecommendationRequest
from app.schemas.user import MacroTargets, UserProfile
from app.services.constraint_engine import validate_recipe


@pytest.fixture(autouse=True)
def _isolated_library_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """The recommendation graph's nodes read/write via RecipeLibraryRepository,
    which lazily opens SessionLocal() against `app.data.db`'s module-level,
    real on-disk engine (default sqlite:///./macrochef.db) unless overridden.
    run_recommendation_graph is called directly here (no FastAPI app, so
    init_db() -- only ever invoked from the startup hook -- never fires), so
    on a genuinely fresh checkout (no pre-existing macrochef.db, exactly what
    CI's `test` job starts from) this raises `OperationalError: no such
    table: user_saved_recipes`. This was previously masked on a dev machine
    only because a real macrochef.db with that table already happens to
    exist on disk.

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


def test_full_graph_with_text_input_produces_safe_recommendations() -> None:
    profile = UserProfile(
        user_id="demo_user",
        allergies=["peanut"],
        disliked_ingredients=[],
        diet_type=None,
        preferred_cuisines=["Thai"],
        macro_targets=MacroTargets(calories=600, protein_g=40, carbs_g=60, fat_g=20, fiber_g=8),
        max_cook_time_min=40,
    )
    request = RecommendationRequest(
        input_type="text",
        typed_ingredients="chicken breast, rice, bell pepper, spinach",
        user_profile=profile,
        cuisine_preference="Thai",
        meal_type="dinner",
    )

    response = run_recommendation_graph(request, "demo_user")

    assert response.recommendations
    assert len(response.recommendations) <= MAX_RECOMMENDATIONS
    assert response.debug_trace
    assert any("inventory_confirmation_node" in item for item in response.debug_trace)
    assert not response.errors
    for recommendation in response.recommendations:
        assert validate_recipe(recommendation.recipe, profile).is_valid
        assert "peanut" not in [item.lower() for item in recommendation.recipe.allergens]


def test_full_graph_with_mixed_text_and_image_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Vision must be enabled for this test; it verifies the mixed text+image path.
    monkeypatch.setenv("MACROCHEF_ENABLE_VISION", "true")
    get_settings.cache_clear()

    profile = UserProfile(
        user_id="demo_user",
        allergies=[],
        disliked_ingredients=[],
        diet_type=None,
        preferred_cuisines=[],
        macro_targets=MacroTargets(calories=600, protein_g=35, carbs_g=60, fat_g=20),
        max_cook_time_min=45,
    )
    request = RecommendationRequest(
        input_type="mixed",
        typed_ingredients="chicken breast, spinach, rice",
        image_path="vegetarian_pantry_upload.png",
        user_profile=profile,
        meal_type="dinner",
    )

    response = run_recommendation_graph(request, "demo_user")
    inventory_names = {item.normalized_name for item in response.inventory_observations}

    assert response.recommendations
    assert {"chicken breast", "spinach", "rice", "tofu", "broccoli"}.issubset(inventory_names)
    assert response.debug_trace
