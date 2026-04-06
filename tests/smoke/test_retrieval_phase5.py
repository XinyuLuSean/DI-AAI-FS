"""Phase 5 tests — retrieval foundations for Applied AI.

Tests cover:
  - QUERY_RANKED chunk selection strategy
  - Query-ranked vs positional selection (the core Phase 5 thesis)
  - Retrieval comparison function
  - Comparison report structure and recommendation
  - Fallback when no query provided
  - API endpoint for retrieval comparison
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from data_model import (
    ChunkSelectionStrategy,
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentStatus,
    DocumentType,
    ParseMeta,
    ParseQuality,
    RoutingResult,
)
from di_core import (
    compare_strategies,
    enrich_chunks_for_retrieval,
)
from di_core.chunk_selector import select_chunks_for_llm

from py_api.main import app


def _make_long_doc() -> Document:
    """Build a 10-chunk medical document with varied content.

    Key layout:
      chunks 0-2: administrative header (dates, names, addresses)
      chunks 3-4: medical history (hypertension, diabetes)
      chunk 5:    diagnosis (herniated disc L4-L5, MRI findings)
      chunks 6-7: treatment plan (physical therapy, medications)
      chunks 8-9: billing summary (costs, totals)
    """
    texts = [
        "ADMINISTRATIVE INFORMATION\nPatient: James Wilson\nDOB: 1975-03-22\nMRN: 2024-08-001",
        "REFERRAL DETAILS\nReferred by Dr. Sarah Chen on August 10, 2024\nReason: chronic lower back pain",
        "INSURANCE VERIFICATION\nProvider: Blue Cross Blue Shield\nPolicy: BC-2024-4412\nAuthorized for evaluation",
        "MEDICAL HISTORY\nPatient has a 15-year history of hypertension managed with lisinopril.\nDiabetes Type 2 diagnosed in 2018.",
        "PRIOR TREATMENTS\nPhysical therapy in 2022 (6 sessions, partial improvement)\nEpidural injection March 2023 (temporary relief)",
        "DIAGNOSIS AND FINDINGS\nMRI dated August 12, 2024 reveals herniated disc at L4-L5.\nModerate central canal stenosis with nerve root compression.\nPatient reports radiating pain down left leg (sciatica).",
        "TREATMENT PLAN\n1. Physical therapy 3x/week for 8 weeks\n2. Gabapentin 300mg TID for neuropathic pain\n3. Follow-up MRI in 12 weeks",
        "MEDICATIONS PRESCRIBED\nGabapentin 300mg - three times daily\nNaproxen 500mg - twice daily as needed\nContinue lisinopril and metformin",
        "BILLING SUMMARY\nMRI lumbar spine: $1,450.00\nOffice consultation: $375.00\nTotal: $1,825.00",
        "FOLLOW-UP SCHEDULE\nWeek 4: phone check-in\nWeek 8: in-person evaluation\nWeek 12: repeat MRI and reassessment",
    ]
    pages = [
        DocumentPage(page_number=i + 1, text=t, char_count=len(t))
        for i, t in enumerate(texts)
    ]
    chunks = [
        DocumentChunk(
            document_id="longdoc",
            index=i,
            text=t,
            page_numbers=[i + 1],
            char_start=sum(len(texts[j]) for j in range(i)),
            char_end=sum(len(texts[j]) for j in range(i + 1)),
            token_estimate=len(t.split()),
        )
        for i, t in enumerate(texts)
    ]
    doc = Document(
        filename="medical_record_detailed.pdf",
        pages=pages,
        chunks=chunks,
        status=DocumentStatus.CHUNKED,
        parse_meta=ParseMeta(
            page_count=10,
            total_chars=sum(len(t) for t in texts),
            quality=ParseQuality.GOOD,
        ),
        routing=RoutingResult(
            predicted_type=DocumentType.MEDICAL,
            confidence=0.9,
            is_fallback=False,
        ),
    )
    return enrich_chunks_for_retrieval(doc)


# ═══════════════════════════════════════════════════════════════════════════
# Test: QUERY_RANKED chunk selection
# ═══════════════════════════════════════════════════════════════════════════


class TestQueryRankedSelection:
    def test_query_ranked_selects_relevant_chunks(self):
        doc = _make_long_doc()
        selected, meta = select_chunks_for_llm(
            doc, max_chunks=3,
            strategy=ChunkSelectionStrategy.QUERY_RANKED,
            query="diagnosis herniated disc MRI findings",
        )
        indices = {c.index for c in selected}
        assert 5 in indices, "Diagnosis chunk (idx 5) should be selected for a diagnosis query"

    def test_query_ranked_differs_from_head(self):
        doc = _make_long_doc()
        head_selected, _ = select_chunks_for_llm(
            doc, max_chunks=3, strategy=ChunkSelectionStrategy.HEAD,
        )
        ranked_selected, _ = select_chunks_for_llm(
            doc, max_chunks=3,
            strategy=ChunkSelectionStrategy.QUERY_RANKED,
            query="diagnosis herniated disc MRI findings",
        )
        head_ids = {c.chunk_id for c in head_selected}
        ranked_ids = {c.chunk_id for c in ranked_selected}
        assert head_ids != ranked_ids, (
            "For a diagnosis query on a 10-chunk doc, query_ranked should "
            "select different chunks than naive head (which picks admin headers)"
        )

    def test_query_ranked_meta_has_warning(self):
        doc = _make_long_doc()
        _, meta = select_chunks_for_llm(
            doc, max_chunks=3,
            strategy=ChunkSelectionStrategy.QUERY_RANKED,
            query="billing costs",
        )
        assert any("Query-ranked" in w for w in meta.warnings)

    def test_query_ranked_falls_back_without_query(self):
        doc = _make_long_doc()
        selected, meta = select_chunks_for_llm(
            doc, max_chunks=3,
            strategy=ChunkSelectionStrategy.QUERY_RANKED,
        )
        assert any("fell back" in w.lower() for w in meta.warnings)

    def test_query_ranked_billing_query_finds_billing(self):
        doc = _make_long_doc()
        selected, _ = select_chunks_for_llm(
            doc, max_chunks=3,
            strategy=ChunkSelectionStrategy.QUERY_RANKED,
            query="billing total cost amount",
        )
        indices = {c.index for c in selected}
        assert 8 in indices, "Billing chunk (idx 8) should be selected for billing query"


# ═══════════════════════════════════════════════════════════════════════════
# Test: Retrieval comparison
# ═══════════════════════════════════════════════════════════════════════════


class TestRetrievalComparison:
    def test_comparison_returns_all_strategies(self):
        doc = _make_long_doc()
        report = compare_strategies(doc, query="diagnosis MRI", max_chunks=3)
        strategy_names = {s.strategy for s in report.strategies}
        assert "head" in strategy_names
        assert "query_ranked" in strategy_names
        assert len(report.strategies) >= 4

    def test_comparison_has_overlap_matrix(self):
        doc = _make_long_doc()
        report = compare_strategies(doc, query="treatment plan", max_chunks=3)
        assert "head" in report.overlap_matrix
        assert "query_ranked" in report.overlap_matrix
        for strat in report.overlap_matrix:
            assert report.overlap_matrix[strat][strat] == 3

    def test_comparison_identifies_unique_chunks(self):
        doc = _make_long_doc()
        report = compare_strategies(doc, query="diagnosis MRI herniated", max_chunks=3)
        has_any_unique = any(len(ids) > 0 for ids in report.unique_to.values())
        assert has_any_unique, "At least one strategy should have unique chunks"

    def test_comparison_has_recommendation(self):
        doc = _make_long_doc()
        report = compare_strategies(doc, query="billing insurance cost", max_chunks=3)
        assert len(report.recommendation) > 0

    def test_comparison_no_query_gives_generic_recommendation(self):
        doc = _make_long_doc()
        report = compare_strategies(doc, query="", max_chunks=3)
        assert "no query" in report.recommendation.lower()

    def test_comparison_relevance_scores_populated(self):
        doc = _make_long_doc()
        report = compare_strategies(doc, query="diagnosis", max_chunks=3)
        for sr in report.strategies:
            for chunk in sr.chunks:
                assert isinstance(chunk.relevance_score, float)

    def test_query_ranked_has_higher_avg_relevance(self):
        """The core Phase 5 thesis: retrieval beats naive head selection."""
        doc = _make_long_doc()
        report = compare_strategies(
            doc, query="diagnosis herniated disc MRI nerve", max_chunks=3,
        )
        head = next(s for s in report.strategies if s.strategy == "head")
        ranked = next(s for s in report.strategies if s.strategy == "query_ranked")

        head_avg = sum(c.relevance_score for c in head.chunks) / len(head.chunks)
        ranked_avg = sum(c.relevance_score for c in ranked.chunks) / len(ranked.chunks)

        assert ranked_avg >= head_avg, (
            f"query_ranked (avg {ranked_avg:.3f}) should have at least as high "
            f"relevance as head (avg {head_avg:.3f}) for a specific query"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Test: API endpoint
# ═══════════════════════════════════════════════════════════════════════════


class TestRetrievalCompareEndpoint:
    def setup_method(self):
        self.client = TestClient(app)

    def _upload(self, filename: str = "medical_record.txt") -> dict:
        from pathlib import Path
        fixture = Path(__file__).resolve().parents[2] / "data" / "fixtures" / filename
        with open(fixture, "rb") as f:
            resp = self.client.post(
                "/documents/upload",
                files={"file": (filename, f, "text/plain")},
            )
        assert resp.status_code == 200
        return resp.json()

    def test_compare_endpoint_returns_report(self):
        data = self._upload()
        doc_id = data["id"]

        resp = self.client.post(
            f"/documents/{doc_id}/retrieval-compare",
            json={"query": "patient diagnosis", "max_chunks": 3},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["document_id"] == doc_id
        assert "strategies" in result
        assert "recommendation" in result
        assert len(result["strategies"]) >= 4

    def test_compare_endpoint_not_found(self):
        resp = self.client.post(
            "/documents/nonexistent/retrieval-compare",
            json={"query": "test"},
        )
        assert resp.status_code == 404
