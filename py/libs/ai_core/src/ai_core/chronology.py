"""Chronology extraction workflow — the second AI task.

Extracts a timeline of dated events from document chunks with evidence
references.  Follows the same pipeline pattern as summarisation:
  select chunks → build prompt → LLM call → validate → audit grounding → package result

This task demonstrates the task abstraction (Phase 4): same infrastructure,
different prompt, different output schema, different evaluation criteria.

Key differences from summarisation:
  - Output is a list of dated events, not a narrative summary
  - Evidence is per-event, not per-key-point
  - Evaluation focuses on date accuracy and event completeness, not narrative quality
  - Grounding checks that events trace to real chunks
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from data_model import (
    ChronologyEvent,
    ChronologyResult,
    ChunkSelectionStrategy,
    Document,
    DocumentChunk,
    EvidenceReference,
    ExtractionResult,
    GroundingAudit,
    OutputType,
    StructuredField,
    SummarisationMeta,
)

from ai_core.adapter import LLMAdapter
from ai_core.grounding import (
    _extract_best_snippet,
    build_evidence_gap_analysis,
    enrich_summarisation_meta,
)
from ai_core.prompts import (
    CHRONOLOGY_V1,
    PromptTemplate,
    build_chronology_user_prompt,
)
from ai_core.validation import (
    LLMChronologyOutput,
    ValidationStatus,
    validate_chronology_output,
)
from di_core.chunk_selector import select_chunks_for_llm
from di_core.evidence import package_evidence_from_ids

logger = structlog.get_logger()


def _audit_chronology_grounding(
    events: list[LLMChronologyOutput],
    used_ids: list[str],
    provided_ids: set[str],
    chunk_map: dict[str, DocumentChunk],
) -> tuple[list[ChronologyEvent], GroundingAudit]:
    """Build ChronologyEvent list with per-event evidence and grounding audit.

    Parallel to audit_grounding in grounding.py but adapted for the
    chronology event structure instead of key points.
    """
    grounded_events: list[ChronologyEvent] = []
    total_grounded = 0
    total_ungrounded = 0
    valid_cited = set()
    invalid_cited = set()

    for ev in events:
        event_grounded = False
        page_nums: list[int] = []
        snippets: list[str] = []

        for cid in ev.chunk_ids:
            if cid in provided_ids:
                valid_cited.add(cid)
                event_grounded = True
                chunk = chunk_map.get(cid)
                if chunk:
                    page_nums.extend(chunk.page_numbers)
                    snippets.append(
                        _extract_best_snippet(chunk.text, ev.description)
                    )
            else:
                invalid_cited.add(cid)

        if event_grounded:
            total_grounded += 1
        else:
            total_ungrounded += 1

        grounded_events.append(ChronologyEvent(
            date_raw=ev.date,
            date_normalised=ev.date_normalised,
            description=ev.description,
            chunk_ids=ev.chunk_ids,
            page_numbers=sorted(set(page_nums)),
            evidence_snippets=snippets,
            grounded=event_grounded,
        ))

    total = total_grounded + total_ungrounded
    score = total_grounded / total if total > 0 else 0.0

    warnings: list[str] = []
    needs_review = False

    if invalid_cited:
        warnings.append(
            f"LLM cited {len(invalid_cited)} chunk ID(s) not in provided set"
        )
        needs_review = True

    if total_grounded == 0 and total > 0:
        warnings.append("No events have valid evidence — entire timeline ungrounded")
        needs_review = True

    audit = GroundingAudit(
        chunks_provided=len(provided_ids),
        chunks_cited_by_llm=len(valid_cited | invalid_cited),
        chunks_cited_valid=len(valid_cited),
        chunks_cited_invalid=len(invalid_cited),
        key_points_total=total,
        key_points_grounded=total_grounded,
        key_points_ungrounded=total_ungrounded,
        grounding_score=round(score, 4),
        needs_review=needs_review,
        warnings=warnings,
    )

    return grounded_events, audit


def extract_chronology(
    doc: Document,
    llm: LLMAdapter | None = None,
    max_chunks: int = 10,
    chunk_selection: ChunkSelectionStrategy = ChunkSelectionStrategy.HEAD,
    prompt_template: PromptTemplate | None = None,
    query: str | None = None,
) -> ExtractionResult:
    """Run chronology extraction over a budget-selected subset of chunks.

    Pipeline: select → prompt → LLM → validate → audit grounding → package result.

    When query is provided with QUERY_RANKED strategy, chunks are selected
    by relevance to the query rather than by position.
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

    # ── Resolve prompt template ──────────────────────────────────────
    template = prompt_template or CHRONOLOGY_V1

    # ── Build and send prompt ────────────────────────────────────────
    user_prompt = build_chronology_user_prompt(chunk_dicts)

    raw: dict[str, Any] = llm.complete_json(
        system_prompt=template.system_prompt,
        user_prompt=user_prompt,
    )

    # ── Validate LLM output ──────────────────────────────────────────
    vr = validate_chronology_output(raw)

    validation_warnings: list[str] = [
        f"[{issue.field}] {issue.issue}" for issue in vr.issues
    ]

    if not vr.ok:
        logger.warning(
            "chronology.validation_failed",
            doc_id=doc.id,
            status=vr.status.value,
            errors=vr.error_count,
            warnings=vr.warning_count,
            issues=validation_warnings,
        )
        elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)
        return ExtractionResult(
            document_id=doc.id,
            output_type=OutputType.AI_CHRONOLOGY,
            model_used=llm.model,
            prompt_name=template.name,
            prompt_version=template.version,
            chronology=ChronologyResult(),
            summarisation_meta=summarisation_meta,
            validation_status=vr.status.value,
            validation_warnings=validation_warnings,
            processing_time_ms=elapsed_ms,
        )

    validated: LLMChronologyOutput = vr.output
    assert validated is not None

    if vr.status == ValidationStatus.PARTIAL_RECOVERY:
        logger.info(
            "chronology.validation_partial",
            doc_id=doc.id,
            warnings=vr.warning_count,
            issues=validation_warnings,
        )

    # ── Grounding audit ──────────────────────────────────────────────
    used_ids: list[str] = validated.chunk_ids_used
    evidence = package_evidence_from_ids(used_ids, chunk_map)

    grounded_events, grounding_audit = _audit_chronology_grounding(
        validated.events, used_ids, provided_ids, chunk_map,
    )

    grounded_count = sum(1 for e in grounded_events if e.grounded)
    coverage = grounded_count / len(grounded_events) if grounded_events else 0.0

    # ── Evidence gap analysis ────────────────────────────────────────
    from data_model import GroundedKeyPoint
    pseudo_key_points = [
        GroundedKeyPoint(
            text=ev.description,
            chunk_ids=ev.chunk_ids,
            grounded=ev.grounded,
            page_numbers=ev.page_numbers,
            evidence_snippets=ev.evidence_snippets,
        )
        for ev in grounded_events
    ]
    total_pages = doc.parse_meta.page_count if doc.parse_meta else len(doc.pages)
    evidence_gap = build_evidence_gap_analysis(
        pseudo_key_points, provided_ids, used_ids, chunk_map,
        total_pages=total_pages,
    )

    # ── Assemble result ──────────────────────────────────────────────
    chronology = ChronologyResult(
        events=grounded_events,
        evidence=evidence,
        grounding_coverage=round(coverage, 4),
    )

    summarisation_meta = enrich_summarisation_meta(
        summarisation_meta, used_ids, chunk_map,
    )

    elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    return ExtractionResult(
        document_id=doc.id,
        output_type=OutputType.AI_CHRONOLOGY,
        model_used=llm.model,
        prompt_name=template.name,
        prompt_version=template.version,
        chronology=chronology,
        grounding_audit=grounding_audit,
        summarisation_meta=summarisation_meta,
        evidence_gap=evidence_gap.model_dump(),
        validation_status=vr.status.value,
        validation_warnings=validation_warnings,
        processing_time_ms=elapsed_ms,
    )
