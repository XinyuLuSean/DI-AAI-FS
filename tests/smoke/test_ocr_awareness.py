"""Smoke tests: OCR-awareness and parse quality signals (Phase 5).

Run with:  uv run pytest tests/smoke/test_ocr_awareness.py -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient

from data_model import ParseQuality
from di_core.ocr import NoOpAdapter, TesseractAdapter, get_default_ocr_adapter
from py_api.main import app

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def _upload(client: TestClient, filename: str, fixture_dir: Path = FIXTURES) -> dict:
    with open(fixture_dir / filename, "rb") as f:
        resp = client.post(
            "/documents/upload",
            files={"file": (filename, f, "text/plain")},
        )
    return resp.json(), resp.status_code


def _create_blank_pdf(dir_path: Path, pages: int = 3) -> Path:
    """Create a PDF with blank pages (no text) to simulate a scanned doc."""
    pdf_path = dir_path / "scanned_blank.pdf"
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=612, height=792)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


class TestNativeTextQuality:
    """Normal text files produce good quality signals."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_text_file_has_good_quality(self) -> None:
        data, status = _upload(self.client, "sample.txt")
        assert status == 200
        meta = data["parse_meta"]
        assert meta["native_text_extracted"] is True
        assert meta["likely_scanned"] is False
        assert meta["likely_needs_ocr"] is False
        assert meta["ocr_applied"] is False
        assert meta["quality"] == "good"
        assert meta["downstream_limitations"] == []


class TestBlankPDFDetection:
    """A blank PDF triggers OCR-need signals and honest degradation."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_blank_pdf_degrades_honestly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = _create_blank_pdf(Path(tmp), pages=3)
            with open(pdf_path, "rb") as f:
                resp = self.client.post(
                    "/documents/upload",
                    files={"file": ("scanned_blank.pdf", f, "application/pdf")},
                )
            assert resp.status_code == 200
            data = resp.json()
            meta = data["parse_meta"]
            assert meta["quality"] == "unusable"
            assert meta["likely_scanned"] is True
            assert meta["likely_needs_ocr"] is True
            assert len(meta["downstream_limitations"]) >= 1
            assert data["status"] == "chunked"
            assert data["chunks"] == []

    def test_blank_pdf_parse_meta_via_direct_parse(self) -> None:
        """Parse directly to inspect the full ParseMeta."""
        from data_model import Document, DocumentSource, DocumentStatus
        from di_core import parse_document
        from di_core.ocr import NoOpAdapter

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = _create_blank_pdf(Path(tmp), pages=2)
            doc = Document(
                filename="scanned_blank.pdf",
                content_type="application/pdf",
                status=DocumentStatus.PENDING,
                source=DocumentSource(
                    path=str(pdf_path),
                    original_filename="scanned_blank.pdf",
                    content_type="application/pdf",
                    size_bytes=pdf_path.stat().st_size,
                ),
            )
            doc = parse_document(doc, str(pdf_path), ocr_adapter=NoOpAdapter())

        assert doc.status == DocumentStatus.PARSED
        meta = doc.parse_meta
        assert meta is not None
        assert meta.likely_scanned is True
        assert meta.likely_needs_ocr is True
        assert meta.ocr_applied is False
        assert meta.quality == ParseQuality.UNUSABLE
        assert len(meta.downstream_limitations) >= 1
        assert any("OCR" in lim for lim in meta.downstream_limitations)
        assert any("OCR" in w or "zero" in w.lower() for w in meta.warnings)


class TestOCRAdapterInterface:
    """Adapter interface contracts."""

    def test_noop_adapter_is_unavailable(self) -> None:
        adapter = NoOpAdapter()
        assert adapter.is_available() is False
        assert adapter.name == "none"
        result = adapter.extract_text(Path("/dev/null"))
        assert result.available is False
        assert result.error is not None

    def test_tesseract_adapter_has_name(self) -> None:
        adapter = TesseractAdapter()
        assert adapter.name == "tesseract"

    def test_default_adapter_returns_valid_adapter(self) -> None:
        adapter = get_default_ocr_adapter()
        assert hasattr(adapter, "is_available")
        assert hasattr(adapter, "extract_text")
        assert hasattr(adapter, "name")

    def test_tesseract_unavailable_returns_error(self) -> None:
        adapter = TesseractAdapter()
        if not adapter.is_available():
            result = adapter.extract_text(Path("/dev/null"))
            assert result.available is False
            assert "not found" in (result.error or "")


class TestQualitySignalsOnExistingFixtures:
    """Verify quality signals on all existing text fixtures."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_invoice_has_good_quality(self) -> None:
        data, status = _upload(self.client, "invoice_plumbing.txt")
        assert status == 200
        assert data["parse_meta"]["quality"] == "good"
        assert data["parse_meta"]["native_text_extracted"] is True

    def test_medical_record_has_good_quality(self) -> None:
        data, status = _upload(self.client, "medical_record.txt")
        assert status == 200
        assert data["parse_meta"]["quality"] == "good"

    def test_attorney_letter_has_good_quality(self) -> None:
        data, status = _upload(self.client, "attorney_letter.txt")
        assert status == 200
        assert data["parse_meta"]["quality"] == "good"


class TestDownstreamLimitations:
    """When quality is degraded/unusable, downstream_limitations are populated."""

    def test_blank_pdf_lists_limitations(self) -> None:
        from data_model import Document, DocumentSource, DocumentStatus
        from di_core import parse_document
        from di_core.ocr import NoOpAdapter

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = _create_blank_pdf(Path(tmp))
            doc = Document(
                filename="blank.pdf",
                content_type="application/pdf",
                status=DocumentStatus.PENDING,
                source=DocumentSource(
                    path=str(pdf_path),
                    original_filename="blank.pdf",
                    content_type="application/pdf",
                    size_bytes=pdf_path.stat().st_size,
                ),
            )
            doc = parse_document(doc, str(pdf_path), ocr_adapter=NoOpAdapter())

        meta = doc.parse_meta
        assert meta is not None
        assert len(meta.downstream_limitations) >= 2
        assert any("extraction" in l.lower() for l in meta.downstream_limitations)
        assert any("summarisation" in l.lower() or "summaris" in l.lower() for l in meta.downstream_limitations)
