"""Chunk selection strategies for LLM context budget.

Replaces the naive ``doc.chunks[:N]`` approach with explicit strategies
that maximise information coverage within the LLM's token budget.

Strategies:
  head         — first N chunks (original behaviour, fast, biased to beginning)
  tail         — last N chunks (useful for conclusions/signatures)
  head_tail    — first N/2 + last N/2 (covers both ends, good default for
                 documents with preamble + conclusion)
  sampled      — evenly spaced sample across all chunks (best coverage for
                 long uniform documents)
  routing_aware — adapts selection based on document type:
                    legal → head_tail (preambles + conclusions matter)
                    billing → head (key info is usually early)
                    medical → sampled (information distributed throughout)
                    default → head_tail
  query_ranked — rank all chunks against a query using SalienceRanker,
                 select the top-N most relevant.  Requires a query string.
                 Falls back to head_tail when no query is provided.
  diversified  — section-aware selection that combines relevance scoring
                 with coverage diversity.  Ensures chunks are drawn from
                 multiple sections/page ranges instead of clustering in
                 one region.  Falls back to sampled without a query.
"""

from __future__ import annotations

from data_model import (
    ChunkSelectionStrategy,
    Document,
    DocumentChunk,
    DocumentType,
    SummarisationMeta,
)


def select_chunks_for_llm(
    doc: Document,
    max_chunks: int = 10,
    strategy: ChunkSelectionStrategy = ChunkSelectionStrategy.HEAD,
    query: str | None = None,
) -> tuple[list[DocumentChunk], SummarisationMeta]:
    """Select chunks and build a transparency record of what was chosen.

    When strategy is QUERY_RANKED, chunks are ranked by relevance to query
    using SalienceRanker and the top max_chunks are selected.

    Returns (selected_chunks, summarisation_meta) so the caller can pass
    both to the LLM and to the response.
    """
    all_chunks = doc.chunks
    total = len(all_chunks)
    total_pages = doc.parse_meta.page_count if doc.parse_meta else len(doc.pages)

    if total <= max_chunks:
        selected = list(all_chunks)
        return selected, _build_meta(
            selected, total, total_pages, strategy, is_partial=False,
        )

    effective_strategy = strategy

    if strategy == ChunkSelectionStrategy.QUERY_RANKED:
        if query:
            selected = _apply_query_ranked(all_chunks, max_chunks, query)
            meta = _build_meta(
                selected, total, total_pages, strategy, is_partial=True,
            )
            meta.warnings.append(
                f"Query-ranked selection for: '{query[:80]}'"
            )
            return selected, meta
        else:
            effective_strategy = ChunkSelectionStrategy.HEAD_TAIL
            meta_extra = (
                "Query-ranked requested but no query provided — "
                "fell back to head_tail"
            )

    if strategy == ChunkSelectionStrategy.DIVERSIFIED:
        selected = _apply_diversified(all_chunks, max_chunks, query)
        meta = _build_meta(
            selected, total, total_pages, strategy, is_partial=True,
        )
        sections_hit = {c.section_label or "(no section)" for c in selected}
        meta.warnings.append(
            f"Diversified selection across {len(sections_hit)} section(s): "
            f"{', '.join(sorted(sections_hit))}"
        )
        return selected, meta

    if strategy == ChunkSelectionStrategy.ROUTING_AWARE:
        effective_strategy = _pick_routing_strategy(doc)

    selected = _apply_strategy(all_chunks, max_chunks, effective_strategy)

    meta = _build_meta(
        selected, total, total_pages, strategy, is_partial=True,
    )
    if strategy == ChunkSelectionStrategy.ROUTING_AWARE:
        meta.warnings.append(
            f"Routing-aware selection resolved to '{effective_strategy.value}' "
            f"for document type "
            f"'{doc.routing.predicted_type.value if doc.routing else 'unknown'}'"
        )
    if strategy == ChunkSelectionStrategy.QUERY_RANKED and not query:
        meta.warnings.append(meta_extra)  # noqa: F821 — defined in the branch above

    return selected, meta


def _apply_query_ranked(
    chunks: list[DocumentChunk],
    budget: int,
    query: str,
) -> list[DocumentChunk]:
    """Rank chunks by query relevance and return the top-budget."""
    from di_core.ranker import SalienceRanker

    ranker = SalienceRanker()
    ranked = ranker.rank(chunks, query, top_k=budget)
    return [r.chunk for r in ranked]


