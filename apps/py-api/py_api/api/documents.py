"""Document API — upload, extraction, summarisation, retrieval, review, inspection.

Endpoints:
  GET  /documents                                       — list all documents (lightweight)
  POST /documents/upload                                — accept a file, parse, preprocess, chunk, enrich, store
  GET  /documents/review-queue                          — list items needing review (Phase 11)
  GET  /documents/{id}                                  — retrieve document metadata + chunks
  GET  /documents/{id}/extractions                      — list extractions for a document (with review status)
  POST /documents/{id}/extract                          — deterministic field extraction (no LLM) + postprocessing
  POST /documents/{id}/summarise                        — LLM-based summarisation
  POST /documents/{id}/search                           — rank chunks against a query
  GET  /documents/{id}/chunks/debug                     — chunk inspection for debugging
  GET  /documents/{id}/extractions/{ext_id}             — retrieve extraction result
  POST /documents/{id}/extractions/{ext_id}/review      — submit a review decision (Phase 11)
  POST /documents/{id}/extractions/{ext_id}/correct     — submit corrections (Phase 11)
  GET  /documents/{id}/extractions/{ext_id}/review      — get review status (Phase 11)
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, UploadFile

from pydantic import BaseModel, Field

from datetime import UTC, datetime

from data_model import (
    ChunkSelectionStrategy,
    ChunkStrategy,
    CorrectionRecord,
    Document,
    DocumentSource,
    DocumentStatus,
    EvidenceReference,
    ExtractionResult,
    FeedbackSignal,
    PipelineStage,
    PipelineTrace,
    ReviewableOutput,
    ReviewDecision,
    ReviewStatus,
)
from di_core import (
    ChunkConfig,
    LexicalRanker,
    SalienceRanker,
    chunk_text,
    classify_document_size,
    create_reviewable_output,
    enrich_chunks_for_retrieval,
    extract_fields,
    generate_feedback_signals,
    log_pipeline_summary,
    package_evidence,
    parse_document,
    postprocess_extraction,
    preprocess_document,
    rank_chunks,
    route_document,
    trace_stage,
)
from storage import LocalStorage

from py_api.core.config import get_settings

logger = structlog.get_logger()
router = APIRouter()

_documents: dict[str, Document] = {}
_extractions: dict[str, ExtractionResult] = {}
_reviewables: dict[str, ReviewableOutput] = {}  # keyed by extraction_id
_corrections: dict[str, CorrectionRecord] = {}  # keyed by correction_id
_feedback: list[FeedbackSignal] = []


def _ensure_reviewable(extraction_id: str) -> ReviewableOutput:
    """Get or create a ReviewableOutput for an extraction, using document context."""
    if extraction_id in _reviewables:
        return _reviewables[extraction_id]
    result = _extractions[extraction_id]
    doc = _documents.get(result.document_id)
    parse_quality = doc.parse_meta.quality if doc and doc.parse_meta else None
    routing_confidence = doc.routing.confidence if doc and doc.routing else None
    reviewable = create_reviewable_output(
        result,
        parse_quality=parse_quality,
        routing_confidence=routing_confidence,
    )
    _reviewables[extraction_id] = reviewable
    return reviewable


# ── Request / response models ─────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    ranker: str = Field(default="salience", pattern="^(lexical|salience)$")


class SearchResult(BaseModel):
    document_id: str
    query: str
    ranker: str
    results: list[EvidenceReference]


class SubmitReviewRequest(BaseModel):
    status: ReviewStatus
    reviewer_id: str = ""
    notes: str = ""


class SubmitCorrectionRequest(BaseModel):
    reviewer_id: str = ""
    field_corrections: list[dict] = Field(default_factory=list)
    summary_correction: dict | None = None
    evidence_mismatches: list[dict] = Field(default_factory=list)
    parse_complaints: list[dict] = Field(default_factory=list)
    notes: str = ""


class ReviewQueueResponse(BaseModel):
    items: list[ReviewableOutput]
    total: int
    pending_count: int
    auto_accepted_count: int


class DocumentListItem(BaseModel):
    """Lightweight document summary for list views (no pages/chunks payload)."""
    id: str
    filename: str
    status: str
    content_type: str
    doc_type: str | None = None
    page_count: int = 0
    chunk_count: int = 0
    size_category: str | None = None
    extraction_count: int = 0
    created_at: str


class ExtractionListItem(BaseModel):
    """Extraction summary with review status for document detail view."""
    id: str
    document_id: str
    output_type: str
    model_used: str
    field_count: int = 0
    has_summary: bool = False
    processing_time_ms: int = 0
    review_status: str | None = None
    review_triggers: list[str] = Field(default_factory=list)
    review_priority: float = 0.0
    created_at: str


def _get_storage() -> LocalStorage:
    settings = get_settings()
    return LocalStorage(base_dir=settings.storage_local_path)


@router.post("/upload")
async def upload_document(
    file: UploadFile,
    chunk_strategy: ChunkStrategy = Query(default=ChunkStrategy.FIXED_SIZE),
    chunk_size: int = Query(default=800, ge=100, le=8000),
    chunk_overlap: int = Query(default=200, ge=0),
    max_chunks: int | None = Query(default=None, ge=1),
) -> Document:
    """Accept a file upload, parse, preprocess, chunk, and return the document record.

    The pipeline now records a PipelineTrace with per-stage timing and
    failure classification (Phase 10).
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    trace = PipelineTrace()

    storage = _get_storage()
    content = await file.read()
    stored_path = storage.save_bytes(file.filename, content)

    doc = Document(
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        status=DocumentStatus.PENDING,
        source=DocumentSource(
            storage_backend="local",
            path=stored_path,
            original_filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            size_bytes=len(content),
        ),
    )

    logger.info("document.upload", doc_id=doc.id, filename=file.filename, size=len(content))

    # ── Stage: Parse ──────────────────────────────────────────────────
    with trace_stage(trace, PipelineStage.PARSE):
        doc = parse_document(doc, stored_path)

    if doc.parse_meta:
        logger.info(
            "document.parsed",
            doc_id=doc.id,
            strategy=doc.parse_meta.parse_strategy,
            suffix=doc.parse_meta.file_suffix,
            pages=doc.parse_meta.page_count,
            empty_pages=doc.parse_meta.empty_page_count,
            total_chars=doc.parse_meta.total_chars,
            text_density=round(doc.parse_meta.text_density, 1),
            failure_reason=doc.parse_meta.failure_reason.value,
            warnings=doc.parse_meta.warnings,
        )

    if doc.status == DocumentStatus.FAILED:
        doc.pipeline_trace = trace.model_dump()
        _documents[doc.id] = doc
        failure_reason = ""
        if doc.parse_meta:
            failure_reason = doc.parse_meta.failure_reason.value
        raise HTTPException(
            status_code=422,
            detail={
                "message": doc.error or "Parsing failed",
                "failure_reason": failure_reason,
            },
        )

    # ── Stage: Preprocess (Phase 10A) ────────────────────────────────
    with trace_stage(trace, PipelineStage.PREPROCESS):
        doc, preprocess_meta = preprocess_document(doc)
        doc.preprocess_meta = preprocess_meta.model_dump()

    logger.info(
        "document.preprocessed",
        doc_id=doc.id,
        chars_before=preprocess_meta.chars_before,
        chars_after=preprocess_meta.chars_after,
        chars_removed=preprocess_meta.chars_removed,
        headers_removed=preprocess_meta.headers_removed,
        footers_removed=preprocess_meta.footers_removed,
        duplicates_suppressed=preprocess_meta.duplicate_lines_suppressed,
        warnings=preprocess_meta.warnings,
    )

    # ── Stage: Route ──────────────────────────────────────────────────
    with trace_stage(trace, PipelineStage.ROUTE):
        doc.routing = route_document(doc)

    logger.info(
        "document.routed",
        doc_id=doc.id,
        predicted_type=doc.routing.predicted_type.value,
        confidence=doc.routing.confidence,
        rules=len(doc.routing.matched_rules),
        is_fallback=doc.routing.is_fallback,
        warnings=doc.routing.warnings,
    )

    # ── Stage: Chunk ──────────────────────────────────────────────────
    chunk_cfg = ChunkConfig(
        strategy=chunk_strategy,
        chunk_size=chunk_size,
        overlap=chunk_overlap,
        max_chunks=max_chunks,
    )
    with trace_stage(trace, PipelineStage.CHUNK):
        doc = chunk_text(doc, chunk_cfg)

    if doc.chunk_meta:
        logger.info(
            "document.chunked",
            doc_id=doc.id,
            strategy=doc.chunk_meta.strategy.value,
            chunks=doc.chunk_meta.chunk_count,
            avg_chars=doc.chunk_meta.avg_chunk_chars,
            truncated=doc.chunk_meta.is_truncated,
            pages_covered=len(doc.chunk_meta.page_coverage),
        )

    # ── Stage: Size classify ──────────────────────────────────────────
    with trace_stage(trace, PipelineStage.SIZE_CLASSIFY):
        size_guard = classify_document_size(doc)
        doc.size_category = size_guard.category

    logger.info(
        "document.size_classified",
        doc_id=doc.id,
        category=size_guard.category.value,
        pages=size_guard.page_count,
        chars=size_guard.total_chars,
        chunks=size_guard.chunk_count,
        file_bytes=size_guard.file_size_bytes,
        recommended_llm_chunks=size_guard.recommended_max_llm_chunks,
        warnings=size_guard.warnings,
    )

    # ── Stage: Enrich ─────────────────────────────────────────────────
    with trace_stage(trace, PipelineStage.ENRICH):
        doc = enrich_chunks_for_retrieval(doc)

    doc.status = DocumentStatus.COMPLETED
    logger.info(
        "document.enriched",
        doc_id=doc.id,
        sections=len(doc.sections),
        section_labels=[s.label for s in doc.sections],
    )

    # ── Finalize pipeline trace ───────────────────────────────────────
    doc.pipeline_trace = trace.model_dump()
    log_pipeline_summary(trace, doc.id)

    _documents[doc.id] = doc
    return doc


