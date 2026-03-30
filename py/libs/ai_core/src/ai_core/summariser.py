"""Document summarisation workflow.

Orchestrates: select chunks → build prompt → call LLM → parse into schema.

This is the first AI task in the vertical slice.  It demonstrates:
- strict JSON output via the adapter
- evidence references back to source chunks
- separation between prompt definition and execution
"""

from __future__ import annotations

import time
from typing import Any

from data_model import (
    Document,
    EvidenceReference,
    ExtractionResult,
    StructuredField,
    SummaryResult,
)

from ai_core.adapter import LLMAdapter
from ai_core.prompts import SUMMARISE_SYSTEM, build_summarise_user_prompt


def summarise_document(
    doc: Document,
    llm: LLMAdapter | None = None,
    max_chunks: int = 10,
) -> ExtractionResult:
    """Run summarisation over the document's chunks and return structured output."""
    llm = llm or LLMAdapter()
    start = time.perf_counter_ns()

    selected = doc.chunks[:max_chunks]
    chunk_dicts = [{"chunk_id": c.chunk_id, "text": c.text} for c in selected]
    chunk_map = {c.chunk_id: c for c in selected}

    user_prompt = build_summarise_user_prompt(chunk_dicts)
    raw: dict[str, Any] = llm.complete_json(
        system_prompt=SUMMARISE_SYSTEM,
        user_prompt=user_prompt,
    )

    used_ids: list[str] = raw.get("chunk_ids_used", [])
    evidence = _build_evidence(used_ids, chunk_map)

    fields = [
        StructuredField(
            field_name=f.get("field_name", ""),
            field_value=f.get("field_value", ""),
            confidence=float(f.get("confidence", 0.0)),
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
