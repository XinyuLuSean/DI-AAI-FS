"""Schema validation tests (Phase 2 — Module 2D).

Tests the validation layer against a library of fixtures:
  - valid output (clean pass)
  - partial recovery cases (missing chunk_ids_used, empty key points, etc.)
  - hard failures (empty summary_text, wrong structure, non-dict)
  - edge cases (string key_points, confidence out of range, etc.)

These fixtures also serve as documentation of the LLM output contract.
"""

import pytest

from ai_core.validation import (
    LLMSummarisationOutput,
    ValidationStatus,
    validate_summarisation_output,
)


# ── Fixture library ──────────────────────────────────────────────────────

VALID_OUTPUT = {
    "summary_text": "Patient John Smith was admitted on 2024-08-15 for a fractured tibia.",
    "key_points": [
        {"point": "Patient admitted on 2024-08-15.", "chunk_ids": ["c1"]},
        {"point": "Diagnosis: fractured left tibia.", "chunk_ids": ["c1", "c2"]},
        {"point": "Total billed: $12,450.", "chunk_ids": ["c3"]},
    ],
    "structured_fields": [
        {"field_name": "document_type", "field_value": "medical", "confidence": 0.92},
    ],
    "chunk_ids_used": ["c1", "c2", "c3"],
}

MISSING_CHUNK_IDS_USED = {
    "summary_text": "A valid summary without chunk_ids_used at top level.",
    "key_points": [
        {"point": "Claim one.", "chunk_ids": ["c1"]},
        {"point": "Claim two.", "chunk_ids": ["c2"]},
    ],
    "structured_fields": [],
}

EMPTY_KEY_POINTS = {
    "summary_text": "A summary with no key points at all.",
    "key_points": [],
    "structured_fields": [],
    "chunk_ids_used": [],
}

KEY_POINTS_WITH_EMPTY_TEXT = {
    "summary_text": "A summary where some key points have empty text.",
    "key_points": [
        {"point": "Valid claim.", "chunk_ids": ["c1"]},
        {"point": "", "chunk_ids": ["c2"]},
        {"point": "   ", "chunk_ids": ["c3"]},
    ],
    "structured_fields": [],
    "chunk_ids_used": ["c1", "c2", "c3"],
}

KEY_POINTS_NO_CITATIONS = {
    "summary_text": "Key points exist but none cite chunks.",
    "key_points": [
        {"point": "Uncited claim one.", "chunk_ids": []},
        {"point": "Uncited claim two.", "chunk_ids": []},
    ],
    "structured_fields": [],
    "chunk_ids_used": [],
}

STRING_KEY_POINTS = {
    "summary_text": "LLM returned key_points as plain strings instead of dicts.",
    "key_points": [
        "First point as a string",
        "Second point as a string",
    ],
    "structured_fields": [],
    "chunk_ids_used": ["c1"],
}

CONFIDENCE_OUT_OF_RANGE = {
    "summary_text": "Fields with out-of-range confidence.",
    "key_points": [
        {"point": "A claim.", "chunk_ids": ["c1"]},
    ],
    "structured_fields": [
        {"field_name": "amount", "field_value": "$100", "confidence": 1.5},
        {"field_name": "date", "field_value": "2024-01-01", "confidence": -0.3},
    ],
    "chunk_ids_used": ["c1"],
}

EMPTY_SUMMARY_TEXT = {
    "summary_text": "",
    "key_points": [
        {"point": "Some claim.", "chunk_ids": ["c1"]},
    ],
    "structured_fields": [],
    "chunk_ids_used": ["c1"],
}

COMPLETELY_EMPTY = {}

NOT_A_DICT = "this is just a string"

ARRAY_ROOT = [{"summary_text": "wrong shape"}]

MISSING_ALL_FIELDS = {
    "unrelated_key": "unrelated_value",
}


# ── Tests: Valid output ──────────────────────────────────────────────────


class TestValidOutput:
    def test_valid_output_passes(self):
        vr = validate_summarisation_output(VALID_OUTPUT)
        assert vr.status == ValidationStatus.VALID
        assert vr.ok
        assert vr.error_count == 0
        assert vr.warning_count == 0
        assert vr.output is not None
        assert vr.output.summary_text == VALID_OUTPUT["summary_text"]
        assert len(vr.output.key_points) == 3
        assert len(vr.output.chunk_ids_used) == 3

    def test_valid_output_preserves_structured_fields(self):
        vr = validate_summarisation_output(VALID_OUTPUT)
        assert vr.output is not None
        assert len(vr.output.structured_fields) == 1
        assert vr.output.structured_fields[0].field_name == "document_type"
        assert vr.output.structured_fields[0].confidence == pytest.approx(0.92)


