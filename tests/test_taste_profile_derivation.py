"""Phase 3: visible personalization loop -- generalizing taste-profile
derivation (app.services.memory_service.derive_taste_profile and its pure
helpers `_derive_avoided_ingredients` / `_derive_preferred_cuisines`).

Unlike `get_user_memory` (exact recipe_id re-recognition only), this signal
must GENERALIZE: a brand-new recipe the user has never rated can still be
flagged if it shares an ingredient/cuisine pattern with recipes the user
has liked or disliked before. This is a ranking/UX signal only -- nothing
here is ever consulted by app.services.constraint_engine, and it is proven
never to cross between users (mirrors tests/test_feedback_isolation.py's
isolation pattern).

Covers:
- enough disliked samples + a recurring, disproportionate ingredient ->
  it is surfaced as "avoided";
- too few disliked samples -> no signal at all, even if the pattern is
  otherwise strong (the minimum-sample-size floor);
- an ingredient recurring only once in the user's disliked history is not
  surfaced, even past the sample-size floor;
- the mirrored cases for preferred-cuisine drift;
- end-to-end `derive_taste_profile`, including that user A's derived
  profile never leaks into user B's.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.memory_service as memory_service_module
from app.data.db import Base
from app.data.repositories import FeedbackRepository
from app.schemas.recipe import Recipe
from app.services.memory_service import (
    _derive_avoided_ingredients,
    _derive_preferred_cuisines,
    derive_taste_profile,
)


def _recipe(recipe_id: str, ingredients: list[str], cuisine: str | None = None) -> Recipe:
    return Recipe(
        recipe_id=recipe_id,
        title=f"Recipe {recipe_id}",
        cuisine=cuisine,
        ingredients=ingredients,
        instructions=["Cook."],
    )


# ---------------------------------------------------------------------------
# _derive_avoided_ingredients
# ---------------------------------------------------------------------------


def test_avoided_ingredient_surfaces_when_recurring_and_disproportionate() -> None:
    disliked = [
        _recipe("d1", ["xyzzyplorp", "rice"]),
        _recipe("d2", ["xyzzyplorp", "onion"]),
        _recipe("d3", ["xyzzyplorp", "garlic"]),
    ]
    # Rare in the corpus baseline (2 / 20) but present in every disliked
    # recipe (3 / 3) -> a clearly disproportionate ratio.
    baseline_counts = {"xyzzyplorp": 2, "rice": 10, "onion": 8, "garlic": 9}

    result = _derive_avoided_ingredients(disliked, baseline_counts, baseline_total_recipes=20)

    assert "xyzzyplorp" in result


def test_no_avoided_ingredients_below_minimum_sample_floor() -> None:
    # Only 2 disliked recipes -- below the _MIN_DISLIKED_SAMPLES floor -- even
    # though the pattern within those 2 would otherwise look strong.
    disliked = [
        _recipe("d1", ["xyzzyplorp"]),
        _recipe("d2", ["xyzzyplorp"]),
    ]
    baseline_counts = {"xyzzyplorp": 1}

    result = _derive_avoided_ingredients(disliked, baseline_counts, baseline_total_recipes=20)

    assert result == []


def test_ingredient_appearing_only_once_is_not_surfaced() -> None:
    # 3 disliked recipes clears the sample floor, but "xyzzyplorp" only
    # recurs in one of them -- a single occurrence must never be enough to
    # label an ingredient "avoided".
    disliked = [
        _recipe("d1", ["xyzzyplorp"]),
        _recipe("d2", ["onion"]),
        _recipe("d3", ["garlic"]),
    ]
    baseline_counts = {"xyzzyplorp": 1, "onion": 8, "garlic": 9}

    result = _derive_avoided_ingredients(disliked, baseline_counts, baseline_total_recipes=20)

    assert "xyzzyplorp" not in result


def test_ingredient_at_baseline_rate_is_not_surfaced() -> None:
    # "rice" recurs in every disliked recipe, but it is also common in the
    # corpus baseline at roughly the same rate -- not disproportionate, so
    # it must not be flagged as "avoided".
    disliked = [
        _recipe("d1", ["rice"]),
        _recipe("d2", ["rice"]),
        _recipe("d3", ["rice"]),
    ]
    baseline_counts = {"rice": 18}  # present in 18/20 corpus recipes already

    result = _derive_avoided_ingredients(disliked, baseline_counts, baseline_total_recipes=20)

    assert "rice" not in result


# ---------------------------------------------------------------------------
# _derive_preferred_cuisines
# ---------------------------------------------------------------------------


def test_preferred_cuisine_surfaces_when_recurring_and_disproportionate() -> None:
    liked = [
        _recipe("l1", ["pasta"], cuisine="Italian"),
        _recipe("l2", ["basil"], cuisine="Italian"),
        _recipe("l3", ["olive oil"], cuisine="Italian"),
    ]
    baseline_counts = {"italian": 5}

    result = _derive_preferred_cuisines(liked, baseline_counts, baseline_total_with_cuisine=50)

    assert "Italian" in result


def test_no_preferred_cuisines_below_minimum_sample_floor() -> None:
    liked = [
        _recipe("l1", ["pasta"], cuisine="Italian"),
        _recipe("l2", ["basil"], cuisine="Italian"),
    ]
    baseline_counts = {"italian": 5}

    result = _derive_preferred_cuisines(liked, baseline_counts, baseline_total_with_cuisine=50)

    assert result == []


def test_cuisine_at_baseline_rate_is_not_surfaced() -> None:
    liked = [
        _recipe("l1", ["chicken"], cuisine="American"),
        _recipe("l2", ["beef"], cuisine="American"),
        _recipe("l3", ["turkey"], cuisine="American"),
    ]
    # American is already the most common cuisine in the corpus -- liking it
    # 3/3 times is not a distinctive drift.
    baseline_counts = {"american": 45}

    result = _derive_preferred_cuisines(liked, baseline_counts, baseline_total_with_cuisine=50)

    assert "American" not in result


# ---------------------------------------------------------------------------
# derive_taste_profile end-to-end, including multi-user isolation.
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_session_factory(monkeypatch: pytest.MonkeyPatch):
    """Mirrors tests/test_feedback_isolation.py's fixture of the same name:
    an isolated in-memory SQLite DB, never the developer's real macrochef.db.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(memory_service_module, "SessionLocal", test_session_local)
    monkeypatch.setattr(memory_service_module, "init_db", lambda: None)
    return test_session_local