# ── List endpoints (must be before /{document_id} to avoid route conflict) ──

@router.get("", response_model=list[DocumentListItem])
async def list_documents() -> list[DocumentListItem]:
    """Return lightweight summaries of all uploaded documents, newest first."""
    items: list[DocumentListItem] = []
    for doc in _documents.values():
        ext_count = sum(
            1 for e in _extractions.values() if e.document_id == doc.id
        )
        items.append(DocumentListItem(
            id=doc.id,
            filename=doc.filename,
            status=doc.status.value,
            content_type=doc.content_type,
            doc_type=doc.routing.predicted_type.value if doc.routing else None,
            page_count=len(doc.pages),
            chunk_count=len(doc.chunks),
            size_category=doc.size_category.value if doc.size_category else None,
            extraction_count=ext_count,
            created_at=doc.created_at.isoformat(),
        ))
    items.sort(key=lambda d: d.created_at, reverse=True)
    return items


@router.get("/review-queue", response_model=ReviewQueueResponse)
async def get_review_queue() -> ReviewQueueResponse:
    """List all reviewable items, sorted by priority (highest first).

    Returns all items including auto-accepted ones.  The response includes
    separate counts for pending and auto-accepted items so the UI can
    filter or badge as needed.
    """
    all_items = list(_reviewables.values())
    pending = [r for r in all_items if r.status == ReviewStatus.PENDING_REVIEW]
    auto_accepted = [r for r in all_items if r.status == ReviewStatus.AUTO_ACCEPTED]

    sorted_items = sorted(all_items, key=lambda r: r.priority_score, reverse=True)

    return ReviewQueueResponse(
        items=sorted_items,
        total=len(all_items),
        pending_count=len(pending),
        auto_accepted_count=len(auto_accepted),
    )


