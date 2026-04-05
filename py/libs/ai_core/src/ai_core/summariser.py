"""Document summarisation workflow.

Orchestrates: select chunks → build prompt → call LLM → validate grounding
→ package evidence → return structured output with audit trail.

This is the first AI task in the vertical slice.  It demonstrates:
- strict JSON output via the adapter
- evidence references back to source chunks
- separation between prompt definition and execution
- grounding by pre-extracted deterministic fields (when available)
- budget-aware chunk selection (Phase 6) with explicit coverage reporting
- per-key-point evidence binding + grounding audit (Phase 8)
"""

from __future__ import annotations

import time
from typing import Any

from data_model import (
    ChunkSelectionStrategy,
    Document,
    DocumentChunk,
    ExtractionResult,
    OutputType,
    StructuredField,
    SummaryResult,
)

from ai_core.adapter import LLMAdapter
from ai_core.grounding import audit_grounding, enrich_summarisation_meta
from ai_core.prompts import (
    GROUNDED_SUMMARISE_SYSTEM,
    SUMMARISE_SYSTEM,
    build_summarise_user_prompt,
)
from di_core.chunk_selector import select_chunks_for_llm
from di_core.evidence import package_evidence_from_ids


def summarise_document(
    doc: Document,
    llm: LLMAdapter | None = None,
    max_chunks: int = 10,
    chunk_selection: ChunkSelectionStrategy = ChunkSelectionStrategy.HEAD,
    grounding_fields: list[StructuredField] | None = None,
) -> ExtractionResult:
    """Run summarisation over a budget-selected subset of chunks.

    Pipeline: select → prompt → LLM → audit grounding → package evidence.
    """
    llm = llm or LLMAdapter()
    start = time.perf_counter_ns()

    selected, summarisation_meta = select_chunks_for_llm(
        doc, max_chunks=max_chunks, strategy=chunk_selection,
    )

    chunk_dicts = [{"chunk_id": c.chunk_id, "text": c.text} for c in selected]
    chunk_map = {c.chunk_id: c for c in selected}
    provided_ids = set(chunk_map.keys())

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
    evidence = package_evidence_from_ids(used_ids, chunk_map)

    raw_key_points = raw.get("key_points", [])
    grounded_points, grounding_audit_result = audit_grounding(
        raw_key_points, used_ids, provided_ids, chunk_map,
    )

    plain_key_points = [gkp.text for gkp in grounded_points]
    grounded_count = sum(1 for gkp in grounded_points if gkp.grounded)
    grounding_coverage = grounded_count / len(grounded_points) if grounded_points else 0.0

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
        key_points=plain_key_points,
        grounded_key_points=grounded_points,
        evidence=evidence,
        grounding_coverage=round(grounding_coverage, 4),
    )

    summarisation_meta = enrich_summarisation_meta(
        summarisation_meta, used_ids, chunk_map,
    )

    elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    return ExtractionResult(
        document_id=doc.id,
        output_type=OutputType.AI_SUMMARY,
        model_used=llm.model,
        structured_fields=fields,
        summary=summary,
        grounding_audit=grounding_audit_result,
        summarisation_meta=summarisation_meta,
        processing_time_ms=elapsed_ms,
    )
