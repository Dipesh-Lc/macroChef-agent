import hashlib
import math
from collections.abc import Sequence
from functools import lru_cache

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


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


@lru_cache(maxsize=1)
def get_embedding_function():
    settings = get_settings()
    if settings.embedding_provider.lower() == "local":
        try:
            return SentenceTransformerEmbeddingFunction(settings.embedding_model)
        except Exception as exc:  # pragma: no cover - depends on local model availability
            logger.warning("Falling back to deterministic hashing embeddings: %s", exc)
    return HashingEmbeddingFunction()