@router.get("/{document_id}")
async def get_document(document_id: str) -> Document:
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{document_id}/extractions", response_model=list[ExtractionListItem])
async def list_extractions(document_id: str) -> list[ExtractionListItem]:
    """List all extractions for a document, with review status attached."""
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    items: list[ExtractionListItem] = []
    for ext in _extractions.values():
        if ext.document_id != document_id:
            continue
        review = _reviewables.get(ext.id)
        items.append(ExtractionListItem(
            id=ext.id,
            document_id=ext.document_id,
            output_type=ext.output_type,
            model_used=ext.model_used,
            field_count=len(ext.structured_fields),
            has_summary=ext.summary is not None,
            processing_time_ms=ext.processing_time_ms,
            review_status=review.status.value if review else None,
            review_triggers=[t.value for t in review.trigger_reasons] if review else [],
            review_priority=review.priority_score if review else 0.0,
            created_at=ext.created_at.isoformat() if hasattr(ext.created_at, "isoformat") else str(ext.created_at),
        ))
    items.sort(key=lambda e: e.created_at, reverse=True)
    return items


@router.get("/{document_id}/chunks/debug")
async def debug_chunks(document_id: str) -> dict[str, Any]:
    """Return a compact debug view of a document's chunks for inspection.

    Includes size classification and summarisation-readiness information
    so large-document behavior is transparent.
    """
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    chunk_debug = []
    for c in doc.chunks:
        preview = c.text[:120].replace("\n", " ")
        if len(c.text) > 120:
            preview += "…"
        chunk_debug.append({
            "index": c.index,
            "chunk_id": c.chunk_id,
            "chars": len(c.text),
            "tokens_est": c.token_estimate,
            "pages": c.page_numbers,
            "char_span": [c.char_start, c.char_end],
            "strategy": c.strategy,
            "is_truncated": c.is_truncated,
            "doc_type": c.doc_type,
            "section_label": c.section_label,
            "parse_quality": c.parse_quality,
            "preview": preview,
        })

    size_guard = classify_document_size(doc)

    return {
        "document_id": document_id,
        "filename": doc.filename,
        "size_category": doc.size_category,
        "size_guard": size_guard.model_dump(),
        "sections": [s.model_dump() for s in doc.sections],
        "chunk_meta": doc.chunk_meta.model_dump() if doc.chunk_meta else None,
        "chunks": chunk_debug,
    }


