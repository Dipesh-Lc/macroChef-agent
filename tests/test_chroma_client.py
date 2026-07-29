"""Chroma-specific behavior of `ChromaVectorStore` (ROADMAP 5.2 moved this
out of `recipe_indexing_service.py`, which is now backend-agnostic -- see
`tests/test_recipe_indexing_service.py` for the seam-level tests)."""

from app.rag import chroma_client
from app.rag.chroma_client import ChromaVectorStore

# --- Chroma max-batch-size chunking (silent-zero-index bug fix) -----------
#
# chromadb's client enforces a max batch size (observed at 5,461 on the
# installed version) and raises ValueError if a single upsert() call
# exceeds it. The old unchunked, single-call upsert wrapped in a broad
# `except Exception` meant any corpus larger than that limit would fail
# the upsert, get silently swallowed, and return 0 -- degrading the whole
# app to keyword-only search with nothing but a log line. These tests
# prove chunking keeps every corpus size working and that the return
# value reflects the true total indexed, not just the last batch.


class _BatchLimitedFakeClient:
    """Mimics chromadb's real client: exposes get_max_batch_size() and
    raises ValueError if a single upsert() call exceeds it."""

    def __init__(self, max_batch_size: int):
        self._max_batch_size = max_batch_size

    def get_max_batch_size(self) -> int:
        return self._max_batch_size


class _BatchLimitedFakeCollection:
    def __init__(self, max_batch_size: int):
        self._client = _BatchLimitedFakeClient(max_batch_size)
        self.upsert_calls: list[dict] = []

    def upsert(self, ids, documents, metadatas):
        if len(ids) > self._client._max_batch_size:
            raise ValueError(
                f"Batch size of {len(ids)} is greater than max batch size of {self._client._max_batch_size}"
            )
        self.upsert_calls.append({"ids": list(ids), "documents": list(documents), "metadatas": list(metadatas)})


def _ids(n: int) -> list[str]:
    return [f"r{i}" for i in range(n)]


def test_upsert_below_batch_size_indexes_in_a_single_call(monkeypatch) -> None:
    """Regression test: a corpus smaller than the max batch size must still
    be indexed in one upsert call, unchanged from prior behavior."""
    collection = _BatchLimitedFakeCollection(max_batch_size=5461)
    monkeypatch.setattr(chroma_client, "get_chroma_collection", lambda: collection)

    ids = _ids(3)
    count = ChromaVectorStore().upsert(ids=ids, documents=ids, metadatas=[{} for _ in ids])

    assert count == 3
    assert len(collection.upsert_calls) == 1
    assert collection.upsert_calls[0]["ids"] == ["r0", "r1", "r2"]


def test_upsert_above_batch_size_chunks_across_multiple_upserts(monkeypatch) -> None:
    """A corpus larger than the max batch size must be chunked into
    multiple upsert() calls, each within the limit, with every id indexed
    exactly once and no omissions."""
    collection = _BatchLimitedFakeCollection(max_batch_size=3)
    monkeypatch.setattr(chroma_client, "get_chroma_collection", lambda: collection)

    ids = _ids(10)
    count = ChromaVectorStore().upsert(ids=ids, documents=ids, metadatas=[{} for _ in ids])

    # Total indexed reflects every id across all batches, not just the last batch's count.
    assert count == 10

    # Chunked into ceil(10/3) = 4 batches, each within the max batch size.
    assert len(collection.upsert_calls) == 4
    batch_sizes = [len(call["ids"]) for call in collection.upsert_calls]
    assert batch_sizes == [3, 3, 3, 1]
    assert all(size <= 3 for size in batch_sizes)

    # Every id indexed exactly once, no duplicates or omissions.
    all_indexed_ids = [recipe_id for call in collection.upsert_calls for recipe_id in call["ids"]]
    assert sorted(all_indexed_ids) == sorted(ids)
    assert len(all_indexed_ids) == len(set(all_indexed_ids))


def test_upsert_falls_back_to_default_batch_size_without_client(monkeypatch) -> None:
    """A collection fake with no `_client` must still index correctly via
    the documented default, rather than crashing on the batch-size lookup."""
    captured = {}

    class FakeCollectionNoClient:
        def upsert(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(chroma_client, "get_chroma_collection", lambda: FakeCollectionNoClient())

    ids = _ids(3)
    count = ChromaVectorStore().upsert(ids=ids, documents=ids, metadatas=[{} for _ in ids])

    assert count == 3
    assert captured["ids"] == ["r0", "r1", "r2"]


def test_upsert_with_no_ids_is_a_noop() -> None:
    assert ChromaVectorStore().upsert(ids=[], documents=[], metadatas=[]) == 0


def test_resolve_max_batch_size_reads_client_at_runtime() -> None:
    """The batch size is queried from the client at call time rather than
    hardcoded, so it stays correct if chromadb's own limit ever changes."""
    collection = _BatchLimitedFakeCollection(max_batch_size=42)
    assert chroma_client._resolve_max_batch_size(collection) == 42
