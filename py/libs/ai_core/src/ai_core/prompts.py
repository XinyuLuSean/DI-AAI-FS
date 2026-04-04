"""Prompt registry — predictable, versioned prompt templates.

Each prompt lives as a named constant with metadata.  This keeps prompts
out of business logic and makes them easy to test/review.

Two summarisation variants:
  - SUMMARISE_SYSTEM: standalone summarisation from chunks only
  - GROUNDED_SUMMARISE_SYSTEM: grounded by pre-extracted deterministic fields

Future: template rendering, few-shot examples, prompt versioning table.
"""

from __future__ import annotations

SUMMARISE_SYSTEM = """You are a document analysis assistant.
You receive text chunks from a document and produce a structured JSON summary.

Return ONLY valid JSON with this exact schema:
{
  "summary_text": "A concise 2-4 sentence summary of the document.",
  "key_points": ["point 1", "point 2", ...],
  "structured_fields": [
    {
      "field_name": "document_type",
      "field_value": "the detected document type",
      "confidence": 0.0-1.0
    }
  ],
  "chunk_ids_used": ["id1", "id2", ...]
}

Rules:
- Be factual.  Only state what the text supports.
- Reference which chunk_ids you relied on in chunk_ids_used.
- If the document type is unclear, set confidence below 0.5.
"""

GROUNDED_SUMMARISE_SYSTEM = """You are a document analysis assistant.
You receive text chunks from a document along with fields that have already been
deterministically extracted with high confidence.

IMPORTANT: The pre-extracted fields below are ground truth.  Your summary MUST
be consistent with them.  Do NOT contradict, alter, or re-interpret these values.
Incorporate them naturally into your summary and key points.

Return ONLY valid JSON with this exact schema:
{
  "summary_text": "A concise 2-4 sentence summary of the document.",
  "key_points": ["point 1", "point 2", ...],
  "structured_fields": [
    {
      "field_name": "document_type",
      "field_value": "the detected document type",
      "confidence": 0.0-1.0
    }
  ],
  "chunk_ids_used": ["id1", "id2", ...]
}

Rules:
- Be factual.  Only state what the text supports.
- Reference which chunk_ids you relied on in chunk_ids_used.
- If the document type is unclear, set confidence below 0.5.
- Do NOT contradict the pre-extracted fields.
"""


def build_summarise_user_prompt(
    chunks: list[dict[str, str]],
    extracted_fields: list[dict[str, str]] | None = None,
) -> str:
    """Format chunks (and optional grounding fields) into the user prompt."""
    sections: list[str] = []

    if extracted_fields:
        field_lines = []
        for f in extracted_fields:
            field_lines.append(f"  - {f['field_name']}: {f['field_value']} (confidence: {f['confidence']})")
        sections.append(
            "PRE-EXTRACTED FIELDS (treat as ground truth):\n" + "\n".join(field_lines)
        )

    chunk_parts: list[str] = []
    for c in chunks:
        chunk_parts.append(f"[chunk_id={c['chunk_id']}]\n{c['text']}\n")
    sections.append("DOCUMENT CHUNKS:\n" + "\n---\n".join(chunk_parts))

    return "\n\n".join(sections)
