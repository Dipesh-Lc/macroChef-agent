"""Backend-agnostic vector store seam.

ROADMAP.md Step 5.2: retire the multi-replica blocker by making the
embedded, single-writer Chroma store swappable for pgvector (an external,
multi-writer-safe store) without touching any call site. Every caller in
this repo talks to the four operations below -- `count`, `query`, `upsert`,
`reset` -- never to a backend-specific client directly (see
`app.rag.chroma_client` / `app.rag.pgvector_store` for the two
implementations). `get_vector_store()` is the only place backend selection
happens, keyed on `settings.vector_backend` ("chroma" default, "pgvector").

Safety framing (CLAUDE.md invariant #1): this module is retrieval only. A
vector store may rank or retrieve recipes; it never admits, rejects, or
substitutes on allergy/diet grounds. The `contains_*` boolean metadata
written by `app.services.recipe_indexing_service.recipe_index_metadata` is
indexed here purely as a *retrieval* signal (e.g. so a future "avoid
shellfish-tagged" query could rank better) -- `app.services.constraint_engine`
remains the sole deterministic safety authority regardless of which backend
answers a query.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Protocol, runtime_checkable

from app.config import get_settings


@runtime_checkable
class VectorStore(Protocol):
    """The full surface every call site in this repo uses.

    `query` returns recipe_ids ranked by relevance (nearest-neighbor first),
    not raw vectors or scores -- no caller needs anything finer-grained than
    that today, and keeping the contract this narrow is what makes a second
    backend implementable in an afternoon instead of a rewrite.
    """

    def count(self) -> int: ...

    def query(
        self, text: str, n_results: int = 10, where: dict[str, Any] | None = None
    ) -> list[str]: ...

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> int: ...

    def reset(self) -> VectorStore:
        """Drop and recreate the store's index/collection, returning the
        (possibly new) store handle. See `reset_chroma_collection`'s
        docstring for why a clean rebuild -- not just re-`upsert` -- matters:
        upsert never prunes ids no longer present in the source corpus."""
        ...


class VectorBackendUnavailableError(RuntimeError):
    """Raised when the configured backend's dependency isn't installed or a
    connection can't be established. Mirrors `ChromaUnavailableError` --
    callers already catch broadly around indexing/retrieval (see
    `RecipeIndexingService.index_recipes`, `RecipeRetriever.retrieve`) and
    fall back to keyword search, so this is deliberately a plain
    `RuntimeError` subclass rather than something that needs new handling."""


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    """Process-wide singleton, selected by `VECTOR_BACKEND` (default
    "chroma"). Both backends open their own connection/client lazily inside
    each method, so this singleton is cheap to hold even before any recipe
    data exists."""
    settings = get_settings()
    backend = settings.vector_backend.lower()
    if backend == "pgvector":
        from app.rag.pgvector_store import PgVectorStore

        return PgVectorStore()
    if backend == "chroma":
        from app.rag.chroma_client import ChromaVectorStore

        return ChromaVectorStore()
    raise VectorBackendUnavailableError(
        f"Unknown VECTOR_BACKEND '{settings.vector_backend}'; expected 'chroma' or 'pgvector'."
    )
