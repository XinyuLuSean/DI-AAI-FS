"""Document parser — extracts text and page structure from files.

Current scope (MVP):
  - Plain text files  → single-page extraction
  - PDF files         → per-page extraction via PyMuPDF (native text only)

Future adapters (not implemented yet):
  - OCR fallback via Tesseract or AWS Textract for scanned PDFs
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from data_model import Document, DocumentPage, DocumentStatus


def parse_document(doc: Document, file_path: str) -> Document:
    """Parse the file at *file_path* and populate doc.pages.

    The function is intentionally synchronous for the MVP.  In production this
    would run inside a worker process.
    """
    path = Path(file_path)
    if not path.exists():
        doc.status = DocumentStatus.FAILED
        doc.error = f"File not found: {file_path}"
        return doc

    doc.status = DocumentStatus.PARSING

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        pages = _parse_pdf(path)
    elif suffix in {".txt", ".md", ".text"}:
        pages = _parse_text(path)
    else:
        doc.status = DocumentStatus.FAILED
        doc.error = f"Unsupported file type: {suffix}"
        return doc

    doc.pages = pages
    doc.status = DocumentStatus.PARSED
    return doc


def _parse_pdf(path: Path) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    with pymupdf.open(str(path)) as pdf_doc:
        for i, page in enumerate(pdf_doc):
            text = page.get_text()
            pages.append(
                DocumentPage(
                    page_number=i + 1,
                    text=text,
                    char_count=len(text),
                )
            )
    return pages


def _parse_text(path: Path) -> list[DocumentPage]:
    text = path.read_text(encoding="utf-8")
    return [DocumentPage(page_number=1, text=text, char_count=len(text))]
