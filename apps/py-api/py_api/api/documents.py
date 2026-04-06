"""Document API — upload, extraction, summarisation, retrieval, review, inspection.

Endpoints:
  GET  /documents                                       — list all documents (lightweight)
  POST /documents/upload                                — accept a file, parse, preprocess, chunk, enrich, store
  GET  /documents/review-queue                          — list items needing review (Phase 11)
  GET  /documents/{id}                                  — retrieve document metadata + chunks
  GET  /documents/{id}/extractions                      — list extractions for a document (with review status)
  POST /documents/{id}/extract                          — deterministic field extraction (no LLM) + postprocessing
  POST /documents/{id}/summarise                        — LLM-based summarisation
  POST /documents/{id}/classify                         — explainable document readiness classification (Phase 8)
  POST /documents/{id}/semantic-match                  — align extracted facts to supporting chunks (Phase 8)
  POST /documents/{id}/search                           — rank chunks against a query
  GET  /documents/{id}/chunks/debug                     — chunk inspection for debugging
  GET  /documents/{id}/extractions/{ext_id}             — retrieve extraction result
  POST /documents/{id}/extractions/{ext_id}/review      — submit a review decision (Phase 11)
  POST /documents/{id}/extractions/{ext_id}/correct     — submit corrections (Phase 11)
  GET  /documents/{id}/extractions/{ext_id}/corrections — list stored corrections for one extraction
  GET  /documents/{id}/feedback-signals                 — list feedback signals for one document
  GET  /documents/{id}/extractions/{ext_id}/review      — get review status (Phase 11)
"""

from __future__ import annotations

import time
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
    OutputType,
    PipelineStage,
    PipelineTrace,
    ReviewableOutput,
    ReviewDecision,
    ReviewStatus,
)
from di_core import (
    ChunkConfig,
    ComparisonReport,
    LexicalRanker,
    SalienceRanker,
    chunk_text,
    classify_document_size,
    compare_strategies,
    compare_with_hybrid,
    create_reviewable_output,
    enrich_chunks_for_retrieval,
    align_extracted_fields_to_chunks,
    extract_fields,
    classify_document_readiness,
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
    document_type = doc.routing.predicted_type if doc and doc.routing else None
    reviewable = create_reviewable_output(
        result,
        parse_quality=parse_quality,
        routing_confidence=routing_confidence,
        document_type=document_type,
    )
    _reviewables[extraction_id] = reviewable
    return reviewable


def _latest_extraction_for_document(
    document_id: str,
    output_type: OutputType | None = None,
) -> ExtractionResult | None:
    """Return the newest extraction for a document, optionally filtered by type."""
    candidates = [
        result for result in _extractions.values()
        if result.document_id == document_id
        and (output_type is None or result.output_type == output_type)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda result: result.created_at)


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


class CompareRequest(BaseModel):
    query: str
    max_chunks: int = Field(default=5, ge=1, le=50)
    include_hybrid: bool = Field(default=False)


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


class CorrectionSubmissionResponse(BaseModel):
    correction_id: str
    total_corrections: int
    feedback_signals_generated: int
    review_status: str
    correction: CorrectionRecord
    feedback_signals: list[FeedbackSignal]


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
    prompt_name: str = ""
    prompt_version: str = ""
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


def _raise_provider_http_error(exc: Exception, *, operation: str) -> None:
    from ai_core import LLMProviderError

    if not isinstance(exc, LLMProviderError):
        raise exc

    logger.warning(
        "document.ai_provider_error",
        operation=operation,
        provider=exc.provider,
        model=exc.model,
        retryable=exc.retryable,
        attempts=exc.attempts,
        error=str(exc)[:200],
    )
    raise HTTPException(
        status_code=503,
        detail={
            "message": f"{operation} failed due to upstream AI provider error",
            "provider": exc.provider,
            "model": exc.model,
            "retryable": exc.retryable,
            "attempts": exc.attempts,
            "error": str(exc),
        },
    ) from exc


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
            prompt_name=ext.prompt_name,
            prompt_version=ext.prompt_version,
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
    t0 = time.perf_counter_ns()
    ranked = rank_chunks(doc.chunks, body.query, ranker=ranker_impl, top_k=body.top_k)
    retrieval_ms = int((time.perf_counter_ns() - t0) / 1_000_000)

    from ai_core import record_retrieval_latency

    record_retrieval_latency(retrieval_ms)

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
        retrieval_ms=retrieval_ms,
    )

    return SearchResult(
        document_id=document_id,
        query=body.query,
        ranker=body.ranker,
        results=evidence,
    )


