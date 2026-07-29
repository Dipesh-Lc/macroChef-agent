"""pgvector-backed `VectorStore` implementation.

ROADMAP.md Step 5.2: an external, multi-writer-safe alternative to the
embedded, single-writer Chroma store (see `app.rag.chroma_client`) --
retiring the multi-replica blocker documented in
`app.services.rate_limiter`'s module docstring. Selected via
`VECTOR_BACKEND=pgvector`; see `app.rag.vector_store.get_vector_store`.

Safety framing (CLAUDE.md invariant #1): this module is retrieval only. A
vector store may rank or retrieve recipes; it never admits, rejects, or
substitutes on allergy/diet grounds -- `app.services.constraint_engine`
remains the sole deterministic safety authority regardless of backend.

Schema: `recipe_embeddings` is defined on its own SQLAlchemy `MetaData`
(`PGVECTOR_METADATA` below), deliberately NOT part of
`app.data.db.Base.metadata`. Step 5.1's CI schema-drift gate (`alembic
check`, see `tests/test_alembic_migrations.py`) autogenerate-compares the
live DB against `Base.metadata` on a FRESH SQLITE database -- sqlite has no
`vector` type/extension, so if this table lived on `Base.metadata` that
gate would fail permanently on every commit, not just ones touching this
table. The migration that creates it
(`alembic/versions/0002_pgvector_recipe_embeddings.py`) imports this same
`Table` object (single source of truth) and no-ops on any non-Postgres
dialect for the same reason.

Connection: does NOT reuse `app.data.db.engine`. That module reads
`DATABASE_URL` via `app.config.get_settings()` and binds its engine once at
first import (both are process-wide cached/singleton -- see
`app.data.db`'s own docstring and `tests/test_alembic_migrations.py`'s,
which runs Alembic in a subprocess for exactly this reason). Reusing it
here would mean this store silently keeps talking to whatever
`DATABASE_URL` happened to be set when *some other module* first imported
`app.data.db` in this process -- invisible in production (env vars are
fixed at process start anyway) but a real footgun for tests, where dozens
of other test modules already import `app.data.db` against the default
sqlite URL before a pgvector-backend test ever runs. `_engine()` below
reads `DATABASE_URL` fresh (via `os.environ`, not the cached Settings
object) and caches one engine per URL seen, so it always targets the
Postgres instance actually configured right now.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import (
    Column,
    Engine,
    MetaData,
    String,
    Table,
    Text,
    and_,
    create_engine,
    delete,
    func,
    select,
)

from app.rag.embeddings import get_embedding_function
from app.rag.vector_store import VectorBackendUnavailableError
from app.utils.logging import get_logger

logger = get_logger(__name__)

EMBEDDING_DIM = 384
"""Both embedding providers this app ships (`HashingEmbeddingFunction`'s
default and the `sentence-transformers/all-MiniLM-L6-v2` model
`SentenceTransformerEmbeddingFunction` wraps) produce 384-dimensional
vectors -- see `app.rag.embeddings`. Fixed at table-creation time in the
Postgres `vector(384)` column type, so a future embedding model with a
different dimension needs both a new migration and this constant updated
together, not a config flag."""

PGVECTOR_METADATA = MetaData()

try:
    from pgvector.sqlalchemy import Vector
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    recipe_embeddings_table = Table(
        "recipe_embeddings",
        PGVECTOR_METADATA,
        Column("recipe_id", String(128), primary_key=True),
        Column("document", Text, nullable=False),
        Column("metadata_json", JSONB, nullable=False),
        Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
    )
except Exception:  # pragma: no cover - exercised only if pgvector/sqlalchemy import breaks
    recipe_embeddings_table = None  # noqa: N816 -- resolved lazily, see _table() below


class EmbeddingDimensionMismatchError(VectorBackendUnavailableError):
    """Raised when the live embedding provider's output dimension doesn't
    match `EMBEDDING_DIM` -- mirrors the reasoning in
    `app.rag.embeddings.EmbeddingModelUnavailableError`: a dimension
    mismatch (e.g. `EMBEDDING_PROVIDER=hash` queried against a table built
    with the real MiniLM model, or vice versa) must fail loudly rather than
    silently return nonsense nearest-neighbor results or a raw Postgres
    type error."""


def _table() -> Table:
    if recipe_embeddings_table is None:
        raise VectorBackendUnavailableError(
            "VECTOR_BACKEND=pgvector requires the 'pgvector' package "
            "(pip install pgvector) in addition to psycopg2/SQLAlchemy."
        )
    return recipe_embeddings_table


_engine_cache: dict[str, Engine] = {}


def _engine() -> Engine:
    database_url = os.environ.get("DATABASE_URL", "sqlite:///./macrochef.db")
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    if database_url not in _engine_cache:
        _engine_cache[database_url] = create_engine(database_url, pool_pre_ping=True)
    return _engine_cache[database_url]


def _check_dimension(vector: list[float]) -> None:
    if len(vector) != EMBEDDING_DIM:
        raise EmbeddingDimensionMismatchError(
            f"Embedding provider produced a {len(vector)}-dim vector but "
            f"recipe_embeddings is a vector({EMBEDDING_DIM}) column -- "
            "EMBEDDING_PROVIDER changed since this table was built. Rerun "
            "scripts/seed_pgvector.py after fixing EMBEDDING_PROVIDER, or "
            "restore it to match the value used to build this index."
        )


def build_where_clause(table: Table, where: dict[str, Any] | None):
    """Translate the `where` shapes `app.services.recipe_retriever.
    build_metadata_filter` emits -- `{"cuisine": x}`, `{"meal_type": x}`,
    `{"$and": [...]}` -- into a SQLAlchemy Core predicate over the JSONB
    `metadata_json` column. Raises `ValueError` on any other shape rather
    than silently degrading to "no filter", which would corrupt any
    retrieval-quality comparison that assumes the filter was actually
    applied (see ROADMAP 5.2's acceptance criterion: Recall@10 parity
    between backends)."""
    if where is None:
        return None
    if set(where.keys()) == {"$and"}:
        clauses = where["$and"]
        if not isinstance(clauses, list) or not clauses:
            raise ValueError(f"Unsupported where clause shape: {where!r}")
        return and_(*[_single_clause(table, clause) for clause in clauses])
    return _single_clause(table, where)


def _single_clause(table: Table, clause: Any):
    if not isinstance(clause, dict) or len(clause) != 1:
        raise ValueError(f"Unsupported where clause shape: {clause!r}")
    (key, value), = clause.items()
    if not isinstance(key, str) or not isinstance(value, str):
        raise ValueError(f"Unsupported where clause shape: {clause!r}")
    return table.c.metadata_json[key].astext == value


class PgVectorStore:
    """`app.rag.vector_store.VectorStore` implementation over Postgres +
    pgvector. Each method opens its own short-lived connection via
    `_engine()`'s pool (keyed on the current `DATABASE_URL`, not the app's
    shared `app.data.db.engine` -- see this module's docstring) rather than
    holding one open across calls."""

    def count(self) -> int:
        table = _table()
        with _engine().connect() as conn:
            return int(conn.execute(select(func.count()).select_from(table)).scalar_one())

    def query(
        self, text: str, n_results: int = 10, where: dict[str, Any] | None = None
    ) -> list[str]:
        table = _table()
        vector = get_embedding_function().embed_query(text)
        _check_dimension(vector)
        predicate = build_where_clause(table, where)

        stmt = (
            select(table.c.recipe_id)
            .order_by(table.c.embedding.cosine_distance(vector))
            .limit(n_results)
        )
        if predicate is not None:
            stmt = stmt.where(predicate)

        with _engine().connect() as conn:
            return [row[0] for row in conn.execute(stmt)]

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> int:
        if not ids:
            return 0
        table = _table()
        embed_documents = get_embedding_function().embed_documents
        vectors = embed_documents(documents)
        for vector in vectors:
            _check_dimension(vector)

        rows = [
            {
                "recipe_id": recipe_id,
                "document": document,
                "metadata_json": metadata,
                "embedding": vector,
            }
            for recipe_id, document, metadata, vector in zip(
                ids, documents, metadatas, vectors, strict=True
            )
        ]
        stmt = pg_insert(table).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["recipe_id"],
            set_={
                "document": stmt.excluded.document,
                "metadata_json": stmt.excluded.metadata_json,
                "embedding": stmt.excluded.embedding,
            },
        )
        with _engine().begin() as conn:
            conn.execute(stmt)
        return len(rows)

    def reset(self) -> PgVectorStore:
        table = _table()
        with _engine().begin() as conn:
            conn.execute(delete(table))
        return self
