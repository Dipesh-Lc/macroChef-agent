"""ROADMAP.md Step 5.2: contract tests every `VectorStore` backend must
satisfy identically (count/query/upsert/reset), parameterized over Chroma
(always runs) and pgvector (skipped unless `TEST_POSTGRES_URL` is set --
see `docker-compose.yml`'s `pgvector` service).

Both backends embed with `EMBEDDING_PROVIDER=hash` (the deterministic
fallback -- see `app.rag.embeddings.HashingEmbeddingFunction`), so a query
whose text exactly matches an indexed document's text is guaranteed to be
its own nearest neighbor under either backend, making these tests provider-
and network-independent.
"""

from __future__ import annotations

import os

import pytest

from app.rag.chroma_client import ChromaVectorStore

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")


def _chroma_store(tmp_path, monkeypatch) -> ChromaVectorStore:
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("CHROMA_COLLECTION_NAME", "contract_test")
    from app.config import get_settings

    get_settings.cache_clear()
    return ChromaVectorStore()


def _pgvector_store():
    from sqlalchemy import create_engine, text

    from app.rag.pgvector_store import PGVECTOR_METADATA, PgVectorStore, recipe_embeddings_table

    engine = create_engine(TEST_POSTGRES_URL)
    # This fixture builds the table directly rather than running the real
    # migration (0002_pgvector_recipe_embeddings.py) -- deliberately, so
    # these contract tests exercise PgVectorStore in isolation from Alembic
    # state/ordering. But that migration is also the only other place that
    # runs `CREATE EXTENSION IF NOT EXISTS vector`, so on a completely fresh
    # Postgres (e.g. a brand-new CI service container that has never had
    # any migration applied to it) the `vector` type doesn't exist yet
    # unless this fixture creates the extension itself too. Idempotent
    # (`IF NOT EXISTS`), so this is a no-op on a DB where the migration (or
    # a prior test in this same run) already created it.
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    PGVECTOR_METADATA.create_all(bind=engine, tables=[recipe_embeddings_table])
    engine.dispose()
    return PgVectorStore()


@pytest.fixture(params=["chroma", "pgvector"])
def store(request, tmp_path, monkeypatch):
    if request.param == "chroma":
        yield _chroma_store(tmp_path, monkeypatch)
        return

    if TEST_POSTGRES_URL is None:
        pytest.skip("TEST_POSTGRES_URL not set (needs `docker compose up pgvector`)")

    monkeypatch.setenv("DATABASE_URL", TEST_POSTGRES_URL)
    vector_store = _pgvector_store()
    vector_store.reset()
    yield vector_store
    vector_store.reset()


def _meta(recipe_id: str, **extra: str) -> dict:
    """Chroma's `query_collection` (see app.rag.chroma_client) resolves
    returned ids from each hit's `metadata["recipe_id"]`, not Chroma's own
    native id -- an existing, working production convention
    (`app.services.recipe_indexing_service.recipe_index_metadata` always
    sets this) that these synthetic test fixtures must follow too. Chroma
    also rejects a completely empty metadata dict, so `recipe_id` alone
    already satisfies both constraints."""
    return {"recipe_id": recipe_id, **extra}


def test_empty_store_has_zero_count(store) -> None:
    assert store.count() == 0


def test_upsert_then_count_reflects_inserted_rows(store) -> None:
    store.upsert(
        ids=["r1", "r2"],
        documents=["chicken and rice bowl", "beef stir fry with broccoli"],
        metadatas=[_meta("r1", cuisine="japanese"), _meta("r2", cuisine="chinese")],
    )
    assert store.count() == 2


def test_upsert_is_idempotent_on_recipe_id(store) -> None:
    store.upsert(
        ids=["r1"], documents=["chicken and rice bowl"], metadatas=[_meta("r1", cuisine="japanese")]
    )
    store.upsert(
        ids=["r1"],
        documents=["updated chicken and rice bowl"],
        metadatas=[_meta("r1", cuisine="japanese")],
    )
    assert store.count() == 1


