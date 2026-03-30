"""Deterministic text chunker with provenance tracking.

Strategy (MVP): fixed-size character windows with overlap.
This is intentionally simple and inspectable.  Future iterations can use
semantic or structural chunking strategies without changing the interface.
"""

from __future__ import annotations

from data_model import Document, DocumentChunk, DocumentStatus

DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 200


def chunk_text(
    doc: Document,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> Document:
    """Split doc.pages into overlapping chunks and attach to doc.chunks."""
    full_text = "\n\n".join(p.text for p in doc.pages)
    if not full_text.strip():
        doc.status = DocumentStatus.FAILED
        doc.error = "No text extracted from document"
        return doc

    page_ranges = _build_page_offset_map(doc)
    chunks: list[DocumentChunk] = []
    start = 0
    idx = 0

    while start < len(full_text):
        end = min(start + chunk_size, len(full_text))
        chunk_text_slice = full_text[start:end]
        page_nums = _pages_for_range(page_ranges, start, end)

        chunks.append(
            DocumentChunk(
                document_id=doc.id,
                index=idx,
                text=chunk_text_slice,
                page_numbers=page_nums,
                char_start=start,
                char_end=end,
                token_estimate=len(chunk_text_slice) // 4,
            )
        )

        idx += 1
        step = chunk_size - overlap
        if step <= 0:
            step = chunk_size
        start += step

    doc.chunks = chunks
    doc.status = DocumentStatus.CHUNKED
    return doc


def _build_page_offset_map(doc: Document) -> list[tuple[int, int, int]]:
    """Return list of (page_number, char_start, char_end) for the joined text."""
    ranges: list[tuple[int, int, int]] = []
    offset = 0
    for page in doc.pages:
        page_len = len(page.text)
        ranges.append((page.page_number, offset, offset + page_len))
        offset += page_len + 2  # +2 for the "\n\n" joiner
    return ranges


def _pages_for_range(
    page_ranges: list[tuple[int, int, int]], start: int, end: int
) -> list[int]:
    pages: list[int] = []
    for page_num, p_start, p_end in page_ranges:
        if p_start < end and p_end > start:
            pages.append(page_num)
    return pages
