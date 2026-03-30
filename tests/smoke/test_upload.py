"""Smoke test: upload a fixture file and verify parsing + chunking.

Run with:  uv run pytest tests/smoke/test_upload.py -v
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from py_api.main import app

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "sample.txt"


class TestDocumentUpload:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_upload_text_file(self) -> None:
        with open(FIXTURE_PATH, "rb") as f:
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
        with open(FIXTURE_PATH, "rb") as f:
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
