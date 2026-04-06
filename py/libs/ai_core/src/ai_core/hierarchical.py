"""Hierarchical AI strategy for long documents (Phase 7C).

Implements a MapReduce-style approach:
  1. Chunk-level: extract key facts from each chunk (deterministic)
  2. Section-level: aggregate chunk facts per section
  3. Document-level: synthesize section summaries via LLM

This approach handles documents of arbitrary length because:
  - Each chunk is processed independently (parallelizable)
  - Section aggregation is deterministic (no token limit)
  - Only the final synthesis step calls the LLM, with compact
    per-section summaries instead of raw text

Trade-off: the LLM never sees raw text directly, only pre-digested
section summaries.  This reduces hallucination risk but can lose
nuance.  For short documents, direct summarisation is still better.
"""

from __future__ import annotations

import re
import time
from typing import Any

import structlog

from pydantic import BaseModel, Field

from data_model import (
    Document,
    DocumentChunk,
    ExtractionResult,
    OutputType,
    SummaryResult,
    SummarisationMeta,
    ChunkSelectionStrategy,
)

from ai_core.adapter import LLMAdapter
from ai_core.prompts import PromptTemplate
from di_core.coverage import build_coverage_report

logger = structlog.get_logger()


# ═══════════════════════════════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════════════════════════════


class ChunkFacts(BaseModel):
    """Key facts extracted from a single chunk (deterministic)."""

    chunk_id: str
    section_label: str = ""
    page_numbers: list[int] = Field(default_factory=list)
    key_sentences: list[str] = Field(default_factory=list)
    word_count: int = 0


class SectionSummary(BaseModel):
    """Aggregated summary for one document section."""

    section_label: str
    chunk_count: int = 0
    page_range: list[int] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    condensed_text: str = ""


class HierarchicalResult(BaseModel):
    """Full hierarchical analysis output."""

    chunk_facts: list[ChunkFacts] = Field(default_factory=list)
    section_summaries: list[SectionSummary] = Field(default_factory=list)
    document_synthesis: str = ""
    strategy: str = "hierarchical_map_reduce"
    total_chunks_processed: int = 0
    sections_found: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Chunk-level fact extraction (deterministic, no LLM)
# ═══════════════════════════════════════════════════════════════════════════

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
MAX_SENTENCES_PER_CHUNK = 3


