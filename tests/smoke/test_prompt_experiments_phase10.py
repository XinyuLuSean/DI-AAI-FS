"""Phase 10 tests — prompt optimization and experiment tracking."""

from __future__ import annotations

from data_model import (
    ChunkSelectionStrategy,
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentStatus,
    ParseMeta,
    ParseQuality,
    StructuredField,
)

from ai_core import get_prompt, list_prompt_registry
from di_eval import format_experiment_report, run_summary_experiment, ExperimentVariant


class FakeLLM:
    def __init__(self, model: str, canned: dict) -> None:
        self.model = model
        self._canned = canned

    def complete_json(self, system_prompt: str, user_prompt: str, response_schema=None):  # noqa: ANN001
        return self._canned


def _make_doc() -> Document:
    text = (
        "Jane Doe reported water damage from a burst pipe on January 15, 2024. "
        "Estimated repair cost was $20,600. Adjuster John Smith recommended net "
        "payment of $19,600 after deductible."
    )
    return Document(
        id="phase10-doc",
        filename="sample.txt",
        status=DocumentStatus.CHUNKED,
        parse_meta=ParseMeta(page_count=1, total_chars=len(text), quality=ParseQuality.GOOD),
        pages=[DocumentPage(page_number=1, text=text, char_count=len(text))],
        chunks=[
            DocumentChunk(
                chunk_id="c1",
                document_id="phase10-doc",
                index=0,
                text=text,
                page_numbers=[1],
                token_estimate=len(text.split()),
            )
        ],
    )


def test_prompt_registry_lists_versions() -> None:
    entries = list_prompt_registry()
    refs = {(entry.name, entry.version) for entry in entries}
    assert ("summarise", "1.0") in refs
    assert ("summarise", "1.1") in refs
    assert any(entry.recommended_model for entry in entries)


def test_get_prompt_v1_1_exists() -> None:
    prompt = get_prompt("summarise", "1.1")
    assert prompt.version == "1.1"
    assert len(prompt.notes) > 0


def test_run_summary_experiment_returns_comparison() -> None:
    doc = _make_doc()
    expected_key_facts = [
        "Water damage from burst pipe on January 15, 2024",
        "Estimated repair cost $20,600",
        "Recommended net payment $19,600 after deductible",
    ]
    grounding_fields = [
        StructuredField(field_name="patient_name", field_value="Jane Doe", confidence=0.95),
    ]

    canned_outputs = {
        "baseline": {
            "summary_text": "Water damage claim with estimated repairs.",
            "key_points": [
                {"point": "Water damage occurred on January 15, 2024.", "chunk_ids": ["c1"]},
            ],
            "structured_fields": [],
            "chunk_ids_used": ["c1"],
        },
        "decision_v11": {
            "summary_text": "Jane Doe reported burst-pipe water damage on January 15, 2024. Estimated repairs were $20,600 and the adjuster recommended $19,600 net payment after deductible.",
            "key_points": [
                {"point": "Burst-pipe water damage was reported on January 15, 2024.", "chunk_ids": ["c1"]},
                {"point": "Estimated repairs were $20,600.", "chunk_ids": ["c1"]},
                {"point": "Recommended net payment was $19,600 after deductible.", "chunk_ids": ["c1"]},
            ],
            "structured_fields": [],
            "chunk_ids_used": ["c1"],
        },
    }

    def llm_factory(variant: ExperimentVariant) -> FakeLLM:
        key = "decision_v11" if variant.prompt_version == "1.1" else "baseline"
        return FakeLLM(model=variant.model, canned=canned_outputs[key])

    comparison = run_summary_experiment(
        doc=doc,
        expected_key_facts=expected_key_facts,
        grounding_fields=grounding_fields,
        variants=[
            ExperimentVariant(
                label="baseline",
                prompt_name="summarise",
                prompt_version="1.0",
                model="fake-mini",
                chunk_selection=ChunkSelectionStrategy.HEAD,
            ),
            ExperimentVariant(
                label="decision_v11",
                prompt_name="summarise",
                prompt_version="1.1",
                model="fake-mini",
                chunk_selection=ChunkSelectionStrategy.HEAD,
                use_grounding_fields=True,
            ),
        ],
        llm_factory=llm_factory,
    )

    assert len(comparison.rows) == 2
    assert comparison.best_factual_coverage == "decision_v11"
    assert any(row.result and row.result.experiment_meta for row in comparison.rows)

    report = format_experiment_report(comparison)
    assert "PROMPT EXPERIMENT COMPARISON REPORT" in report
    assert "decision_v11" in report
