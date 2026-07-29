"""ROADMAP.md Step 5.2 -- release-job entrypoint for seeding a pgvector-backed
Postgres instance with the full recipe corpus.

Unlike the Chroma path (baked into the Docker image at *build* time, see
`Dockerfile`), pgvector's data lives in the external Postgres database, not
the container image -- so seeding it is a one-shot *release* step, not a
build step: run this once per environment (or after a corpus/embedding-model
change), pointed at that environment's `DATABASE_URL`.

Usage:
    VECTOR_BACKEND=pgvector DATABASE_URL=postgresql://... python scripts/seed_pgvector.py

Refuses to run unless `VECTOR_BACKEND=pgvector` is set explicitly -- this
guards against the easy mistake of running this against a `DATABASE_URL`
whose `VECTOR_BACKEND` is still (or accidentally) "chroma", which would
silently seed a table nothing reads from.
"""

import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.services.recipe_indexing_service import RecipeIndexingService  # noqa: E402


def _redact_credentials(database_url: str) -> str:
    """Never print a DATABASE_URL's embedded password to stdout/CI logs."""
    parts = urlsplit(database_url)
    if not parts.password:
        return database_url
    host_part = f"{parts.hostname or ''}"
    if parts.port:
        host_part += f":{parts.port}"
    netloc = f"{parts.username}:***@{host_part}" if parts.username else f"***@{host_part}"
    return parts._replace(netloc=netloc).geturl()


def main() -> int:
    settings = get_settings()
    if settings.vector_backend.lower() != "pgvector":
        print(
            f"VECTOR_BACKEND is '{settings.vector_backend}', not 'pgvector' -- "
            "refusing to run. Set VECTOR_BACKEND=pgvector explicitly to seed "
            "the pgvector backend (see this script's module docstring)."
        )
        return 1

    print(f"Seeding pgvector at {_redact_credentials(settings.database_url)} (clean rebuild)...")
    count = RecipeIndexingService().rebuild_index_clean(include_base=True, include_user=True)
    print(f"Indexed {count} recipes into pgvector.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
