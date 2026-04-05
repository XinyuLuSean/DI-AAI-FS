"""Smoke tests: HITL review, correction, review queue, feedback (Phase 11).

Run with:  uv run pytest tests/smoke/test_hitl.py -v
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from py_api.main import app

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def fixture_path(name: str) -> Path:
    direct = FIXTURES / name
    if direct.exists():
        return direct
    matches = sorted(FIXTURES.rglob(name))
    if not matches:
        raise FileNotFoundError(f"Fixture not found: {name}")
    return matches[0]


def _upload(client: TestClient, filename: str) -> dict:
    with open(fixture_path(filename), "rb") as f:
        resp = client.post(
            "/documents/upload",
            files={"file": (filename, f, "text/plain")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _extract(client: TestClient, doc_id: str) -> dict:
    resp = client.post(f"/documents/{doc_id}/extract")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Module 11A: Reviewable output ────────────────────────────────────────

class TestReviewStatusEndpoint:
    """GET review status creates a ReviewableOutput with auto-classified triggers."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_get_review_status_creates_reviewable(self) -> None:
        doc = _upload(self.client, "sample.txt")
        ext = _extract(self.client, doc["id"])
        resp = self.client.get(
            f"/documents/{doc['id']}/extractions/{ext['id']}/review"
        )
        assert resp.status_code == 200
        review = resp.json()
        assert review["extraction_id"] == ext["id"]
        assert review["document_id"] == doc["id"]
        assert review["status"] in (
            "pending_review", "auto_accepted",
        )

    def test_review_has_trigger_reasons(self) -> None:
        doc = _upload(self.client, "sample.txt")
        ext = _extract(self.client, doc["id"])
        resp = self.client.get(
            f"/documents/{doc['id']}/extractions/{ext['id']}/review"
        )
        review = resp.json()
        assert "trigger_reasons" in review
        assert isinstance(review["trigger_reasons"], list)

    def test_review_has_priority_score(self) -> None:
        doc = _upload(self.client, "sample.txt")
        ext = _extract(self.client, doc["id"])
        resp = self.client.get(
            f"/documents/{doc['id']}/extractions/{ext['id']}/review"
        )
        review = resp.json()
        assert "priority_score" in review
        assert 0.0 <= review["priority_score"] <= 1.0


