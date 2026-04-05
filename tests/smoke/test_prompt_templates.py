"""Prompt template sanity checks (Phase 1 — Module 1D).

Verifies:
  - PromptTemplate model is well-formed
  - Registered templates have required metadata
  - Registry lookup works
  - Prompt goals (evidence, uncertainty, guardrails) are non-empty
  - User prompt builder produces expected structure
  - A fixture-based input/output pair validates the prompt contract
"""

import json

import pytest

from ai_core.prompts import (
    GROUNDED_SUMMARISE_V1,
    SUMMARISE_V1,
    PromptTemplate,
    TaskType,
    build_summarise_user_prompt,
    get_prompt,
    list_prompts,
    register_prompt,
)


# ── Template well-formedness ──────────────────────────────────────────────


class TestPromptTemplateModel:
    def test_summarise_v1_has_required_metadata(self):
        t = SUMMARISE_V1
        assert t.name == "summarise"
        assert t.version == "1.0"
        assert t.task_type == TaskType.SUMMARISATION
        assert len(t.description) > 10
        assert len(t.system_prompt) > 50
        assert len(t.expected_output_schema) > 0
        assert len(t.model_assumptions) > 0

    def test_grounded_summarise_v1_has_required_metadata(self):
        t = GROUNDED_SUMMARISE_V1
        assert t.name == "grounded_summarise"
        assert t.version == "1.0"
        assert t.task_type == TaskType.SUMMARISATION
        assert len(t.description) > 10
        assert "ground truth" in t.system_prompt.lower() or "pre-extracted" in t.system_prompt.lower()

    def test_all_templates_have_goals(self):
        """Every registered template must have evidence, uncertainty, and guardrail docs."""
        for t in list_prompts():
            assert len(t.evidence_requirements) > 0, f"{t.name}@{t.version} missing evidence_requirements"
            assert len(t.uncertainty_instructions) > 0, f"{t.name}@{t.version} missing uncertainty_instructions"
            assert len(t.guardrails) > 0, f"{t.name}@{t.version} missing guardrails"


# ── Registry ──────────────────────────────────────────────────────────────


class TestPromptRegistry:
    def test_get_prompt_by_name(self):
        t = get_prompt("summarise", "1.0")
        assert t.name == "summarise"

    def test_get_grounded_prompt(self):
        t = get_prompt("grounded_summarise", "1.0")
        assert "ground truth" in t.system_prompt.lower() or "pre-extracted" in t.system_prompt.lower()

    def test_missing_prompt_raises(self):
        with pytest.raises(KeyError, match="not found"):
            get_prompt("nonexistent", "1.0")

    def test_list_prompts(self):
        prompts = list_prompts()
        assert len(prompts) >= 2
        names = {t.name for t in prompts}
        assert "summarise" in names
        assert "grounded_summarise" in names

    def test_register_custom_prompt(self):
        custom = PromptTemplate(
            name="test_custom",
            version="0.1",
            task_type=TaskType.SUMMARISATION,
            description="Test-only prompt",
            system_prompt="You are a test assistant.",
            evidence_requirements=["test"],
            uncertainty_instructions=["test"],
            guardrails=["test"],
        )
        register_prompt(custom)
        found = get_prompt("test_custom", "0.1")
        assert found.name == "test_custom"


# ── User prompt builder ──────────────────────────────────────────────────


class TestUserPromptBuilder:
    def test_chunks_only(self):
        chunks = [
            {"chunk_id": "c1", "text": "Alice signed the contract on Jan 1."},
            {"chunk_id": "c2", "text": "The total amount was $5,000."},
        ]
        prompt = build_summarise_user_prompt(chunks)
        assert "[chunk_id=c1]" in prompt
        assert "[chunk_id=c2]" in prompt
        assert "Alice signed" in prompt
        assert "PRE-EXTRACTED" not in prompt

    def test_with_grounding_fields(self):
        chunks = [{"chunk_id": "c1", "text": "Some text."}]
        fields = [
            {"field_name": "date", "field_value": "2024-01-01", "confidence": "0.95"},
        ]
        prompt = build_summarise_user_prompt(chunks, extracted_fields=fields)
        assert "PRE-EXTRACTED FIELDS" in prompt
        assert "date: 2024-01-01" in prompt
        assert "confidence: 0.95" in prompt


