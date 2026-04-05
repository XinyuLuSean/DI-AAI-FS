"""Document parser — extracts text and page structure from files.

Current scope:
  - Plain text files  → single-page extraction
  - PDF files         → per-page extraction via PyMuPDF (native text only)
  - OCR-aware         → detects when OCR is needed, attempts via adapter,
                         degrades honestly when unavailable

The parser produces a ParseMeta record on every run so downstream stages
can make quality-aware decisions.
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
    ParseQuality,
)

from di_core.ocr import OCRAdapter, get_default_ocr_adapter

SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".text"}
LOW_DENSITY_THRESHOLD = 20.0
SCANNED_DENSITY_THRESHOLD = 50.0
EMPTY_PAGE_RATIO_THRESHOLD = 0.5

# These failures are truly unrecoverable — hard reject with 422.
# ZERO_TEXT_PDF degrades honestly (scanned PDF still has pages/metadata).
_HARD_FAILURES = frozenset({
    ParseFailureReason.FILE_NOT_FOUND,
    ParseFailureReason.UNSUPPORTED_FILE_TYPE,
    ParseFailureReason.UNREADABLE_PDF,
    ParseFailureReason.EMPTY_EXTRACTION,
})


def parse_document(
    doc: Document,
    file_path: str,
    ocr_adapter: OCRAdapter | None = None,
) -> Document:
    """Parse the file at *file_path* and populate doc.pages + doc.parse_meta.

    The function is intentionally synchronous.  In production this would run
    inside a worker process.

    When ocr_adapter is None the default adapter is auto-detected (Tesseract
    if available, otherwise NoOp).
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    meta = ParseMeta(file_suffix=suffix)

    if not path.exists():
        meta.failure_reason = ParseFailureReason.FILE_NOT_FOUND
        meta.quality = ParseQuality.UNUSABLE
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
        meta.quality = ParseQuality.UNUSABLE
        doc.parse_meta = meta
        doc.status = DocumentStatus.FAILED
        doc.error = f"Unsupported file type: {suffix}"
        return doc

    if meta.failure_reason in _HARD_FAILURES:
        doc.parse_meta = meta
        doc.status = DocumentStatus.FAILED
        doc.error = f"Parse failed: {meta.failure_reason.value}"
        return doc

    if meta.failure_reason != ParseFailureReason.NONE:
        original_pages = pages
        if meta.likely_needs_ocr:
            adapter = ocr_adapter or get_default_ocr_adapter()
            pages, meta = _attempt_ocr_fallback(path, meta, adapter)
            if not pages:
                pages = original_pages

        if meta.failure_reason != ParseFailureReason.NONE:
            meta.quality = ParseQuality.UNUSABLE
            if not meta.downstream_limitations:
                meta.downstream_limitations.append(
                    "Document has no extractable text — "
                    "extraction, chunking, and AI tasks will be limited"
                )

    _assess_quality(meta)

    doc.pages = pages
    doc.parse_meta = meta
    doc.status = DocumentStatus.PARSED
    return doc


def _parse_pdf(path: Path, meta: ParseMeta) -> tuple[list[DocumentPage], ParseMeta]:
    try:
        pdf_doc = pymupdf.open(str(path))
    except Exception as exc:
        meta.failure_reason = ParseFailureReason.UNREADABLE_PDF
        meta.quality = ParseQuality.UNUSABLE
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
        meta.likely_scanned = True
        meta.likely_needs_ocr = True
        meta.warnings.append(
            "PDF produced zero extracted text — likely scanned/image-only"
        )
    elif empty_count == page_count:
        meta.failure_reason = ParseFailureReason.ZERO_TEXT_PDF
        meta.likely_scanned = True
        meta.likely_needs_ocr = True
        meta.warnings.append("Every page in the PDF is empty")
    else:
        meta.native_text_extracted = True
        empty_ratio = empty_count / page_count if page_count > 0 else 0

        if meta.text_density < LOW_DENSITY_THRESHOLD:
            meta.likely_scanned = True
            meta.likely_needs_ocr = True
            meta.warnings.append(
                f"Very low text density ({meta.text_density:.1f} chars/page) "
                "— likely scanned with minimal embedded text"
            )
        elif meta.text_density < SCANNED_DENSITY_THRESHOLD:
            meta.likely_scanned = True
            meta.warnings.append(
                f"Low text density ({meta.text_density:.1f} chars/page) "
                "— may contain scanned pages mixed with native text"
            )

        if empty_ratio > EMPTY_PAGE_RATIO_THRESHOLD:
            meta.likely_needs_ocr = True
            meta.warnings.append(
                f"{empty_count}/{page_count} pages have no text — "
                "OCR may recover content from these pages"
            )
        elif empty_count > 0:
            meta.warnings.append(
                f"{empty_count}/{page_count} pages have no text"
            )

    return pages, meta


