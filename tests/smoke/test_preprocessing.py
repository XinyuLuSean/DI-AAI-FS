"""Smoke tests: preprocessing, postprocessing, pipeline trace (Phase 10).

Run with:  uv run pytest tests/smoke/test_preprocessing.py -v
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


def _extract(client: TestClient, doc_id: str) -> dict:
    resp = client.post(f"/documents/{doc_id}/extract")
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestPreprocessMetaOnUpload:
    """Upload response contains preprocess_meta with transparency data."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_preprocess_meta_present(self) -> None:
        doc = _upload(self.client, "sample.txt")
        assert doc["preprocess_meta"] is not None
        meta = doc["preprocess_meta"]
        assert meta["applied"] is True
        assert meta["chars_before"] > 0
        assert meta["chars_after"] > 0

    def test_chars_removed_non_negative(self) -> None:
        doc = _upload(self.client, "sample.txt")
        meta = doc["preprocess_meta"]
        assert meta["chars_removed"] >= 0
        assert meta["chars_after"] <= meta["chars_before"]


class TestPipelineTrace:
    """Upload response contains a pipeline_trace with per-stage timing."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_pipeline_trace_present(self) -> None:
        doc = _upload(self.client, "sample.txt")
        assert doc["pipeline_trace"] is not None

    def test_pipeline_trace_has_all_stages(self) -> None:
        doc = _upload(self.client, "sample.txt")
        trace = doc["pipeline_trace"]
        stage_names = [s["stage"] for s in trace["stages"]]
        assert "parse" in stage_names
        assert "preprocess" in stage_names
        assert "route" in stage_names
        assert "chunk" in stage_names
        assert "enrich" in stage_names

    def test_pipeline_trace_all_stages_succeeded(self) -> None:
        doc = _upload(self.client, "sample.txt")
        trace = doc["pipeline_trace"]
        for stage in trace["stages"]:
            assert stage["success"] is True, f"Stage {stage['stage']} failed"

    def test_pipeline_trace_total_elapsed(self) -> None:
        doc = _upload(self.client, "sample.txt")
        trace = doc["pipeline_trace"]
        assert trace["total_elapsed_ms"] >= 0
        assert trace["has_hard_failure"] is False

    def test_pipeline_trace_stage_timing(self) -> None:
        doc = _upload(self.client, "sample.txt")
        trace = doc["pipeline_trace"]
        for stage in trace["stages"]:
            assert stage["elapsed_ms"] >= 0


class TestPostprocessingOnExtract:
    """Extraction endpoint applies postprocessing to field values."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_confidence_clamped(self) -> None:
        doc = _upload(self.client, "sample.txt")
        result = _extract(self.client, doc["id"])
        for field in result["structured_fields"]:
            assert 0.0 <= field["confidence"] <= 1.0

    def test_service_date_normalized(self) -> None:
        """service_date from sample.txt ('January 15, 2024') should become ISO."""
        doc = _upload(self.client, "sample.txt")
        result = _extract(self.client, doc["id"])
        fields = {f["field_name"]: f for f in result["structured_fields"]}
        if "service_date" in fields:
            assert fields["service_date"]["field_value"] == "2024-01-15"


class TestPreprocessorUnit:
    """Unit-level tests for preprocessor functions."""

    def test_unicode_normalization(self) -> None:
        from di_core.preprocessor import _normalize_unicode
        text = "caf\u0065\u0301"  # e + combining accent
        normalized, changes = _normalize_unicode(text)
        assert "\u00e9" in normalized  # should become single é

    def test_control_char_removal(self) -> None:
        from di_core.preprocessor import _strip_control_chars
        text = "hello\x00world\x07test"
        cleaned, removed = _strip_control_chars(text)
        assert "\x00" not in cleaned
        assert "\x07" not in cleaned
        assert removed == 2

    def test_whitespace_normalization(self) -> None:
        from di_core.preprocessor import _normalize_whitespace
        text = "hello   world  \n  trailing  \n\n\n\n\nblank"
        result = _normalize_whitespace(text)
        assert "   " not in result
        assert result.count("\n") < text.count("\n")

    def test_consecutive_duplicate_suppression(self) -> None:
        from di_core.preprocessor import _suppress_consecutive_duplicates
        text = "header\nheader\nheader\ncontent\ncontent\nfooter"
        result, suppressed = _suppress_consecutive_duplicates(text)
        assert suppressed == 3
        assert result == "header\ncontent\nfooter"

    def test_header_footer_detection(self) -> None:
        from data_model import DocumentPage
        from di_core.preprocessor import _detect_repeated_headers_footers
        pages = [
            DocumentPage(page_number=i, text=f"HEADER LINE\ncontent page {i}\nFOOTER LINE", char_count=30)
            for i in range(1, 6)
        ]
        headers, footers = _detect_repeated_headers_footers(pages)
        assert "HEADER LINE" in headers
        assert "FOOTER LINE" in footers


