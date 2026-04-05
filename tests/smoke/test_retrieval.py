"""Smoke tests: Phase 7 — retrieval-oriented document intelligence.

Covers:
  Module 7A — retrieval metadata on chunks
  Module 7B — chunk ranking (lexical, salience)
  Module 7C — citation-ready evidence packaging
  Module 7D — section detection

Run with:  uv run pytest tests/smoke/test_retrieval.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data_model import (
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentStatus,
    DocumentType,
    ParseMeta,
    ParseQuality,
    RoutingResult,
    SectionLabel,
)
from di_core import (
    LexicalRanker,
    SalienceRanker,
    detect_sections,
    enrich_chunks_for_retrieval,
    package_evidence,
    rank_chunks,
)
from di_core.section_detector import section_label_for_chunk

from py_api.main import app

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def fixture_path(name: str) -> Path:
    direct = FIXTURES / name
    if direct.exists():
        return direct
    matches = sorted(FIXTURES.rglob(name))
    if not matches:
        raise FileNotFoundError(f"Fixture not found: {name}")
    if len(matches) > 1:
        raise ValueError(f"Fixture name is ambiguous: {name} -> {matches}")
    return matches[0]


def _upload(client: TestClient, filename: str = "sample.txt", **params: object) -> dict:
    with open(fixture_path(filename), "rb") as f:
        resp = client.post(
            "/documents/upload",
            files={"file": (filename, f, "text/plain")},
            params=params,
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _make_structured_doc() -> Document:
    """Build a document with clear headings for section detection."""
    pages = [
        DocumentPage(
            page_number=1,
            text=(
                "MEDICAL HISTORY\n\n"
                "Patient has a history of hypertension and diabetes.\n"
                "Previous surgeries include appendectomy in 2015.\n"
            ),
            char_count=120,
        ),
        DocumentPage(
            page_number=2,
            text=(
                "DIAGNOSIS\n\n"
                "The patient presents with acute lower back pain.\n"
                "MRI shows herniated disc at L4-L5.\n"
            ),
            char_count=100,
        ),
        DocumentPage(
            page_number=3,
            text=(
                "TREATMENT PLAN\n\n"
                "1. Physical therapy 3x per week for 6 weeks\n"
                "2. NSAIDs for pain management\n"
                "3. Follow-up in 4 weeks\n"
            ),
            char_count=120,
        ),
        DocumentPage(
            page_number=4,
            text=(
                "BILLING SUMMARY\n\n"
                "MRI scan: $1,200.00\n"
                "Consultation: $350.00\n"
                "Total Due: $1,550.00\n"
            ),
            char_count=90,
        ),
    ]
    chunks = [
        DocumentChunk(
            document_id="test",
            index=i,
            text=p.text,
            page_numbers=[p.page_number],
            char_start=i * 200,
            char_end=(i + 1) * 200,
            token_estimate=30,
        )
        for i, p in enumerate(pages)
    ]
    return Document(
        filename="medical_record.pdf",
        pages=pages,
        chunks=chunks,
        status=DocumentStatus.CHUNKED,
        parse_meta=ParseMeta(
            page_count=4,
            total_chars=430,
            quality=ParseQuality.GOOD,
        ),
        routing=RoutingResult(
            predicted_type=DocumentType.MEDICAL,
            confidence=0.9,
            is_fallback=False,
        ),
    )


# ── Module 7D: Section detection ────────────────────────────────────────


class TestSectionDetection:
    def test_detects_headings(self) -> None:
        doc = _make_structured_doc()
        sections = detect_sections(doc)
        labels = [s.label for s in sections]
        assert "Medical History" in labels
        assert "Diagnosis" in labels
        assert "Treatment Plan" in labels
        assert "Billing Summary" in labels

    def test_sections_have_page_ranges(self) -> None:
        doc = _make_structured_doc()
        sections = detect_sections(doc)
        for section in sections:
            assert section.page_start >= 1
            assert section.page_end >= section.page_start
            assert section.detection_method != ""

    def test_section_label_for_chunk(self) -> None:
        doc = _make_structured_doc()
        sections = detect_sections(doc)
        label = section_label_for_chunk(sections, [2], 200)
        assert label != ""

    def test_no_sections_in_unstructured_text(self) -> None:
        doc = Document(
            filename="plain.txt",
            pages=[DocumentPage(page_number=1, text="just some text here.", char_count=20)],
            status=DocumentStatus.PARSED,
        )
        sections = detect_sections(doc)
        assert len(sections) == 0


# ── Module 7A: Retrieval metadata enrichment ────────────────────────────


class TestRetrievalEnrichment:
    def test_enrichment_populates_metadata(self) -> None:
        doc = _make_structured_doc()
        doc = enrich_chunks_for_retrieval(doc)

        for chunk in doc.chunks:
            assert chunk.doc_type == "medical"
            assert chunk.source_filename == "medical_record.pdf"
            assert chunk.parse_quality == "good"

    def test_enrichment_assigns_section_labels(self) -> None:
        doc = _make_structured_doc()
        doc = enrich_chunks_for_retrieval(doc)

        labels = [c.section_label for c in doc.chunks]
        assert any(l != "" for l in labels)

    def test_enrichment_stores_sections_on_document(self) -> None:
        doc = _make_structured_doc()
        doc = enrich_chunks_for_retrieval(doc)
        assert len(doc.sections) > 0

    def test_upload_enriches_chunks(self) -> None:
        client = TestClient(app)
        data = _upload(client, "medical_record.txt")
        for chunk in data["chunks"]:
            assert "doc_type" in chunk
            assert "source_filename" in chunk
            assert chunk["source_filename"] == "medical_record.txt"


# ── Module 7C: Citation-ready evidence ──────────────────────────────────


class TestCitationEvidence:
    def test_evidence_carries_source_metadata(self) -> None:
        doc = _make_structured_doc()
        doc = enrich_chunks_for_retrieval(doc)

        evidence = package_evidence(doc.chunks)
        assert len(evidence) == len(doc.chunks)
        for ev in evidence:
            assert ev.source_filename == "medical_record.pdf"
            assert ev.doc_type == "medical"
            assert ev.parse_quality == "good"
            assert len(ev.chunk_text) > 0
            assert len(ev.page_numbers) > 0

    def test_evidence_carries_section_label(self) -> None:
        doc = _make_structured_doc()
        doc = enrich_chunks_for_retrieval(doc)

        evidence = package_evidence(doc.chunks)
        labels = [ev.section_label for ev in evidence]
        assert any(l != "" for l in labels)

    def test_evidence_respects_relevance_scores(self) -> None:
        doc = _make_structured_doc()
        doc = enrich_chunks_for_retrieval(doc)

        scores = {doc.chunks[0].chunk_id: 0.95, doc.chunks[1].chunk_id: 0.5}
        evidence = package_evidence(doc.chunks[:2], relevance_scores=scores)
        assert evidence[0].relevance_score == 0.95
        assert evidence[1].relevance_score == 0.5


# ── Module 7B: Chunk ranking ────────────────────────────────────────────


class TestLexicalRanker:
    def test_ranks_by_keyword_overlap(self) -> None:
        doc = _make_structured_doc()
        doc = enrich_chunks_for_retrieval(doc)

        ranker = LexicalRanker()
        results = ranker.rank(doc.chunks, "diagnosis MRI herniated disc", top_k=4)
        assert len(results) == 4
        assert results[0].score >= results[-1].score
        assert results[0].chunk.page_numbers == [2]

    def test_empty_query(self) -> None:
        doc = _make_structured_doc()
        results = LexicalRanker().rank(doc.chunks, "", top_k=2)
        assert len(results) == 2
        assert all(r.score == 0.0 for r in results)


class TestSalienceRanker:
    def test_ranks_with_multiple_signals(self) -> None:
        doc = _make_structured_doc()
        doc = enrich_chunks_for_retrieval(doc)

        ranker = SalienceRanker()
        results = ranker.rank(doc.chunks, "treatment plan therapy", top_k=4)
        assert len(results) == 4
        assert results[0].score > 0

    def test_high_value_section_boosted(self) -> None:
        doc = _make_structured_doc()
        doc = enrich_chunks_for_retrieval(doc)

        ranker = SalienceRanker()
        results = ranker.rank(doc.chunks, "some generic query", top_k=4)
        labels = [r.chunk.section_label.lower() for r in results]
        high_value = {"diagnosis", "treatment plan", "billing summary"}
        top_labels = set(labels[:2])
        assert top_labels & high_value


class TestRankChunksConvenience:
    def test_default_ranker_works(self) -> None:
        doc = _make_structured_doc()
        doc = enrich_chunks_for_retrieval(doc)
        results = rank_chunks(doc.chunks, "billing total amount", top_k=2)
        assert len(results) == 2
        assert results[0].score >= results[1].score


# ── Search endpoint ─────────────────────────────────────────────────────


class TestSearchEndpoint:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_search_returns_ranked_evidence(self) -> None:
        data = _upload(self.client, "medical_record.txt")
        doc_id = data["id"]

        resp = self.client.post(
            f"/documents/{doc_id}/search",
            json={"query": "diagnosis patient", "top_k": 3},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["document_id"] == doc_id
        assert result["ranker"] == "salience"
        assert len(result["results"]) <= 3
        for ev in result["results"]:
            assert "chunk_id" in ev
            assert "relevance_score" in ev
            assert "source_filename" in ev

    def test_search_with_lexical_ranker(self) -> None:
        data = _upload(self.client, "medical_record.txt")
        doc_id = data["id"]

        resp = self.client.post(
            f"/documents/{doc_id}/search",
            json={"query": "patient", "top_k": 2, "ranker": "lexical"},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["ranker"] == "lexical"

    def test_search_not_found(self) -> None:
        resp = self.client.post(
            "/documents/nonexistent/search",
            json={"query": "test"},
        )
        assert resp.status_code == 404


# ── Debug endpoint enrichment ───────────────────────────────────────────


class TestDebugEndpointRetrieval:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_debug_shows_retrieval_metadata(self) -> None:
        data = _upload(self.client, "medical_record.txt")
        doc_id = data["id"]

        resp = self.client.get(f"/documents/{doc_id}/chunks/debug")
        assert resp.status_code == 200
        debug = resp.json()

        assert "sections" in debug
        for chunk in debug["chunks"]:
            assert "doc_type" in chunk
            assert "section_label" in chunk
            assert "parse_quality" in chunk