@router.post("/{document_id}/extract")
async def extract(document_id: str) -> ExtractionResult:
    """Run deterministic field extraction (regex/heuristic — no LLM) + postprocessing."""
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.pages:
        raise HTTPException(status_code=422, detail="Document has no pages")

    result = extract_fields(doc)

    result, postprocess_meta = postprocess_extraction(result)

    _extractions[result.id] = result
    reviewable = _ensure_reviewable(result.id)

    logger.info(
        "document.extracted",
        doc_id=document_id,
        fields=len(result.structured_fields),
        time_ms=result.processing_time_ms,
        field_names=[f.field_name for f in result.structured_fields],
        dates_normalized=postprocess_meta.dates_normalized,
        currencies_normalized=postprocess_meta.currencies_normalized,
        evidence_deduped=postprocess_meta.evidence_deduped,
        review_status=reviewable.status.value,
        review_triggers=[t.value for t in reviewable.trigger_reasons],
        review_priority=reviewable.priority_score,
    )
    return result


@router.post("/{document_id}/search")
async def search_chunks(document_id: str, body: SearchRequest) -> SearchResult:
    """Rank document chunks against a query and return citation-ready results.

    Available rankers:
      salience — heuristic scoring using position, section, metadata, keywords
      lexical  — keyword overlap scoring (term frequency)
    """
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.chunks:
        raise HTTPException(status_code=422, detail="Document has no chunks")

    ranker_impl = SalienceRanker() if body.ranker == "salience" else LexicalRanker()
    ranked = rank_chunks(doc.chunks, body.query, ranker=ranker_impl, top_k=body.top_k)

    scores = {r.chunk.chunk_id: r.score for r in ranked}
    evidence = package_evidence(
        [r.chunk for r in ranked],
        relevance_scores=scores,
    )

    logger.info(
        "document.search",
        doc_id=document_id,
        query=body.query[:80],
        ranker=body.ranker,
        results=len(evidence),
        top_score=ranked[0].score if ranked else 0.0,
    )

    return SearchResult(
        document_id=document_id,
        query=body.query,
        ranker=body.ranker,
        results=evidence,
    )


