"""Proves the /library user-data isolation properties end to end:

- a client-supplied user id is never trusted (no more `/library/{user_id}`
  path param) -- user B cannot read or delete user A's library by knowing/
  guessing an id;
- the row-stealing bug is fixed: two different users can each save a row
  under the same `recipe_id` without either one clobbering the other's row
  (see app.data.recipe_library_repository.save_recipe and the composite
  unique constraint on UserSavedRecipe);
- a forged/tampered session token is rejected by the real HTTP routes, not
  just by the dependency in isolation (see tests/test_session_auth.py for
  the dependency-level coverage).

Uses an isolated in-memory SQLite database (never the developer's real
macrochef.db) for every test in this module.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.routing import Route

import app.data.recipe_library_repository as repo_module
from app.config import get_settings
from app.data.db import Base
from app.data.models import UserSavedRecipe
from app.data.recipe_library_repository import RecipeLibraryRepository
from app.dependencies import SESSION_TOKEN_HEADER, mint_session_token
from app.main import create_app
from app.schemas.recipe import Recipe
from app.spa import _SPA_ASSETS_MOUNT_NAME, _SPA_FALLBACK_ROUTE_NAME


@pytest.fixture(autouse=True)
def _no_spa_mount(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Force `create_app()` in this module to never mount the SPA catch-all
    (see app/spa.py), regardless of whether a developer's working tree
    happens to have `web/dist` built.

    This module tests pure API-isolation behavior (a client-supplied user id
    must never resolve to someone's library data), including an assertion
    that an unmatched GET path 404s/405s. That assertion is about the API
    surface, not about whether the SPA shell happens to be mounted -- so it
    must not become flaky/wrong depending on local build state. Pointing
    `MACROCHEF_WEB_DIST` at a directory that is guaranteed to never exist
    (a `tmp_path` subdirectory that is never created) makes `mount_spa`
    (app/spa.py) skip the mount entirely, matching this suite's pre-SPA
    assumptions exactly. `app/spa.py` itself is untouched -- this only
    changes what this test module points the setting at.
    """
    never_built = tmp_path / "web-dist-never-built"
    monkeypatch.setenv("MACROCHEF_WEB_DIST", str(never_built))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    """Provide an explicit SESSION_SECRET so this suite tests the real
    signing/verification behavior regardless of ambient environment state.

    Without this, `_token()` below mints via the ambient `get_settings()`,
    which only resolves because a developer's local `.env` happens to have
    SESSION_SECRET set -- CI's `test` job sets only EMBEDDING_PROVIDER=hash
    and has no `.env` (gitignored), so `_resolve_session_secret` would raise
    there (see app.dependencies). `get_settings` is `lru_cache`d, so the
    cache must be cleared both before (to pick up the monkeypatched env) and
    after (so a stale Settings instance never leaks into a later test) --
    matches the pattern in tests/conftest.py's `force_mock_model_provider`.
    This also covers the FastAPI startup hook (validate_session_secret_at_
    startup, which reads ambient settings and is unaffected by dependency
    overrides): if any client here were constructed via
    `with TestClient(app):`, the ambient secret set here would still let it
    pass.
    """
    monkeypatch.setenv("SESSION_SECRET", "library-isolation-test-session-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def isolated_session_factory(monkeypatch: pytest.MonkeyPatch):
    """Point RecipeLibraryRepository's default (no-session-passed) path at a
    fresh in-memory SQLite DB instead of the developer's real macrochef.db."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(repo_module, "SessionLocal", test_session_local)
    return test_session_local


def _recipe(recipe_id: str, title: str = "Shared Recipe") -> Recipe:
    return Recipe(
        recipe_id=recipe_id,
        title=title,
        ingredients=[{"name": "rice", "amount": 100, "unit": "g"}],
        instructions=["Cook the rice."],
    )


def _client() -> TestClient:
    return TestClient(create_app())


def _token(user_id: str) -> str:
    return mint_session_token(user_id, get_settings())


def _auth_headers(user_id: str) -> dict[str, str]:
    return {SESSION_TOKEN_HEADER: _token(user_id)}


def _tamper(token: str) -> str:
    """Flip a character guaranteed to change the token's decoded bytes.

    Deliberately avoids the very last character: unpadded base64 (what
    itsdangerous uses) can have "don't care" bits in its final symbol, so
    some last-character edits decode to the exact same bytes as the
    original and would flakily leave the signature valid. See the identical
    helper in tests/test_session_auth.py for the full explanation.
    """
    middle = len(token) // 2
    original = token[middle]
    replacement = "A" if original != "A" else "B"
    return token[:middle] + replacement + token[middle + 1 :]


# ---------------------------------------------------------------------------
# The row-stealing bug: same recipe_id, two different users.
# ---------------------------------------------------------------------------


def test_second_user_saving_same_recipe_id_does_not_steal_first_users_row(
    isolated_session_factory,
) -> None:
    repo = RecipeLibraryRepository()

    shared_recipe_id = "user_deadbeefdeadbeef"
    repo.save_recipe("user_a", _recipe(shared_recipe_id, title="Alice's Bowl"))
    repo.save_recipe("user_b", _recipe(shared_recipe_id, title="Bob's Bowl"))

    alice_recipes = repo.list_user_recipes("user_a")
    bob_recipes = repo.list_user_recipes("user_b")

    assert [r.title for r in alice_recipes] == ["Alice's Bowl"]
    assert [r.title for r in bob_recipes] == ["Bob's Bowl"]
    assert alice_recipes[0].owner_user_id == "user_a"
    assert bob_recipes[0].owner_user_id == "user_b"

    # Both rows genuinely exist in the DB, distinctly owned.
    session = isolated_session_factory()
    try:
        rows = session.scalars(
            select(UserSavedRecipe).where(UserSavedRecipe.recipe_id == shared_recipe_id)
        ).all()
        assert len(rows) == 2
        owners = {row.user_id for row in rows}
        assert owners == {"user_a", "user_b"}
    finally:
        session.close()


def test_resaving_own_recipe_updates_in_place_without_duplicating(
    isolated_session_factory,
) -> None:
    repo = RecipeLibraryRepository()
    recipe_id = "user_cafefeedcafefeed"

    repo.save_recipe("user_a", _recipe(recipe_id, title="Original Title"))
    repo.save_recipe("user_a", _recipe(recipe_id, title="Updated Title"))

    recipes = repo.list_user_recipes("user_a")
    assert len(recipes) == 1
    assert recipes[0].title == "Updated Title"


def test_deactivating_one_users_recipe_does_not_touch_another_users_same_id(
    isolated_session_factory,
) -> None:
    repo = RecipeLibraryRepository()
    shared_recipe_id = "user_0123456789abcdef"

    repo.save_recipe("user_a", _recipe(shared_recipe_id, title="Alice's Bowl"))
    repo.save_recipe("user_b", _recipe(shared_recipe_id, title="Bob's Bowl"))

    deleted = repo.deactivate_recipe("user_a", shared_recipe_id)

    assert deleted is True
    assert repo.list_user_recipes("user_a") == []
    assert [r.title for r in repo.list_user_recipes("user_b")] == ["Bob's Bowl"]


# ---------------------------------------------------------------------------
# HTTP-level isolation: GET/DELETE no longer take a client-supplied user id.
# ---------------------------------------------------------------------------


def test_user_b_cannot_read_user_as_library_via_the_api(isolated_session_factory) -> None:
    RecipeLibraryRepository().save_recipe("user_a", _recipe("user_aaaa1111", "Alice's Secret Bowl"))

    client = _client()
    response = client.get("/library", headers=_auth_headers("user_b"))

    assert response.status_code == 200
    assert response.json()["recipes"] == []


def test_user_a_can_read_their_own_library_via_the_api(isolated_session_factory) -> None:
    RecipeLibraryRepository().save_recipe("user_a", _recipe("user_aaaa2222", "Alice's Bowl"))

    client = _client()
    response = client.get("/library", headers=_auth_headers("user_a"))

    assert response.status_code == 200
    titles = [r["title"] for r in response.json()["recipes"]]
    assert titles == ["Alice's Bowl"]


def test_user_b_cannot_delete_user_as_recipe_via_the_api(isolated_session_factory) -> None:
    RecipeLibraryRepository().save_recipe("user_a", _recipe("user_aaaa3333", "Alice's Bowl"))

    client = _client()
    response = client.delete("/library/user_aaaa3333", headers=_auth_headers("user_b"))

    assert response.status_code == 404
    # Alice's recipe must still be there afterwards.
    still_there = RecipeLibraryRepository().list_user_recipes("user_a")
    assert [r.title for r in still_there] == ["Alice's Bowl"]


def test_user_a_can_delete_their_own_recipe_via_the_api(isolated_session_factory) -> None:
    RecipeLibraryRepository().save_recipe("user_a", _recipe("user_aaaa4444", "Alice's Bowl"))

    client = _client()
    response = client.delete("/library/user_aaaa4444", headers=_auth_headers("user_a"))

    assert response.status_code == 200
    assert response.json() == {"recipe_id": "user_aaaa4444", "deleted": True}
    assert RecipeLibraryRepository().list_user_recipes("user_a") == []


def _flatten_routes(routes) -> list:
    """Recursively expand router-wrapper objects into the underlying `Route`/
    `Mount` instances. Adapted from the identical helper in
    tests/test_spa_serving.py (see that module's docstring for why the naive
    `isinstance` scan over `app.routes` is insufficient with this repo's
    pinned FastAPI version)."""
    flattened: list = []
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            flattened.extend(_flatten_routes(original_router.routes))
        else:
            flattened.append(route)
    return flattened


def _segments(path: str) -> list[str]:
    return [segment for segment in path.strip("/").split("/") if segment != ""]


def _is_wildcard(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def test_get_library_with_path_param_is_not_a_registered_api_route() -> None:
    """Regression guard, at the route-table level rather than the HTTP-status
    level: no `APIRouter`-registered route (i.e. excluding the SPA catch-all
    itself, see app/spa.py) may match `GET /library/<anything>`. Only
    `GET /library` (no param) and `DELETE /library/{recipe_id}` are meant to
    exist under `/library/` -- this is the precise way to assert "isn't even
    a registered route" that stays true regardless of whether the SPA shell
    happens to be mounted (mirrors the collision-guard pattern in
    tests/test_spa_serving.py::test_no_api_route_collides_with_spa_client_routes).
    """
    app = create_app()

    for route in _flatten_routes(app.routes):
        if getattr(route, "name", None) in (_SPA_FALLBACK_ROUTE_NAME, _SPA_ASSETS_MOUNT_NAME):
            continue  # the SPA's own catch-all/asset mount, not an API route
        if not isinstance(route, Route):
            continue
        if "GET" not in (route.methods or set()):
            continue
        segments = _segments(route.path)
        if len(segments) == 2 and segments[0] == "library" and _is_wildcard(segments[1]):
            pytest.fail(
                f"Found a registered GET route {route.path!r} under /library/ "
                "that would resolve a client-supplied id to someone's library "
                "contents -- this must never exist."
            )


def test_the_old_path_param_route_no_longer_exists(isolated_session_factory) -> None:
    """Regression guard: GET/DELETE must never again accept a user id as a
    path parameter -- that was the original vulnerability (anyone could read
    or delete anyone's library by guessing a string)."""
    client = _client()

    response = client.get("/library/user_a", headers=_auth_headers("user_a"))
    # No longer a valid list-library route; recipe_id "user_a" belongs to
    # nobody's deleted-lookup either, so both should never leak library
    # contents. GET /library/{recipe_id} isn't even a registered route (only
    # GET /library and DELETE /library/{recipe_id} are -- see
    # test_get_library_with_path_param_is_not_a_registered_api_route above
    # for the route-table-level proof of that).
    #
    # This module's `_no_spa_mount` fixture points MACROCHEF_WEB_DIST at a
    # directory that never exists, so in practice this always 404s here (the
    # SPA catch-all is never mounted in this suite). The branch below is
    # extra defense-in-depth so this assertion stays correct even if that
    # weren't true: if some future change to app.main ever made the SPA
    # catch-all reachable in this module anyway, a 200 would only be
    # acceptable if it's the static SPA shell (text/html, not JSON) -- proof
    # that no library data leaked at this path even though it "resolved" to
    # something.
    if response.status_code == 200:
        content_type = response.headers.get("content-type", "")
        assert not content_type.startswith("application/json")
        with pytest.raises(ValueError):
            response.json()
    else:
        assert response.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Forged/missing token rejection at the HTTP layer.
# ---------------------------------------------------------------------------


def test_missing_token_rejected_on_list_route(isolated_session_factory) -> None:
    client = _client()
    response = client.get("/library")
    assert response.status_code == 401


def test_forged_token_rejected_on_list_route(isolated_session_factory) -> None:
    client = _client()
    response = client.get("/library", headers={SESSION_TOKEN_HEADER: "forged.token.value"})
    assert response.status_code == 401


def test_tampered_token_rejected_on_delete_route(isolated_session_factory) -> None:
    RecipeLibraryRepository().save_recipe("user_a", _recipe("user_aaaa5555", "Alice's Bowl"))
    client = _client()
    token = _token("user_a")
    tampered = _tamper(token)

    response = client.delete(
        "/library/user_aaaa5555", headers={SESSION_TOKEN_HEADER: tampered}
    )

    assert response.status_code == 401
    # The recipe must survive an authentication failure untouched.
    still_there = RecipeLibraryRepository().list_user_recipes("user_a")
    assert [r.title for r in still_there] == ["Alice's Bowl"]


def test_missing_token_rejected_on_discover_route(isolated_session_factory) -> None:
    client = _client()
    response = client.post("/library/discover", json={"count": 1})
    assert response.status_code == 401


def test_missing_token_rejected_on_save_route(isolated_session_factory) -> None:
    client = _client()
    response = client.post("/library/save", json={"selected_candidates": []})
    assert response.status_code == 401


def test_client_supplied_user_id_field_is_ignored_not_honored(isolated_session_factory) -> None:
    """Even if a caller stuffs a `user_id` field into the request body (old
    API shape), the request body no longer has that field wired to
    anything -- identity comes only from the verified session token."""
    RecipeLibraryRepository().save_recipe("user_a", _recipe("user_aaaa6666", "Alice's Bowl"))

    client = _client()
    # Authenticate as user_b but try to smuggle user_id="user_a" in the body.
    response = client.post(
        "/library/discover",
        json={"count": 1, "user_id": "user_a"},
        headers=_auth_headers("user_b"),
    )

    assert response.status_code == 200
    # Discovery succeeded as user_b (the verified identity), regardless of
    # the ignored body field -- proven indirectly by there being no server
    # error and by the isolation tests above showing user_id is sourced only
    # from get_session_user.
