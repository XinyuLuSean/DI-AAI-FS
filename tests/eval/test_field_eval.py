"""Unit tests for di_eval.field_eval scoring functions.

These test the scoring logic in isolation — no API calls, no fixtures needed.
Run with:  uv run pytest tests/eval/test_field_eval.py -v
"""

from __future__ import annotations

from di_eval.field_eval import FieldMatchResult, score_field, score_field_set


class TestScoreField:
    """Per-field scoring against ground truth entries."""

    def test_exact_match(self) -> None:
        r = score_field("claim_number", {"value": "2024-INS-00142", "must_extract": True}, "2024-INS-00142")
        assert r.exact_match is True
        assert r.best_match is True

    def test_normalised_match_ignores_case(self) -> None:
        r = score_field("patient_name", {"value": "Jane Doe", "must_extract": True}, "jane doe")
        assert r.exact_match is False
        assert r.normalized_match is True
        assert r.best_match is True

    def test_numeric_tolerance_match(self) -> None:
        r = score_field("total_amount", {"value": "20,600", "must_extract": True}, "20600")
        assert r.numeric_close is True
        assert r.best_match is True

    def test_numeric_mismatch(self) -> None:
        r = score_field("total_amount", {"value": "20,600", "must_extract": True}, "19,600")
        assert r.numeric_close is False
        assert r.exact_match is False

    def test_date_tolerance_match(self) -> None:
        r = score_field(
            "service_date",
            {"value": "January 15, 2024", "must_extract": True, "normalized": "2024-01-15"},
            "January 15, 2024",
        )
        assert r.date_close is True or r.exact_match is True
        assert r.best_match is True

    def test_null_expected_null_actual(self) -> None:
        r = score_field("mrn", {"value": None, "must_extract": False}, None)
        assert r.exact_match is True

    def test_null_expected_but_extracted(self) -> None:
        r = score_field("mrn", {"value": None, "must_extract": False}, "MED-123")
        assert r.exact_match is False

    def test_missing_required_field(self) -> None:
        r = score_field("claim_number", {"value": "2024-INS-00142", "must_extract": True}, None)
        assert r.best_match is False
        assert r.must_extract is True


class TestScoreFieldSet:
    """Aggregate P/R/F1 computation."""

    def test_perfect_extraction(self) -> None:
        expected = {
            "claim_number": {"value": "CLM-001", "must_extract": True},
            "patient_name": {"value": "Jane", "must_extract": True},
            "mrn": {"value": None, "must_extract": False},
        }
        actual = {"claim_number": "CLM-001", "patient_name": "Jane"}
        m = score_field_set("test.txt", expected, actual)
        assert m.true_positives == 2
        assert m.false_negatives == 0
        assert m.precision == 1.0
        assert m.recall == 1.0
        assert m.f1 == 1.0

    def test_missing_required_lowers_recall(self) -> None:
        expected = {
            "claim_number": {"value": "CLM-001", "must_extract": True},
            "patient_name": {"value": "Jane", "must_extract": True},
        }
        actual = {"claim_number": "CLM-001"}
        m = score_field_set("test.txt", expected, actual)
        assert m.true_positives == 1
        assert m.false_negatives == 1
        assert m.recall == 0.5

    def test_spurious_field_lowers_precision(self) -> None:
        expected = {
            "mrn": {"value": None, "must_extract": False},
        }
        actual = {"mrn": "FAKE-MRN"}
        m = score_field_set("test.txt", expected, actual)
        assert m.false_positives == 1
