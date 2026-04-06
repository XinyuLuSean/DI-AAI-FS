"""Phase 11 tests — hallucination control, uncertainty, and safe failure."""

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
from ai_core.summariser import summarise_document
from di_core.review_queue import classify_review_triggers


class FakeLLM:
    def __init__(self, payload: dict, model: str = "fake-llm") -> None:
        self.payload = payload
        self.model = model

    def complete_json(self, system_prompt: str, user_prompt: str, response_schema=None):  # noqa: ANN001
        return self.payload


def _make_doc(parse_quality: ParseQuality = ParseQuality.GOOD, n_chunks: int = 4) -> Document:
    chunks = []
    pages = []
    for i in range(n_chunks):
        text = f"Page {i + 1} content about the claim and water damage."
        pages.append(DocumentPage(page_number=i + 1, text=text, char_count=len(text)))
        chunks.append(
            DocumentChunk(
                chunk_id=f"c{i + 1}",
                document_id="doc-safe",
                index=i,
                text=text,
                page_numbers=[i + 1],
                token_estimate=len(text.split()),
            )
        )
    return Document(
        id="doc-safe",
        filename="sample.txt",
        status=DocumentStatus.CHUNKED,
        parse_meta=ParseMeta(
            page_count=n_chunks,
            total_chars=sum(len(p.text) for p in pages),
            quality=parse_quality,
            likely_needs_ocr=parse_quality != ParseQuality.GOOD,
        ),
        pages=pages,
        chunks=chunks,
    )


def test_safe_failure_abstains_on_weak_evidence() -> None:
    doc = _make_doc(parse_quality=ParseQuality.DEGRADED, n_chunks=6)
    llm = FakeLLM({
        "summary_text": "This appears to describe many damages across the file.",
        "key_points": [
            {"point": "Likely severe damage exists.", "chunk_ids": []},
            {"point": "Payment may be required.", "chunk_ids": []},
        ],
        "structured_fields": [],
        "chunk_ids_used": [],
    })

    result = summarise_document(
        doc,
        llm=llm,
        max_chunks=1,
        chunk_selection=ChunkSelectionStrategy.HEAD,
    )

    assert result.uncertainty_assessment is not None
    assert result.uncertainty_assessment.abstained is True
    assert result.uncertainty_assessment.review_recommended is True
    assert result.summary is not None
    assert "Abstained:" in result.summary.summary_text
    assert result.summary.key_points == []


def test_deterministic_contradiction_triggers_review() -> None:
    doc = _make_doc()
    llm = FakeLLM({
        "summary_text": "Claim number differs from extracted record.",
        "key_points": [
            {"point": "Claim number is CLM-999.", "chunk_ids": ["c1"]},
        ],
        "structured_fields": [
            {"field_name": "claim_number", "field_value": "CLM-999", "confidence": 0.9},
        ],
        "chunk_ids_used": ["c1"],
    })
    grounding_fields = [
        StructuredField(field_name="claim_number", field_value="CLM-001", confidence=0.99),
    ]

    result = summarise_document(
        doc,
        llm=llm,
        grounding_fields=grounding_fields,
    )

    assert result.uncertainty_assessment is not None
    assert len(result.uncertainty_assessment.contradiction_warnings) == 1
    triggers = classify_review_triggers(result)
    assert "deterministic_contradiction" in triggers
    assert any("conflicts with deterministic value" in warning for warning in result.validation_warnings)
