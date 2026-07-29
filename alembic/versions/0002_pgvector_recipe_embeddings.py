"""pgvector recipe_embeddings table

ROADMAP.md Phase 5, Step 5.2: schema for the pgvector `VectorStore` backend
(`app.rag.pgvector_store`). A no-op on any non-Postgres dialect -- this
table is deliberately NOT part of `app.data.db.Base.metadata` (see
`app.rag.pgvector_store`'s module docstring for why), so the Step 5.1
schema-drift gate (`alembic check` against a fresh sqlite DB,
`tests/test_alembic_migrations.py`) never sees it and this migration must
guard itself instead of relying on that gate to skip it.

Reuses `app.rag.pgvector_store.recipe_embeddings_table` as the single
source of truth for the table shape, rather than re-declaring the columns
here, so the store module and this migration can never drift apart.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-29 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_recipe_embeddings_embedding_hnsw"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # sqlite (local dev/tests) and any other non-Postgres dialect: no
        # vector type/extension available, and nothing reads this table
        # unless VECTOR_BACKEND=pgvector anyway.
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    from app.rag.pgvector_store import PGVECTOR_METADATA, recipe_embeddings_table

    PGVECTOR_METADATA.create_all(bind=bind, tables=[recipe_embeddings_table])

    op.create_index(
        INDEX_NAME,
        "recipe_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index(INDEX_NAME, table_name="recipe_embeddings")
    op.drop_table("recipe_embeddings")
