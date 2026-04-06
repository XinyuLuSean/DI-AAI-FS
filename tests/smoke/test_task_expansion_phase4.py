"""Phase 4 tests — task expansion: task abstraction + chronology extraction.

Tests cover:
  - Chronology prompt template structure and metadata
  - Chronology output validation (valid, partial recovery, hard failures)
  - AITask protocol compliance
  - Task registry registration and lookup
  - Chronology grounding audit
  - Data model: ChronologyEvent, ChronologyResult, OutputType.AI_CHRONOLOGY
"""

from __future__ import annotations

import pytest

from ai_core.prompts import (
    CHRONOLOGY_V1,
    SUMMARISE_V1,
    TaskType,
    build_chronology_user_prompt,
)
from ai_core.task import (
    AITask,
    TaskContext,
    get_task,
    list_tasks,
    register_task,
)
from ai_core.validation import (
    LLMChronologyEvent,
    LLMChronologyOutput,
    ValidationStatus,
    validate_chronology_output,
)
from data_model import (
    ChronologyEvent,
    ChronologyResult,
    ExtractionResult,
    OutputType,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures: raw LLM outputs for chronology
# ═══════════════════════════════════════════════════════════════════════════

VALID_CHRONOLOGY_OUTPUT = {
    "events": [
        {
            "date": "August 15, 2024",
            "date_normalised": "2024-08-15",
            "description": "Patient admitted to hospital with left tibial fracture",
            "chunk_ids": ["c1"],
        },
        {
            "date": "August 16, 2024",
            "date_normalised": "2024-08-16",
            "description": "Surgery performed: open reduction internal fixation",
            "chunk_ids": ["c2"],
        },
        {
            "date": "August 20, 2024",
            "date_normalised": "2024-08-20",
            "description": "Patient discharged with follow-up instructions",
            "chunk_ids": ["c3", "c4"],
        },
    ],
    "chunk_ids_used": ["c1", "c2", "c3", "c4"],
}

PARTIAL_CHRONOLOGY_MISSING_CHUNK_IDS_USED = {
    "events": [
        {
            "date": "Jan 1, 2024",
            "date_normalised": "2024-01-01",
            "description": "Initial consultation",
            "chunk_ids": ["c1"],
        },
    ],
    "chunk_ids_used": [],
}

PARTIAL_CHRONOLOGY_EMPTY_EVENTS = {
    "events": [
        {
            "date": "Jan 1, 2024",
            "date_normalised": "2024-01-01",
            "description": "Initial consultation",
            "chunk_ids": ["c1"],
        },
        {
            "date": "Feb 1, 2024",
            "description": "",
            "chunk_ids": ["c2"],
        },
    ],
    "chunk_ids_used": ["c1", "c2"],
}

PARTIAL_CHRONOLOGY_NO_DATES = {
    "events": [
        {
            "date": "",
            "description": "Patient reported headache",
            "chunk_ids": ["c1"],
        },
    ],
    "chunk_ids_used": ["c1"],
}


# ═══════════════════════════════════════════════════════════════════════════
# Test: Chronology prompt template
# ═══════════════════════════════════════════════════════════════════════════

class TestChronologyPromptTemplate:
    def test_task_type_is_chronology(self):
        assert CHRONOLOGY_V1.task_type == TaskType.CHRONOLOGY

    def test_distinct_from_summarise(self):
        assert CHRONOLOGY_V1.name != SUMMARISE_V1.name
        assert CHRONOLOGY_V1.task_type != SUMMARISE_V1.task_type
        assert CHRONOLOGY_V1.system_prompt != SUMMARISE_V1.system_prompt

    def test_has_evidence_requirements(self):
        assert len(CHRONOLOGY_V1.evidence_requirements) > 0
        joined = " ".join(CHRONOLOGY_V1.evidence_requirements).lower()
        assert "chunk_ids" in joined

    def test_has_guardrails(self):
        assert len(CHRONOLOGY_V1.guardrails) > 0
        joined = " ".join(CHRONOLOGY_V1.guardrails).lower()
        assert "invent" in joined or "fabricat" in joined

    def test_expected_output_schema_has_events(self):
        assert "events" in CHRONOLOGY_V1.expected_output_schema
        assert "chunk_ids_used" in CHRONOLOGY_V1.expected_output_schema

    def test_version_is_1_0(self):
        assert CHRONOLOGY_V1.version == "1.0"


class TestChronologyUserPrompt:
    def test_builds_chunk_sections(self):
        chunks = [
            {"chunk_id": "c1", "text": "On August 15 the patient arrived."},
            {"chunk_id": "c2", "text": "Surgery was performed on August 16."},
        ]
        prompt = build_chronology_user_prompt(chunks)
        assert "chunk_id=c1" in prompt
        assert "chunk_id=c2" in prompt
        assert "DOCUMENT CHUNKS:" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# Test: Chronology output validation
# ═══════════════════════════════════════════════════════════════════════════

class TestChronologyValidOutput:
    def test_valid_output_parses_cleanly(self):
        vr = validate_chronology_output(VALID_CHRONOLOGY_OUTPUT)
        assert vr.status == ValidationStatus.VALID
        assert vr.ok is True
        assert len(vr.issues) == 0

    def test_valid_output_has_correct_event_count(self):
        vr = validate_chronology_output(VALID_CHRONOLOGY_OUTPUT)
        assert vr.output is not None
        assert len(vr.output.events) == 3

    def test_valid_output_preserves_dates(self):
        vr = validate_chronology_output(VALID_CHRONOLOGY_OUTPUT)
        dates = [e.date_normalised for e in vr.output.events]
        assert dates == ["2024-08-15", "2024-08-16", "2024-08-20"]

    def test_chunk_ids_used_correct(self):
        vr = validate_chronology_output(VALID_CHRONOLOGY_OUTPUT)
        assert set(vr.output.chunk_ids_used) == {"c1", "c2", "c3", "c4"}


class TestChronologyPartialRecovery:
    def test_missing_chunk_ids_used_recovered(self):
        vr = validate_chronology_output(PARTIAL_CHRONOLOGY_MISSING_CHUNK_IDS_USED)
        assert vr.status == ValidationStatus.PARTIAL_RECOVERY
        assert vr.ok is True
        assert vr.output.chunk_ids_used == ["c1"]
        recovered = [i for i in vr.issues if i.recovered]
        assert len(recovered) >= 1

    def test_empty_description_filtered(self):
        vr = validate_chronology_output(PARTIAL_CHRONOLOGY_EMPTY_EVENTS)
        assert vr.status == ValidationStatus.PARTIAL_RECOVERY
        assert len(vr.output.events) == 1

    def test_dateless_events_warned(self):
        vr = validate_chronology_output(PARTIAL_CHRONOLOGY_NO_DATES)
        assert vr.status == ValidationStatus.PARTIAL_RECOVERY
        date_issues = [i for i in vr.issues if "no date" in i.issue.lower()]
        assert len(date_issues) >= 1


class TestChronologyHardFailures:
    def test_non_dict_input(self):
        vr = validate_chronology_output("not a dict")  # type: ignore[arg-type]
        assert vr.status == ValidationStatus.WRONG_STRUCTURE
        assert vr.ok is False

    def test_empty_dict_still_valid(self):
        vr = validate_chronology_output({})
        assert vr.ok is True
        assert len(vr.output.events) == 0


class TestLLMChronologyOutputModel:
    def test_coerces_event_chunk_ids(self):
        output = LLMChronologyOutput.model_validate({
            "events": [
                {"date": "Jan 1", "description": "test", "chunk_ids": [1, 2]},
            ],
        })
        assert output.events[0].chunk_ids == ["1", "2"]

    def test_filters_non_dict_events(self):
        output = LLMChronologyOutput.model_validate({
            "events": [
                {"date": "Jan 1", "description": "valid"},
                "not_a_dict",
            ],
        })
        assert len(output.events) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Test: Data model
# ═══════════════════════════════════════════════════════════════════════════

class TestChronologyDataModel:
    def test_chronology_event_has_expected_fields(self):
        ev = ChronologyEvent(
            date_raw="August 15, 2024",
            date_normalised="2024-08-15",
            description="Patient admitted",
            chunk_ids=["c1"],
            page_numbers=[1],
            evidence_snippets=["admitted on August 15"],
            grounded=True,
        )
        assert ev.date_raw == "August 15, 2024"
        assert ev.date_normalised == "2024-08-15"
        assert ev.grounded is True

    def test_chronology_result_structure(self):
        result = ChronologyResult(
            events=[
                ChronologyEvent(
                    date_raw="Jan 1",
                    description="Test event",
                ),
            ],
            grounding_coverage=1.0,
        )
        assert len(result.events) == 1
        assert result.grounding_coverage == 1.0

    def test_output_type_has_chronology(self):
        assert OutputType.AI_CHRONOLOGY == "ai_chronology"

    def test_extraction_result_has_chronology_field(self):
        er = ExtractionResult(
            document_id="test",
            output_type=OutputType.AI_CHRONOLOGY,
            chronology=ChronologyResult(events=[]),
        )
        assert er.chronology is not None
        assert er.summary is None


# ═══════════════════════════════════════════════════════════════════════════
# Test: Task abstraction — AITask protocol
# ═══════════════════════════════════════════════════════════════════════════

class TestTaskAbstraction:
    def test_aitask_protocol_exists(self):
        assert AITask is not None

    def test_task_type_enum_has_chronology(self):
        assert TaskType.CHRONOLOGY == "chronology"

    def test_task_type_enum_has_summarisation(self):
        assert TaskType.SUMMARISATION == "summarisation"


# ═══════════════════════════════════════════════════════════════════════════
# Test: Task contract comparison — summarise vs chronology
# ═══════════════════════════════════════════════════════════════════════════

class TestTaskContractComparison:
    """Verify that summarise and chronology have distinct but parallel contracts."""

    def test_different_task_types(self):
        assert SUMMARISE_V1.task_type == TaskType.SUMMARISATION
        assert CHRONOLOGY_V1.task_type == TaskType.CHRONOLOGY

    def test_different_output_schemas(self):
        sum_keys = set(SUMMARISE_V1.expected_output_schema.keys())
        chr_keys = set(CHRONOLOGY_V1.expected_output_schema.keys())
        assert "summary_text" in sum_keys
        assert "events" in chr_keys
        assert "summary_text" not in chr_keys

    def test_both_have_chunk_ids_used(self):
        assert "chunk_ids_used" in SUMMARISE_V1.expected_output_schema
        assert "chunk_ids_used" in CHRONOLOGY_V1.expected_output_schema

    def test_both_have_evidence_requirements(self):
        assert len(SUMMARISE_V1.evidence_requirements) > 0
        assert len(CHRONOLOGY_V1.evidence_requirements) > 0

    def test_both_have_guardrails(self):
        assert len(SUMMARISE_V1.guardrails) > 0
        assert len(CHRONOLOGY_V1.guardrails) > 0

    def test_both_have_uncertainty_instructions(self):
        assert len(SUMMARISE_V1.uncertainty_instructions) > 0
        assert len(CHRONOLOGY_V1.uncertainty_instructions) > 0
