"""Smoke tests: Phase 8 — evidence-backed summaries and traceability.

Covers:
  Module 8A — per-key-point evidence binding (GroundedKeyPoint)
  Module 8B — OutputType distinction (deterministic vs ai_summary)
  Module 8C — grounding audit validation
  Module 8D — SummarisationMeta evidence-cited metrics

Run with:  uv run pytest tests/smoke/test_evidence_grounding.py -v
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from data_model import (
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentStatus,
    GroundedKeyPoint,
    GroundingAudit,
    OutputType,
    SummarisationMeta,
    SummaryResult,
)
from ai_core.grounding import audit_grounding, enrich_summarisation_meta

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


def _make_chunk_map(n: int = 5) -> dict[str, DocumentChunk]:
    """Build a map of N chunks with predictable IDs."""
    chunks = {}
    for i in range(n):
        cid = f"chunk_{i:03d}"
        chunks[cid] = DocumentChunk(
            chunk_id=cid,
            document_id="test",
            index=i,
            text=f"Content for chunk {i}.",
            page_numbers=[i + 1],
            char_start=i * 100,
            char_end=(i + 1) * 100,
        )
    return chunks


# ── Module 8A: Per-key-point evidence binding ────────────────────────────


class TestGroundedKeyPoints:
    def test_all_points_grounded(self) -> None:
        chunk_map = _make_chunk_map(3)
        provided = set(chunk_map.keys())

        raw_kps = [
            {"point": "First claim.", "chunk_ids": ["chunk_000"]},
            {"point": "Second claim.", "chunk_ids": ["chunk_001", "chunk_002"]},
        ]

        points, audit = audit_grounding(raw_kps, ["chunk_000", "chunk_001", "chunk_002"], provided, chunk_map)

        assert len(points) == 2
        assert all(p.grounded for p in points)
        assert points[0].chunk_ids == ["chunk_000"]
        assert points[1].chunk_ids == ["chunk_001", "chunk_002"]
        assert audit.key_points_grounded == 2
        assert audit.key_points_ungrounded == 0
        assert audit.grounding_score == 1.0

    def test_ungrounded_point_detected(self) -> None:
        chunk_map = _make_chunk_map(3)
        provided = set(chunk_map.keys())

        raw_kps = [
            {"point": "Grounded claim.", "chunk_ids": ["chunk_000"]},
            {"point": "Ungrounded claim.", "chunk_ids": []},
        ]

        points, audit = audit_grounding(raw_kps, ["chunk_000"], provided, chunk_map)

        assert points[0].grounded is True
        assert points[1].grounded is False
        assert audit.key_points_grounded == 1
        assert audit.key_points_ungrounded == 1
        assert any("no evidence" in w for w in audit.warnings)

    def test_backward_compat_string_key_points(self) -> None:
        """Old-style key_points that are plain strings (no chunk_ids)."""
        chunk_map = _make_chunk_map(2)
        provided = set(chunk_map.keys())

        raw_kps = ["A plain string point", "Another plain point"]
        points, audit = audit_grounding(raw_kps, ["chunk_000"], provided, chunk_map)

        assert len(points) == 2
        assert points[0].text == "A plain string point"
        assert points[0].grounded is False
        assert audit.key_points_ungrounded == 2


# ── Module 8B: OutputType distinction ────────────────────────────────────


class TestOutputType:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_deterministic_extraction_has_output_type(self) -> None:
        with open(fixture_path("medical_record.txt"), "rb") as f:
            resp = self.client.post(
                "/documents/upload",
                files={"file": ("medical_record.txt", f, "text/plain")},
            )
        doc_id = resp.json()["id"]

        resp = self.client.post(f"/documents/{doc_id}/extract")
        assert resp.status_code == 200
        data = resp.json()
        assert data["output_type"] == "deterministic"
        assert data["grounding_audit"] is None

    def test_output_type_field_present(self) -> None:
        with open(fixture_path("sample.txt"), "rb") as f:
            resp = self.client.post(
                "/documents/upload",
                files={"file": ("sample.txt", f, "text/plain")},
            )
        doc_id = resp.json()["id"]

        resp = self.client.post(f"/documents/{doc_id}/extract")
        data = resp.json()
        assert "output_type" in data


# ── Module 8C: Grounding audit validation ────────────────────────────────


class TestGroundingAudit:
    def test_hallucinated_ids_detected(self) -> None:
        chunk_map = _make_chunk_map(3)
        provided = set(chunk_map.keys())

        raw_kps = [
            {"point": "Claim.", "chunk_ids": ["chunk_000", "fake_999"]},
        ]
        used_ids = ["chunk_000", "fake_999"]

        _, audit = audit_grounding(raw_kps, used_ids, provided, chunk_map)

        assert audit.chunks_cited_valid == 1
        assert audit.chunks_cited_invalid == 1
        assert audit.needs_review is True
        assert any("hallucination" in w for w in audit.warnings)

    def test_fully_grounded_no_review(self) -> None:
        chunk_map = _make_chunk_map(2)
        provided = set(chunk_map.keys())

        raw_kps = [
            {"point": "Claim 1.", "chunk_ids": ["chunk_000"]},
            {"point": "Claim 2.", "chunk_ids": ["chunk_001"]},
        ]

        _, audit = audit_grounding(raw_kps, ["chunk_000", "chunk_001"], provided, chunk_map)

        assert audit.grounding_score == 1.0
        assert audit.needs_review is False
        assert audit.chunks_cited_invalid == 0

    def test_low_grounding_triggers_review(self) -> None:
        chunk_map = _make_chunk_map(3)
        provided = set(chunk_map.keys())

        raw_kps = [
            {"point": "Unsupported 1.", "chunk_ids": []},
            {"point": "Unsupported 2.", "chunk_ids": []},
            {"point": "Supported.", "chunk_ids": ["chunk_000"]},
        ]

        _, audit = audit_grounding(raw_kps, ["chunk_000"], provided, chunk_map)

        assert audit.grounding_score < 0.5
        assert audit.needs_review is True

    def test_empty_key_points(self) -> None:
        chunk_map = _make_chunk_map(2)
        provided = set(chunk_map.keys())

        _, audit = audit_grounding([], [], provided, chunk_map)

        assert audit.key_points_total == 0
        assert any("No key points" in w for w in audit.warnings)


# ── Module 8D: SummarisationMeta evidence metrics ───────────────────────


class TestSummarisationMetaEvidence:
    def test_evidence_metrics_populated(self) -> None:
        chunk_map = _make_chunk_map(5)
        meta = SummarisationMeta(
            total_chunks_available=10,
            total_pages_available=10,
            chunks_sent_to_llm=5,
            coverage_ratio=0.5,
            is_partial=True,
        )

        used_ids = ["chunk_000", "chunk_002", "chunk_004"]
        meta = enrich_summarisation_meta(meta, used_ids, chunk_map)

        assert meta.chunks_cited_by_llm == 3
        assert meta.evidence_usage_ratio == 0.6
        assert set(meta.pages_covered_by_evidence) == {1, 3, 5}

    def test_zero_cited_triggers_warning(self) -> None:
        chunk_map = _make_chunk_map(3)
        meta = SummarisationMeta(
            chunks_sent_to_llm=3,
        )

        meta = enrich_summarisation_meta(meta, [], chunk_map)

        assert meta.chunks_cited_by_llm == 0
        assert meta.evidence_usage_ratio == 0.0
        assert any("not cite any" in w for w in meta.warnings)


# ── Schema integration via API ──────────────────────────────────────────


class TestSchemaIntegration:
    """Verify the new fields survive round-trip through the API."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_grounded_key_points_schema(self) -> None:
        gkp = GroundedKeyPoint(text="Test point", chunk_ids=["c1"], grounded=True)
        summary = SummaryResult(
            summary_text="Test",
            key_points=["Test point"],
            grounded_key_points=[gkp],
            grounding_coverage=1.0,
        )
        data = summary.model_dump()
        assert data["grounded_key_points"][0]["grounded"] is True
        assert data["grounding_coverage"] == 1.0

    def test_grounding_audit_schema(self) -> None:
        audit = GroundingAudit(
            chunks_provided=5,
            chunks_cited_by_llm=3,
            chunks_cited_valid=2,
            chunks_cited_invalid=1,
            key_points_total=4,
            key_points_grounded=3,
            key_points_ungrounded=1,
            grounding_score=0.75,
            needs_review=True,
            warnings=["test warning"],
        )
        data = audit.model_dump()
        assert data["needs_review"] is True
        assert data["grounding_score"] == 0.75

    def test_extraction_result_carries_output_type(self) -> None:
        from data_model import ExtractionResult

        det = ExtractionResult(document_id="d1", output_type=OutputType.DETERMINISTIC)
        ai = ExtractionResult(document_id="d1", output_type=OutputType.AI_SUMMARY)

        assert det.model_dump()["output_type"] == "deterministic"
        assert ai.model_dump()["output_type"] == "ai_summary"
