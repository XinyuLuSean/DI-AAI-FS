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
) -> tuple[list[DocumentChunk], SummarisationMeta]:
    """Select chunks and build a transparency record of what was chosen.

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

    return selected, meta


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
