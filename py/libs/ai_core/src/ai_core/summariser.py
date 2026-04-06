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
    ExperimentMeta,
    ExtractionResult,
    OutputType,
    RetrievalConfig,
    StructuredField,
    SummaryResult,
)

from ai_core.adapter import LLMAdapter
from ai_core.grounding import (
    apply_grounding_safeguards,
    audit_grounding,
    build_evidence_gap_analysis,
    enrich_summarisation_meta,
)
from ai_core.safety import (
    apply_safe_summary_degradation,
    build_uncertainty_assessment,
    detect_field_contradictions,
)
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
from di_core.coverage import CoverageReport, build_coverage_report
from di_core.evidence import package_evidence_from_ids

logger = structlog.get_logger()


def summarise_document(
    doc: Document,
    llm: LLMAdapter | None = None,
    max_chunks: int = 10,
    chunk_selection: ChunkSelectionStrategy = ChunkSelectionStrategy.HEAD,
    grounding_fields: list[StructuredField] | None = None,
    prompt_template: PromptTemplate | None = None,
    query: str | None = None,
    run_label: str = "",
) -> ExtractionResult:
    """Run summarisation over a budget-selected subset of chunks.

    Pipeline: select → prompt → LLM → validate → audit grounding → package evidence.

    When query is provided with QUERY_RANKED strategy, chunks are selected
    by relevance to the query rather than by position.

    If prompt_template is not provided, the appropriate default is chosen
    based on whether grounding_fields are present.
    """
    llm = llm or LLMAdapter()
    start = time.perf_counter_ns()

    # ── Chunk selection ───────────────────────────────────────────────
    selected, summarisation_meta = select_chunks_for_llm(
        doc, max_chunks=max_chunks, strategy=chunk_selection, query=query,
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

    # ── Coverage-aware input preparation (Phase 7B) ─────────────────
    coverage_report = build_coverage_report(doc, selected)

    # ── Build and send prompt ────────────────────────────────────────
    user_prompt = build_summarise_user_prompt(chunk_dicts, extracted_field_dicts)

    if coverage_report.coverage_level != "comprehensive":
        user_prompt = coverage_report.disclosure_text + "\n\n" + user_prompt

    raw: dict[str, Any] = llm.complete_json(
        system_prompt=template.system_prompt,
        user_prompt=user_prompt,
    )

    # ── Validate LLM output (Phase 2) ────────────────────────────────
    vr = validate_summarisation_output(raw)

    validation_warnings: list[str] = [
        f"[{issue.field}] {issue.issue}" for issue in vr.issues
    ]
    experiment_meta = ExperimentMeta(
        task_type="summarisation",
        prompt_name=template.name,
        prompt_version=template.version,
        model_used=llm.model,
        retrieval=RetrievalConfig(
            chunk_selection=chunk_selection,
            max_chunks=max_chunks,
            query=query or "",
        ),
        output_valid=vr.ok,
        validation_status=vr.status.value,
        run_label=run_label,
        notes=[
            f"coverage_level={coverage_report.coverage_level}",
            f"grounded_fields={'yes' if grounding_fields else 'no'}",
        ],
    )

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
            experiment_meta=experiment_meta,
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

    # ── Apply grounding safeguards (Phase 3B) ──────────────────────────
    grounded_points, grounding_audit_result = apply_grounding_safeguards(
        grounded_points, grounding_audit_result,
    )

    plain_key_points = [gkp.text for gkp in grounded_points]
    grounded_count = sum(1 for gkp in grounded_points if gkp.grounded)
    grounding_coverage = grounded_count / len(grounded_points) if grounded_points else 0.0

    # ── Evidence gap analysis (Phase 3C) ─────────────────────────────
    total_pages = doc.parse_meta.page_count if doc.parse_meta else len(doc.pages)
    evidence_gap = build_evidence_gap_analysis(
        grounded_points, provided_ids, used_ids, chunk_map,
        total_pages=total_pages,
    )

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
    contradiction_warnings = detect_field_contradictions(fields, grounding_fields)
    combined_validation_warnings = validation_warnings + contradiction_warnings

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

    parse_quality = doc.parse_meta.quality.value if doc.parse_meta else ""
    likely_low_quality_source = bool(
        doc.parse_meta and (
            doc.parse_meta.quality.value != "good"
            or doc.parse_meta.likely_needs_ocr
            or doc.parse_meta.likely_scanned
        )
    )
    unsupported_claim_count = (
        grounding_audit_result.key_points_ungrounded
        + grounding_audit_result.chunks_cited_invalid
    )
    uncertainty_assessment = build_uncertainty_assessment(
        parse_quality=parse_quality,
        likely_low_quality_source=likely_low_quality_source,
        coverage_level=coverage_report.coverage_level,
        grounding_score=grounding_audit_result.grounding_score,
        unsupported_claim_count=unsupported_claim_count,
        contradiction_warnings=contradiction_warnings,
        validation_status=vr.status.value,
        grounded_points=grounded_points,
    )
    summary = apply_safe_summary_degradation(summary, uncertainty_assessment)
    if uncertainty_assessment.review_recommended:
        experiment_meta.notes.append("review_recommended=yes")
    if uncertainty_assessment.abstained:
        experiment_meta.notes.append("safe_failure=abstained")

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
        evidence_gap=evidence_gap.model_dump(),
        coverage_report=coverage_report.model_dump(),
        experiment_meta=experiment_meta,
        uncertainty_assessment=uncertainty_assessment,
        validation_status=vr.status.value,
        validation_warnings=combined_validation_warnings,
        processing_time_ms=elapsed_ms,
    )
