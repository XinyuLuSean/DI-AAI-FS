"""Size-aware guards for large-document processing.

Classifies documents by size and attaches warnings/recommendations so
downstream stages (chunking, summarisation) can adapt behaviour.  Guards
are informational — they do not block processing but make large-document
limitations explicit.

Thresholds (page-count based for PDFs, char-count based for text files):
  SMALL      ≤ 20 pages / ≤ 50 000 chars
  MEDIUM     ≤ 200 pages / ≤ 1 000 000 chars
  LARGE      ≤ 2 000 pages / ≤ 10 000 000 chars
  OVERSIZED  > 2 000 pages / > 10 000 000 chars
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from data_model import Document, DocumentSizeCategory

PAGE_THRESHOLDS: list[tuple[int, DocumentSizeCategory]] = [
    (20, DocumentSizeCategory.SMALL),
    (200, DocumentSizeCategory.MEDIUM),
    (2_000, DocumentSizeCategory.LARGE),
]

CHAR_THRESHOLDS: list[tuple[int, DocumentSizeCategory]] = [
    (50_000, DocumentSizeCategory.SMALL),
    (1_000_000, DocumentSizeCategory.MEDIUM),
    (10_000_000, DocumentSizeCategory.LARGE),
]

BYTES_THRESHOLDS: list[tuple[int, DocumentSizeCategory]] = [
    (50_000, DocumentSizeCategory.SMALL),
    (2_000_000, DocumentSizeCategory.MEDIUM),
    (50_000_000, DocumentSizeCategory.LARGE),
]


class SizeGuardResult(BaseModel):
    """Output of size classification + guard evaluation."""

    category: DocumentSizeCategory = DocumentSizeCategory.SMALL
    page_count: int = 0
    total_chars: int = 0
    file_size_bytes: int = 0
    chunk_count: int = 0
    recommended_max_llm_chunks: int = 10
    warnings: list[str] = Field(default_factory=list)


def classify_document_size(doc: Document) -> SizeGuardResult:
    """Classify a document by size and produce guard recommendations.

    Should be called after parse + chunk so all signals are available.
    """
    page_count = doc.parse_meta.page_count if doc.parse_meta else len(doc.pages)
    total_chars = doc.parse_meta.total_chars if doc.parse_meta else sum(p.char_count for p in doc.pages)
    file_size = doc.source.size_bytes if doc.source else 0
    chunk_count = len(doc.chunks)

    category = _classify(page_count, total_chars, file_size)
    warnings: list[str] = []
    recommended = _recommended_llm_chunks(category, chunk_count)

    if category == DocumentSizeCategory.LARGE:
        warnings.append(
            f"Large document ({page_count} pages, {total_chars:,} chars) — "
            "summarisation will cover only a sample of chunks"
        )
    elif category == DocumentSizeCategory.OVERSIZED:
        warnings.append(
            f"Oversized document ({page_count} pages, {total_chars:,} chars) — "
            "synchronous processing may be slow; "
            "summarisation will cover a small fraction of content"
        )

    if chunk_count > 0 and recommended < chunk_count:
        coverage = recommended / chunk_count
        warnings.append(
            f"LLM will see {recommended}/{chunk_count} chunks "
            f"({coverage:.0%} coverage)"
        )

    return SizeGuardResult(
        category=category,
        page_count=page_count,
        total_chars=total_chars,
        file_size_bytes=file_size,
        chunk_count=chunk_count,
        recommended_max_llm_chunks=recommended,
        warnings=warnings,
    )


def _classify(
    page_count: int,
    total_chars: int,
    file_size_bytes: int,
) -> DocumentSizeCategory:
    """Use the most aggressive signal — the one that classifies highest wins."""
    page_cat = DocumentSizeCategory.OVERSIZED
    for threshold, cat in PAGE_THRESHOLDS:
        if page_count <= threshold:
            page_cat = cat
            break

    char_cat = DocumentSizeCategory.OVERSIZED
    for threshold, cat in CHAR_THRESHOLDS:
        if total_chars <= threshold:
            char_cat = cat
            break

    byte_cat = DocumentSizeCategory.OVERSIZED
    for threshold, cat in BYTES_THRESHOLDS:
        if file_size_bytes <= threshold:
            byte_cat = cat
            break

    _RANK = {
        DocumentSizeCategory.SMALL: 0,
        DocumentSizeCategory.MEDIUM: 1,
        DocumentSizeCategory.LARGE: 2,
        DocumentSizeCategory.OVERSIZED: 3,
    }
    return max(page_cat, char_cat, byte_cat, key=lambda c: _RANK[c])


def _recommended_llm_chunks(
    category: DocumentSizeCategory,
    chunk_count: int,
) -> int:
    """Suggest how many chunks to send to the LLM based on size category.

    For small documents the LLM can see everything.  For larger ones we
    limit to a budget that stays within typical context windows without
    overwhelming the model.
    """
    budget_map = {
        DocumentSizeCategory.SMALL: chunk_count,
        DocumentSizeCategory.MEDIUM: min(chunk_count, 15),
        DocumentSizeCategory.LARGE: min(chunk_count, 20),
        DocumentSizeCategory.OVERSIZED: min(chunk_count, 25),
    }
    return budget_map.get(category, min(chunk_count, 10))