def test_query_returns_exact_text_match_as_top_result(store) -> None:
    store.upsert(
        ids=["r1", "r2", "r3"],
        documents=["chicken and rice bowl", "beef stir fry with broccoli", "chocolate lava cake"],
        metadatas=[_meta("r1"), _meta("r2"), _meta("r3")],
    )

    results = store.query("chicken and rice bowl", n_results=3)

    assert results
    assert results[0] == "r1"

    results = store.query("chocolate lava cake", n_results=3)
    assert results[0] == "r3"


def test_query_respects_single_key_where_filter(store) -> None:
    store.upsert(
        ids=["r1", "r2"],
        documents=["chicken and rice bowl", "chicken and rice bowl"],
        metadatas=[_meta("r1", cuisine="japanese"), _meta("r2", cuisine="thai")],
    )

    results = store.query("chicken and rice bowl", n_results=10, where={"cuisine": "thai"})

    assert results == ["r2"]


def test_query_respects_and_filter(store) -> None:
    store.upsert(
        ids=["r1", "r2", "r3"],
        documents=["chicken and rice bowl"] * 3,
        metadatas=[
            _meta("r1", cuisine="japanese", meal_type="dinner"),
            _meta("r2", cuisine="japanese", meal_type="lunch"),
            _meta("r3", cuisine="thai", meal_type="dinner"),
        ],
    )

    results = store.query(
        "chicken and rice bowl",
        n_results=10,
        where={"$and": [{"cuisine": "japanese"}, {"meal_type": "dinner"}]},
    )

    assert results == ["r1"]


def test_reset_drops_all_prior_rows(store) -> None:
    store.upsert(ids=["r1"], documents=["chicken and rice bowl"], metadatas=[_meta("r1")])
    assert store.count() == 1

    store.reset()

    assert store.count() == 0


def test_query_on_empty_store_returns_empty_list(store) -> None:
    assert store.query("anything", n_results=5) == []


def test_upsert_with_empty_ids_is_a_noop(store) -> None:
    assert store.upsert(ids=[], documents=[], metadatas=[]) == 0
    assert store.count() == 0


# --- pgvector-only: where-clause shape enforcement (ROADMAP 5.2 acceptance:
# an unsupported filter shape must raise, never silently degrade to
# "no filter" -- see app.rag.pgvector_store.build_where_clause's docstring)
# --------------------------------------------------------------------------


@pytest.mark.skipif(TEST_POSTGRES_URL is None, reason="TEST_POSTGRES_URL not set")
def test_pgvector_rejects_unsupported_where_shape(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_POSTGRES_URL)
    vector_store = _pgvector_store()
    try:
        with pytest.raises(ValueError):
            vector_store.query("anything", n_results=5, where={"$or": [{"cuisine": "thai"}]})
        with pytest.raises(ValueError):
            vector_store.query(
                "anything", n_results=5, where={"cuisine": {"$in": ["thai", "japanese"]}}
            )
    finally:
        vector_store.reset()


@pytest.mark.skipif(TEST_POSTGRES_URL is None, reason="TEST_POSTGRES_URL not set")
def test_pgvector_dimension_mismatch_raises(monkeypatch) -> None:
    """`EMBEDDING_PROVIDER=hash` -> 384-dim (see app.rag.embeddings) --
    matches the table's vector(384) column, so this proves the guard is
    live (not just present in source) by forcing a mismatched provider
    output via a monkeypatched embedding function rather than actually
    reconfiguring EMBEDDING_PROVIDER (which would need a real MiniLM model
    download to demonstrate the other direction)."""
    monkeypatch.setenv("DATABASE_URL", TEST_POSTGRES_URL)
    vector_store = _pgvector_store()
    try:
        import app.rag.pgvector_store as pgvector_store_module
        from app.rag.pgvector_store import EmbeddingDimensionMismatchError

        class _WrongDimEmbedder:
            def embed_query(self, text):
                return [0.0] * 16

            def embed_documents(self, texts):
                return [[0.0] * 16 for _ in texts]

        monkeypatch.setattr(
            pgvector_store_module, "get_embedding_function", lambda: _WrongDimEmbedder()
        )

        with pytest.raises(EmbeddingDimensionMismatchError):
            vector_store.query("anything", n_results=5)
    finally:
        vector_store.reset()