@router.post("/{document_id}/summarise")
async def summarise(
    document_id: str,
    extraction_id: str | None = Query(default=None),
    max_chunks: int = Query(default=10, ge=1, le=100),
    chunk_selection: ChunkSelectionStrategy = Query(
        default=ChunkSelectionStrategy.HEAD,
    ),
) -> ExtractionResult:
    """Run AI summarisation on a previously uploaded document.

    When extraction_id is provided, the prior deterministic extraction's fields
    are injected into the LLM prompt as grounding constraints so the summary
    stays consistent with known facts.

    chunk_selection controls how chunks are chosen for the LLM context budget:
      head          — first N chunks (default, fast, biased to beginning)
      tail          — last N chunks
      head_tail     — first N/2 + last N/2
      sampled       — evenly spaced across all chunks
      routing_aware — adapts based on document type
    """
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.chunks:
        raise HTTPException(status_code=422, detail="Document has no chunks")

    from ai_core import summarise_document

    grounding_fields = None
    if extraction_id:
        prior = _extractions.get(extraction_id)
        if prior and prior.document_id == document_id:
            grounding_fields = prior.structured_fields
            logger.info(
                "document.summarise_grounded",
                doc_id=document_id,
                extraction_id=extraction_id,
                grounding_fields=len(grounding_fields),
            )

    result = summarise_document(
        doc,
        max_chunks=max_chunks,
        chunk_selection=chunk_selection,
        grounding_fields=grounding_fields,
    )
    _extractions[result.id] = result
    reviewable = _ensure_reviewable(result.id)

    sm = result.summarisation_meta
    logger.info(
        "document.summarised",
        doc_id=document_id,
        model=result.model_used,
        time_ms=result.processing_time_ms,
        grounded=grounding_fields is not None,
        selection_strategy=sm.selection_strategy.value if sm else None,
        chunks_sent=sm.chunks_sent_to_llm if sm else None,
        total_available=sm.total_chunks_available if sm else None,
        coverage=sm.coverage_ratio if sm else None,
        is_partial=sm.is_partial if sm else None,
        review_status=reviewable.status.value,
        review_triggers=[t.value for t in reviewable.trigger_reasons],
    )
    return result


@router.post("/{document_id}/chronology")
async def chronology(
    document_id: str,
    max_chunks: int = Query(default=10, ge=1, le=100),
    chunk_selection: ChunkSelectionStrategy = Query(
        default=ChunkSelectionStrategy.HEAD,
    ),
) -> ExtractionResult:
    """Run AI chronology extraction on a previously uploaded document.

    Extracts a timeline of dated events from the document with evidence
    references back to source chunks.

    chunk_selection controls how chunks are chosen for the LLM context budget
    (same options as /summarise).
    """
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.chunks:
        raise HTTPException(status_code=422, detail="Document has no chunks")

    from ai_core import extract_chronology

    result = extract_chronology(
        doc,
        max_chunks=max_chunks,
        chunk_selection=chunk_selection,
    )
    _extractions[result.id] = result
    reviewable = _ensure_reviewable(result.id)

    sm = result.summarisation_meta
    logger.info(
        "document.chronology_extracted",
        doc_id=document_id,
        model=result.model_used,
        time_ms=result.processing_time_ms,
        events=len(result.chronology.events) if result.chronology else 0,
        selection_strategy=sm.selection_strategy.value if sm else None,
        chunks_sent=sm.chunks_sent_to_llm if sm else None,
        review_status=reviewable.status.value,
    )
    return result


@router.get("/{document_id}/extractions/{extraction_id}")
async def get_extraction(document_id: str, extraction_id: str) -> ExtractionResult:
    result = _extractions.get(extraction_id)
    if result is None or result.document_id != document_id:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return result


# ── HITL: Review and Correction (Phase 11) ────────────────────────────────

