"""Document API — upload, extraction, summarisation, inspection.

Endpoints:
  POST /documents/upload                      — accept a file, parse, chunk, store
  GET  /documents/{id}                        — retrieve document metadata + chunks
  POST /documents/{id}/extract                — deterministic field extraction (no LLM)
  POST /documents/{id}/summarise              — LLM-based summarisation
  GET  /documents/{id}/chunks/debug           — chunk inspection for debugging
  GET  /documents/{id}/extractions/{ext_id}   — retrieve extraction result
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, UploadFile

from data_model import ChunkSelectionStrategy, ChunkStrategy, Document, DocumentSource, DocumentStatus, ExtractionResult
from di_core import ChunkConfig, chunk_text, classify_document_size, extract_fields, parse_document, route_document
from storage import LocalStorage

from py_api.core.config import get_settings

logger = structlog.get_logger()
router = APIRouter()

_documents: dict[str, Document] = {}
_extractions: dict[str, ExtractionResult] = {}


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
    """Accept a file upload, parse it, chunk it, and return the document record."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

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

    chunk_cfg = ChunkConfig(
        strategy=chunk_strategy,
        chunk_size=chunk_size,
        overlap=chunk_overlap,
        max_chunks=max_chunks,
    )
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

    _documents[doc.id] = doc
    return doc


@router.get("/{document_id}")
async def get_document(document_id: str) -> Document:
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


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
            "preview": preview,
        })

    size_guard = classify_document_size(doc)

    return {
        "document_id": document_id,
        "filename": doc.filename,
        "size_category": doc.size_category,
        "size_guard": size_guard.model_dump(),
        "chunk_meta": doc.chunk_meta.model_dump() if doc.chunk_meta else None,
        "chunks": chunk_debug,
    }


@router.post("/{document_id}/extract")
async def extract(document_id: str) -> ExtractionResult:
    """Run deterministic field extraction (regex/heuristic — no LLM)."""
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.pages:
        raise HTTPException(status_code=422, detail="Document has no pages")

    result = extract_fields(doc)
    _extractions[result.id] = result

    logger.info(
        "document.extracted",
        doc_id=document_id,
        fields=len(result.structured_fields),
        time_ms=result.processing_time_ms,
        field_names=[f.field_name for f in result.structured_fields],
    )
    return result


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
    )
    return result


@router.get("/{document_id}/extractions/{extraction_id}")
async def get_extraction(document_id: str, extraction_id: str) -> ExtractionResult:
    result = _extractions.get(extraction_id)
    if result is None or result.document_id != document_id:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return result
