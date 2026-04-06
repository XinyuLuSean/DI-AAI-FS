"""Phase 7 tests — Long-Context and Large-Document AI Strategy.

Covers:
  Module 7A: Diversified context selection
  Module 7B: Coverage-aware AI input preparation
  Module 7C: Hierarchical AI strategy (chunk → section → document)
  Module 7D: Long-document warnings
"""

from __future__ import annotations

import pytest

from data_model import (
    ChunkSelectionStrategy,
    Document,
    DocumentChunk,
    DocumentPage,
    SectionLabel,
)

from di_core.chunk_selector import select_chunks_for_llm
from di_core.coverage import CoverageReport, build_coverage_report

from ai_core.hierarchical import (
    ChunkFacts,
    SectionSummary,
    HierarchicalResult,
    extract_chunk_facts,
    aggregate_by_section,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


def _make_long_doc(n_chunks: int = 30) -> Document:
    """Build a document with contiguous section blocks (realistic layout).

    Sections are contiguous: chunks 0-2 = intro, 3-5 = history, etc.
    This means HEAD selection only covers the first few sections,
    while DIVERSIFIED should draw from all sections.
    """
    section_names = [
        "introduction", "patient_history", "diagnosis",
        "treatment_plan", "lab_results", "imaging",
        "medication", "follow_up", "notes", "billing",
    ]
    chunks_per_section = n_chunks // len(section_names)

    chunks = []
    for i in range(n_chunks):
        section_idx = i // chunks_per_section if chunks_per_section > 0 else 0
        section_idx = min(section_idx, len(section_names) - 1)
        page = (i // 3) + 1
        chunks.append(DocumentChunk(
            chunk_id=f"c{i}",
            document_id="doc-long",
            index=i,
            text=f"Content for {section_names[section_idx]} on page {page}. "
                 f"The patient had condition-{i} noted in this section. "
                 f"Lab value was {100 + i * 3}.",
            page_numbers=[page],
            section_label=section_names[section_idx],
            char_start=0,
            char_end=100,
        ))

    sections = [
        SectionLabel(
            label=name,
            page_start=1 + (i * 3),
            page_end=3 + (i * 3),
        )
        for i, name in enumerate(section_names)
    ]

    total_pages = (n_chunks // 3) + 1
    pages = [
        DocumentPage(page_number=p, text=f"Page {p} content.", char_count=20)
        for p in range(1, total_pages + 1)
    ]

    return Document(
        id="doc-long",
        filename="long_medical_record.pdf",
        raw_text=" ".join(c.text for c in chunks),
        chunks=chunks,
        sections=sections,
        pages=pages,
    )


def _make_short_doc() -> Document:
    """A short document where all strategies should be equivalent."""
    chunks = [
        DocumentChunk(
            chunk_id=f"s{i}",
            document_id="doc-short",
            index=i,
            text=f"Short chunk {i} content.",
            page_numbers=[1],
            section_label="body",
            char_start=0,
            char_end=30,
        )
        for i in range(3)
    ]
    return Document(
        id="doc-short",
        filename="short_note.txt",
        raw_text=" ".join(c.text for c in chunks),
        chunks=chunks,
    )


@pytest.fixture
def long_doc():
    return _make_long_doc()


@pytest.fixture
def short_doc():
    return _make_short_doc()


# ═══════════════════════════════════════════════════════════════════════════
# Module 7A: Diversified selection
# ═══════════════════════════════════════════════════════════════════════════


class TestDiversifiedSelection:
    def test_diversified_selects_from_multiple_sections(self, long_doc):
        selected, meta = select_chunks_for_llm(
            long_doc, max_chunks=5,
            strategy=ChunkSelectionStrategy.DIVERSIFIED,
        )
        sections = {c.section_label for c in selected}
        assert len(sections) >= 3, f"Expected >=3 sections, got {sections}"

    def test_diversified_differs_from_head(self, long_doc):
        """Diversified picks from many sections; head picks sequentially.

        With 10 sections in a 30-chunk doc and budget=10, head takes c0-c9
        while diversified round-robins across all 10 sections.
        """
        head_sel, _ = select_chunks_for_llm(
            long_doc, max_chunks=10,
            strategy=ChunkSelectionStrategy.HEAD,
        )
        div_sel, _ = select_chunks_for_llm(
            long_doc, max_chunks=10,
            strategy=ChunkSelectionStrategy.DIVERSIFIED,
        )
        head_ids = {c.chunk_id for c in head_sel}
        div_ids = {c.chunk_id for c in div_sel}
        assert head_ids != div_ids

    def test_diversified_with_query(self, long_doc):
        selected, meta = select_chunks_for_llm(
            long_doc, max_chunks=5,
            strategy=ChunkSelectionStrategy.DIVERSIFIED,
            query="lab results diagnosis",
        )
        assert len(selected) == 5
        sections = {c.section_label for c in selected}
        assert len(sections) >= 2

    def test_diversified_meta_mentions_sections(self, long_doc):
        _, meta = select_chunks_for_llm(
            long_doc, max_chunks=5,
            strategy=ChunkSelectionStrategy.DIVERSIFIED,
        )
        assert any("Diversified" in w for w in meta.warnings)
        assert any("section" in w for w in meta.warnings)

    def test_diversified_covers_more_pages_than_head(self, long_doc):
        head_sel, head_meta = select_chunks_for_llm(
            long_doc, max_chunks=5,
            strategy=ChunkSelectionStrategy.HEAD,
        )
        div_sel, div_meta = select_chunks_for_llm(
            long_doc, max_chunks=5,
            strategy=ChunkSelectionStrategy.DIVERSIFIED,
        )
        head_pages = {p for c in head_sel for p in c.page_numbers}
        div_pages = {p for c in div_sel for p in c.page_numbers}
        assert len(div_pages) >= len(head_pages)

    def test_diversified_small_doc_selects_all(self, short_doc):
        selected, meta = select_chunks_for_llm(
            short_doc, max_chunks=10,
            strategy=ChunkSelectionStrategy.DIVERSIFIED,
        )
        assert len(selected) == len(short_doc.chunks)

    def test_diversified_returns_sorted_by_index(self, long_doc):
        selected, _ = select_chunks_for_llm(
            long_doc, max_chunks=8,
            strategy=ChunkSelectionStrategy.DIVERSIFIED,
        )
        indices = [c.index for c in selected]
        assert indices == sorted(indices)


# ═══════════════════════════════════════════════════════════════════════════
# Module 7B: Coverage report
# ═══════════════════════════════════════════════════════════════════════════


class TestCoverageReport:
    def test_comprehensive_when_all_chunks(self, short_doc):
        report = build_coverage_report(short_doc, short_doc.chunks)
        assert report.is_comprehensive or report.coverage_level in ("comprehensive", "good")
        assert report.chunk_coverage_ratio == 1.0

    def test_partial_when_few_chunks(self, long_doc):
        selected = long_doc.chunks[:3]
        report = build_coverage_report(long_doc, selected)
        assert report.coverage_level in ("partial", "minimal")
        assert not report.is_comprehensive
        assert report.chunk_coverage_ratio < 0.2

    def test_pages_missing_populated(self, long_doc):
        selected = long_doc.chunks[:3]
        report = build_coverage_report(long_doc, selected)
        assert len(report.pages_missing) > 0
        assert len(report.pages_covered) > 0

    def test_sections_missing_populated(self, long_doc):
        selected = long_doc.chunks[:3]
        report = build_coverage_report(long_doc, selected)
        assert len(report.sections_missing) > 0

    def test_disclosure_text_present(self, long_doc):
        selected = long_doc.chunks[:3]
        report = build_coverage_report(long_doc, selected)
        assert "COVERAGE DISCLOSURE" in report.disclosure_text
        assert "chunks" in report.disclosure_text.lower()

    def test_disclosure_mentions_partial_warning(self, long_doc):
        selected = long_doc.chunks[:3]
        report = build_coverage_report(long_doc, selected)
        assert "limited" in report.disclosure_text.lower() or "part" in report.disclosure_text.lower()

    def test_comprehensive_disclosure_no_warning(self, short_doc):
        report = build_coverage_report(short_doc, short_doc.chunks)
        disclosure = report.disclosure_text.lower()
        assert "warning" not in disclosure or report.coverage_level != "comprehensive"

    def test_section_coverage_ratio(self, long_doc):
        selected = long_doc.chunks[:3]
        report = build_coverage_report(long_doc, selected)
        assert 0.0 < report.section_coverage_ratio < 1.0

    def test_page_coverage_ratio(self, long_doc):
        selected = long_doc.chunks[:3]
        report = build_coverage_report(long_doc, selected)
        assert 0.0 < report.page_coverage_ratio < 1.0


# ═══════════════════════════════════════════════════════════════════════════
# Module 7C: Hierarchical strategy
# ═══════════════════════════════════════════════════════════════════════════


class TestChunkFactExtraction:
    def test_extracts_key_sentences(self, long_doc):
        chunk = long_doc.chunks[0]
        facts = extract_chunk_facts(chunk)
        assert isinstance(facts, ChunkFacts)
        assert facts.chunk_id == chunk.chunk_id
        assert facts.section_label == chunk.section_label
        assert len(facts.key_sentences) > 0
        assert facts.word_count > 0

    def test_page_numbers_carried(self, long_doc):
        facts = extract_chunk_facts(long_doc.chunks[5])
        assert facts.page_numbers == long_doc.chunks[5].page_numbers

    def test_max_sentences_respected(self, long_doc):
        facts = extract_chunk_facts(long_doc.chunks[0])
        assert len(facts.key_sentences) <= 3


class TestSectionAggregation:
    def test_groups_by_section(self, long_doc):
        facts = [extract_chunk_facts(c) for c in long_doc.chunks]
        sections = aggregate_by_section(facts)
        assert isinstance(sections, list)
        assert all(isinstance(s, SectionSummary) for s in sections)
        section_labels = {s.section_label for s in sections}
        assert len(section_labels) >= 5

    def test_section_has_chunk_ids(self, long_doc):
        facts = [extract_chunk_facts(c) for c in long_doc.chunks]
        sections = aggregate_by_section(facts)
        for s in sections:
            assert len(s.chunk_ids) > 0

    def test_section_has_page_range(self, long_doc):
        facts = [extract_chunk_facts(c) for c in long_doc.chunks]
        sections = aggregate_by_section(facts)
        for s in sections:
            if s.page_range:
                assert s.page_range == sorted(s.page_range)

    def test_section_has_key_facts(self, long_doc):
        facts = [extract_chunk_facts(c) for c in long_doc.chunks]
        sections = aggregate_by_section(facts)
        for s in sections:
            assert len(s.key_facts) > 0

    def test_condensed_text_bounded(self, long_doc):
        facts = [extract_chunk_facts(c) for c in long_doc.chunks]
        sections = aggregate_by_section(facts)
        for s in sections:
            assert len(s.condensed_text) <= 500

    def test_deduplicates_facts(self, long_doc):
        c = long_doc.chunks[0]
        dup_facts = [extract_chunk_facts(c), extract_chunk_facts(c)]
        sections = aggregate_by_section(dup_facts)
        for s in sections:
            normalized = [f.lower().strip() for f in s.key_facts]
            assert len(normalized) == len(set(normalized))


class TestHierarchicalResult:
    def test_model_structure(self):
        result = HierarchicalResult(
            chunk_facts=[ChunkFacts(chunk_id="c0", key_sentences=["fact1"])],
            section_summaries=[SectionSummary(section_label="intro", chunk_count=1)],
            document_synthesis="Overall summary.",
            total_chunks_processed=10,
            sections_found=3,
        )
        assert result.strategy == "hierarchical_map_reduce"
        assert result.total_chunks_processed == 10
        assert result.sections_found == 3


# ═══════════════════════════════════════════════════════════════════════════
# Module 7D: Long-document warnings
# ═══════════════════════════════════════════════════════════════════════════


class TestLongDocumentWarnings:
    def test_partial_selection_generates_warning(self, long_doc):
        _, meta = select_chunks_for_llm(
            long_doc, max_chunks=5,
            strategy=ChunkSelectionStrategy.HEAD,
        )
        assert meta.is_partial
        assert any("coverage" in w.lower() for w in meta.warnings)

    def test_full_selection_no_partial_warning(self, short_doc):
        _, meta = select_chunks_for_llm(
            short_doc, max_chunks=10,
            strategy=ChunkSelectionStrategy.HEAD,
        )
        assert not meta.is_partial

    def test_coverage_report_on_extraction_result(self):
        from data_model import ExtractionResult
        schema = ExtractionResult.model_json_schema()
        assert "coverage_report" in schema["properties"]

    def test_diversified_meta_warns_about_sections(self, long_doc):
        _, meta = select_chunks_for_llm(
            long_doc, max_chunks=5,
            strategy=ChunkSelectionStrategy.DIVERSIFIED,
        )
        assert any("section" in w.lower() for w in meta.warnings)


# ═══════════════════════════════════════════════════════════════════════════
# API endpoint schema
# ═══════════════════════════════════════════════════════════════════════════


class TestAPIEndpoints:
    def test_hierarchical_endpoint_exists(self):
        import importlib
        docs_module = importlib.import_module("py_api.api.documents")
        assert hasattr(docs_module, "hierarchical_summarise_endpoint")

    def test_compare_request_includes_diversified(self):
        from di_core.retrieval_compare import STRATEGIES_TO_COMPARE
        strategy_values = [s.value for s in STRATEGIES_TO_COMPARE]
        assert "diversified" in strategy_values
