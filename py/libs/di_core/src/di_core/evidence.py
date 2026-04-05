"""Citation-ready evidence packaging.

Transforms enriched DocumentChunks into EvidenceReferences that carry
enough context for:
  - UI display (page numbers, section label, snippet)
  - Reviewer inspection (source filename, doc type, parse quality)
  - Future RAG answer grounding (char offsets, relevance score)

This module is intentionally separate from the summariser so deterministic
extraction, LLM summarisation, and future RAG can all share the same
evidence-packaging logic.
"""

from __future__ import annotations

from data_model import DocumentChunk, EvidenceReference

SNIPPET_MAX_CHARS = 300


def package_evidence(
    chunks: list[DocumentChunk],
    relevance_scores: dict[str, float] | None = None,
) -> list[EvidenceReference]:
    """Convert a list of enriched chunks into citation-ready evidence.

    If relevance_scores is provided (chunk_id → score), each reference
    gets a score.  Otherwise defaults to 1.0.
    """
    scores = relevance_scores or {}
    return [
        EvidenceReference(
            chunk_id=c.chunk_id,
            chunk_text=c.text[:SNIPPET_MAX_CHARS],
            relevance_score=scores.get(c.chunk_id, 1.0),
            page_numbers=c.page_numbers,
            source_filename=c.source_filename,
            doc_type=c.doc_type,
            section_label=c.section_label,
            parse_quality=c.parse_quality,
            char_start=c.char_start,
            char_end=c.char_end,
        )
        for c in chunks
    ]


def package_evidence_from_ids(
    used_ids: list[str],
    chunk_map: dict[str, DocumentChunk],
) -> list[EvidenceReference]:
    """Build evidence from a list of chunk IDs returned by the LLM.

    Skips IDs not found in chunk_map (the LLM may hallucinate IDs).
    """
    chunks = [chunk_map[cid] for cid in used_ids if cid in chunk_map]
    return package_evidence(chunks)
