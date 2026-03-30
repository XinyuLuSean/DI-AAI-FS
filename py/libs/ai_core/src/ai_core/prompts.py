"""Prompt registry — predictable, versioned prompt templates.

Each prompt lives as a named constant with metadata.  This keeps prompts
out of business logic and makes them easy to test/review.

MVP: one summarisation prompt.
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


def build_summarise_user_prompt(
    chunks: list[dict[str, str]],
) -> str:
    """Format chunks into the user-message for the summarisation prompt."""
    parts: list[str] = []
    for c in chunks:
        parts.append(f"[chunk_id={c['chunk_id']}]\n{c['text']}\n")
    return "\n---\n".join(parts)
