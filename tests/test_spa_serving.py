"""HTTP-level tests for SPA static-file serving + fallback (SPA rebuild,
roadmap item W1a, `app/spa.py`).

Covers:
1. `GET /` serves `index.html` (`Cache-Control: no-cache`).
2. SPA client routes (`/week`, `/shared/{id}`) also fall back to
   `index.html` (client-side routing).
3. `GET /assets/<file>` serves the built asset with a long-lived,
   immutable `Cache-Control` (Vite content-hashes these filenames).
4. `GET /health` and `GET /api-info` (the relocated root JSON route) are
   unaffected -- still JSON.
5. A non-GET request to an unmatched path (`POST /plan/nope`) never falls
   through to the SPA shell -- the fallback is GET-only.
6. A dotted, nonexistent path 404s rather than serving `index.html`.
7. A path-traversal attempt never escapes `WEB_DIST`.
8. With `WEB_DIST` missing entirely, the app still boots; `/health` keeps
   working and `GET /` 404s (no crash, no partial mount).
9. Route-collision guard: no API route may equal or be a prefix-parent of
   any SPA client route in `app.spa.SPA_ROUTES` -- this MUST fail if
   someone later adds e.g. `GET /day` to the API.

No safety/nutrition logic is exercised here -- this module is pure
static-file serving.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Mount, Route

from app.config import get_settings
from app.main import create_app
from app.spa import _SPA_ASSETS_MOUNT_NAME, _SPA_FALLBACK_ROUTE_NAME, SPA_ROUTES

INDEX_HTML = "<!doctype html><html><body>MacroChef SPA</body></html>"
APP_JS = "console.log('macrochef spa bundle');"


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch):
    # Only needed so TestClient requests that trigger the startup event
    # (validate_session_secret_at_startup) don't raise -- unrelated to SPA
    # serving itself.
    monkeypatch.setenv("SESSION_SECRET", "spa-serving-test-session-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def web_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (assets / "app.js").write_text(APP_JS, encoding="utf-8")
    return dist


@pytest.fixture()
def client(web_dist: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MACROCHEF_WEB_DIST", str(web_dist))
    get_settings.cache_clear()
    test_client = TestClient(create_app())
    yield test_client
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 1-2: index.html + SPA client-route fallback
# ---------------------------------------------------------------------------


def test_root_serves_index_html(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert INDEX_HTML in resp.text
    assert resp.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/week", "/shared/abc123"])
def test_spa_client_routes_fall_back_to_index_html(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert INDEX_HTML in resp.text
    assert resp.headers["cache-control"] == "no-cache"


# ---------------------------------------------------------------------------
# 3: hashed asset serving
# ---------------------------------------------------------------------------


def test_assets_served_with_immutable_cache_control(client: TestClient) -> None:
    resp = client.get("/assets/app.js")
    assert resp.status_code == 200
    assert resp.text == APP_JS
    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"


# ---------------------------------------------------------------------------
# 4: existing JSON endpoints unaffected
# ---------------------------------------------------------------------------


def test_health_still_json(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"status": "ok", "service": "macrochef-agent"}


def test_api_info_relocated_from_root(client: TestClient) -> None:
    resp = client.get("/api-info")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body == {
        "service": "macrochef-agent",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


# ---------------------------------------------------------------------------
# 5: fallback is GET-only
# ---------------------------------------------------------------------------


def test_post_to_unmatched_path_never_returns_spa_shell(client: TestClient) -> None:
    resp = client.post("/plan/nope")
    assert resp.status_code in (404, 405)
    assert INDEX_HTML not in resp.text
    content_type = resp.headers.get("content-type", "")
    assert not content_type.startswith("text/html")


# ---------------------------------------------------------------------------
# 6: dotted, missing path -> 404 (never the SPA shell)
# ---------------------------------------------------------------------------


def test_dotted_missing_path_404s(client: TestClient) -> None:
    resp = client.get("/nonexistent.js")
    assert resp.status_code == 404
    assert INDEX_HTML not in resp.text


# ---------------------------------------------------------------------------
# 7: path traversal never escapes WEB_DIST
# ---------------------------------------------------------------------------


def test_path_traversal_attempt_404s(client: TestClient) -> None:
    resp = client.get("/..%2f..%2fapp%2fconfig.py")
    assert resp.status_code == 404
    assert "SESSION_SECRET" not in resp.text  # app/config.py contents must never leak
    assert "class Settings" not in resp.text


# ---------------------------------------------------------------------------
# 8: WEB_DIST missing entirely -> app still boots, degrades gracefully
# ---------------------------------------------------------------------------


def test_missing_web_dist_degrades_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("MACROCHEF_WEB_DIST", str(missing))
    get_settings.cache_clear()

    no_spa_client = TestClient(create_app())

    resp = no_spa_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    resp = no_spa_client.get("/")
    assert resp.status_code == 404

    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# 9: route-collision guard
# ---------------------------------------------------------------------------


def _segments(path: str) -> list[str]:
    return [segment for segment in path.strip("/").split("/") if segment != ""]


def _is_wildcard(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def _segments_match(a_segments: list[str], b_segments: list[str]) -> bool:
    return all(
        a == b or _is_wildcard(a) or _is_wildcard(b) for a, b in zip(a_segments, b_segments)
    )


def _mount_collides(mount_segments: list[str], spa_segments: list[str]) -> bool:
    """A `Mount` matches its path AND everything beneath it (Starlette
    routes sub-paths through to the mounted app), so it collides with a SPA
    route whenever the mount's path is a prefix of (or equal to) that SPA
    route's path."""
    if len(mount_segments) > len(spa_segments):
        return False
    return _segments_match(mount_segments, spa_segments[: len(mount_segments)])


