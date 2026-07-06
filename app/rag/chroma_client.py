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
