from pathlib import Path
from typing import Any

from app.config import get_settings
from app.rag.embeddings import get_embedding_function
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ChromaUnavailableError(RuntimeError):
    pass


def get_chroma_collection():
    settings = get_settings()
    try:
        import chromadb
    except Exception as exc:  # pragma: no cover - only when dependency missing
        raise ChromaUnavailableError("chromadb is not installed") from exc

    Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=settings.chroma_path)
    embedding_function = get_embedding_function()
    return client.get_or_create_collection(
        name=settings.chroma_collection_name,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )


def reset_chroma_collection():
    """Delete and recreate the collection so a rebuild starts from empty.

    `collection.upsert` (used by normal indexing) never prunes ids that are no
    longer present in the source data, so a corpus re-import with a smaller or
    corrected dataset would otherwise leave orphaned embeddings behind. Callers
    that want a true clean rebuild should call this before re-indexing.
    """
    settings = get_settings()
    try:
        import chromadb
    except Exception as exc:  # pragma: no cover - only when dependency missing
        raise ChromaUnavailableError("chromadb is not installed") from exc

    Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=settings.chroma_path)
    try:
        client.delete_collection(name=settings.chroma_collection_name)
    except Exception:
        # Collection may not exist yet on a fresh store; that's fine.
        pass
    return get_chroma_collection()


def collection_count() -> int:
    try:
        collection = get_chroma_collection()
        return int(collection.count())
    except Exception as exc:
        logger.warning("Could not inspect Chroma collection: %s", exc)
        return 0


def query_collection(query: str, n_results: int = 10, where: dict[str, Any] | None = None) -> list[str]:
    collection = get_chroma_collection()
    result = collection.query(query_texts=[query], n_results=n_results, where=where or None)
    metadatas = result.get("metadatas") or [[]]
    ids: list[str] = []
    for metadata in metadatas[0]:
        recipe_id = metadata.get("recipe_id") if metadata else None
        if recipe_id:
            ids.append(str(recipe_id))
    return ids


DEFAULT_MAX_BATCH_SIZE = 5461
"""Fallback only -- used when the collection can't report its own limit
(e.g. a lightweight test fake with no `_client`). The real limit is always
queried at runtime via `_resolve_max_batch_size` so this stays correct if
chromadb's own ceiling ever changes. Chroma-specific: pgvector has no
equivalent per-call item cap, so this constant has no meaning there --
moved into this module (from `recipe_indexing_service.py`) in ROADMAP 5.2
when the `VectorStore` seam was introduced."""


def _resolve_max_batch_size(collection, default: int = DEFAULT_MAX_BATCH_SIZE) -> int:
    """Ask the underlying Chroma client for its actual max batch size.

    `collection.upsert(...)` raises `ValueError` if given more items than
    the client's `get_max_batch_size()` in one call (observed at 5,461 on
    the installed chromadb version). Querying it at runtime -- rather than
    hardcoding a constant -- means this stays correct if that limit ever
    changes in a future chromadb release.
    """
    client = getattr(collection, "_client", None)
    get_max_batch_size = getattr(client, "get_max_batch_size", None)
    if callable(get_max_batch_size):
        try:
            resolved = int(get_max_batch_size())
            if resolved > 0:
                return resolved
        except Exception:
            pass
    return default


class ChromaVectorStore:
    """`app.rag.vector_store.VectorStore` implementation over the module-level
    functions above. A thin wrapper (not a rewrite) so the battle-tested free
    functions -- and every existing direct import of them -- stay exactly as
    they were before ROADMAP 5.2 introduced the `VectorStore` seam.
    """

    def count(self) -> int:
        return collection_count()

    def query(
        self, text: str, n_results: int = 10, where: dict[str, Any] | None = None
    ) -> list[str]:
        return query_collection(text, n_results=n_results, where=where)

    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict[str, Any]]) -> int:
        if not ids:
            return 0
        collection = get_chroma_collection()
        max_batch_size = _resolve_max_batch_size(collection)
        indexed = 0
        for start in range(0, len(ids), max_batch_size):
            end = start + max_batch_size
            collection.upsert(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )
            indexed += len(ids[start:end])
        return indexed

    def reset(self) -> "ChromaVectorStore":
        reset_chroma_collection()
        return self
