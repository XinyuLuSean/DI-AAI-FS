"""Phase 8 tests — classification, clustering thought path, and semantic matching.

Covers:
  - explainable document readiness classification
  - semantic matching of extracted facts back to chunks
  - lightweight topic grouping over matched chunks
  - API endpoints for both tasks
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from data_model import (
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentStatus,
    ParseMeta,
    ParseQuality,
    RoutingResult,
    DocumentType,
)
from di_core import align_extracted_fields_to_chunks, classify_document_readiness, extract_fields

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


def _upload(client: TestClient, filename: str) -> dict:
    with open(fixture_path(filename), "rb") as f:
        resp = client.post(
            "/documents/upload",
            files={"file": (filename, f, "text/plain")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _make_doc() -> Document:
    texts = [
        "CLAIM OVERVIEW Claim Number: CLM-77821. Patient Name: Jane Doe. Service Date: 2024-01-15.",
        "BILLING DETAIL Total Amount Due: 6258.13. Invoice Number: INV-2024-0283. Account Number: ACCT-DOE-2024.",
        "FOLLOW-UP Provider Name: John Smith. Please remit payment within 30 days.",
    ]
    pages = [
        DocumentPage(page_number=i + 1, text=text, char_count=len(text))
        for i, text in enumerate(texts)
    ]
    chunks = [
        DocumentChunk(
            chunk_id=f"c{i + 1}",
            document_id="phase8-doc",
            index=i,
            text=text,
            page_numbers=[i + 1],
            section_label=["overview", "billing", "follow_up"][i],
            char_start=0,
            char_end=len(text),
            token_estimate=len(text.split()),
        )
        for i, text in enumerate(texts)
    ]
    return Document(
        id="phase8-doc",
        filename="claim_packet.txt",
        pages=pages,
        chunks=chunks,
        status=DocumentStatus.CHUNKED,
        parse_meta=ParseMeta(
            page_count=len(pages),
            total_chars=sum(len(text) for text in texts),
            quality=ParseQuality.GOOD,
        ),
        routing=RoutingResult(
            predicted_type=DocumentType.BILLING,
            confidence=0.91,
            is_fallback=False,
        ),
    )


class TestPhase8Functions:
    def test_classification_ready_on_clean_document(self) -> None:
        doc = _make_doc()
        extraction = extract_fields(doc)

        result = classify_document_readiness(doc, extraction=extraction)

        assert result.output_type == "ai_classification"
        assert result.classification is not None
        assert result.classification.label == "ready"
        assert len(result.classification.signals) >= 3

    def test_semantic_matching_aligns_fields(self) -> None:
        doc = _make_doc()
        extraction = extract_fields(doc)

        result = align_extracted_fields_to_chunks(doc, extraction)

        assert result.output_type == "semantic_match"
        assert result.semantic_match is not None
        assert result.semantic_match.matched_count >= 2
        assert any(match.section_label == "billing" for match in result.semantic_match.matches if match.grounded)
        assert len(result.semantic_match.clusters) >= 1


class TestPhase8API:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_classify_endpoint_returns_extraction(self) -> None:
        doc = _upload(self.client, "sample.txt")
        extraction = self.client.post(f"/documents/{doc['id']}/extract").json()

        resp = self.client.post(
            f"/documents/{doc['id']}/classify",
            params={"extraction_id": extraction["id"]},
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["output_type"] == "ai_classification"
        assert data["classification"]["task_name"] == "document_readiness"
        assert data["classification"]["label"] in {"ready", "review_recommended", "blocked"}

    def test_semantic_match_endpoint_returns_matches(self) -> None:
        doc = _upload(self.client, "invoice_plumbing.txt")
        extraction = self.client.post(f"/documents/{doc['id']}/extract").json()

        resp = self.client.post(
            f"/documents/{doc['id']}/semantic-match",
            params={"extraction_id": extraction["id"]},
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["output_type"] == "semantic_match"
        assert data["semantic_match"]["task_name"] == "field_to_evidence_alignment"
        assert data["semantic_match"]["matched_count"] >= 1
        assert len(data["semantic_match"]["matches"]) >= 1

    def test_semantic_match_requires_extraction(self) -> None:
        doc = _upload(self.client, "sample.txt")
        resp = self.client.post(f"/documents/{doc['id']}/semantic-match")
        assert resp.status_code == 422
