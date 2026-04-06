"""Retrieval strategy comparison — side-by-side analysis of chunk selection.

Given a document and a query, runs multiple selection strategies and reports
which chunks each strategy selects, why, and how they differ.  This is the
key tool for answering Phase 5's question: "is retrieval-based selection
more relevant than naive first-N?"

Usage:
    from di_core.retrieval_compare import compare_strategies
    report = compare_strategies(doc, query="patient diagnosis", max_chunks=5)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from data_model import (
    ChunkSelectionStrategy,
    Document,
    DocumentChunk,
)

from di_core.chunk_selector import select_chunks_for_llm
from di_core.ranker import SalienceRanker


class ChunkSelection(BaseModel):
    """One chunk selected by a strategy, with its ranking context."""

    chunk_id: str
    index: int
    page_numbers: list[int] = Field(default_factory=list)
    section_label: str = ""
    relevance_score: float = 0.0
    text_preview: str = ""


class StrategyResult(BaseModel):
    """Chunks selected by one strategy."""

    strategy: str
    chunks: list[ChunkSelection] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)


class ComparisonReport(BaseModel):
    """Side-by-side comparison of multiple retrieval strategies."""

    document_id: str
    query: str
    max_chunks: int
    total_chunks_available: int
    strategies: list[StrategyResult] = Field(default_factory=list)
    overlap_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    unique_to: dict[str, list[str]] = Field(default_factory=dict)
    recommendation: str = ""


PREVIEW_MAX = 120

STRATEGIES_TO_COMPARE = [
    ChunkSelectionStrategy.HEAD,
    ChunkSelectionStrategy.HEAD_TAIL,
    ChunkSelectionStrategy.SAMPLED,
    ChunkSelectionStrategy.ROUTING_AWARE,
    ChunkSelectionStrategy.QUERY_RANKED,
]


def _score_chunks(
    chunks: list[DocumentChunk],
    query: str,
) -> dict[str, float]:
    """Score all chunks by relevance to query, returning chunk_id → score."""
    ranker = SalienceRanker()
    ranked = ranker.rank(chunks, query, top_k=len(chunks))
    return {r.chunk.chunk_id: r.score for r in ranked}


def compare_strategies(
    doc: Document,
    query: str,
    max_chunks: int = 5,
    strategies: list[ChunkSelectionStrategy] | None = None,
) -> ComparisonReport:
    """Run multiple selection strategies and compare results.

    For each strategy, records which chunks were selected and their
    relevance scores (scored uniformly by SalienceRanker regardless
    of which strategy selected them).
    """
    strategies = strategies or list(STRATEGIES_TO_COMPARE)
    all_scores = _score_chunks(doc.chunks, query) if query else {}

    results: list[StrategyResult] = []
    all_id_sets: dict[str, set[str]] = {}

    for strat in strategies:
        selected, _meta = select_chunks_for_llm(
            doc, max_chunks=max_chunks, strategy=strat, query=query,
        )

        chunk_selections = [
            ChunkSelection(
                chunk_id=c.chunk_id,
                index=c.index,
                page_numbers=c.page_numbers,
                section_label=c.section_label,
                relevance_score=all_scores.get(c.chunk_id, 0.0),
                text_preview=c.text[:PREVIEW_MAX].replace("\n", " "),
            )
            for c in selected
        ]

        ids = [c.chunk_id for c in selected]
        results.append(StrategyResult(
            strategy=strat.value,
            chunks=chunk_selections,
            chunk_ids=ids,
        ))
        all_id_sets[strat.value] = set(ids)

    overlap = {}
    for s1 in all_id_sets:
        overlap[s1] = {}
        for s2 in all_id_sets:
            overlap[s1][s2] = len(all_id_sets[s1] & all_id_sets[s2])

    unique_to: dict[str, list[str]] = {}
    for name, ids in all_id_sets.items():
        others = set()
        for other_name, other_ids in all_id_sets.items():
            if other_name != name:
                others |= other_ids
        unique = ids - others
        if unique:
            unique_to[name] = sorted(unique)

    recommendation = _recommend(results, all_id_sets, query)

    return ComparisonReport(
        document_id=doc.id,
        query=query,
        max_chunks=max_chunks,
        total_chunks_available=len(doc.chunks),
        strategies=results,
        overlap_matrix=overlap,
        unique_to=unique_to,
        recommendation=recommendation,
    )


def _recommend(
    results: list[StrategyResult],
    id_sets: dict[str, set[str]],
    query: str,
) -> str:
    """Generate a plain-English recommendation based on the comparison."""
    if not query:
        return (
            "No query provided — positional strategies are equivalent. "
            "Use head_tail as a safe default for documents with important "
            "preamble and conclusion sections."
        )

    best_strat = ""
    best_avg = -1.0
    for r in results:
        if not r.chunks:
            continue
        avg = sum(c.relevance_score for c in r.chunks) / len(r.chunks)
        if avg > best_avg:
            best_avg = avg
            best_strat = r.strategy

    head_result = next((r for r in results if r.strategy == "head"), None)
    ranked_result = next((r for r in results if r.strategy == "query_ranked"), None)

    if head_result and ranked_result:
        head_avg = (
            sum(c.relevance_score for c in head_result.chunks) / len(head_result.chunks)
            if head_result.chunks else 0.0
        )
        ranked_avg = (
            sum(c.relevance_score for c in ranked_result.chunks) / len(ranked_result.chunks)
            if ranked_result.chunks else 0.0
        )
        improvement = ranked_avg - head_avg

        if improvement > 0.1:
            return (
                f"query_ranked selects significantly more relevant chunks than head "
                f"(avg relevance {ranked_avg:.2f} vs {head_avg:.2f}, "
                f"+{improvement:.2f}). For this query, retrieval-based selection "
                f"is clearly better than naive first-N."
            )
        elif improvement > 0.0:
            return (
                f"query_ranked is slightly better than head "
                f"(avg relevance {ranked_avg:.2f} vs {head_avg:.2f}). "
                f"The improvement is modest — the relevant content may be "
                f"concentrated near the beginning of the document."
            )
        else:
            return (
                f"head and query_ranked produce similar relevance "
                f"(avg {head_avg:.2f} vs {ranked_avg:.2f}). "
                f"For this document, key information appears early. "
                f"Head selection is adequate but may miss content in longer documents."
            )

    return f"Best average relevance: {best_strat} ({best_avg:.2f})"
