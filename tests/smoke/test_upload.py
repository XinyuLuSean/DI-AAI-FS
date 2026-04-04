"""Smoke tests: upload, parse metadata, failure classification.

Run with:  uv run pytest tests/smoke/test_upload.py -v
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from py_api.main import app

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


class TestDocumentUpload:
    """Happy-path upload tests (existing from Phase 0)."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_upload_text_file(self) -> None:
        with open(FIXTURES / "sample.txt", "rb") as f:
            response = self.client.post(
                "/documents/upload",
                files={"file": ("sample.txt", f, "text/plain")},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "chunked"
        assert data["filename"] == "sample.txt"
        assert len(data["pages"]) >= 1
        assert len(data["chunks"]) >= 1

    def test_upload_returns_chunk_provenance(self) -> None:
        with open(FIXTURES / "sample.txt", "rb") as f:
            response = self.client.post(
                "/documents/upload",
                files={"file": ("sample.txt", f, "text/plain")},
            )
        data = response.json()
        chunk = data["chunks"][0]
        assert "chunk_id" in chunk
        assert "page_numbers" in chunk
        assert chunk["page_numbers"] == [1]
        assert chunk["token_estimate"] > 0


class TestParseMeta:
    """Phase 1: parse metadata is present and accurate."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_text_file_parse_meta(self) -> None:
        with open(FIXTURES / "sample.txt", "rb") as f:
            resp = self.client.post(
                "/documents/upload",
                files={"file": ("sample.txt", f, "text/plain")},
            )
        data = resp.json()
        meta = data["parse_meta"]
        assert meta is not None
        assert meta["parse_strategy"] == "plain_text_read"
        assert meta["file_suffix"] == ".txt"
        assert meta["page_count"] == 1
        assert meta["empty_page_count"] == 0
        assert meta["total_chars"] > 0
        assert meta["text_density"] > 0
        assert meta["failure_reason"] == "none"
        assert meta["warnings"] == []


class TestFailureClassification:
    """Phase 1: parser failures carry typed reasons, not just strings."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_unsupported_file_type(self) -> None:
        with open(FIXTURES / "unsupported.docx", "rb") as f:
            resp = self.client.post(
                "/documents/upload",
                files={"file": ("report.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["failure_reason"] == "unsupported_file_type"

    def test_empty_text_file(self) -> None:
        with open(FIXTURES / "empty.txt", "rb") as f:
            resp = self.client.post(
                "/documents/upload",
                files={"file": ("empty.txt", f, "text/plain")},
            )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["failure_reason"] == "empty_extraction"

    def test_no_filename_rejected(self) -> None:
        resp = self.client.post(
            "/documents/upload",
            files={"file": ("", b"content", "text/plain")},
        )
        assert resp.status_code in (400, 422)
