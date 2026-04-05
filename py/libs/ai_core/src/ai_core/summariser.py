"""Document summarisation workflow.

Orchestrates: select chunks → build prompt → call LLM → parse into schema.

This is the first AI task in the vertical slice.  It demonstrates:
- strict JSON output via the adapter
- evidence references back to source chunks
- separation between prompt definition and execution
- grounding by pre-extracted deterministic fields (when available)
- budget-aware chunk selection (Phase 6) with explicit coverage reporting
"""

from __future__ import annotations

import time
from typing import Any

from data_model import (
    ChunkSelectionStrategy,
    Document,
    EvidenceReference,
    ExtractionResult,
    StructuredField,
    SummaryResult,
)

from ai_core.adapter import LLMAdapter
from ai_core.prompts import (
    GROUNDED_SUMMARISE_SYSTEM,
    SUMMARISE_SYSTEM,
    build_summarise_user_prompt,
)
from di_core.chunk_selector import select_chunks_for_llm


def summarise_document(
    doc: Document,
    llm: LLMAdapter | None = None,
    max_chunks: int = 10,
    chunk_selection: ChunkSelectionStrategy = ChunkSelectionStrategy.HEAD,
    grounding_fields: list[StructuredField] | None = None,
) -> ExtractionResult:
    """Run summarisation over a budget-selected subset of chunks.

    Instead of blindly taking the first N chunks, uses select_chunks_for_llm
    which applies the requested strategy (head, tail, head_tail, sampled,
    routing_aware) and produces a SummarisationMeta record so the caller
    and user know exactly what the LLM saw vs what was available.
    """
    llm = llm or LLMAdapter()
    start = time.perf_counter_ns()

    selected, summarisation_meta = select_chunks_for_llm(
        doc, max_chunks=max_chunks, strategy=chunk_selection,
    )

    chunk_dicts = [{"chunk_id": c.chunk_id, "text": c.text} for c in selected]
    chunk_map = {c.chunk_id: c for c in selected}

    extracted_field_dicts: list[dict[str, str]] | None = None
    if grounding_fields:
        extracted_field_dicts = [
            {
                "field_name": f.field_name,
                "field_value": f.field_value,
                "confidence": str(f.confidence),
            }
            for f in grounding_fields
        ]

    system_prompt = GROUNDED_SUMMARISE_SYSTEM if grounding_fields else SUMMARISE_SYSTEM
    user_prompt = build_summarise_user_prompt(chunk_dicts, extracted_field_dicts)

    raw: dict[str, Any] = llm.complete_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    used_ids: list[str] = raw.get("chunk_ids_used", [])
    evidence = _build_evidence(used_ids, chunk_map)

    fields = [
        StructuredField(
            field_name=f.get("field_name", ""),
            field_value=f.get("field_value", ""),
            confidence=float(f.get("confidence", 0.0)),
            extraction_method="llm",
            evidence=evidence,
        )
        for f in raw.get("structured_fields", [])
    ]

    summary = SummaryResult(
        summary_text=raw.get("summary_text", ""),
        key_points=raw.get("key_points", []),
        evidence=evidence,
    )

    elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    return ExtractionResult(
        document_id=doc.id,
        model_used=llm.model,
        structured_fields=fields,
        summary=summary,
        summarisation_meta=summarisation_meta,
        processing_time_ms=elapsed_ms,
    )


def _build_evidence(
    used_ids: list[str],
    chunk_map: dict[str, Any],
) -> list[EvidenceReference]:
    evidence: list[EvidenceReference] = []
    for cid in used_ids:
        chunk = chunk_map.get(cid)
        if chunk is None:
            continue
        evidence.append(
            EvidenceReference(
                chunk_id=cid,
                chunk_text=chunk.text[:300],
                relevance_score=1.0,
                page_numbers=chunk.page_numbers,
            )
        )
    return evidence
