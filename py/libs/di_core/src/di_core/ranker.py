"""Chunk ranking hooks for retrieval.

Provides a common interface for scoring and ranking chunks against a query
without requiring a full vector database.  Three implementations:

  LexicalRanker    — keyword overlap (BM25-inspired term frequency)
  SalienceRanker   — heuristic importance based on position, metadata, section
  EmbeddingRanker  — stub interface for future vector similarity

All rankers implement the ChunkRanker protocol: given a list of chunks
and a query string, return the chunks sorted by relevance with scores.

Future evolution:
  - EmbeddingRanker backed by a real embedding model + vector index
  - Hybrid ranker combining lexical + embedding + salience
  - Learned re-ranker fine-tuned on HITL feedback
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from data_model import DocumentChunk


class RankedChunk:
    """A chunk with an attached relevance score."""

    __slots__ = ("chunk", "score")

    def __init__(self, chunk: DocumentChunk, score: float) -> None:
        self.chunk = chunk
        self.score = score


class ChunkRanker(ABC):
    """Protocol for chunk ranking implementations."""

    @abstractmethod
    def rank(
        self,
        chunks: list[DocumentChunk],
        query: str,
        top_k: int = 10,
    ) -> list[RankedChunk]:
        """Score and sort chunks by relevance to query. Return top_k."""
        ...


class LexicalRanker(ChunkRanker):
    """Simple keyword-overlap scoring (term frequency, case-insensitive).

    Scores each chunk by counting how many unique query terms appear in
    the chunk text, normalized by total query terms.  This is a minimal
    BM25-like signal without IDF or length normalization — good enough for
    an MVP ranking baseline.
    """

    _WORD_SPLIT = re.compile(r"\W+")

    def rank(
        self,
        chunks: list[DocumentChunk],
        query: str,
        top_k: int = 10,
    ) -> list[RankedChunk]:
        query_terms = set(self._WORD_SPLIT.split(query.lower())) - {""}
        if not query_terms:
            return [RankedChunk(c, 0.0) for c in chunks[:top_k]]

        scored: list[RankedChunk] = []
        for chunk in chunks:
            chunk_lower = chunk.text.lower()
            hits = sum(1 for t in query_terms if t in chunk_lower)
            score = hits / len(query_terms)
            scored.append(RankedChunk(chunk, round(score, 4)))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]


class SalienceRanker(ChunkRanker):
    """Heuristic salience scoring using position, metadata, and section.

    Combines multiple lightweight signals that don't require embeddings:
      - Position bonus: early and late chunks score higher (head/tail bias)
      - Section bonus: chunks from known high-value sections score higher
      - Quality penalty: chunks from degraded parse quality score lower
      - Query overlap: basic lexical match (weaker than LexicalRanker)
    """

    HIGH_VALUE_SECTIONS = frozenset({
        "summary", "conclusion", "findings", "recommendations",
        "diagnosis", "treatment plan", "billing summary",
        "damage assessment",
    })

    def rank(
        self,
        chunks: list[DocumentChunk],
        query: str,
        top_k: int = 10,
    ) -> list[RankedChunk]:
        if not chunks:
            return []

        total = len(chunks)
        query_lower = query.lower()
        query_terms = set(re.split(r"\W+", query_lower)) - {""}

        scored: list[RankedChunk] = []
        for chunk in chunks:
            score = 0.0

            position_ratio = chunk.index / max(total - 1, 1)
            score += 0.2 * (1 - abs(2 * position_ratio - 1))
            if chunk.index < 3:
                score += 0.15
            if chunk.index >= total - 3:
                score += 0.10

            if chunk.section_label.lower() in self.HIGH_VALUE_SECTIONS:
                score += 0.25

            if chunk.parse_quality == "degraded":
                score -= 0.1
            elif chunk.parse_quality == "unusable":
                score -= 0.3

            if query_terms:
                chunk_lower = chunk.text.lower()
                hits = sum(1 for t in query_terms if t in chunk_lower)
                score += 0.3 * (hits / len(query_terms))

            scored.append(RankedChunk(chunk, round(max(score, 0.0), 4)))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]


class EmbeddingRanker(ChunkRanker):
    """Stub for future embedding-based retrieval.

    Raises NotImplementedError until an embedding model and vector index
    are integrated.  The interface is defined now so the ranking pipeline
    can be designed around it.
    """

    def rank(
        self,
        chunks: list[DocumentChunk],
        query: str,
        top_k: int = 10,
    ) -> list[RankedChunk]:
        raise NotImplementedError(
            "EmbeddingRanker requires an embedding model and vector index. "
            "Use LexicalRanker or SalienceRanker for now."
        )


def rank_chunks(
    chunks: list[DocumentChunk],
    query: str,
    ranker: ChunkRanker | None = None,
    top_k: int = 10,
) -> list[RankedChunk]:
    """Convenience function: rank chunks with a default ranker.

    Defaults to SalienceRanker which combines position, metadata, and
    keyword signals.
    """
    r = ranker or SalienceRanker()
    return r.rank(chunks, query, top_k=top_k)
