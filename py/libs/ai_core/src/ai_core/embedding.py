"""Embedding adapter — isolates all embedding-provider logic.

Mirrors the LLMAdapter pattern: provider-specific details stay here,
the rest of the codebase works with plain float vectors.

Implementations:
  LiteLLMEmbeddingAdapter  — real embeddings via litellm (OpenAI, Cohere, etc.)
  HashEmbeddingAdapter     — deterministic hash-based pseudo-embeddings for
                             testing without API keys or network access

Usage:
    adapter = LiteLLMEmbeddingAdapter()       # needs OPENAI_API_KEY
    adapter = HashEmbeddingAdapter(dim=64)     # zero-config, deterministic

    vec = adapter.embed_text("hello world")    # list[float]
    vecs = adapter.embed_batch(["a", "b"])     # list[list[float]]
"""

from __future__ import annotations

import hashlib
import math
import os
import struct
from abc import ABC, abstractmethod

Vector = list[float]


class EmbeddingAdapter(ABC):
    """Interface for embedding providers.

    Every implementation must return fixed-dimension float vectors.
    The dimension property lets downstream code allocate storage correctly.
    """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the output vectors."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model identifier for logging and audit."""
        ...

    @abstractmethod
    def embed_text(self, text: str) -> Vector:
        """Embed a single text string."""
        ...

    def embed_batch(self, texts: list[str]) -> list[Vector]:
        """Embed a batch of texts. Override for providers with batch APIs."""
        return [self.embed_text(t) for t in texts]


# ── LiteLLM implementation (real embeddings) ──────────────────────────────


class LiteLLMEmbeddingAdapter(EmbeddingAdapter):
    """Real embeddings via litellm — supports OpenAI, Cohere, etc.

    Requires an API key for the chosen provider (e.g. OPENAI_API_KEY).
    """

    _DIMENSION_MAP = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, model: str | None = None) -> None:
        import litellm  # noqa: F811 — deferred import
        self._litellm = litellm
        self._model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self._dim = self._DIMENSION_MAP.get(self._model, 1536)

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model

    def embed_text(self, text: str) -> Vector:
        response = self._litellm.embedding(
            model=self._model,
            input=[text],
        )
        return response.data[0]["embedding"]

    def embed_batch(self, texts: list[str]) -> list[Vector]:
        if not texts:
            return []
        response = self._litellm.embedding(
            model=self._model,
            input=texts,
        )
        return [item["embedding"] for item in response.data]


# ── Hash-based adapter (deterministic, no API keys) ──────────────────────


class HashEmbeddingAdapter(EmbeddingAdapter):
    """Deterministic pseudo-embeddings from text hashing.

    Produces consistent vectors for the same input text, enabling
    reproducible tests without network access.  NOT suitable for
    real semantic similarity — only for testing pipeline mechanics.

    Vectors are unit-normalised so cosine similarity is meaningful
    (i.e., similar text will NOT produce similar vectors, but the
    math works correctly for pipeline testing).
    """

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return f"hash-{self._dim}d"

    def embed_text(self, text: str) -> Vector:
        return _hash_to_vector(text, self._dim)


def _hash_to_vector(text: str, dim: int) -> Vector:
    """Convert text to a deterministic unit-length float vector.

    Uses unsigned ints from the hash, converting to [-1, 1] range to avoid
    inf/nan that struct float unpacking can produce from arbitrary bytes.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    needed_bytes = dim * 4
    expanded = digest
    while len(expanded) < needed_bytes:
        expanded += hashlib.sha256(expanded).digest()

    ints = struct.unpack(f">{dim}I", expanded[:needed_bytes])
    floats = [(x / 2_147_483_648.0) - 1.0 for x in ints]
    norm = math.sqrt(sum(x * x for x in floats)) or 1.0
    return [x / norm for x in floats]
