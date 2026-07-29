from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.data import models  # noqa: F401
from app.data.db import Base, database_url

# ROADMAP.md Phase 5, Step 5.1: reuse the app's own DB target/normalization
# logic rather than re-deriving it here. `app.data.db` already reads
# `DATABASE_URL` via `app.config.get_settings()` and normalizes a
# `postgres://` URL (Neon-style) to `postgresql://` for SQLAlchemy 2.x --
# see that module's docstring comment. Importing `database_url` from there
# means this file can never drift out of sync with how the running app
# itself connects, and `alembic.ini` deliberately carries no
# `sqlalchemy.url` so the same alembic.ini works unmodified against the
# sqlite dev DB and a real Postgres prod DB.
#
# `app.data.models` must be imported (even though nothing here references
# it by name) so every table class is registered on `Base.metadata` before
# `target_metadata` is read below -- autogenerate only sees tables that
# have actually been imported.

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# Tables deliberately NOT part of Base.metadata, each owned/versioned by
# something other than this app's own Alembic migrations:
#
# - "recipe_embeddings" (ROADMAP 5.2, app.rag.pgvector_store): its own
#   hand-written migration (0002), no-ops on non-Postgres dialects -- see
#   that module's docstring.
# - "checkpoints" / "checkpoint_blobs" / "checkpoint_writes" /
#   "checkpoint_migrations" (ROADMAP 3.2, app.graph.builder.
#   _select_checkpointer): created by the upstream langgraph-checkpoint-
#   postgres package's own idempotent `.setup()` migrations, not by this
#   app -- see that function's docstring for why hand-copying that DDL into
#   an Alembic revision would be a drift trap the moment the upstream
#   package's schema changes.
#
# On a real Postgres DB, autogenerate/`check` reflects EVERY table actually
# present and compares it against target_metadata regardless of which
# MetaData (or which package) created it -- without this exclusion,
# `alembic check` would see each of the above sitting in the live DB, find
# it absent from Base.metadata, and propose dropping it as drift on every
# run (confirmed directly against a real Postgres instance while building
# ROADMAP 3.2 -- the checkpoint tables tripped this exact gate the same way
# recipe_embeddings did for 5.2). `include_object` scopes the comparison to
# exactly the tables Base.metadata owns, leaving everything in this set
# entirely to its own migration/setup mechanism.
_EXCLUDED_FROM_DRIFT_GATE = {
    "recipe_embeddings",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name in _EXCLUDED_FROM_DRIFT_GATE:
        return False
    table = getattr(object, "table", None)
    if type_ == "index" and table is not None and table.name in _EXCLUDED_FROM_DRIFT_GATE:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Builds a short-lived engine from the same normalized `database_url`
    the app uses, rather than reusing `app.data.db.engine`'s live
    connection pool -- a migration run is a one-shot process (CLI
    invocation or CI step), so it gets its own `NullPool` connection
    instead of borrowing from the app's pool.
    """
    connectable = create_engine(database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