class TestSubmitReview:
    """POST review decision transitions status correctly."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_approve_extraction(self) -> None:
        doc = _upload(self.client, "sample.txt")
        ext = _extract(self.client, doc["id"])
        resp = self.client.post(
            f"/documents/{doc['id']}/extractions/{ext['id']}/review",
            json={
                "status": "approved",
                "reviewer_id": "test-reviewer",
                "notes": "All fields look correct",
            },
        )
        assert resp.status_code == 200
        review = resp.json()
        assert review["status"] == "approved"
        assert len(review["decisions"]) >= 1
        assert review["decisions"][-1]["reviewer_id"] == "test-reviewer"

    def test_reject_extraction(self) -> None:
        doc = _upload(self.client, "sample.txt")
        ext = _extract(self.client, doc["id"])
        resp = self.client.post(
            f"/documents/{doc['id']}/extractions/{ext['id']}/review",
            json={
                "status": "rejected",
                "reviewer_id": "test-reviewer",
                "notes": "Document was misclassified",
            },
        )
        assert resp.status_code == 200
        review = resp.json()
        assert review["status"] == "rejected"

    def test_review_not_found(self) -> None:
        resp = self.client.post(
            "/documents/fake/extractions/fake/review",
            json={"status": "approved"},
        )
        assert resp.status_code == 404


# ── Module 11B: Correction capture ───────────────────────────────────────

class TestSubmitCorrection:
    """POST corrections stores them and generates feedback signals."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_correct_field_value(self) -> None:
        doc = _upload(self.client, "sample.txt")
        ext = _extract(self.client, doc["id"])
        resp = self.client.post(
            f"/documents/{doc['id']}/extractions/{ext['id']}/correct",
            json={
                "reviewer_id": "test-reviewer",
                "field_corrections": [
                    {
                        "field_name": "total_amount",
                        "corrected_value": "21500.00",
                        "reason": "Original amount missed one line item",
                    }
                ],
                "notes": "Updated total based on full invoice review",
            },
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["total_corrections"] == 1
        assert result["feedback_signals_generated"] >= 1

    def test_correction_transitions_to_corrected(self) -> None:
        doc = _upload(self.client, "sample.txt")
        ext = _extract(self.client, doc["id"])

        self.client.get(
            f"/documents/{doc['id']}/extractions/{ext['id']}/review"
        )

        self.client.post(
            f"/documents/{doc['id']}/extractions/{ext['id']}/correct",
            json={
                "reviewer_id": "test-reviewer",
                "field_corrections": [
                    {
                        "field_name": "patient_name",
                        "corrected_value": "Jane M. Doe",
                        "reason": "Middle initial was missing",
                    }
                ],
            },
        )

        resp = self.client.get(
            f"/documents/{doc['id']}/extractions/{ext['id']}/review"
        )
        review = resp.json()
        assert review["status"] == "corrected"
        assert review["correction_id"] is not None

    def test_evidence_mismatch_report(self) -> None:
        doc = _upload(self.client, "sample.txt")
        ext = _extract(self.client, doc["id"])
        resp = self.client.post(
            f"/documents/{doc['id']}/extractions/{ext['id']}/correct",
            json={
                "reviewer_id": "test-reviewer",
                "evidence_mismatches": [
                    {
                        "field_name": "total_amount",
                        "chunk_id": "page:1",
                        "mismatch_type": "partial",
                        "explanation": "Chunk only contains one of three amounts",
                    }
                ],
            },
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["total_corrections"] == 1

    def test_correction_not_found(self) -> None:
        resp = self.client.post(
            "/documents/fake/extractions/fake/correct",
            json={"field_corrections": []},
        )
        assert resp.status_code == 404


# ── Module 11C: Review queue ─────────────────────────────────────────────

class TestReviewQueue:
    """GET review-queue returns prioritised review items."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_review_queue_endpoint(self) -> None:
        resp = self.client.get("/documents/review-queue")
        assert resp.status_code == 200
        queue = resp.json()
        assert "items" in queue
        assert "total" in queue
        assert "pending_count" in queue
        assert "auto_accepted_count" in queue

    def test_review_queue_populates_after_extract(self) -> None:
        doc = _upload(self.client, "sample.txt")
        ext = _extract(self.client, doc["id"])
        self.client.get(
            f"/documents/{doc['id']}/extractions/{ext['id']}/review"
        )

        resp = self.client.get("/documents/review-queue")
        queue = resp.json()
        assert queue["total"] >= 1

    def test_review_queue_sorted_by_priority(self) -> None:
        doc1 = _upload(self.client, "sample.txt")
        ext1 = _extract(self.client, doc1["id"])
        self.client.get(
            f"/documents/{doc1['id']}/extractions/{ext1['id']}/review"
        )

        doc2 = _upload(self.client, "medical_record.txt")
        ext2 = _extract(self.client, doc2["id"])
        self.client.get(
            f"/documents/{doc2['id']}/extractions/{ext2['id']}/review"
        )

        resp = self.client.get("/documents/review-queue")
        queue = resp.json()
        if len(queue["items"]) >= 2:
            priorities = [item["priority_score"] for item in queue["items"]]
            assert priorities == sorted(priorities, reverse=True)


# ── Module 11C: Auto-accept and trigger logic (unit tests) ───────────────

class TestAutoAcceptLogic:
    """Unit tests for auto-accept and trigger classification."""

    def test_high_confidence_deterministic_auto_accepts(self) -> None:
        from data_model import ExtractionResult, ParseQuality, StructuredField
        from di_core.review_queue import classify_review_triggers, should_auto_accept

        result = ExtractionResult(
            document_id="test",
            output_type="deterministic",
            structured_fields=[
                StructuredField(field_name="claim_number", field_value="CLM-001", confidence=0.9),
                StructuredField(field_name="policy_number", field_value="POL-001", confidence=0.9),
                StructuredField(field_name="patient_name", field_value="Jane Doe", confidence=0.9),
            ],
        )
        triggers = classify_review_triggers(result, parse_quality=ParseQuality.GOOD)
        assert len(triggers) == 0
        assert should_auto_accept(result, triggers, ParseQuality.GOOD) is True

    def test_low_confidence_triggers_review(self) -> None:
        from data_model import ExtractionResult, StructuredField
        from di_core.review_queue import classify_review_triggers

        result = ExtractionResult(
            document_id="test",
            output_type="deterministic",
            structured_fields=[
                StructuredField(field_name="total_amount", field_value="100", confidence=0.3),
            ],
        )
        triggers = classify_review_triggers(result)
        assert any(t == "low_confidence_field" for t in triggers)

    def test_no_fields_triggers_review(self) -> None:
        from data_model import ExtractionResult
        from di_core.review_queue import classify_review_triggers

        result = ExtractionResult(
            document_id="test",
            output_type="deterministic",
            structured_fields=[],
        )
        triggers = classify_review_triggers(result)
        assert any(t == "no_fields_extracted" for t in triggers)

    def test_degraded_parse_triggers_review(self) -> None:
        from data_model import ExtractionResult, ParseQuality, StructuredField
        from di_core.review_queue import classify_review_triggers

        result = ExtractionResult(
            document_id="test",
            structured_fields=[
                StructuredField(field_name="test", field_value="val", confidence=0.9),
            ],
        )
        triggers = classify_review_triggers(
            result, parse_quality=ParseQuality.DEGRADED,
        )
        assert any(t == "degraded_parse_quality" for t in triggers)

    def test_weak_grounding_triggers_review(self) -> None:
        from data_model import ExtractionResult, GroundingAudit
        from di_core.review_queue import classify_review_triggers

        result = ExtractionResult(
            document_id="test",
            output_type="ai_summary",
            grounding_audit=GroundingAudit(
                grounding_score=0.2,
                key_points_ungrounded=3,
                chunks_cited_invalid=1,
            ),
        )
        triggers = classify_review_triggers(result)
        assert "weak_grounding" in triggers
        assert "ungrounded_key_points" in triggers
        assert "hallucinated_chunk_ids" in triggers


class TestPriorityScoring:
    """Unit tests for review priority computation."""

    def test_no_triggers_zero_priority(self) -> None:
        from data_model import ExtractionResult
        from di_core.review_queue import compute_review_priority

        result = ExtractionResult(document_id="test")
        assert compute_review_priority([], result) == 0.0

    def test_hallucinated_ids_highest_priority(self) -> None:
        from data_model import ExtractionResult
        from data_model.review import ReviewTriggerReason
        from di_core.review_queue import compute_review_priority

        result = ExtractionResult(document_id="test")
        triggers = [ReviewTriggerReason.HALLUCINATED_CHUNK_IDS]
        score = compute_review_priority(triggers, result)
        assert score >= 0.9

    def test_multiple_triggers_boost_priority(self) -> None:
        from data_model import ExtractionResult
        from data_model.review import ReviewTriggerReason
        from di_core.review_queue import compute_review_priority

        result = ExtractionResult(document_id="test")
        single = compute_review_priority(
            [ReviewTriggerReason.LOW_CONFIDENCE_FIELD], result,
        )
        multi = compute_review_priority(
            [ReviewTriggerReason.LOW_CONFIDENCE_FIELD, ReviewTriggerReason.DEGRADED_PARSE_QUALITY],
            result,
        )
        assert multi >= single


# ── Module 11D: Feedback signals (unit tests) ────────────────────────────

class TestFeedbackSignals:
    """Unit tests for feedback signal generation."""

    def test_field_correction_generates_signals(self) -> None:
        from data_model.review import CorrectionRecord, FieldCorrection
        from di_core.review_queue import generate_feedback_signals

        correction = CorrectionRecord(
            extraction_id="ext1",
            document_id="doc1",
            field_corrections=[
                FieldCorrection(
                    field_name="total_amount",
                    original_value="20600.00",
                    corrected_value="21500.00",
                    original_confidence=0.9,
                    reason="Missed one line item",
                ),
            ],
        )
        signals = generate_feedback_signals(correction)
        assert len(signals) >= 2
        categories = [s.category for s in signals]
        assert "extraction_heuristic" in categories
        assert "evaluation_fixture" in categories

    def test_summary_correction_generates_signals(self) -> None:
        from data_model.review import CorrectionRecord, SummaryCorrection
        from di_core.review_queue import generate_feedback_signals

        correction = CorrectionRecord(
            extraction_id="ext1",
            document_id="doc1",
            summary_correction=SummaryCorrection(
                original_summary_text="The claim was for $20,600.",
                corrected_summary_text="The claim was for $21,500 including all line items.",
                reason="Total was wrong",
            ),
        )
        signals = generate_feedback_signals(correction)
        categories = [s.category for s in signals]
        assert "summary_prompt" in categories
        assert "fine_tuning_data" in categories

    def test_evidence_mismatch_generates_retrieval_signal(self) -> None:
        from data_model.review import CorrectionRecord, EvidenceMismatchReport
        from di_core.review_queue import generate_feedback_signals

        correction = CorrectionRecord(
            extraction_id="ext1",
            document_id="doc1",
            evidence_mismatches=[
                EvidenceMismatchReport(
                    field_name="total_amount",
                    chunk_id="chunk_a",
                    mismatch_type="irrelevant",
                ),
            ],
        )
        signals = generate_feedback_signals(correction)
        categories = [s.category for s in signals]
        assert "retrieval_ranking" in categories

    def test_empty_correction_no_signals(self) -> None:
        from data_model.review import CorrectionRecord
        from di_core.review_queue import generate_feedback_signals

        correction = CorrectionRecord(
            extraction_id="ext1",
            document_id="doc1",
        )
        signals = generate_feedback_signals(correction)
        assert signals == []
