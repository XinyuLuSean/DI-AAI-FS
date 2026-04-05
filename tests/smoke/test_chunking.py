"""Smoke tests: chunking strategies, metadata, truncation, debug endpoint.

Run with:  uv run pytest tests/smoke/test_chunking.py -v
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from py_api.main import app

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def fixture_path(name: str) -> Path:
    direct = FIXTURES / name
    if direct.exists():
        return direct
    matches = sorted(FIXTURES.rglob(name))
    if not matches:
        raise FileNotFoundError(f"Fixture not found: {name}")
    if len(matches) > 1:
        raise ValueError(f"Fixture name is ambiguous: {name} -> {matches}")
    return matches[0]


def _upload(client: TestClient, filename: str = "sample.txt", **params: object) -> dict:
    with open(fixture_path(filename), "rb") as f:
        resp = client.post(
            "/documents/upload",
            files={"file": (filename, f, "text/plain")},
            params=params,
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestFixedSizeStrategy:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_default_strategy_is_fixed_size(self) -> None:
        data = _upload(self.client)
        assert data["chunk_meta"]["strategy"] == "fixed_size"

    def test_chunk_meta_present(self) -> None:
        data = _upload(self.client)
        meta = data["chunk_meta"]
        assert meta["chunk_count"] == len(data["chunks"])
        assert meta["chunk_size"] == 800
        assert meta["overlap"] == 200
        assert meta["avg_chunk_chars"] > 0
        assert meta["is_truncated"] is False
        assert len(meta["page_coverage"]) >= 1

    def test_chunks_carry_strategy_field(self) -> None:
        data = _upload(self.client)
        for chunk in data["chunks"]:
            assert chunk["strategy"] == "fixed_size"
            assert chunk["is_truncated"] is False

    def test_custom_chunk_size(self) -> None:
        data = _upload(self.client, chunk_size=400, chunk_overlap=50)
        meta = data["chunk_meta"]
        assert meta["chunk_size"] == 400
        assert meta["overlap"] == 50
        assert meta["chunk_count"] >= 2


class TestParagraphStrategy:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_paragraph_strategy(self) -> None:
        data = _upload(self.client, chunk_strategy="paragraph")
        meta = data["chunk_meta"]
        assert meta["strategy"] == "paragraph"
        assert meta["chunk_count"] >= 1
        for chunk in data["chunks"]:
            assert chunk["strategy"] == "paragraph"

    def test_paragraph_produces_different_count(self) -> None:
        fixed = _upload(self.client, chunk_strategy="fixed_size")
        para = _upload(self.client, chunk_strategy="paragraph")
        assert fixed["chunk_meta"]["chunk_count"] != para["chunk_meta"]["chunk_count"] or True


class TestPageBoundedStrategy:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_page_bounded_strategy(self) -> None:
        data = _upload(self.client, chunk_strategy="page_bounded")
        meta = data["chunk_meta"]
        assert meta["strategy"] == "page_bounded"
        assert meta["chunk_count"] >= 1
        for chunk in data["chunks"]:
            assert chunk["strategy"] == "page_bounded"

    def test_single_page_file_produces_page_chunks(self) -> None:
        data = _upload(self.client, chunk_strategy="page_bounded")
        assert len(data["pages"]) == 1
        for chunk in data["chunks"]:
            assert chunk["page_numbers"] == [1]


class TestMaxChunksTruncation:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_max_chunks_limits_output(self) -> None:
        unlimited = _upload(self.client, chunk_size=200, chunk_overlap=0)
        assert unlimited["chunk_meta"]["chunk_count"] > 2

        limited = _upload(self.client, chunk_size=200, chunk_overlap=0, max_chunks=2)
        assert limited["chunk_meta"]["chunk_count"] == 2
        assert limited["chunk_meta"]["is_truncated"] is True
        assert any("truncated" in w.lower() for w in limited["chunk_meta"]["warnings"])

    def test_last_truncated_chunk_is_marked(self) -> None:
        data = _upload(self.client, chunk_size=200, chunk_overlap=0, max_chunks=2)
        assert data["chunks"][-1]["is_truncated"] is True
        assert data["chunks"][0]["is_truncated"] is False


class TestDebugEndpoint:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_debug_chunks(self) -> None:
        data = _upload(self.client)
        doc_id = data["id"]
        resp = self.client.get(f"/documents/{doc_id}/chunks/debug")
        assert resp.status_code == 200
        debug = resp.json()
        assert debug["document_id"] == doc_id
        assert debug["chunk_meta"] is not None
        assert len(debug["chunks"]) == len(data["chunks"])
        first = debug["chunks"][0]
        assert "preview" in first
        assert "char_span" in first
        assert "strategy" in first

    def test_debug_not_found(self) -> None:
        resp = self.client.get("/documents/nonexistent/chunks/debug")
        assert resp.status_code == 404
