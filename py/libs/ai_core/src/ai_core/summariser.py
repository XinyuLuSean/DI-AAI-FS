"""Document summarisation workflow.

Orchestrates: select chunks → resolve prompt template → build prompt
→ call LLM → validate output schema → audit grounding → package evidence
→ return structured output with audit trail.

This is the first AI task in the vertical slice.  It demonstrates:
- prompt templates as first-class objects (Phase 1)
- strict schema validation with failure classification (Phase 2)
- evidence references back to source chunks
- grounding by pre-extracted deterministic fields (when available)
- budget-aware chunk selection with explicit coverage reporting
- per-key-point evidence binding + grounding audit
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from data_model import (
    ChunkSelectionStrategy,
    Document,
    DocumentChunk,
    ExtractionResult,
    OutputType,
    StructuredField,
    SummaryResult,
)

from ai_core.adapter import LLMAdapter
from ai_core.grounding import audit_grounding, enrich_summarisation_meta
from ai_core.prompts import (
    GROUNDED_SUMMARISE_V1,
    SUMMARISE_V1,
    PromptTemplate,
    build_summarise_user_prompt,
)
from ai_core.validation import (
    ValidationStatus,
    validate_summarisation_output,
)
from di_core.chunk_selector import select_chunks_for_llm
from di_core.evidence import package_evidence_from_ids

logger = structlog.get_logger()


def summarise_document(
    doc: Document,
    llm: LLMAdapter | None = None,
    max_chunks: int = 10,
    chunk_selection: ChunkSelectionStrategy = ChunkSelectionStrategy.HEAD,
    grounding_fields: list[StructuredField] | None = None,
    prompt_template: PromptTemplate | None = None,
) -> ExtractionResult:
    """Run summarisation over a budget-selected subset of chunks.

    Pipeline: select → prompt → LLM → validate → audit grounding → package evidence.

    If prompt_template is not provided, the appropriate default is chosen
    based on whether grounding_fields are present.
    """
    llm = llm or LLMAdapter()
    start = time.perf_counter_ns()

    # ── Chunk selection ───────────────────────────────────────────────
    selected, summarisation_meta = select_chunks_for_llm(
        doc, max_chunks=max_chunks, strategy=chunk_selection,
    )

    chunk_dicts = [{"chunk_id": c.chunk_id, "text": c.text} for c in selected]
    chunk_map = {c.chunk_id: c for c in selected}
    provided_ids = set(chunk_map.keys())

    # ── Grounding fields (optional) ──────────────────────────────────
    extracted_field_dicts: list[dict[str, str]] | None = None
    if grounding_fields:
        extracted_field_dicts = [
            {
                "field_name": f.field_name,
                "field_value": f.field_value,
                "confidence": str(f.confidence),
            }
            for f in grounding_fields
        ]

    # ── Resolve prompt template ──────────────────────────────────────
    template = prompt_template
    if template is None:
        template = GROUNDED_SUMMARISE_V1 if grounding_fields else SUMMARISE_V1

    # ── Build and send prompt ────────────────────────────────────────
    user_prompt = build_summarise_user_prompt(chunk_dicts, extracted_field_dicts)

    raw: dict[str, Any] = llm.complete_json(
        system_prompt=template.system_prompt,
        user_prompt=user_prompt,
    )

    # ── Validate LLM output (Phase 2) ────────────────────────────────
    vr = validate_summarisation_output(raw)

    validation_warnings: list[str] = [
        f"[{issue.field}] {issue.issue}" for issue in vr.issues
    ]

    if not vr.ok:
        logger.warning(
            "summariser.validation_failed",
            doc_id=doc.id,
            status=vr.status.value,
            errors=vr.error_count,
            warnings=vr.warning_count,
            issues=validation_warnings,
        )
        elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)
        return ExtractionResult(
            document_id=doc.id,
            output_type=OutputType.AI_SUMMARY,
            model_used=llm.model,
            prompt_name=template.name,
            prompt_version=template.version,
            summary=SummaryResult(summary_text=""),
            summarisation_meta=summarisation_meta,
            validation_status=vr.status.value,
            validation_warnings=validation_warnings,
            processing_time_ms=elapsed_ms,
        )

    validated = vr.output
    assert validated is not None  # guaranteed by vr.ok

    if vr.status == ValidationStatus.PARTIAL_RECOVERY:
        logger.info(
            "summariser.validation_partial",
            doc_id=doc.id,
            warnings=vr.warning_count,
            issues=validation_warnings,
        )

    # ── Grounding audit ──────────────────────────────────────────────
    used_ids: list[str] = validated.chunk_ids_used
    evidence = package_evidence_from_ids(used_ids, chunk_map)

    raw_key_points = [
        {"point": kp.point, "chunk_ids": kp.chunk_ids}
        for kp in validated.key_points
    ]
    grounded_points, grounding_audit_result = audit_grounding(
        raw_key_points, used_ids, provided_ids, chunk_map,
    )

    plain_key_points = [gkp.text for gkp in grounded_points]
    grounded_count = sum(1 for gkp in grounded_points if gkp.grounded)
    grounding_coverage = grounded_count / len(grounded_points) if grounded_points else 0.0

    # ── Structured fields from LLM ───────────────────────────────────
    fields = [
        StructuredField(
            field_name=sf.field_name,
            field_value=sf.field_value,
            confidence=sf.confidence,
            extraction_method="llm",
            evidence=evidence,
        )
        for sf in validated.structured_fields
    ]

    # ── Assemble result ──────────────────────────────────────────────
    summary = SummaryResult(
        summary_text=validated.summary_text,
        key_points=plain_key_points,
        grounded_key_points=grounded_points,
        evidence=evidence,
        grounding_coverage=round(grounding_coverage, 4),
    )

    summarisation_meta = enrich_summarisation_meta(
        summarisation_meta, used_ids, chunk_map,
    )

    elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    return ExtractionResult(
        document_id=doc.id,
        output_type=OutputType.AI_SUMMARY,
        model_used=llm.model,
        prompt_name=template.name,
        prompt_version=template.version,
        structured_fields=fields,
        summary=summary,
        grounding_audit=grounding_audit_result,
        summarisation_meta=summarisation_meta,
        validation_status=vr.status.value,
        validation_warnings=validation_warnings,
        processing_time_ms=elapsed_ms,
    )
