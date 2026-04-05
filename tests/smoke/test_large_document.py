"""Smoke tests: Phase 6 — large-document handling.

Covers:
  Module 6A — size classification and guards
  Module 6B — progressive processing (page_bounded avoids giant join)
  Module 6C — chunk selection strategies
  Module 6D — debug endpoint enrichment with size_guard

Run with:  uv run pytest tests/smoke/test_large_document.py -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from data_model import (
    ChunkSelectionStrategy,
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentSizeCategory,
    DocumentStatus,
    ParseMeta,
    RoutingResult,
    DocumentType,
)
from di_core import classify_document_size
from di_core.chunk_selector import select_chunks_for_llm

from py_api.main import app

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def _make_doc(
    page_count: int = 10,
    chars_per_page: int = 500,
    chunk_count: int = 20,
    file_size_bytes: int = 50_000,
) -> Document:
    """Build a synthetic document with controllable size signals."""
    pages = [
        DocumentPage(
            page_number=i + 1,
            text=f"Page {i + 1} content. " * (chars_per_page // 20),
            char_count=chars_per_page,
        )
        for i in range(page_count)
    ]
    chunks = [
        DocumentChunk(
            document_id="test",
            index=i,
            text=f"Chunk {i} text.",
            page_numbers=[i % page_count + 1],
            char_start=i * 100,
            char_end=(i + 1) * 100,
            token_estimate=25,
        )
        for i in range(chunk_count)
    ]
    from data_model import DocumentSource

    return Document(
        filename="synthetic.pdf",
        pages=pages,
        chunks=chunks,
        status=DocumentStatus.CHUNKED,
        parse_meta=ParseMeta(page_count=page_count, total_chars=page_count * chars_per_page),
        source=DocumentSource(
            path="/tmp/synthetic.pdf",
            original_filename="synthetic.pdf",
            content_type="application/pdf",
            size_bytes=file_size_bytes,
        ),
    )


# ── Module 6A: Size classification ──────────────────────────────────────


class TestSizeClassification:
    def test_small_document(self) -> None:
        doc = _make_doc(page_count=5, chars_per_page=200, file_size_bytes=5_000)
        result = classify_document_size(doc)
        assert result.category == DocumentSizeCategory.SMALL
        assert len(result.warnings) == 0

    def test_medium_document(self) -> None:
        doc = _make_doc(page_count=50, chars_per_page=1_000, file_size_bytes=100_000)
        result = classify_document_size(doc)
        assert result.category == DocumentSizeCategory.MEDIUM

    def test_large_document(self) -> None:
        doc = _make_doc(page_count=500, chars_per_page=1_000, file_size_bytes=5_000_000)
        result = classify_document_size(doc)
        assert result.category == DocumentSizeCategory.LARGE
        assert any("Large document" in w for w in result.warnings)

    def test_oversized_document(self) -> None:
        doc = _make_doc(page_count=3_000, chars_per_page=1_000, file_size_bytes=60_000_000)
        result = classify_document_size(doc)
        assert result.category == DocumentSizeCategory.OVERSIZED
        assert any("Oversized" in w for w in result.warnings)

    def test_classification_uses_most_aggressive_signal(self) -> None:
        doc = _make_doc(page_count=5, chars_per_page=200, file_size_bytes=60_000_000)
        result = classify_document_size(doc)
        assert result.category == DocumentSizeCategory.OVERSIZED

    def test_recommended_llm_chunks_scales(self) -> None:
        small = classify_document_size(
            _make_doc(page_count=3, chunk_count=5, file_size_bytes=1_000)
        )
        large = classify_document_size(
            _make_doc(page_count=500, chunk_count=200, file_size_bytes=5_000_000)
        )
        assert small.recommended_max_llm_chunks == 5  # all chunks for small
        assert large.recommended_max_llm_chunks == 20


# ── Module 6A: Size category on upload ──────────────────────────────────


class TestSizeCategoryOnUpload:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_upload_sets_size_category(self) -> None:
        with open(FIXTURES / "sample.txt", "rb") as f:
            resp = self.client.post(
                "/documents/upload",
                files={"file": ("sample.txt", f, "text/plain")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["size_category"] is not None
        assert data["size_category"] in ("small", "medium", "large", "oversized")


# ── Module 6C: Chunk selection strategies ────────────────────────────────


class TestChunkSelectionStrategies:
    def _doc_with_chunks(self, n: int = 20) -> Document:
        return _make_doc(page_count=n, chunk_count=n, chars_per_page=200)

    def test_head_strategy(self) -> None:
        doc = self._doc_with_chunks(20)
        selected, meta = select_chunks_for_llm(
            doc, max_chunks=5, strategy=ChunkSelectionStrategy.HEAD,
        )
        assert len(selected) == 5
        assert [c.index for c in selected] == [0, 1, 2, 3, 4]
        assert meta.is_partial is True
        assert meta.coverage_ratio < 1.0

    def test_tail_strategy(self) -> None:
        doc = self._doc_with_chunks(20)
        selected, meta = select_chunks_for_llm(
            doc, max_chunks=5, strategy=ChunkSelectionStrategy.TAIL,
        )
        assert len(selected) == 5
        assert [c.index for c in selected] == [15, 16, 17, 18, 19]

    def test_head_tail_strategy(self) -> None:
        doc = self._doc_with_chunks(20)
        selected, meta = select_chunks_for_llm(
            doc, max_chunks=6, strategy=ChunkSelectionStrategy.HEAD_TAIL,
        )
        assert len(selected) == 6
        indices = [c.index for c in selected]
        assert indices[:3] == [0, 1, 2]
        assert indices[3:] == [17, 18, 19]

    def test_sampled_strategy(self) -> None:
        doc = self._doc_with_chunks(20)
        selected, meta = select_chunks_for_llm(
            doc, max_chunks=5, strategy=ChunkSelectionStrategy.SAMPLED,
        )
        assert len(selected) == 5
        indices = [c.index for c in selected]
        assert indices[0] == 0
        assert indices[-1] >= 15
        for i in range(len(indices) - 1):
            assert indices[i] < indices[i + 1]

    def test_routing_aware_strategy(self) -> None:
        doc = self._doc_with_chunks(20)
        doc.routing = RoutingResult(
            predicted_type=DocumentType.MEDICAL,
            confidence=0.9,
            is_fallback=False,
        )
        selected, meta = select_chunks_for_llm(
            doc, max_chunks=5, strategy=ChunkSelectionStrategy.ROUTING_AWARE,
        )
        assert len(selected) == 5
        assert meta.selection_strategy == ChunkSelectionStrategy.ROUTING_AWARE
        assert any("Routing-aware" in w for w in meta.warnings)

    def test_small_doc_gets_all_chunks(self) -> None:
        doc = self._doc_with_chunks(3)
        selected, meta = select_chunks_for_llm(
            doc, max_chunks=10, strategy=ChunkSelectionStrategy.HEAD,
        )
        assert len(selected) == 3
        assert meta.is_partial is False
        assert meta.coverage_ratio == 1.0

    def test_meta_reports_coverage(self) -> None:
        doc = self._doc_with_chunks(20)
        _, meta = select_chunks_for_llm(
            doc, max_chunks=5, strategy=ChunkSelectionStrategy.HEAD,
        )
        assert meta.total_chunks_available == 20
        assert meta.chunks_sent_to_llm == 5
        assert meta.coverage_ratio == 0.25
        assert meta.is_partial is True
        assert len(meta.warnings) >= 1


# ── Module 6D: Debug endpoint includes size info ────────────────────────


class TestDebugEndpointSizeInfo:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_debug_includes_size_guard(self) -> None:
        with open(FIXTURES / "sample.txt", "rb") as f:
            resp = self.client.post(
                "/documents/upload",
                files={"file": ("sample.txt", f, "text/plain")},
            )
        doc_id = resp.json()["id"]

        debug_resp = self.client.get(f"/documents/{doc_id}/chunks/debug")
        assert debug_resp.status_code == 200
        debug = debug_resp.json()

        assert "size_category" in debug
        assert "size_guard" in debug
        guard = debug["size_guard"]
        assert "category" in guard
        assert "recommended_max_llm_chunks" in guard
        assert "page_count" in guard
        assert "total_chars" in guard


# ── Module 6B: page_bounded strategy still works ────────────────────────


class TestProgressiveProcessing:
    """Verify that page_bounded strategy works without building a full join."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_page_bounded_upload(self) -> None:
        with open(FIXTURES / "sample.txt", "rb") as f:
            resp = self.client.post(
                "/documents/upload",
                files={"file": ("sample.txt", f, "text/plain")},
                params={"chunk_strategy": "page_bounded"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["chunk_meta"]["strategy"] == "page_bounded"
        assert data["size_category"] is not None

    def test_large_synthetic_file_chunking(self) -> None:
        """Generate a large text file and verify processing completes."""
        content = "\n\n".join(
            f"Section {i}: " + "Lorem ipsum dolor sit amet. " * 50
            for i in range(100)
        )
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content.encode())
            tmp_path = f.name

        try:
            with open(tmp_path, "rb") as f:
                resp = self.client.post(
                    "/documents/upload",
                    files={"file": ("large_test.txt", f, "text/plain")},
                    params={"chunk_size": 400, "chunk_overlap": 50},
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["chunk_meta"]["chunk_count"] > 10
            assert data["size_category"] is not None
        finally:
            Path(tmp_path).unlink(missing_ok=True)