class TestPostprocessorUnit:
    """Unit-level tests for postprocessor functions."""

    def test_date_normalization(self) -> None:
        from di_core.postprocessor import _normalize_date
        assert _normalize_date("January 15, 2024") == "2024-01-15"
        assert _normalize_date("01/15/2024") == "2024-01-15"
        assert _normalize_date("2024-01-15") == "2024-01-15"
        assert _normalize_date("15 January 2024") == "2024-01-15"
        assert _normalize_date("not a date") is None

    def test_currency_normalization(self) -> None:
        from di_core.postprocessor import _normalize_currency
        assert _normalize_currency("$1,234.56") == "1234.56"
        assert _normalize_currency("20,600") == "20600.00"
        assert _normalize_currency("6,258.13") == "6258.13"
        assert _normalize_currency("not money") is None

    def test_confidence_clamping(self) -> None:
        from data_model import StructuredField
        from di_core.postprocessor import PostprocessMeta, _clamp_confidence
        meta = PostprocessMeta()
        field = StructuredField(field_name="test", field_value="v", confidence=1.5)
        _clamp_confidence(field, meta)
        assert field.confidence == 1.0
        assert meta.confidences_clamped == 1

    def test_evidence_dedup(self) -> None:
        from data_model import EvidenceReference, StructuredField
        from di_core.postprocessor import PostprocessMeta, _dedup_evidence
        meta = PostprocessMeta()
        field = StructuredField(
            field_name="test",
            field_value="v",
            evidence=[
                EvidenceReference(chunk_id="a", chunk_text="t1", relevance_score=0.8),
                EvidenceReference(chunk_id="a", chunk_text="t1", relevance_score=0.6),
                EvidenceReference(chunk_id="b", chunk_text="t2", relevance_score=0.9),
            ],
        )
        _dedup_evidence(field, meta)
        assert len(field.evidence) == 2
        assert meta.evidence_deduped == 1
        ids = [e.chunk_id for e in field.evidence]
        assert "a" in ids
        assert "b" in ids


class TestPipelineFailureClassification:
    """Unit tests for failure classification helpers."""

    def test_hard_parse_failure(self) -> None:
        from data_model.pipeline import classify_parse_outcome
        outcome = classify_parse_outcome("file_not_found", "unusable")
        assert outcome.success is False
        assert outcome.failure_kind == "hard"

    def test_soft_parse_failure(self) -> None:
        from data_model.pipeline import classify_parse_outcome
        outcome = classify_parse_outcome("none", "degraded")
        assert outcome.success is True
        assert outcome.failure_kind == "soft"

    def test_good_parse(self) -> None:
        from data_model.pipeline import classify_parse_outcome
        outcome = classify_parse_outcome("none", "good")
        assert outcome.success is True
        assert outcome.failure_kind == "none"

    def test_no_fields_needs_review(self) -> None:
        from data_model.pipeline import classify_extraction_outcome
        outcome = classify_extraction_outcome(0, 9, 0.0)
        assert outcome.failure_kind == "review_needed"

    def test_low_confidence_needs_review(self) -> None:
        from data_model.pipeline import classify_extraction_outcome
        outcome = classify_extraction_outcome(3, 9, 0.3)
        assert outcome.failure_kind == "review_needed"
