"""Serve the built React SPA (SPA rebuild, roadmap item W1a) as static files,
with a client-side-routing fallback.

The `web/` directory (Vite build) is added by a later roadmap item. Until
then -- and in any environment without a Node toolchain, notably pytest/CI --
`mount_spa` is a no-op: it logs a single warning and registers nothing, so
`GET /` simply 404s while every JSON API route, `/health`, and `/docs`
continue to work exactly as before.

No safety/nutrition logic lives here -- this module only serves files.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Client-side routes the SPA itself handles (React Router or equivalent).
# Used to mount the catch-all fallback below AND by
# tests/test_spa_serving.py as a guard: no API route may equal or be a
# prefix-parent of any of these, or a browser GET to that path would hit the
# JSON API instead of the SPA shell.
SPA_ROUTES: list[str] = ["/", "/day", "/week", "/batch", "/my-recipes", "/shared/{id}"]

# Name assigned to the catch-all fallback route, so other code (e.g. the
# route-collision guard test) can identify and exclude it -- it is a
# deliberate, intentional "match everything" route, not a collision.
_SPA_FALLBACK_ROUTE_NAME = "spa-fallback"
_SPA_ASSETS_MOUNT_NAME = "spa-assets"


class _ImmutableCacheStaticFiles(StaticFiles):
    """StaticFiles that marks every response long-lived + immutable.

    Vite emits content-hashed filenames under `assets/` (e.g.
    `index-a1b2c3d4.js`), so a cached response is always correct for that
    exact URL -- a new build produces new filenames rather than mutating an
    existing one.
    """

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def mount_spa(app: FastAPI) -> None:
    """Mount the built SPA onto `app`, if it has been built.

    Must be called LAST in `app.main.create_app`, after every API router is
    registered -- the fallback route below matches any path, so anything
    registered after it would be unreachable.
    """
    settings = get_settings()
    web_dist = Path(settings.web_dist).resolve()
    index_html = web_dist / "index.html"

    if not index_html.is_file():
        logger.warning(
            "SPA build not found at %s -- skipping SPA/static mounts; "
            "GET / will 404 until `web/dist` is built (see MACROCHEF_WEB_DIST "
            "in .env.example).",
            index_html,
        )
        return

    assets_dir = web_dist / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            _ImmutableCacheStaticFiles(directory=assets_dir),
            name=_SPA_ASSETS_MOUNT_NAME,
        )

    @app.get(
        "/{full_path:path}",
        include_in_schema=False,
        name=_SPA_FALLBACK_ROUTE_NAME,
    )
    def spa_fallback(full_path: str) -> FileResponse:
        """Serve `index.html` for any SPA client route; serve a real file
        (e.g. `favicon.svg`, `robots.txt`) if one exists directly under
        `web_dist`; 404 otherwise. Registered GET-only and last, so it never
        shadows an existing API route and never intercepts non-GET requests
        (those correctly 404/405 instead of returning the SPA shell).
        """
        normalized = full_path.lstrip("/")
        candidate = (web_dist / normalized).resolve()

        # Containment check FIRST, independent of whether the path "looks
        # like" a file request: never resolve or serve anything outside
        # web_dist, regardless of how `..` / encoded traversal segments made
        # it into `full_path`.
        try:
            candidate.relative_to(web_dist)
        except ValueError:
            raise HTTPException(status_code=404)

        last_segment = normalized.rsplit("/", 1)[-1]
        looks_like_file = "." in last_segment

        if looks_like_file:
            if candidate.is_file():
                return FileResponse(candidate)
            raise HTTPException(status_code=404)

        return FileResponse(index_html, headers={"Cache-Control": "no-cache"})