# ── Fixture-based prompt contract test ───────────────────────────────────


FIXTURE_CHUNKS = [
    {"chunk_id": "chunk_001", "text": "Patient John Smith, DOB 1985-03-12, was admitted on 2024-08-15 for treatment of a fractured left tibia."},
    {"chunk_id": "chunk_002", "text": "X-ray confirmed a displaced fracture of the proximal tibia. Surgery was scheduled for August 16."},
    {"chunk_id": "chunk_003", "text": "The total billed amount for the procedure was $12,450.00, covered under insurance policy #INS-9982."},
]

FIXTURE_GROUNDING_FIELDS = [
    {"field_name": "patient_name", "field_value": "John Smith", "confidence": "0.98"},
    {"field_name": "admission_date", "field_value": "2024-08-15", "confidence": "0.95"},
    {"field_name": "total_amount", "field_value": "$12,450.00", "confidence": "0.92"},
]

FIXTURE_EXPECTED_OUTPUT = {
    "summary_text": "John Smith was admitted on 2024-08-15 for treatment of a fractured left tibia. Surgery was performed on August 16. The total billed amount was $12,450.00.",
    "key_points": [
        {"point": "Patient John Smith was admitted on 2024-08-15 for a fractured left tibia.", "chunk_ids": ["chunk_001"]},
        {"point": "X-ray confirmed a displaced fracture; surgery was scheduled for August 16.", "chunk_ids": ["chunk_002"]},
        {"point": "Total billed amount was $12,450.00 under insurance policy #INS-9982.", "chunk_ids": ["chunk_003"]},
    ],
    "structured_fields": [
        {"field_name": "document_type", "field_value": "medical", "confidence": 0.9},
    ],
    "chunk_ids_used": ["chunk_001", "chunk_002", "chunk_003"],
}


class TestPromptFixture:
    """Validate that the prompt + fixture pair form a coherent contract.

    This does NOT call the LLM — it validates the structural contract:
    the prompt asks for a specific schema, and the fixture output
    conforms to that schema.  This catches drift between what the prompt
    requests and what downstream code expects.
    """

    def test_fixture_output_matches_expected_schema(self):
        """The fixture output must have all keys the prompt schema requires."""
        schema = SUMMARISE_V1.expected_output_schema
        for key in schema:
            assert key in FIXTURE_EXPECTED_OUTPUT, f"Fixture missing required key: {key}"

    def test_fixture_key_points_have_chunk_ids(self):
        for kp in FIXTURE_EXPECTED_OUTPUT["key_points"]:
            assert "point" in kp, "key_point missing 'point'"
            assert "chunk_ids" in kp, "key_point missing 'chunk_ids'"
            assert len(kp["chunk_ids"]) > 0, f"key_point has empty chunk_ids: {kp['point'][:40]}"

    def test_fixture_chunk_ids_used_is_union(self):
        all_cited = set()
        for kp in FIXTURE_EXPECTED_OUTPUT["key_points"]:
            all_cited.update(kp["chunk_ids"])
        declared = set(FIXTURE_EXPECTED_OUTPUT["chunk_ids_used"])
        assert all_cited == declared, (
            f"chunk_ids_used mismatch: declared={declared}, actual union={all_cited}"
        )

    def test_fixture_chunk_ids_are_valid(self):
        """All cited chunks must be in the fixture input."""
        input_ids = {c["chunk_id"] for c in FIXTURE_CHUNKS}
        cited_ids = set(FIXTURE_EXPECTED_OUTPUT["chunk_ids_used"])
        invalid = cited_ids - input_ids
        assert not invalid, f"Fixture cites chunks not in input: {invalid}"

    def test_grounded_prompt_includes_fields_in_user_prompt(self):
        prompt = build_summarise_user_prompt(FIXTURE_CHUNKS, FIXTURE_GROUNDING_FIELDS)
        assert "John Smith" in prompt
        assert "2024-08-15" in prompt
        assert "$12,450.00" in prompt

    def test_fixture_output_is_valid_json_string(self):
        """Ensure the fixture can round-trip through JSON serialization."""
        serialized = json.dumps(FIXTURE_EXPECTED_OUTPUT)
        parsed = json.loads(serialized)
        assert parsed["summary_text"] == FIXTURE_EXPECTED_OUTPUT["summary_text"]