def extract_chunk_facts(chunk: DocumentChunk) -> ChunkFacts:
    """Extract key facts from a single chunk using heuristics.

    Picks the most information-dense sentences based on length
    and keyword density.  No LLM call needed.
    """
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(chunk.text) if s.strip()]

    scored = []
    for s in sentences:
        words = s.split()
        length_score = min(len(words) / 15.0, 1.0)
        has_number = 1.0 if any(c.isdigit() for c in s) else 0.0
        has_proper_noun = 1.0 if any(w[0].isupper() and i > 0 for i, w in enumerate(words) if w) else 0.0
        score = length_score + has_number * 0.3 + has_proper_noun * 0.2
        scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    key_sentences = [s for _, s in scored[:MAX_SENTENCES_PER_CHUNK]]

    return ChunkFacts(
        chunk_id=chunk.chunk_id,
        section_label=chunk.section_label or "",
        page_numbers=list(chunk.page_numbers),
        key_sentences=key_sentences,
        word_count=len(chunk.text.split()),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Section-level aggregation (deterministic)
# ═══════════════════════════════════════════════════════════════════════════


def aggregate_by_section(
    facts: list[ChunkFacts],
) -> list[SectionSummary]:
    """Group chunk facts by section and produce per-section summaries."""
    groups: dict[str, list[ChunkFacts]] = {}
    for f in facts:
        key = f.section_label or "(unsectioned)"
        groups.setdefault(key, []).append(f)

    summaries: list[SectionSummary] = []
    for label, chunk_facts in groups.items():
        all_pages: set[int] = set()
        all_facts: list[str] = []
        all_ids: list[str] = []

        for cf in chunk_facts:
            all_pages.update(cf.page_numbers)
            all_facts.extend(cf.key_sentences)
            all_ids.append(cf.chunk_id)

        seen: set[str] = set()
        unique_facts: list[str] = []
        for f in all_facts:
            normalised = f.lower().strip()
            if normalised not in seen:
                seen.add(normalised)
                unique_facts.append(f)

        condensed = " ".join(unique_facts[:10])

        summaries.append(SectionSummary(
            section_label=label,
            chunk_count=len(chunk_facts),
            page_range=sorted(all_pages),
            key_facts=unique_facts[:10],
            chunk_ids=all_ids,
            condensed_text=condensed[:500],
        ))

    summaries.sort(key=lambda s: s.page_range[0] if s.page_range else 0)
    return summaries


# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Document-level synthesis (LLM)
# ═══════════════════════════════════════════════════════════════════════════

_HIERARCHICAL_SYSTEM = """You are a document analysis assistant.
You receive pre-extracted section summaries from a document.
Your job is to synthesize these into a coherent, comprehensive document summary.

Rules:
- Cover findings from ALL sections, don't skip any
- Note which sections contributed which findings
- If a section has limited data, say so
- Be specific: use dates, names, numbers from the section summaries
- Output valid JSON with this schema:
  {
    "summary_text": "string — comprehensive document summary",
    "key_points": ["string — one key point per section or major finding"],
    "sections_synthesized": number,
    "coverage_notes": "string — any gaps or limitations noted"
  }
"""


def _build_synthesis_prompt(sections: list[SectionSummary]) -> str:
    """Build the user prompt for document-level synthesis."""
    parts = ["Here are the pre-extracted section summaries:\n"]
    for i, s in enumerate(sections, 1):
        pages = f"pp. {s.page_range[0]}-{s.page_range[-1]}" if s.page_range else "no pages"
        parts.append(
            f"--- Section {i}: {s.section_label} ({pages}, {s.chunk_count} chunks) ---\n"
            f"{s.condensed_text}\n"
        )
    parts.append(
        f"\nTotal sections: {len(sections)}. "
        "Synthesize these into a comprehensive document summary."
    )
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Full hierarchical pipeline
# ═══════════════════════════════════════════════════════════════════════════


def hierarchical_summarise(
    doc: Document,
    llm: LLMAdapter | None = None,
) -> ExtractionResult:
    """Run the full hierarchical summarisation pipeline.

    1. Extract facts from every chunk (deterministic)
    2. Aggregate by section (deterministic)
    3. Synthesize via LLM (single call with compact input)
    """
    llm = llm or LLMAdapter()
    start = time.perf_counter_ns()

    chunk_facts = [extract_chunk_facts(c) for c in doc.chunks]
    section_summaries = aggregate_by_section(chunk_facts)

    logger.info(
        "hierarchical.pipeline",
        doc_id=doc.id,
        total_chunks=len(doc.chunks),
        sections=len(section_summaries),
    )

    synthesis_prompt = _build_synthesis_prompt(section_summaries)
    raw: dict[str, Any] = llm.complete_json(
        system_prompt=_HIERARCHICAL_SYSTEM,
        user_prompt=synthesis_prompt,
    )

    summary_text = raw.get("summary_text", "")
    key_points = raw.get("key_points", [])
    coverage_notes = raw.get("coverage_notes", "")

    all_chunk_ids = [cid for s in section_summaries for cid in s.chunk_ids]
    all_pages = sorted({p for s in section_summaries for p in s.page_range})
    total_pages = doc.parse_meta.page_count if doc.parse_meta else len(doc.pages)

    hierarchical_result = HierarchicalResult(
        chunk_facts=chunk_facts,
        section_summaries=section_summaries,
        document_synthesis=summary_text,
        total_chunks_processed=len(doc.chunks),
        sections_found=len(section_summaries),
    )

    coverage = len(doc.chunks) / len(doc.chunks) if doc.chunks else 1.0
    meta = SummarisationMeta(
        total_chunks_available=len(doc.chunks),
        total_pages_available=total_pages,
        chunks_sent_to_llm=0,
        pages_covered_by_selection=all_pages,
        coverage_ratio=round(coverage, 4),
        selection_strategy=ChunkSelectionStrategy.SAMPLED,
        is_partial=False,
        warnings=[
            f"Hierarchical MapReduce: {len(doc.chunks)} chunks → "
            f"{len(section_summaries)} sections → 1 synthesis call",
            f"Coverage notes: {coverage_notes}" if coverage_notes else "",
        ],
    )
    meta.warnings = [w for w in meta.warnings if w]

    summary = SummaryResult(
        summary_text=summary_text,
        key_points=key_points if isinstance(key_points, list) else [],
    )

    elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    coverage_report = build_coverage_report(doc, doc.chunks)

    return ExtractionResult(
        document_id=doc.id,
        output_type=OutputType.AI_SUMMARY,
        model_used=llm.model,
        prompt_name="hierarchical_v1",
        prompt_version="1.0",
        summary=summary,
        summarisation_meta=meta,
        coverage_report=coverage_report.model_dump(),
        validation_status="valid",
        processing_time_ms=elapsed_ms,
    )