def _shared_corpus_and_lookup() -> tuple[list[Recipe], dict[str, Recipe]]:
    corpus = [
        *[_recipe(f"filler{i}", ["rice", "onion"], cuisine="American") for i in range(20)],
        _recipe("alice_d1", ["xyzzyplorp", "rice"]),
        _recipe("alice_d2", ["xyzzyplorp", "onion"]),
        _recipe("alice_d3", ["xyzzyplorp", "garlic"]),
        _recipe("bob_d1", ["frobnicate", "rice"]),
        _recipe("bob_d2", ["frobnicate", "onion"]),
        _recipe("bob_d3", ["frobnicate", "garlic"]),
    ]
    lookup = {recipe.recipe_id: recipe for recipe in corpus}
    return corpus, lookup


def test_derive_taste_profile_end_to_end_avoided_ingredient(
    isolated_session_factory,
) -> None:
    session = isolated_session_factory()
    from app.schemas.recommendation import FeedbackRequest

    try:
        repo = FeedbackRepository(session)
        for recipe_id in ["alice_d1", "alice_d2", "alice_d3"]:
            repo.add_feedback(
                "user_alice",
                FeedbackRequest(recipe_id=recipe_id, feedback_type="disliked"),
            )
    finally:
        session.close()

    corpus, lookup = _shared_corpus_and_lookup()
    profile = derive_taste_profile(
        "user_alice", recipe_lookup=lookup, corpus_recipes=corpus
    )

    assert "xyzzyplorp" in profile.avoided_ingredients


def test_derive_taste_profile_never_leaks_between_users(
    isolated_session_factory,
) -> None:
    session = isolated_session_factory()
    from app.schemas.recommendation import FeedbackRequest

    try:
        repo = FeedbackRepository(session)
        for recipe_id in ["alice_d1", "alice_d2", "alice_d3"]:
            repo.add_feedback(
                "user_alice",
                FeedbackRequest(recipe_id=recipe_id, feedback_type="disliked"),
            )
        for recipe_id in ["bob_d1", "bob_d2", "bob_d3"]:
            repo.add_feedback(
                "user_bob",
                FeedbackRequest(recipe_id=recipe_id, feedback_type="disliked"),
            )
    finally:
        session.close()

    corpus, lookup = _shared_corpus_and_lookup()
    alice_profile = derive_taste_profile("user_alice", recipe_lookup=lookup, corpus_recipes=corpus)
    bob_profile = derive_taste_profile("user_bob", recipe_lookup=lookup, corpus_recipes=corpus)

    assert "xyzzyplorp" in alice_profile.avoided_ingredients
    assert "frobnicate" not in alice_profile.avoided_ingredients
    assert "frobnicate" in bob_profile.avoided_ingredients
    assert "xyzzyplorp" not in bob_profile.avoided_ingredients


def test_derive_taste_profile_empty_when_no_feedback(isolated_session_factory) -> None:
    corpus, lookup = _shared_corpus_and_lookup()
    profile = derive_taste_profile(
        "user_with_no_history", recipe_lookup=lookup, corpus_recipes=corpus
    )

    assert profile.avoided_ingredients == []
    assert profile.preferred_cuisines == []