@router.post("/{document_id}/retrieval-compare")
async def retrieval_compare(
    document_id: str,
    body: CompareRequest,
) -> ComparisonReport:
    """Compare chunk selection strategies side-by-side for a given query.

    Runs all strategies (head, head_tail, sampled, routing_aware, query_ranked)
    against the same document and query, then reports which chunks each selects,
    overlap between strategies, and a plain-English recommendation.
    """
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.chunks:
        raise HTTPException(status_code=422, detail="Document has no chunks")

    t0 = time.perf_counter_ns()
    if body.include_hybrid:
        report = compare_with_hybrid(
            doc, query=body.query, max_chunks=body.max_chunks,
        )
    else:
        report = compare_strategies(
            doc, query=body.query, max_chunks=body.max_chunks,
        )
    retrieval_ms = int((time.perf_counter_ns() - t0) / 1_000_000)

    from ai_core import record_retrieval_latency

    record_retrieval_latency(retrieval_ms)

    logger.info(
        "document.retrieval_compare",
        doc_id=document_id,
        query=body.query[:80],
        max_chunks=body.max_chunks,
        strategies=len(report.strategies),
        recommendation=report.recommendation[:120],
        retrieval_ms=retrieval_ms,
    )

    return report


@router.post("/{document_id}/summarise")
async def summarise(
    document_id: str,
    extraction_id: str | None = Query(default=None),
    max_chunks: int = Query(default=10, ge=1, le=100),
    chunk_selection: ChunkSelectionStrategy = Query(
        default=ChunkSelectionStrategy.HEAD,
    ),
    query: str | None = Query(default=None),
    prompt_name: str | None = Query(default=None),
    prompt_version: str = Query(default="1.0"),
    model: str | None = Query(default=None),
    run_label: str = Query(default=""),
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
      query_ranked  — rank by relevance to query (requires query parameter)
      diversified   — section-aware selection balancing relevance with diversity
    """
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.chunks:
        raise HTTPException(status_code=422, detail="Document has no chunks")

    from ai_core import LLMProviderError, record_ai_task_result, summarise_document
    from ai_core.prompts import get_prompt
    from ai_core.adapter import LLMAdapter

    grounding_fields = None
    if extraction_id:
        prior = _extractions.get(extraction_id)
        if prior is None or prior.document_id != document_id:
            raise HTTPException(status_code=404, detail="Extraction not found")
        grounding_fields = prior.structured_fields or None
        logger.info(
            "document.summarise_grounded",
            doc_id=document_id,
            extraction_id=extraction_id,
            grounding_fields=len(grounding_fields or []),
        )

    prompt_template = None
    if prompt_name:
        try:
            prompt_template = get_prompt(prompt_name, prompt_version)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Prompt '{prompt_name}@{prompt_version}' not found",
            ) from exc

    llm = LLMAdapter(model=model) if model else None

    try:
        result = summarise_document(
            doc,
            llm=llm,
            max_chunks=max_chunks,
            chunk_selection=chunk_selection,
            grounding_fields=grounding_fields,
            prompt_template=prompt_template,
            query=query,
            run_label=run_label,
        )
    except LLMProviderError as exc:
        _raise_provider_http_error(exc, operation="summarise")
    _extractions[result.id] = result
    reviewable = _ensure_reviewable(result.id)
    record_ai_task_result(result)

    sm = result.summarisation_meta
    logger.info(
        "document.summarised",
        doc_id=document_id,
        model=result.model_used,
        time_ms=result.processing_time_ms,
        grounded=grounding_fields is not None,
        prompt_name=result.prompt_name,
        prompt_version=result.prompt_version,
        selection_strategy=sm.selection_strategy.value if sm else None,
        chunks_sent=sm.chunks_sent_to_llm if sm else None,
        total_available=sm.total_chunks_available if sm else None,
        coverage=sm.coverage_ratio if sm else None,
        is_partial=sm.is_partial if sm else None,
        review_status=reviewable.status.value,
        review_triggers=[t.value for t in reviewable.trigger_reasons],
    )
    return result


@router.post("/{document_id}/classify")
async def classify(
    document_id: str,
    extraction_id: str | None = Query(default=None),
) -> ExtractionResult:
    """Run an explainable document-readiness classification.

    This classification is intentionally non-generative. It combines parse,
    routing, chunk, and optional extraction signals to decide whether the
    document is ready, review-recommended, or blocked for higher-trust AI use.
    """
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    prior = None
    if extraction_id:
        prior = _extractions.get(extraction_id)
        if prior is None or prior.document_id != document_id:
            raise HTTPException(status_code=404, detail="Extraction not found")
    else:
        prior = _latest_extraction_for_document(document_id, OutputType.DETERMINISTIC)

    result = classify_document_readiness(doc, extraction=prior)
    _extractions[result.id] = result
    reviewable = _ensure_reviewable(result.id)

    logger.info(
        "document.classified",
        doc_id=document_id,
        label=result.classification.label if result.classification else None,
        confidence=result.classification.confidence if result.classification else None,
        review_status=reviewable.status.value,
    )
    return result


@router.post("/{document_id}/semantic-match")
async def semantic_match(
    document_id: str,
    extraction_id: str | None = Query(default=None),
    top_k: int = Query(default=1, ge=1, le=5),
    threshold: float = Query(default=0.35, ge=0.0, le=1.0),
) -> ExtractionResult:
    """Align extracted fields to supporting chunks using semantic similarity.

    Reuses deterministic structured outputs as the query anchors, then scores
    every chunk by lexical overlap plus embedding similarity. This makes fact-
    to-evidence QA more inspectable than free-form generation.
    """
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.chunks:
        raise HTTPException(status_code=422, detail="Document has no chunks")

    prior = None
    if extraction_id:
        prior = _extractions.get(extraction_id)
        if prior is None or prior.document_id != document_id:
            raise HTTPException(status_code=404, detail="Extraction not found")
    else:
        prior = _latest_extraction_for_document(document_id, OutputType.DETERMINISTIC)

    if prior is None or not prior.structured_fields:
        raise HTTPException(
            status_code=422,
            detail="Semantic matching requires a deterministic extraction with fields",
        )

    result = align_extracted_fields_to_chunks(
        doc,
        extraction=prior,
        top_k=top_k,
        threshold=threshold,
    )
    _extractions[result.id] = result
    reviewable = _ensure_reviewable(result.id)

    logger.info(
        "document.semantic_matched",
        doc_id=document_id,
        matched=result.semantic_match.matched_count if result.semantic_match else None,
        unmatched=result.semantic_match.unmatched_count if result.semantic_match else None,
        threshold=threshold,
        review_status=reviewable.status.value,
    )
    return result


@router.post("/{document_id}/chronology")
async def chronology(
    document_id: str,
    max_chunks: int = Query(default=10, ge=1, le=100),
    chunk_selection: ChunkSelectionStrategy = Query(
        default=ChunkSelectionStrategy.HEAD,
    ),
    query: str | None = Query(default=None),
) -> ExtractionResult:
    """Run AI chronology extraction on a previously uploaded document.

    Extracts a timeline of dated events from the document with evidence
    references back to source chunks.

    chunk_selection controls how chunks are chosen for the LLM context budget
    (same options as /summarise, including query_ranked with a query parameter).
    """
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.chunks:
        raise HTTPException(status_code=422, detail="Document has no chunks")

    from ai_core import LLMProviderError, extract_chronology, record_ai_task_result

    try:
        result = extract_chronology(
            doc,
            max_chunks=max_chunks,
            chunk_selection=chunk_selection,
            query=query,
        )
    except LLMProviderError as exc:
        _raise_provider_http_error(exc, operation="chronology")
    _extractions[result.id] = result
    reviewable = _ensure_reviewable(result.id)
    record_ai_task_result(result)

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


@router.post("/{document_id}/hierarchical-summarise")
async def hierarchical_summarise_endpoint(
    document_id: str,
) -> ExtractionResult:
    """Run hierarchical MapReduce summarisation on a document.

    Processes ALL chunks through a 3-stage pipeline:
      1. Chunk-level fact extraction (deterministic, no LLM)
      2. Section-level aggregation (deterministic)
      3. Document-level synthesis (single LLM call)

    This approach handles long documents without chunk budget limits
    because the LLM only sees compact section summaries, not raw text.
    """
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.chunks:
        raise HTTPException(status_code=422, detail="Document has no chunks")

    from ai_core import LLMProviderError, hierarchical_summarise, record_ai_task_result

    try:
        result = hierarchical_summarise(doc)
    except LLMProviderError as exc:
        _raise_provider_http_error(exc, operation="hierarchical_summarise")
    _extractions[result.id] = result
    _ensure_reviewable(result.id)
    record_ai_task_result(result)

    logger.info(
        "document.hierarchical_summarised",
        doc_id=document_id,
        model=result.model_used,
        time_ms=result.processing_time_ms,
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
) -> CorrectionSubmissionResponse:
    """Submit corrections for an extraction result.

    Creates a CorrectionRecord, generates feedback signals, and
    transitions the review status to CORRECTED.
    """
    from data_model.review import (
        EvidenceMismatchReport,
        FeedbackFailureSource,
        FeedbackFailureType,
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
            failure_type=fc.get("failure_type", FeedbackFailureType.WRONG_VALUE),
            failure_source=fc.get(
                "failure_source",
                FeedbackFailureSource.DETERMINISTIC_EXTRACTION,
            ),
            suggested_chunk_id=fc.get("suggested_chunk_id", ""),
            corrected_by=body.reviewer_id,
        ))

    summary_correction = None
    if body.summary_correction and result.summary:
        summary_correction = SummaryCorrection(
            original_summary_text=result.summary.summary_text,
            corrected_summary_text=body.summary_correction.get("corrected_summary_text", ""),
            reason=body.summary_correction.get("reason", ""),
            failure_type=body.summary_correction.get(
                "failure_type",
                FeedbackFailureType.UNSUPPORTED_CLAIM,
            ),
            failure_source=body.summary_correction.get(
                "failure_source",
                FeedbackFailureSource.PROMPT,
            ),
            supporting_chunk_ids=body.summary_correction.get("supporting_chunk_ids", []),
            corrected_by=body.reviewer_id,
        )

    evidence_mismatches = []
    for em in body.evidence_mismatches:
        mismatch_type = em.get("mismatch_type", "")
        evidence_mismatches.append(EvidenceMismatchReport(
            field_name=em.get("field_name", ""),
            key_point_text=em.get("key_point_text", ""),
            chunk_id=em.get("chunk_id", ""),
            mismatch_type=mismatch_type,
            failure_type=em.get(
                "failure_type",
                FeedbackFailureType.MISSING_EVIDENCE if mismatch_type == "missing" else FeedbackFailureType.WRONG_EVIDENCE,
            ),
            failure_source=em.get(
                "failure_source",
                FeedbackFailureSource.RETRIEVAL,
            ),
            suggested_chunk_id=em.get("suggested_chunk_id", ""),
            suggested_evidence_snippet=em.get("suggested_evidence_snippet", ""),
            explanation=em.get("explanation", ""),
            reported_by=body.reviewer_id,
        ))

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

    reviewable = _ensure_reviewable(extraction_id)
    reviewable.status = ReviewStatus.CORRECTED
    reviewable.correction_id = correction.id
    reviewable.updated_at = datetime.now(UTC)

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

    return CorrectionSubmissionResponse(
        correction_id=correction.id,
        total_corrections=correction.total_corrections,
        feedback_signals_generated=len(signals),
        review_status=reviewable.status.value,
        correction=correction,
        feedback_signals=signals,
    )


@router.get(
    "/{document_id}/extractions/{extraction_id}/corrections",
    response_model=list[CorrectionRecord],
)
async def list_corrections(
    document_id: str,
    extraction_id: str,
) -> list[CorrectionRecord]:
    """List stored corrections for one extraction."""
    result = _extractions.get(extraction_id)
    if result is None or result.document_id != document_id:
        raise HTTPException(status_code=404, detail="Extraction not found")

    corrections = [
        correction for correction in _corrections.values()
        if correction.document_id == document_id and correction.extraction_id == extraction_id
    ]
    return sorted(corrections, key=lambda correction: correction.created_at, reverse=True)


@router.get(
    "/{document_id}/feedback-signals",
    response_model=list[FeedbackSignal],
)
async def list_feedback_signals(document_id: str) -> list[FeedbackSignal]:
    """List feedback signals derived from corrections for a document."""
    if document_id not in _documents:
        raise HTTPException(status_code=404, detail="Document not found")
    signals = [
        signal for signal in _feedback
        if signal.document_id == document_id
    ]
    return sorted(signals, key=lambda signal: signal.created_at, reverse=True)
