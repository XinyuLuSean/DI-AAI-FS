"""Deterministic text chunker with provenance tracking and multiple strategies.

Strategies:
  fixed_size    — sliding character window with overlap (deterministic baseline)
  paragraph     — split on paragraph boundaries, merge small ones to target size
  page_bounded  — one chunk per page, split pages exceeding max size

All strategies produce DocumentChunks with page provenance and character offsets.
The chunker also produces a ChunkMeta record so downstream stages can inspect
the chunking run without re-processing.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from data_model import (
    ChunkMeta,
    ChunkStrategy,
    Document,
    DocumentChunk,
    DocumentStatus,
)

DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 200


class ChunkConfig(BaseModel):
    """Chunking parameters — passed from the API layer."""

    strategy: ChunkStrategy = ChunkStrategy.PARAGRAPH
    chunk_size: int = DEFAULT_CHUNK_SIZE
    overlap: int = DEFAULT_OVERLAP
    max_chunks: int | None = None


def chunk_text(doc: Document, config: ChunkConfig | None = None) -> Document:
    """Split doc.pages into chunks using the requested strategy.

    Attaches both doc.chunks and doc.chunk_meta.
    """
    cfg = config or ChunkConfig()
    full_text = "\n\n".join(p.text for p in doc.pages)

    if not full_text.strip():
        doc.status = DocumentStatus.FAILED
        doc.error = "No text extracted from document"
        return doc

    page_ranges = _build_page_offset_map(doc)

    if cfg.strategy == ChunkStrategy.PARAGRAPH:
        chunks = _chunk_paragraph(doc, full_text, page_ranges, cfg)
    elif cfg.strategy == ChunkStrategy.PAGE_BOUNDED:
        chunks = _chunk_page_bounded(doc, page_ranges, cfg)
    else:
        chunks = _chunk_fixed_size(doc, full_text, page_ranges, cfg)

    is_truncated = False
    if cfg.max_chunks is not None and len(chunks) > cfg.max_chunks:
        chunks = chunks[: cfg.max_chunks]
        chunks[-1].is_truncated = True
        is_truncated = True

    for i, c in enumerate(chunks):
        c.index = i
        c.strategy = cfg.strategy.value

    covered_pages = sorted({p for c in chunks for p in c.page_numbers})
    total_chars = sum(len(c.text) for c in chunks)
    avg_chars = total_chars / len(chunks) if chunks else 0.0

    warnings: list[str] = []
    if is_truncated:
        warnings.append(
            f"Chunk count truncated to {cfg.max_chunks} "
            f"(would have been {len(chunks) + 1}+)"
        )

    doc.chunks = chunks
    doc.chunk_meta = ChunkMeta(
        strategy=cfg.strategy,
        chunk_size=cfg.chunk_size,
        overlap=cfg.overlap,
        chunk_count=len(chunks),
        avg_chunk_chars=round(avg_chars, 1),
        total_chars_chunked=total_chars,
        max_chunks_limit=cfg.max_chunks,
        is_truncated=is_truncated,
        page_coverage=covered_pages,
        warnings=warnings,
    )
    doc.status = DocumentStatus.CHUNKED
    return doc


# ---------------------------------------------------------------------------
# Strategy: fixed_size (sliding character window)
# ---------------------------------------------------------------------------

def _chunk_fixed_size(
    doc: Document,
    full_text: str,
    page_ranges: list[tuple[int, int, int]],
    cfg: ChunkConfig,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    start = 0
    step = max(cfg.chunk_size - cfg.overlap, 1)

    while start < len(full_text):
        end = min(start + cfg.chunk_size, len(full_text))
        chunks.append(_make_chunk(doc.id, full_text[start:end], start, end, page_ranges))
        start += step

    return chunks


# ---------------------------------------------------------------------------
# Strategy: paragraph (split on double-newline, merge small paragraphs)
# ---------------------------------------------------------------------------

_PARA_SPLIT = re.compile(r"\n\s*\n")


def _chunk_paragraph(
    doc: Document,
    full_text: str,
    page_ranges: list[tuple[int, int, int]],
    cfg: ChunkConfig,
) -> list[DocumentChunk]:
    raw_splits = _PARA_SPLIT.split(full_text)
    if not raw_splits:
        return [_make_chunk(doc.id, full_text, 0, len(full_text), page_ranges)]

    chunks: list[DocumentChunk] = []
    buf: list[str] = []
    buf_char_start = 0
    cursor = 0

    for para in raw_splits:
        para_start = full_text.find(para, cursor)
        if para_start == -1:
            para_start = cursor
        para_end = para_start + len(para)

        if not buf:
            buf_char_start = para_start

        projected_len = sum(len(p) for p in buf) + len(buf) * 2 + len(para)
        if buf and projected_len > cfg.chunk_size:
            merged = "\n\n".join(buf)
            merged_end = buf_char_start + len(merged)
            chunks.append(
                _make_chunk(doc.id, merged, buf_char_start, merged_end, page_ranges)
            )
            buf = [para]
            buf_char_start = para_start
        else:
            buf.append(para)

        cursor = para_end

    if buf:
        merged = "\n\n".join(buf)
        merged_end = buf_char_start + len(merged)
        chunks.append(
            _make_chunk(doc.id, merged, buf_char_start, merged_end, page_ranges)
        )

    return chunks


# ---------------------------------------------------------------------------
# Strategy: page_bounded (one chunk per page, split large pages)
# ---------------------------------------------------------------------------

def _chunk_page_bounded(
    doc: Document,
    page_ranges: list[tuple[int, int, int]],
    cfg: ChunkConfig,
) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []

    for page in doc.pages:
        text = page.text
        if len(text) <= cfg.chunk_size:
            if text.strip():
                chunks.append(
                    DocumentChunk(
                        document_id=doc.id,
                        index=0,
                        text=text,
                        page_numbers=[page.page_number],
                        char_start=0,
                        char_end=len(text),
                        token_estimate=len(text) // 4,
                    )
                )
        else:
            start = 0
            step = max(cfg.chunk_size - cfg.overlap, 1)
            while start < len(text):
                end = min(start + cfg.chunk_size, len(text))
                chunks.append(
                    DocumentChunk(
                        document_id=doc.id,
                        index=0,
                        text=text[start:end],
                        page_numbers=[page.page_number],
                        char_start=start,
                        char_end=end,
                        token_estimate=(end - start) // 4,
                    )
                )
                start += step

    return chunks


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_chunk(
    doc_id: str,
    text: str,
    char_start: int,
    char_end: int,
    page_ranges: list[tuple[int, int, int]],
) -> DocumentChunk:
    return DocumentChunk(
        document_id=doc_id,
        index=0,
        text=text,
        page_numbers=_pages_for_range(page_ranges, char_start, char_end),
        char_start=char_start,
        char_end=char_end,
        token_estimate=len(text) // 4,
    )


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
    return [pn for pn, ps, pe in page_ranges if ps < end and pe > start]
