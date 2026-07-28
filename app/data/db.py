from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

# Neon (and some other Postgres hosts) can hand out a `postgres://` URL, but
# SQLAlchemy 2.x dropped the `postgres://` alias for the `postgresql://`
# dialect -- create_engine() raises NoSuchModuleError on it. Normalize
# defensively here rather than relying on the upstream secret always being
# spelled `postgresql://`.
database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = "postgresql://" + database_url[len("postgres://"):]

connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create tables for local dev / tests; a no-op everywhere else.

    ROADMAP.md Phase 5, Step 5.1: schema management for a real deployment
    (Postgres/Neon) now goes through Alembic (`alembic/`, baseline revision
    `0001`), not `create_all` -- see `.github/workflows/ci.yml`'s `deploy`
    job, which runs `alembic upgrade head` against the prod DB before the
    traffic-shifting `az containerapp update`.

    `create_all` stays enabled here ONLY for sqlite, gated on
    `engine.dialect.name` rather than an env flag or "are we in pytest"
    check: sqlite is what local dev (`DATABASE_URL` unset -> the
    `sqlite:///./macrochef.db` default) and the whole test suite
    (`EMBEDDING_PROVIDER=hash pytest`, same default sqlite URL) both
    actually run against today, and dozens of call sites -- `app.main`'s
    lifespan, `app.services.memory_service`'s defensive per-call guards,
    `scripts/seed_sample_data.py`, `scripts/run_safety_benchmark.py` -- call
    `init_db()` expecting exactly this zero-friction "just works" behavior
    (see docs/BACKLOG.md B1 for the known "called too often" wart, which is
    out of scope here). Keying off the dialect means that behavior is
    preserved automatically for every one of those call sites without
    threading a new flag through any of them, while a Postgres
    `DATABASE_URL` (prod, or a developer pointing sqlite at a local
    Postgres) correctly falls through to the Alembic-only path instead of
    silently running an unversioned `create_all` against it.
    """
    from app.data import models  # noqa: F401

    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(bind=engine)
