"""Phase 6 tests — Embeddings, Vector Retrieval, and Reranking.

Covers:
  Module 6A: Embedding adapter interface (HashEmbeddingAdapter)
  Module 6B: In-memory vector index (VectorIndex)
  Module 6C: Reranking (ScoreFusionReranker, RRF)
  Module 6D: Hybrid retriever + extended pipeline comparison
"""

from __future__ import annotations

import math

import pytest

from data_model import Document, DocumentChunk

from ai_core.embedding import (
    EmbeddingAdapter,
    HashEmbeddingAdapter,
    _hash_to_vector,
)
from di_core.vector_index import VectorIndex, VectorSearchResult, _cosine_similarity
from di_core.ranker import EmbeddingRanker, LexicalRanker, RankedChunk, SalienceRanker
from di_core.reranker import (
    CrossEncoderReranker,
    HybridRetriever,
    HybridRetrievalResult,
    ScoreFusionReranker,
    VectorRanker,
)
from di_core.retrieval_compare import compare_with_hybrid


# ═══════════════════════════════════════════════════════════════════════════
# Test fixtures
# ═══════════════════════════════════════════════════════════════════════════


def _make_chunks(n: int = 10) -> list[DocumentChunk]:
    texts = [
        "The patient presented with acute chest pain and shortness of breath.",
        "Blood pressure was measured at 140/90 mmHg, heart rate 88 bpm.",
        "Electrocardiogram showed ST-elevation in leads V1-V4, suggesting MI.",
        "Troponin levels were elevated at 2.5 ng/mL, confirming myocardial injury.",
        "Patient was started on dual antiplatelet therapy and IV heparin.",
        "Echocardiography revealed reduced left ventricular ejection fraction of 35%.",
        "Coronary angiography demonstrated 90% stenosis of the LAD artery.",
        "PCI was performed with drug-eluting stent placement in the LAD.",
        "Post-procedure the patient was hemodynamically stable with resolved chest pain.",
        "Discharge plan includes aspirin, clopidogrel, atorvastatin, and cardiac rehab.",
    ]
    return [
        DocumentChunk(
            chunk_id=f"c{i}",
            document_id="doc-phase6",
            index=i,
            text=texts[i] if i < len(texts) else f"Chunk {i} content.",
            page_numbers=[i // 3 + 1],
            section_label=["presentation", "vitals", "ecg", "labs", "treatment",
                           "imaging", "angiography", "intervention", "postop", "discharge"][i],
            char_start=0,
            char_end=len(texts[i]) if i < len(texts) else 20,
        )
        for i in range(n)
    ]


def _make_doc(n_chunks: int = 10) -> Document:
    return Document(
        id="doc-phase6",
        filename="cardiac_case.md",
        raw_text=" ".join(c.text for c in _make_chunks(n_chunks)),
        chunks=_make_chunks(n_chunks),
    )


@pytest.fixture
def adapter():
    return HashEmbeddingAdapter(dim=64)


@pytest.fixture
def chunks():
    return _make_chunks()


@pytest.fixture
def doc():
    return _make_doc()


# ═══════════════════════════════════════════════════════════════════════════
# Module 6A: Embedding adapter
# ═══════════════════════════════════════════════════════════════════════════


class TestEmbeddingAdapter:
    def test_hash_adapter_is_embedding_adapter(self, adapter):
        assert isinstance(adapter, EmbeddingAdapter)

    def test_dimension(self, adapter):
        assert adapter.dimension == 64

    def test_model_name(self, adapter):
        assert adapter.model_name == "hash-64d"

    def test_embed_text_returns_vector(self, adapter):
        vec = adapter.embed_text("hello world")
        assert isinstance(vec, list)
        assert len(vec) == 64
        assert all(isinstance(x, float) for x in vec)

    def test_embed_text_is_deterministic(self, adapter):
        v1 = adapter.embed_text("test input")
        v2 = adapter.embed_text("test input")
        assert v1 == v2

    def test_embed_text_different_inputs_differ(self, adapter):
        v1 = adapter.embed_text("input A")
        v2 = adapter.embed_text("input B")
        assert v1 != v2

    def test_embed_text_unit_normalised(self, adapter):
        vec = adapter.embed_text("normalisation test")
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-6

    def test_embed_batch(self, adapter):
        vecs = adapter.embed_batch(["a", "b", "c"])
        assert len(vecs) == 3
        assert all(len(v) == 64 for v in vecs)

    def test_embed_batch_empty(self, adapter):
        assert adapter.embed_batch([]) == []

    def test_hash_to_vector_different_dims(self):
        v16 = _hash_to_vector("test", 16)
        v128 = _hash_to_vector("test", 128)
        assert len(v16) == 16
        assert len(v128) == 128


# ═══════════════════════════════════════════════════════════════════════════
# Module 6B: Vector index
# ═══════════════════════════════════════════════════════════════════════════


class TestVectorIndex:
    def test_empty_index(self):
        idx = VectorIndex()
        assert idx.size == 0
        assert idx.search([1.0, 0.0], top_k=5) == []

    def test_add_and_search(self, adapter):
        idx = VectorIndex()
        idx.add("chunk_a", adapter.embed_text("cardiology"))
        idx.add("chunk_b", adapter.embed_text("dermatology"))
        assert idx.size == 2

        query_vec = adapter.embed_text("heart disease cardiology")
        results = idx.search(query_vec, top_k=2)
        assert len(results) == 2
        assert all(isinstance(r, VectorSearchResult) for r in results)
        assert all(r.chunk_id in ("chunk_a", "chunk_b") for r in results)

    def test_duplicate_ids_skipped(self, adapter):
        idx = VectorIndex()
        idx.add("dup", adapter.embed_text("text1"))
        idx.add("dup", adapter.embed_text("text2"))
        assert idx.size == 1

    def test_add_batch(self, adapter):
        idx = VectorIndex()
        idx.add_batch(
            ["a", "b", "c"],
            [adapter.embed_text(t) for t in ["aa", "bb", "cc"]],
        )
        assert idx.size == 3

    def test_clear(self, adapter):
        idx = VectorIndex()
        idx.add("x", adapter.embed_text("hello"))
        idx.clear()
        assert idx.size == 0

    def test_top_k_respected(self, adapter):
        idx = VectorIndex()
        for i in range(20):
            idx.add(f"c{i}", adapter.embed_text(f"chunk {i}"))
        results = idx.search(adapter.embed_text("query"), top_k=5)
        assert len(results) == 5

    def test_scores_sorted_descending(self, adapter):
        idx = VectorIndex()
        for i in range(10):
            idx.add(f"c{i}", adapter.embed_text(f"text {i}"))
        results = idx.search(adapter.embed_text("query"), top_k=10)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        assert abs(_cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-6

    def test_opposite_vectors(self):
        assert abs(_cosine_similarity([1.0, 0.0], [-1.0, 0.0]) + 1.0) < 1e-6

    def test_zero_vector(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_different_lengths(self):
        assert _cosine_similarity([1.0], [1.0, 2.0]) == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Module 6C: Reranking
# ═══════════════════════════════════════════════════════════════════════════


class TestScoreFusionReranker:
    def test_fuse_single_list(self, chunks):
        ranked = [RankedChunk(c, 1.0 / (i + 1)) for i, c in enumerate(chunks[:5])]
        fuser = ScoreFusionReranker()
        fused = fuser.fuse(ranked, top_k=3)
        assert len(fused) == 3

    def test_fuse_multiple_lists_combines_signals(self, chunks):
        list_a = [RankedChunk(chunks[0], 1.0), RankedChunk(chunks[1], 0.8)]
        list_b = [RankedChunk(chunks[1], 1.0), RankedChunk(chunks[2], 0.8)]
        list_c = [RankedChunk(chunks[0], 1.0), RankedChunk(chunks[2], 0.8)]

        fuser = ScoreFusionReranker()
        fused = fuser.fuse(list_a, list_b, list_c, top_k=3)
        assert len(fused) == 3
        fused_ids = [r.chunk.chunk_id for r in fused]
        assert "c0" in fused_ids
        assert "c1" in fused_ids
        assert "c2" in fused_ids

    def test_chunk_appearing_in_all_lists_gets_highest_score(self, chunks):
        shared_chunk = chunks[0]
        list_a = [RankedChunk(shared_chunk, 1.0), RankedChunk(chunks[1], 0.5)]
        list_b = [RankedChunk(shared_chunk, 1.0), RankedChunk(chunks[2], 0.5)]
        list_c = [RankedChunk(shared_chunk, 1.0), RankedChunk(chunks[3], 0.5)]

        fuser = ScoreFusionReranker()
        fused = fuser.fuse(list_a, list_b, list_c, top_k=5)
        assert fused[0].chunk.chunk_id == "c0"

    def test_rrf_scores_are_rank_based(self, chunks):
        """RRF uses rank position, not the original score values."""
        fuser = ScoreFusionReranker(k=60)
        list_a = [RankedChunk(chunks[i], 100 - i) for i in range(5)]
        fused = fuser.fuse(list_a, top_k=5)
        expected_first = 1.0 / (60 + 1)
        assert abs(fused[0].score - round(expected_first, 6)) < 1e-6

    def test_rerank_returns_top_k(self, chunks):
        ranked = [RankedChunk(c, float(len(chunks) - i)) for i, c in enumerate(chunks)]
        fuser = ScoreFusionReranker()
        result = fuser.rerank(ranked, "query", top_k=3)
        assert len(result) == 3

    def test_cross_encoder_not_implemented(self, chunks):
        reranker = CrossEncoderReranker()
        with pytest.raises(NotImplementedError):
            reranker.rerank([RankedChunk(chunks[0], 1.0)], "query")


# ═══════════════════════════════════════════════════════════════════════════
# VectorRanker (embedding-based ChunkRanker)
# ═══════════════════════════════════════════════════════════════════════════


class TestVectorRanker:
    def test_ranks_chunks(self, adapter, chunks):
        idx = VectorIndex()
        vecs = adapter.embed_batch([c.text for c in chunks])
        idx.add_batch([c.chunk_id for c in chunks], vecs)

        ranker = VectorRanker(adapter, idx)
        ranked = ranker.rank(chunks, "chest pain treatment", top_k=3)
        assert len(ranked) == 3
        assert all(isinstance(r, RankedChunk) for r in ranked)

    def test_empty_query(self, adapter, chunks):
        idx = VectorIndex()
        ranker = VectorRanker(adapter, idx)
        ranked = ranker.rank(chunks, "", top_k=3)
        assert len(ranked) == 3
        assert all(r.score == 0.0 for r in ranked)

    def test_embedding_ranker_delegates(self, adapter, chunks):
        """EmbeddingRanker should now delegate to VectorRanker when configured."""
        idx = VectorIndex()
        vecs = adapter.embed_batch([c.text for c in chunks])
        idx.add_batch([c.chunk_id for c in chunks], vecs)

        ranker = EmbeddingRanker(adapter=adapter, index=idx)
        ranked = ranker.rank(chunks, "cardiac intervention", top_k=5)
        assert len(ranked) == 5

    def test_embedding_ranker_without_config_raises(self):
        ranker = EmbeddingRanker()
        with pytest.raises(NotImplementedError):
            ranker.rank([], "query")


# ═══════════════════════════════════════════════════════════════════════════
# Module 6D: Hybrid retriever
# ═══════════════════════════════════════════════════════════════════════════


class TestHybridRetriever:
    def test_full_pipeline(self, adapter, chunks):
        idx = VectorIndex()
        retriever = HybridRetriever(adapter, idx)
        retriever.index_chunks(chunks)
        assert idx.size == len(chunks)

        result = retriever.retrieve(chunks, "chest pain ECG", top_k=5)
        assert isinstance(result, HybridRetrievalResult)
        assert result.pipeline == "lexical+vector+salience→rrf"
        assert len(result.fused_results) <= 5
        assert len(result.lexical_results) > 0
        assert len(result.vector_results) > 0
        assert len(result.salience_results) > 0

    def test_retrieve_returns_ranked_chunks(self, adapter, chunks):
        idx = VectorIndex()
        retriever = HybridRetriever(adapter, idx)
        retriever.index_chunks(chunks)
        result = retriever.retrieve(chunks, "troponin elevated", top_k=3)
        assert all(isinstance(r, RankedChunk) for r in result.fused_results)

    def test_index_chunks_returns_count(self, adapter, chunks):
        idx = VectorIndex()
        retriever = HybridRetriever(adapter, idx)
        count = retriever.index_chunks(chunks)
        assert count == len(chunks)

    def test_fused_results_are_deduplicated(self, adapter, chunks):
        idx = VectorIndex()
        retriever = HybridRetriever(adapter, idx)
        retriever.index_chunks(chunks)
        result = retriever.retrieve(chunks, "heparin antiplatelet", top_k=5)
        chunk_ids = [r.chunk.chunk_id for r in result.fused_results]
        assert len(chunk_ids) == len(set(chunk_ids))


# ═══════════════════════════════════════════════════════════════════════════
# Extended comparison (compare_with_hybrid)
# ═══════════════════════════════════════════════════════════════════════════


class TestCompareWithHybrid:
    def test_includes_vector_and_hybrid(self, doc):
        report = compare_with_hybrid(doc, query="chest pain treatment", max_chunks=3)
        strat_names = [s.strategy for s in report.strategies]
        assert "vector" in strat_names
        assert "hybrid" in strat_names

    def test_includes_all_base_strategies(self, doc):
        report = compare_with_hybrid(doc, query="cardiac", max_chunks=3)
        strat_names = set(s.strategy for s in report.strategies)
        assert strat_names >= {"head", "head_tail", "query_ranked", "vector", "hybrid"}

    def test_overlap_matrix_includes_new_strategies(self, doc):
        report = compare_with_hybrid(doc, query="cardiac", max_chunks=3)
        assert "vector" in report.overlap_matrix
        assert "hybrid" in report.overlap_matrix

    def test_recommendation_mentions_hybrid(self, doc):
        report = compare_with_hybrid(doc, query="coronary stent", max_chunks=3)
        assert "Hybrid" in report.recommendation or "hybrid" in report.recommendation

    def test_vector_strategy_chunks_have_data(self, doc):
        report = compare_with_hybrid(doc, query="treatment", max_chunks=5)
        vector_sr = next(s for s in report.strategies if s.strategy == "vector")
        assert len(vector_sr.chunks) > 0
        assert all(c.chunk_id for c in vector_sr.chunks)

    def test_hybrid_strategy_chunks_have_data(self, doc):
        report = compare_with_hybrid(doc, query="ECG findings", max_chunks=5)
        hybrid_sr = next(s for s in report.strategies if s.strategy == "hybrid")
        assert len(hybrid_sr.chunks) > 0


# ═══════════════════════════════════════════════════════════════════════════
# API endpoint
# ═══════════════════════════════════════════════════════════════════════════


class TestRetrievalCompareEndpoint:
    """Ensure the API endpoint accepts include_hybrid flag."""

    def test_compare_request_schema_has_hybrid_field(self):
        import importlib
        docs_module = importlib.import_module("py_api.api.documents")
        schema = docs_module.CompareRequest.model_json_schema()
        assert "include_hybrid" in schema["properties"]
        assert schema["properties"]["include_hybrid"]["default"] is False
