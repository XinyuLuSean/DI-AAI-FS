"""Document parser — extracts text and page structure from files.

Current scope:
  - Plain text files  → single-page extraction
  - PDF files         → per-page extraction via PyMuPDF (native text only)

The parser produces a ParseMeta record on every run so downstream stages
can make quality-aware decisions.

Future adapters (not implemented yet):
  - OCR fallback via Tesseract or AWS Textract for scanned PDFs
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from data_model import (
    Document,
    DocumentPage,
    DocumentStatus,
    ParseFailureReason,
    ParseMeta,
)

SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".text"}
LOW_DENSITY_THRESHOLD = 20.0


def parse_document(doc: Document, file_path: str) -> Document:
    """Parse the file at *file_path* and populate doc.pages + doc.parse_meta.

    The function is intentionally synchronous.  In production this would run
    inside a worker process.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    meta = ParseMeta(file_suffix=suffix)

    if not path.exists():
        meta.failure_reason = ParseFailureReason.FILE_NOT_FOUND
        doc.parse_meta = meta
        doc.status = DocumentStatus.FAILED
        doc.error = f"File not found: {file_path}"
        return doc

    doc.status = DocumentStatus.PARSING

    if suffix == ".pdf":
        meta.parse_strategy = "pymupdf_native_text"
        pages, meta = _parse_pdf(path, meta)
    elif suffix in SUPPORTED_TEXT_SUFFIXES:
        meta.parse_strategy = "plain_text_read"
        pages, meta = _parse_text(path, meta)
    else:
        meta.failure_reason = ParseFailureReason.UNSUPPORTED_FILE_TYPE
        doc.parse_meta = meta
        doc.status = DocumentStatus.FAILED
        doc.error = f"Unsupported file type: {suffix}"
        return doc

    if meta.failure_reason != ParseFailureReason.NONE:
        doc.parse_meta = meta
        doc.status = DocumentStatus.FAILED
        doc.error = f"Parse failed: {meta.failure_reason.value}"
        return doc

    doc.pages = pages
    doc.parse_meta = meta
    doc.status = DocumentStatus.PARSED
    return doc


def _parse_pdf(path: Path, meta: ParseMeta) -> tuple[list[DocumentPage], ParseMeta]:
    try:
        pdf_doc = pymupdf.open(str(path))
    except Exception as exc:
        meta.failure_reason = ParseFailureReason.UNREADABLE_PDF
        meta.warnings.append(f"PyMuPDF could not open file: {exc}")
        return [], meta

    pages: list[DocumentPage] = []
    total_chars = 0
    empty_count = 0

    with pdf_doc:
        for i, page in enumerate(pdf_doc):
            text = page.get_text()
            char_count = len(text.strip())
            total_chars += char_count
            if char_count == 0:
                empty_count += 1
            pages.append(
                DocumentPage(
                    page_number=i + 1,
                    text=text,
                    char_count=char_count,
                )
            )

    page_count = len(pages)
    meta.page_count = page_count
    meta.empty_page_count = empty_count
    meta.total_chars = total_chars

    if page_count > 0:
        meta.text_density = total_chars / page_count
    if total_chars == 0:
        meta.failure_reason = ParseFailureReason.ZERO_TEXT_PDF
        meta.warnings.append(
            "PDF produced zero extracted text — likely scanned/image-only"
        )
    elif empty_count == page_count:
        meta.failure_reason = ParseFailureReason.ZERO_TEXT_PDF
        meta.warnings.append("Every page in the PDF is empty")
    else:
        if meta.text_density < LOW_DENSITY_THRESHOLD:
            meta.warnings.append(
                f"Very low text density ({meta.text_density:.1f} chars/page) "
                "— downstream AI quality may be poor"
            )
        if empty_count > 0:
            meta.warnings.append(
                f"{empty_count}/{page_count} pages have no text"
            )

    return pages, meta


def _parse_text(path: Path, meta: ParseMeta) -> tuple[list[DocumentPage], ParseMeta]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        meta.failure_reason = ParseFailureReason.EMPTY_EXTRACTION
        meta.warnings.append(f"Could not read text file: {exc}")
        return [], meta

    char_count = len(text.strip())
    meta.page_count = 1
    meta.total_chars = char_count
    meta.text_density = float(char_count)

    if char_count == 0:
        meta.failure_reason = ParseFailureReason.EMPTY_EXTRACTION
        meta.warnings.append("Text file is empty")
        return [], meta

    pages = [DocumentPage(page_number=1, text=text, char_count=char_count)]
    return pages, meta
