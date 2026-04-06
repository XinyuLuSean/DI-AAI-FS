"""Reranking and hybrid retrieval — combine multiple retrieval signals.

Phase 6C: reranking as a clear stage after initial retrieval.
Phase 6D: hybrid retrieval pipeline combining lexical + vector + reranking.

Reranking techniques:
  ScoreFusionReranker  — Reciprocal Rank Fusion (RRF) across multiple result lists
  CrossEncoderReranker — stub for future cross-encoder reranking

Hybrid pipeline:
  HybridRetriever — lexical + vector + rerank in one call
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from data_model import DocumentChunk

from di_core.ranker import ChunkRanker, LexicalRanker, RankedChunk, SalienceRanker
from di_core.vector_index import VectorIndex, VectorSearchResult

from ai_core.embedding import EmbeddingAdapter


# ═══════════════════════════════════════════════════════════════════════════
# Reranker interface
# ═══════════════════════════════════════════════════════════════════════════


class Reranker(ABC):
    """Interface for reranking a set of retrieval results."""

    @abstractmethod
    def rerank(
        self,
        results: list[RankedChunk],
        query: str,
        top_k: int = 10,
    ) -> list[RankedChunk]:
        """Rerank results, returning top_k in new order."""
        ...


# ═══════════════════════════════════════════════════════════════════════════
# Reciprocal Rank Fusion (RRF)
# ═══════════════════════════════════════════════════════════════════════════


RRF_K = 60  # standard RRF constant


class ScoreFusionReranker(Reranker):
    """Reciprocal Rank Fusion across multiple ranked lists.

    RRF is a well-studied technique that combines multiple rankings
    without needing to normalize scores.  For each chunk, the fused
    score is: sum(1 / (k + rank_in_list_i)) across all lists.

    This reranker is used as the final stage in the hybrid pipeline.
    """

    def __init__(self, k: int = RRF_K) -> None:
        self._k = k

    def rerank(
        self,
        results: list[RankedChunk],
        query: str,
        top_k: int = 10,
    ) -> list[RankedChunk]:
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def fuse(
        self,
        *ranked_lists: list[RankedChunk],
        top_k: int = 10,
    ) -> list[RankedChunk]:
        """Fuse multiple ranked lists using RRF.

        Each list is a separate retrieval signal (lexical, vector, salience).
        Returns a single combined ranking.
        """
        chunk_map: dict[str, DocumentChunk] = {}
        scores: dict[str, float] = {}

        for ranked_list in ranked_lists:
            for rank, rc in enumerate(ranked_list):
                cid = rc.chunk.chunk_id
                chunk_map[cid] = rc.chunk
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (self._k + rank + 1)

        fused = [
            RankedChunk(chunk_map[cid], round(score, 6))
            for cid, score in scores.items()
        ]
        fused.sort(key=lambda r: r.score, reverse=True)
        return fused[:top_k]


class CrossEncoderReranker(Reranker):
    """Stub for future cross-encoder reranking.

    A cross-encoder scores (query, chunk) pairs jointly, giving much
    higher relevance accuracy than independent embeddings.  Requires
    a cross-encoder model (e.g. ms-marco-MiniLM).
    """

    def rerank(
        self,
        results: list[RankedChunk],
        query: str,
        top_k: int = 10,
    ) -> list[RankedChunk]:
        raise NotImplementedError(
            "CrossEncoderReranker requires a cross-encoder model. "
            "Use ScoreFusionReranker for now."
        )


# ═══════════════════════════════════════════════════════════════════════════
# Vector Ranker — implements ChunkRanker using embeddings
# ═══════════════════════════════════════════════════════════════════════════


class VectorRanker(ChunkRanker):
    """Embedding-based chunk ranking using a vector index.

    Replaces the stub EmbeddingRanker from Phase 5. Requires an
    EmbeddingAdapter and a VectorIndex that has been pre-populated
    with chunk embeddings.
    """

    def __init__(
        self,
        adapter: EmbeddingAdapter,
        index: VectorIndex,
    ) -> None:
        self._adapter = adapter
        self._index = index

    def rank(
        self,
        chunks: list[DocumentChunk],
        query: str,
        top_k: int = 10,
    ) -> list[RankedChunk]:
        if not chunks or not query:
            return [RankedChunk(c, 0.0) for c in chunks[:top_k]]

        query_vec = self._adapter.embed_text(query)
        results = self._index.search(query_vec, top_k=top_k)

        chunk_map = {c.chunk_id: c for c in chunks}
        ranked: list[RankedChunk] = []
        for r in results:
            chunk = chunk_map.get(r.chunk_id)
            if chunk:
                ranked.append(RankedChunk(chunk, round(r.score, 4)))

        return ranked


# ═══════════════════════════════════════════════════════════════════════════
# Hybrid Retriever — lexical + vector + rerank
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class HybridRetrievalResult:
    """Detailed output from hybrid retrieval for debugging/inspection."""

    query: str
    lexical_results: list[RankedChunk] = field(default_factory=list)
    vector_results: list[RankedChunk] = field(default_factory=list)
    salience_results: list[RankedChunk] = field(default_factory=list)
    fused_results: list[RankedChunk] = field(default_factory=list)
    pipeline: str = ""


class HybridRetriever:
    """Multi-signal retrieval pipeline: lexical + vector + salience → RRF fusion.

    This is the recommended retrieval approach for Phase 6. It combines:
      - LexicalRanker: keyword overlap (captures exact term matches)
      - VectorRanker: semantic similarity (captures meaning)
      - SalienceRanker: position + metadata + section signals

    Results are fused using Reciprocal Rank Fusion (RRF), which doesn't
    require score normalisation across different rankers.
    """

    def __init__(
        self,
        adapter: EmbeddingAdapter,
        index: VectorIndex,
    ) -> None:
        self._lexical = LexicalRanker()
        self._vector = VectorRanker(adapter, index)
        self._salience = SalienceRanker()
        self._fuser = ScoreFusionReranker()

    def retrieve(
        self,
        chunks: list[DocumentChunk],
        query: str,
        top_k: int = 10,
        candidate_multiplier: int = 3,
    ) -> HybridRetrievalResult:
        """Run the full hybrid pipeline and return detailed results.

        candidate_multiplier controls how many candidates each sub-ranker
        retrieves before fusion (more candidates = better recall, more cost).
        """
        candidate_k = min(top_k * candidate_multiplier, len(chunks))

        lex = self._lexical.rank(chunks, query, top_k=candidate_k)
        vec = self._vector.rank(chunks, query, top_k=candidate_k)
        sal = self._salience.rank(chunks, query, top_k=candidate_k)

        fused = self._fuser.fuse(lex, vec, sal, top_k=top_k)

        return HybridRetrievalResult(
            query=query,
            lexical_results=lex[:top_k],
            vector_results=vec[:top_k],
            salience_results=sal[:top_k],
            fused_results=fused,
            pipeline="lexical+vector+salience→rrf",
        )

    def index_chunks(self, chunks: list[DocumentChunk]) -> int:
        """Embed and index a list of chunks. Returns count indexed."""
        texts = [c.text for c in chunks]
        ids = [c.chunk_id for c in chunks]
        vectors = self._vector._adapter.embed_batch(texts)
        self._vector._index.add_batch(ids, vectors)
        return len(texts)
