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


# ROADMAP.md Phase 5, Step 5.2: `recipe_embeddings` (app.rag.pgvector_store)
# is deliberately NOT part of Base.metadata (see that module's docstring),
# managed instead by its own hand-written migration (0002) that no-ops on
# non-Postgres dialects. On a real Postgres DB, though, autogenerate/`check`
# reflects EVERY table actually present and compares it against
# target_metadata regardless of which MetaData created it -- without this
# exclusion, `alembic check` would see recipe_embeddings sitting in the
# live DB, find it absent from Base.metadata, and propose dropping it as
# drift on every run. `include_object` scopes the comparison to exactly the
# tables Base.metadata owns, leaving recipe_embeddings entirely to its own
# migration.
def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table" and name == "recipe_embeddings":
        return False
    table = getattr(object, "table", None)
    if type_ == "index" and table is not None and table.name == "recipe_embeddings":
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