def _apply_diversified(
    chunks: list[DocumentChunk],
    budget: int,
    query: str | None,
) -> list[DocumentChunk]:
    """Section-aware selection combining relevance with diversity.

    Algorithm:
      1. Score all chunks by relevance (SalienceRanker if query, else position).
      2. Group chunks by section_label (or page bucket if no sections).
      3. Round-robin across groups, picking the highest-scored unselected chunk
         from each group in turn, until budget is filled.

    This ensures long documents get representative coverage instead of
    clustering all context in one section.
    """
    from di_core.ranker import SalienceRanker

    if query:
        ranker = SalienceRanker()
        ranked = ranker.rank(chunks, query, top_k=len(chunks))
        scores = {r.chunk.chunk_id: r.score for r in ranked}
    else:
        scores = {c.chunk_id: 1.0 / (c.index + 1) for c in chunks}

    groups: dict[str, list[DocumentChunk]] = {}
    for c in chunks:
        key = c.section_label or f"page-{c.page_numbers[0]}" if c.page_numbers else f"idx-{c.index // 5}"
        groups.setdefault(key, []).append(c)

    for key in groups:
        groups[key].sort(key=lambda c: scores.get(c.chunk_id, 0.0), reverse=True)

    group_keys = sorted(groups.keys(), key=lambda k: max(
        scores.get(c.chunk_id, 0.0) for c in groups[k]
    ), reverse=True)

    selected: list[DocumentChunk] = []
    selected_ids: set[str] = set()
    group_cursors = {k: 0 for k in group_keys}

    while len(selected) < budget:
        picked_any = False
        for key in group_keys:
            if len(selected) >= budget:
                break
            cursor = group_cursors[key]
            group = groups[key]
            while cursor < len(group) and group[cursor].chunk_id in selected_ids:
                cursor += 1
            if cursor < len(group):
                chunk = group[cursor]
                selected.append(chunk)
                selected_ids.add(chunk.chunk_id)
                group_cursors[key] = cursor + 1
                picked_any = True
        if not picked_any:
            break

    selected.sort(key=lambda c: c.index)
    return selected


def _apply_strategy(
    chunks: list[DocumentChunk],
    budget: int,
    strategy: ChunkSelectionStrategy,
) -> list[DocumentChunk]:
    total = len(chunks)

    if strategy == ChunkSelectionStrategy.TAIL:
        return chunks[-budget:]

    if strategy == ChunkSelectionStrategy.HEAD_TAIL:
        head_n = budget // 2
        tail_n = budget - head_n
        head = chunks[:head_n]
        tail = chunks[-tail_n:] if tail_n > 0 else []
        if head_n + tail_n >= total:
            return list(chunks)
        return head + tail

    if strategy == ChunkSelectionStrategy.SAMPLED:
        if budget >= total:
            return list(chunks)
        step = total / budget
        indices = [int(i * step) for i in range(budget)]
        seen: set[int] = set()
        selected: list[DocumentChunk] = []
        for idx in indices:
            idx = min(idx, total - 1)
            if idx not in seen:
                seen.add(idx)
                selected.append(chunks[idx])
        return selected

    return chunks[:budget]


def _pick_routing_strategy(doc: Document) -> ChunkSelectionStrategy:
    """Choose a selection strategy based on the document's routing type."""
    if not doc.routing:
        return ChunkSelectionStrategy.HEAD_TAIL

    strategy_map = {
        DocumentType.LEGAL: ChunkSelectionStrategy.HEAD_TAIL,
        DocumentType.BILLING: ChunkSelectionStrategy.HEAD,
        DocumentType.MEDICAL: ChunkSelectionStrategy.SAMPLED,
        DocumentType.TREATMENT: ChunkSelectionStrategy.SAMPLED,
        DocumentType.CORRESPONDENCE: ChunkSelectionStrategy.HEAD,
    }
    return strategy_map.get(
        doc.routing.predicted_type,
        ChunkSelectionStrategy.HEAD_TAIL,
    )


def _build_meta(
    selected: list[DocumentChunk],
    total_chunks: int,
    total_pages: int,
    strategy: ChunkSelectionStrategy,
    is_partial: bool,
) -> SummarisationMeta:
    pages_covered = sorted({p for c in selected for p in c.page_numbers})
    coverage = len(selected) / total_chunks if total_chunks > 0 else 1.0

    warnings: list[str] = []
    if is_partial:
        warnings.append(
            f"Summary based on {len(selected)}/{total_chunks} chunks "
            f"({coverage:.0%} coverage) — document content beyond selection "
            "is not reflected in the summary"
        )

    return SummarisationMeta(
        total_chunks_available=total_chunks,
        total_pages_available=total_pages,
        chunks_sent_to_llm=len(selected),
        pages_covered_by_selection=pages_covered,
        coverage_ratio=round(coverage, 4),
        selection_strategy=strategy,
        is_partial=is_partial,
        warnings=warnings,
    )