def _parse_text(path: Path, meta: ParseMeta) -> tuple[list[DocumentPage], ParseMeta]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        meta.failure_reason = ParseFailureReason.EMPTY_EXTRACTION
        meta.quality = ParseQuality.UNUSABLE
        meta.warnings.append(f"Could not read text file: {exc}")
        return [], meta

    char_count = len(text.strip())
    meta.page_count = 1
    meta.total_chars = char_count
    meta.text_density = float(char_count)
    meta.native_text_extracted = True

    if char_count == 0:
        meta.failure_reason = ParseFailureReason.EMPTY_EXTRACTION
        meta.quality = ParseQuality.UNUSABLE
        meta.warnings.append("Text file is empty")
        return [], meta

    pages = [DocumentPage(page_number=1, text=text, char_count=char_count)]
    return pages, meta


def _attempt_ocr_fallback(
    path: Path,
    meta: ParseMeta,
    adapter: OCRAdapter,
) -> tuple[list[DocumentPage], ParseMeta]:
    """Try OCR when native text extraction failed or was insufficient.

    If OCR is unavailable, return the original meta with honest degradation
    signals instead of silently pretending success.
    """
    if not adapter.is_available():
        meta.warnings.append(
            f"OCR needed but backend '{adapter.name}' is not available"
        )
        meta.downstream_limitations.append(
            "Document appears scanned but OCR is unavailable — "
            "extraction, chunking, and AI tasks will have no text to work with"
        )
        meta.downstream_limitations.append(
            "Deterministic field extraction will return zero fields"
        )
        meta.downstream_limitations.append(
            "LLM summarisation will have no content to summarise"
        )
        meta.quality = ParseQuality.UNUSABLE
        return [], meta

    ocr_result = adapter.extract_text(path)
    meta.warnings.extend(ocr_result.warnings)

    if ocr_result.error:
        meta.warnings.append(f"OCR error: {ocr_result.error}")
        meta.downstream_limitations.append(
            "OCR was attempted but failed — text content is unavailable"
        )
        meta.quality = ParseQuality.UNUSABLE
        return [], meta

    meta.ocr_applied = True
    meta.parse_strategy = f"ocr_{adapter.name}"
    pages = [
        DocumentPage(
            page_number=p.page_number,
            text=p.text,
            char_count=len(p.text.strip()),
        )
        for p in ocr_result.pages
    ]

    total = sum(p.char_count for p in pages)
    meta.total_chars = total
    meta.page_count = len(pages)
    meta.empty_page_count = sum(1 for p in pages if p.char_count == 0)
    if meta.page_count > 0:
        meta.text_density = total / meta.page_count

    if total == 0:
        meta.quality = ParseQuality.UNUSABLE
        meta.downstream_limitations.append(
            "OCR ran but extracted zero text — document may be blank or unreadable"
        )
    else:
        meta.failure_reason = ParseFailureReason.NONE
        meta.quality = ParseQuality.DEGRADED
        meta.downstream_limitations.append(
            "Text was recovered via OCR — confidence and accuracy may be lower than native text"
        )

    return pages, meta


def _assess_quality(meta: ParseMeta) -> None:
    """Set overall quality based on accumulated signals."""
    if meta.quality == ParseQuality.UNUSABLE:
        return

    if meta.ocr_applied:
        meta.quality = ParseQuality.DEGRADED
        return

    if meta.likely_scanned and not meta.ocr_applied:
        if meta.likely_needs_ocr:
            meta.quality = ParseQuality.DEGRADED
            meta.downstream_limitations.append(
                "Document has very low text density — AI output quality may be poor"
            )
        else:
            meta.quality = ParseQuality.DEGRADED
            meta.downstream_limitations.append(
                "Document may contain scanned pages — some content might be missing"
            )
        return

    meta.quality = ParseQuality.GOOD