@router.post("/{document_id}/extractions/{extraction_id}/review")
async def submit_review(
    document_id: str,
    extraction_id: str,
    body: SubmitReviewRequest,
) -> ReviewableOutput:
    """Submit a human review decision for an extraction result.

    Transitions the ReviewableOutput to the new status and records
    the decision with reviewer identity and notes.
    """
    result = _extractions.get(extraction_id)
    if result is None or result.document_id != document_id:
        raise HTTPException(status_code=404, detail="Extraction not found")

    reviewable = _ensure_reviewable(extraction_id)

    decision = ReviewDecision(
        extraction_id=extraction_id,
        document_id=document_id,
        reviewer_id=body.reviewer_id,
        status=body.status,
        notes=body.notes,
    )
    reviewable.decisions.append(decision)
    reviewable.status = body.status
    reviewable.updated_at = datetime.now(UTC)

    logger.info(
        "hitl.review_submitted",
        doc_id=document_id,
        extraction_id=extraction_id,
        status=body.status.value,
        reviewer=body.reviewer_id,
        triggers=[t.value for t in reviewable.trigger_reasons],
        priority=reviewable.priority_score,
    )

    return reviewable


@router.get("/{document_id}/extractions/{extraction_id}/review")
async def get_review_status(
    document_id: str,
    extraction_id: str,
) -> ReviewableOutput:
    """Get the current review status for an extraction result.

    If no review exists yet, creates a ReviewableOutput with
    auto-classified triggers and priority.
    """
    result = _extractions.get(extraction_id)
    if result is None or result.document_id != document_id:
        raise HTTPException(status_code=404, detail="Extraction not found")

    return _ensure_reviewable(extraction_id)


@router.post("/{document_id}/extractions/{extraction_id}/correct")
async def submit_correction(
    document_id: str,
    extraction_id: str,
    body: SubmitCorrectionRequest,
) -> dict[str, Any]:
    """Submit corrections for an extraction result.

    Creates a CorrectionRecord, generates feedback signals, and
    transitions the review status to CORRECTED.
    """
    from data_model.review import (
        EvidenceMismatchReport,
        FieldCorrection,
        ParseQualityComplaint,
        SummaryCorrection,
    )

    result = _extractions.get(extraction_id)
    if result is None or result.document_id != document_id:
        raise HTTPException(status_code=404, detail="Extraction not found")

    field_map = {f.field_name: f for f in result.structured_fields}
    field_corrections = []
    for fc in body.field_corrections:
        fname = fc.get("field_name", "")
        original = field_map[fname] if fname in field_map else None
        field_corrections.append(FieldCorrection(
            field_name=fname,
            original_value=original.field_value if original else "",
            corrected_value=fc.get("corrected_value", ""),
            original_confidence=original.confidence if original else 0.0,
            reason=fc.get("reason", ""),
            corrected_by=body.reviewer_id,
        ))

    summary_correction = None
    if body.summary_correction and result.summary:
        summary_correction = SummaryCorrection(
            original_summary_text=result.summary.summary_text,
            corrected_summary_text=body.summary_correction.get("corrected_summary_text", ""),
            reason=body.summary_correction.get("reason", ""),
            corrected_by=body.reviewer_id,
        )

    evidence_mismatches = [
        EvidenceMismatchReport(**em) for em in body.evidence_mismatches
    ]
    parse_complaints = [
        ParseQualityComplaint(**pc) for pc in body.parse_complaints
    ]

    correction = CorrectionRecord(
        extraction_id=extraction_id,
        document_id=document_id,
        reviewer_id=body.reviewer_id,
        field_corrections=field_corrections,
        summary_correction=summary_correction,
        evidence_mismatches=evidence_mismatches,
        parse_complaints=parse_complaints,
        notes=body.notes,
    )
    _corrections[correction.id] = correction

    signals = generate_feedback_signals(correction)
    _feedback.extend(signals)

    if extraction_id in _reviewables:
        reviewable = _reviewables[extraction_id]
        reviewable.status = ReviewStatus.CORRECTED
        reviewable.correction_id = correction.id

    logger.info(
        "hitl.correction_submitted",
        doc_id=document_id,
        extraction_id=extraction_id,
        correction_id=correction.id,
        field_corrections=len(field_corrections),
        summary_corrected=summary_correction is not None,
        evidence_mismatches=len(evidence_mismatches),
        parse_complaints=len(parse_complaints),
        feedback_signals=len(signals),
        reviewer=body.reviewer_id,
    )

    return {
        "correction_id": correction.id,
        "total_corrections": correction.total_corrections,
        "feedback_signals_generated": len(signals),
        "review_status": _reviewables[extraction_id].status.value if extraction_id in _reviewables else "pending_review",
    }
