"""Phase 4 (expiry/waste tracking): `app.services.waste_tracking`.

Covers:
- `build_waste_nudges`: only expiring-soon inventory surfaces a nudge; each
  nudge carries up to the requested number of corpus recipes that use it
  (via the existing `ingredient_matches` matching primitive, not new
  matching logic); nothing expiring -> `[]`; duplicate ingredient names in
  the inventory are merged into one nudge.
- `count_ingredients_used_before_expiring`: a plain count (never a dollar
  figure) of expiring-soon ingredients that also appear in a recipe this
  user has already cooked/liked, end-to-end against an isolated in-memory
  DB (mirrors tests/test_taste_profile_derivation.py's fixture), including
  that it stays 0 with no matching feedback history.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.memory_service as memory_service_module
from app.data.db import Base
from app.data.repositories import FeedbackRepository
from app.schemas.inventory import ConfirmedIngredient
from app.schemas.recipe import Recipe
from app.schemas.recommendation import FeedbackRequest
from app.services.waste_tracking import (
    build_waste_nudges,
    count_ingredients_used_before_expiring,
)


def _recipe(recipe_id: str, ingredients: list[str], title: str | None = None) -> Recipe:
    return Recipe(
        recipe_id=recipe_id,
        title=title or f"Recipe {recipe_id}",
        ingredients=ingredients,
        instructions=["Cook."],
    )


_CORPUS = [
    _recipe("r1", ["spinach", "garlic"], title="Garlic Spinach Saute"),
    _recipe("r2", ["spinach", "egg"], title="Spinach Frittata"),
    _recipe("r3", ["spinach", "feta"], title="Spinach Feta Pie"),
    _recipe("r4", ["spinach", "rice"], title="Spinach Rice Bowl"),
    _recipe("r5", ["chicken breast", "rice"], title="Chicken Rice Bowl"),
]


# ---------------------------------------------------------------------------
# build_waste_nudges
# ---------------------------------------------------------------------------


def test_no_expiring_inventory_returns_no_nudges() -> None:
    inventory = [
        ConfirmedIngredient(name="spinach", expires_soon=False),
        ConfirmedIngredient(name="rice", expires_soon=False),
    ]
    assert build_waste_nudges(inventory, corpus=_CORPUS) == []


def test_empty_inventory_returns_no_nudges() -> None:
    assert build_waste_nudges([], corpus=_CORPUS) == []


def test_expiring_ingredient_surfaces_a_nudge_with_matching_recipes() -> None:
    inventory = [
        ConfirmedIngredient(name="spinach", expires_soon=True),
        ConfirmedIngredient(name="chicken breast", expires_soon=False),
    ]

    nudges = build_waste_nudges(inventory, corpus=_CORPUS)

    assert len(nudges) == 1
    nudge = nudges[0]
    assert nudge.ingredient_name == "spinach"
    # Only up to 3 suggested recipes even though 4 corpus recipes use spinach.
    assert len(nudge.suggested_recipes) == 3
    for suggestion in nudge.suggested_recipes:
        assert suggestion.recipe_id in {"r1", "r2", "r3", "r4"}


def test_non_expiring_chicken_breast_is_not_nudged_even_though_it_matches_a_recipe() -> None:
    inventory = [ConfirmedIngredient(name="chicken breast", expires_soon=False)]
    assert build_waste_nudges(inventory, corpus=_CORPUS) == []


def test_expiring_ingredient_with_no_matching_recipe_still_returns_an_empty_suggestion_list() -> None:
    inventory = [ConfirmedIngredient(name="durian", expires_soon=True)]

    nudges = build_waste_nudges(inventory, corpus=_CORPUS)

    assert len(nudges) == 1
    assert nudges[0].ingredient_name == "durian"
    assert nudges[0].suggested_recipes == []


def test_days_until_expiry_is_carried_through_from_the_inventory_item() -> None:
    from datetime import date, timedelta

    item = ConfirmedIngredient(
        name="spinach", purchase_date=date.today() - timedelta(days=10)
    )
    assert item.expires_soon is True  # sanity check on the derivation itself

    nudges = build_waste_nudges([item], corpus=_CORPUS)

    assert len(nudges) == 1
    assert nudges[0].days_until_expiry == item.days_until_expiry()
    assert nudges[0].days_until_expiry < 0


def test_duplicate_ingredient_names_are_merged_into_one_nudge() -> None:
    inventory = [
        ConfirmedIngredient(name="spinach", expires_soon=True),
        ConfirmedIngredient(name="spinach", expires_soon=True, amount=1, unit="bag"),
    ]

    nudges = build_waste_nudges(inventory, corpus=_CORPUS)

    assert len(nudges) == 1


def test_max_recipes_per_ingredient_is_configurable() -> None:
    inventory = [ConfirmedIngredient(name="spinach", expires_soon=True)]

    nudges = build_waste_nudges(inventory, corpus=_CORPUS, max_recipes_per_ingredient=1)

    assert len(nudges[0].suggested_recipes) == 1


# ---------------------------------------------------------------------------
# count_ingredients_used_before_expiring
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_session_factory(monkeypatch: pytest.MonkeyPatch):
    """Mirrors tests/test_taste_profile_derivation.py's fixture of the same
    name: an isolated in-memory SQLite DB, never the developer's real
    macrochef.db. `count_ingredients_used_before_expiring` calls
    `app.services.memory_service.get_user_memory`, which resolves
    `SessionLocal`/`init_db` from that module's own globals at call time --
    patching them there is sufficient regardless of how
    `app.services.waste_tracking` imported the function.
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


def test_count_is_zero_with_no_expiring_ingredients(isolated_session_factory) -> None:
    inventory = [ConfirmedIngredient(name="spinach", expires_soon=False)]
    assert count_ingredients_used_before_expiring("user_a", inventory, corpus=_CORPUS) == 0


def test_count_is_zero_with_no_cooked_feedback(isolated_session_factory) -> None:
    inventory = [ConfirmedIngredient(name="spinach", expires_soon=True)]
    assert count_ingredients_used_before_expiring("user_a", inventory, corpus=_CORPUS) == 0


def test_count_reflects_a_cooked_recipe_that_used_the_expiring_ingredient(
    isolated_session_factory,
) -> None:
    session = isolated_session_factory()
    try:
        FeedbackRepository(session).add_feedback(
            "user_a", FeedbackRequest(recipe_id="r1", feedback_type="cooked")
        )
    finally:
        session.close()

    inventory = [ConfirmedIngredient(name="spinach", expires_soon=True)]

    assert count_ingredients_used_before_expiring("user_a", inventory, corpus=_CORPUS) == 1


def test_count_never_leaks_between_users(isolated_session_factory) -> None:
    session = isolated_session_factory()
    try:
        FeedbackRepository(session).add_feedback(
            "user_b", FeedbackRequest(recipe_id="r1", feedback_type="cooked")
        )
    finally:
        session.close()

    inventory = [ConfirmedIngredient(name="spinach", expires_soon=True)]

    assert count_ingredients_used_before_expiring("user_a", inventory, corpus=_CORPUS) == 0