# ── Tests: Partial recovery ──────────────────────────────────────────────


class TestPartialRecovery:
    def test_missing_chunk_ids_used_recovered(self):
        vr = validate_summarisation_output(MISSING_CHUNK_IDS_USED)
        assert vr.status == ValidationStatus.PARTIAL_RECOVERY
        assert vr.ok
        assert vr.output is not None
        assert set(vr.output.chunk_ids_used) == {"c1", "c2"}
        recovered = [i for i in vr.issues if i.field == "chunk_ids_used" and i.recovered]
        assert len(recovered) == 1

    def test_empty_key_points_warned(self):
        vr = validate_summarisation_output(EMPTY_KEY_POINTS)
        assert vr.status == ValidationStatus.PARTIAL_RECOVERY
        assert vr.ok
        assert any(i.field == "key_points" and "No key points" in i.issue for i in vr.issues)

    def test_empty_text_key_points_filtered(self):
        vr = validate_summarisation_output(KEY_POINTS_WITH_EMPTY_TEXT)
        assert vr.status == ValidationStatus.PARTIAL_RECOVERY
        assert vr.ok
        assert vr.output is not None
        assert len(vr.output.key_points) == 1
        assert vr.output.key_points[0].point == "Valid claim."

    def test_uncited_key_points_warned(self):
        vr = validate_summarisation_output(KEY_POINTS_NO_CITATIONS)
        assert vr.ok
        assert any("no chunk_ids" in i.issue for i in vr.issues)

    def test_string_key_points_coerced(self):
        vr = validate_summarisation_output(STRING_KEY_POINTS)
        assert vr.ok
        assert vr.output is not None
        assert len(vr.output.key_points) == 2
        assert vr.output.key_points[0].point == "First point as a string"
        assert vr.output.key_points[0].chunk_ids == []

    def test_confidence_clamped(self):
        vr = validate_summarisation_output(CONFIDENCE_OUT_OF_RANGE)
        assert vr.ok
        assert vr.output is not None
        assert vr.output.structured_fields[0].confidence == 1.0
        assert vr.output.structured_fields[1].confidence == 0.0
        clamped = [i for i in vr.issues if "Confidence out of" in i.issue]
        assert len(clamped) == 2

    def test_missing_all_known_fields_still_partial(self):
        """If JSON is valid but has none of the expected keys, we get defaults."""
        vr = validate_summarisation_output(MISSING_ALL_FIELDS)
        assert vr.status == ValidationStatus.MISSING_REQUIRED
        assert not vr.ok


# ── Tests: Hard failures ─────────────────────────────────────────────────


class TestHardFailures:
    def test_empty_summary_text_is_error(self):
        vr = validate_summarisation_output(EMPTY_SUMMARY_TEXT)
        assert vr.status == ValidationStatus.MISSING_REQUIRED
        assert not vr.ok
        assert vr.error_count >= 1
        assert any(i.field == "summary_text" and i.severity == "error" for i in vr.issues)

    def test_completely_empty_dict(self):
        vr = validate_summarisation_output(COMPLETELY_EMPTY)
        assert vr.status == ValidationStatus.MISSING_REQUIRED
        assert not vr.ok

    def test_not_a_dict(self):
        vr = validate_summarisation_output(NOT_A_DICT)  # type: ignore[arg-type]
        assert vr.status == ValidationStatus.WRONG_STRUCTURE
        assert not vr.ok

    def test_array_root(self):
        vr = validate_summarisation_output(ARRAY_ROOT)  # type: ignore[arg-type]
        assert vr.status == ValidationStatus.WRONG_STRUCTURE
        assert not vr.ok


# ── Tests: Pydantic model directly ──────────────────────────────────────


class TestLLMSummarisationOutputModel:
    def test_valid_parse(self):
        output = LLMSummarisationOutput.model_validate(VALID_OUTPUT)
        assert output.summary_text == VALID_OUTPUT["summary_text"]
        assert len(output.key_points) == 3
        assert output.key_points[0].point == "Patient admitted on 2024-08-15."
        assert output.key_points[0].chunk_ids == ["c1"]

    def test_coerces_string_key_points(self):
        output = LLMSummarisationOutput.model_validate(STRING_KEY_POINTS)
        assert len(output.key_points) == 2
        assert output.key_points[0].point == "First point as a string"

    def test_defaults_for_empty(self):
        output = LLMSummarisationOutput.model_validate({})
        assert output.summary_text == ""
        assert output.key_points == []
        assert output.chunk_ids_used == []
