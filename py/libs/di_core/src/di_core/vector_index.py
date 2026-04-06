"""In-memory vector index — pure-Python cosine similarity search.

A minimal but functional vector store for the prototype. Stores
embedding vectors alongside chunk IDs and supports top-k retrieval
by cosine similarity.

This is deliberately simple: no approximate nearest neighbour (ANN),
no persistence, no sharding.  It exists so the retrieval pipeline
can be designed, tested, and demonstrated end-to-end without an
external vector database.

Future evolution:
  - pgvector for persistent storage
  - FAISS or Annoy for ANN at scale
  - Batch indexing with async embedding calls
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


Vector = list[float]


@dataclass
class IndexEntry:
    """One stored vector with its chunk_id."""

    chunk_id: str
    vector: Vector


@dataclass
class VectorSearchResult:
    """A chunk_id with its cosine similarity score."""

    chunk_id: str
    score: float


class VectorIndex:
    """In-memory brute-force cosine similarity index."""

    def __init__(self) -> None:
        self._entries: list[IndexEntry] = []
        self._id_set: set[str] = set()

    @property
    def size(self) -> int:
        return len(self._entries)

    def add(self, chunk_id: str, vector: Vector) -> None:
        """Add a vector. Skips duplicate chunk_ids silently."""
        if chunk_id in self._id_set:
            return
        self._entries.append(IndexEntry(chunk_id=chunk_id, vector=vector))
        self._id_set.add(chunk_id)

    def add_batch(self, chunk_ids: list[str], vectors: list[Vector]) -> None:
        for cid, vec in zip(chunk_ids, vectors):
            self.add(cid, vec)

    def search(self, query_vector: Vector, top_k: int = 10) -> list[VectorSearchResult]:
        """Return top-k most similar entries by cosine similarity."""
        if not self._entries:
            return []

        scored: list[VectorSearchResult] = []
        for entry in self._entries:
            sim = _cosine_similarity(query_vector, entry.vector)
            scored.append(VectorSearchResult(chunk_id=entry.chunk_id, score=sim))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def clear(self) -> None:
        self._entries.clear()
        self._id_set.clear()


def _cosine_similarity(a: Vector, b: Vector) -> float:
    """Cosine similarity between two vectors (pure Python)."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