def _route_collides(route_segments: list[str], spa_segments: list[str]) -> bool:
    """A plain `Route` only matches requests with the exact same number of
    path segments (ignoring FastAPI's `{path:path}` convertor, which this
    codebase's API routes don't use), so it only collides with a SPA route
    of the same segment count."""
    if len(route_segments) != len(spa_segments):
        return False
    return _segments_match(route_segments, spa_segments)


def _flatten_routes(routes) -> list:
    """Recursively expand any router-wrapper objects into the underlying
    `Route`/`Mount` instances.

    Newer FastAPI versions (observed: 0.139.0, this repo's pinned version)
    wrap each `include_router(...)` call in an internal `_IncludedRouter`
    object that sits directly in `app.routes` -- it is neither a `Route` nor
    a `Mount`, so a naive `isinstance` scan over `app.routes` silently sees
    only routes registered directly on `app` (like FastAPI's own `/docs`,
    `/openapi.json`, and this module's own SPA mount/fallback) and misses
    every API router's actual routes entirely. Each such wrapper exposes the
    real `APIRouter` (with its prefix already applied to each route's path)
    via `.original_router.routes`.
    """
    flattened: list = []
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            flattened.extend(_flatten_routes(original_router.routes))
        else:
            flattened.append(route)
    return flattened


def test_no_api_route_collides_with_spa_client_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Starlette matches routes in registration order; the SPA catch-all is
    (deliberately) mounted last in `app.main.create_app`, so any earlier GET
    route whose path equals or is a prefix-parent of an `SPA_ROUTES` entry
    would intercept that browser navigation and serve JSON instead of the
    SPA shell.

    This test MUST fail if someone later adds e.g. `GET /day` to the API.
    """
    # Deterministic regardless of whether a developer's local .env points
    # MACROCHEF_WEB_DIST at a real build -- this test only inspects route
    # *paths*, not served content.
    monkeypatch.delenv("MACROCHEF_WEB_DIST", raising=False)
    get_settings.cache_clear()
    app = create_app()
    get_settings.cache_clear()

    api_mount_paths: list[str] = []
    api_route_paths: list[str] = []
    for route in _flatten_routes(app.routes):
        name = getattr(route, "name", None)
        if name in (_SPA_FALLBACK_ROUTE_NAME, _SPA_ASSETS_MOUNT_NAME):
            continue  # our own, intentional catch-all/mount -- not a collision
        if isinstance(route, Mount):
            api_mount_paths.append(route.path)
        elif isinstance(route, Route):
            if "GET" in (route.methods or set()):
                api_route_paths.append(route.path)

    for spa_route in SPA_ROUTES:
        spa_segments = _segments(spa_route)
        for mount_path in api_mount_paths:
            assert not _mount_collides(_segments(mount_path), spa_segments), (
                f"API mount {mount_path!r} collides with SPA client route "
                f"{spa_route!r} -- it would swallow that browser navigation "
                f"instead of the request reaching the SPA fallback."
            )
        for route_path in api_route_paths:
            assert not _route_collides(_segments(route_path), spa_segments), (
                f"API route {route_path!r} collides with SPA client route "
                f"{spa_route!r} -- it would shadow the SPA fallback for "
                f"that browser navigation instead of serving the SPA shell."
            )
