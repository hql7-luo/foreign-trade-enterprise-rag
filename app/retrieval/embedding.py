"""Configurable multilingual neural embeddings with a deterministic fallback."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from app.text import normalize_text, tokenize

DEFAULT_MULTILINGUAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_MULTILINGUAL_DIMENSION = 384


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    dimension: int
    implementation_version: str

    @property
    def fingerprint(self) -> str: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


def embedding_fingerprint(
    provider: str, model: str, dimension: int, implementation_version: str
) -> str:
    payload = json.dumps(
        {
            "provider": provider,
            "model": model,
            "dimension": dimension,
            "implementation_version": implementation_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def physical_collection_name(base_name: str, embedder: EmbeddingProvider) -> str:
    """Isolate incompatible vector configurations in distinct collections."""

    return f"{base_name}__{embedder.fingerprint[:12]}"


class DomainHashEmbedder:
    """Deterministic deterministic feature-hashing fallback used by offline tests."""

    provider_name = "domain_hash"
    model_name = "domain_hash_v1"
    implementation_version = "1"

    def __init__(self, dimension: int = 384, projections: int = 4) -> None:
        self.dimension = dimension
        self.projections = projections

    @property
    def fingerprint(self) -> str:
        return embedding_fingerprint(
            self.provider_name,
            self.model_name,
            self.dimension,
            self.implementation_version,
        )

    def embed_query(self, text: str) -> list[float]:
        return self.embed(text)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]

    def embed(self, text: str) -> list[float]:
        counts = Counter(tokenize(text))
        vector = [0.0] * self.dimension
        for token, count in counts.items():
            weight = 1.0 + math.log(count)
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=32).digest()
            for projection in range(self.projections):
                offset = projection * 4
                bucket = int.from_bytes(digest[offset : offset + 3], "big") % self.dimension
                sign = 1.0 if digest[offset + 3] & 1 else -1.0
                vector[bucket] += sign * weight / math.sqrt(self.projections)
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            return [value / norm for value in vector]
        return vector

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        return self.embed_documents(texts)


class FastEmbedMultilingualEmbedder:
    """ONNX-backed multilingual MiniLM provider for Chinese/English retrieval."""

    provider_name = "fastembed"

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MULTILINGUAL_MODEL,
        dimension: int = DEFAULT_MULTILINGUAL_DIMENSION,
        cache_dir: Path | str = Path("data/private/models"),
    ) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:  # pragma: no cover - exercised without the optional runtime
            raise RuntimeError(
                "fastembed is unavailable; install project dependencies or select domain_hash"
            ) from exc
        self.model_name = model_name
        self.dimension = dimension
        self.implementation_version = (
            f"fastembed-{importlib.metadata.version('fastembed')}-mean-pooling"
        )
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._model = TextEmbedding(
            model_name=model_name,
            cache_dir=str(self.cache_dir),
        )

    @property
    def fingerprint(self) -> str:
        return embedding_fingerprint(
            self.provider_name,
            self.model_name,
            self.dimension,
            self.implementation_version,
        )

    @staticmethod
    def _as_vector(value: object) -> list[float]:
        vector = value.tolist() if hasattr(value, "tolist") else list(value)  # type: ignore[arg-type]
        return [float(item) for item in vector]

    def _validate(self, vector: list[float]) -> list[float]:
        if len(vector) != self.dimension:
            raise ValueError(
                f"Embedding model returned {len(vector)} dimensions; expected {self.dimension}"
            )
        return vector

    def embed_query(self, text: str) -> list[float]:
        vector = next(iter(self._model.query_embed([normalize_text(text)])))
        return self._validate(self._as_vector(vector))

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return [
            self._validate(self._as_vector(vector))
            for vector in self._model.passage_embed([normalize_text(text) for text in texts])
        ]

    def embed(self, text: str) -> list[float]:
        return self.embed_query(text)

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        return self.embed_documents(texts)


def build_embedding_provider(
    *,
    provider: str,
    model_name: str,
    dimension: int,
    cache_dir: Path | str,
    allow_hash_fallback: bool,
) -> EmbeddingProvider:
    normalized = provider.strip().casefold()
    if normalized == "domain_hash":
        return DomainHashEmbedder(dimension)
    if normalized != "fastembed":
        raise ValueError(f"Unsupported embedding provider: {provider}")
    try:
        return FastEmbedMultilingualEmbedder(
            model_name=model_name,
            dimension=dimension,
            cache_dir=cache_dir,
        )
    except (OSError, RuntimeError, ValueError):
        if not allow_hash_fallback:
            raise
        return DomainHashEmbedder(dimension)
