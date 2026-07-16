import hashlib
import math
from collections.abc import Sequence
from functools import lru_cache

from app.config import get_settings


class HashingEmbeddingFunction:
    """Small deterministic fallback embedding function for offline demos/tests."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = text.lower().replace(",", " ").replace("\n", " ").split()
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def __call__(self, input: Sequence[str]) -> list[list[float]]:  # Chroma signature
        return [self._embed_one(text) for text in input]

    def embed_query(self, input: str | Sequence[str]) -> list[float] | list[list[float]]:
        if isinstance(input, str):
            return self._embed_one(input)
        return self(input)

    def embed_documents(self, input: Sequence[str]) -> list[list[float]]:
        return self(input)

    @staticmethod
    def name() -> str:
        return "macrochef-hashing-embedding"

    def is_legacy(self) -> bool:
        return False

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def get_config(self) -> dict[str, int]:
        return {"dimensions": self.dimensions}

    @classmethod
    def build_from_config(cls, config: dict) -> "HashingEmbeddingFunction":
        return cls(dimensions=int(config.get("dimensions", 384)))


class SentenceTransformerEmbeddingFunction:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        return self.model.encode(list(input), normalize_embeddings=True).tolist()

    def embed_query(self, input: str | Sequence[str]) -> list[float] | list[list[float]]:
        return self.model.encode(input, normalize_embeddings=True).tolist()

    def embed_documents(self, input: Sequence[str]) -> list[list[float]]:
        return self(input)

    @staticmethod
    def name() -> str:
        return "macrochef-sentence-transformer"

    def is_legacy(self) -> bool:
        return False

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def get_config(self) -> dict[str, str]:
        return {"model_name": self.model_name}

    @classmethod
    def build_from_config(cls, config: dict) -> "SentenceTransformerEmbeddingFunction":
        return cls(model_name=str(config.get("model_name") or get_settings().embedding_model))


class EmbeddingModelUnavailableError(RuntimeError):
    """Raised when EMBEDDING_PROVIDER=local is explicitly requested but the
    real sentence-transformers model cannot be loaded.

    This is intentionally NOT swallowed into a hashing-embedding fallback:
    a container that silently degrades to hash embeddings against a
    MiniLM-built Chroma index would serve semantically meaningless
    retrieval while still reporting healthy. Callers that want the
    deterministic fallback must opt in explicitly via EMBEDDING_PROVIDER=hash.
    """


@lru_cache(maxsize=1)
def get_embedding_function():
    settings = get_settings()
    provider = settings.embedding_provider.lower()
    if provider == "local":
        try:
            return SentenceTransformerEmbeddingFunction(settings.embedding_model)
        except Exception as exc:
            raise EmbeddingModelUnavailableError(
                f"EMBEDDING_PROVIDER=local was requested but "
                f"'{settings.embedding_model}' could not be loaded: {exc}. "
                "Set EMBEDDING_PROVIDER=hash to explicitly opt into the "
                "deterministic hashing fallback instead."
            ) from exc
    return HashingEmbeddingFunction()
