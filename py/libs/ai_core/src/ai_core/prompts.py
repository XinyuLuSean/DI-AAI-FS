"""Prompt registry — first-class, versioned, metadata-rich prompt templates.

Each prompt is a PromptTemplate that carries:
  - identity: name, version, task type
  - system prompt text with explicit goals, evidence rules, uncertainty behavior
  - expected output schema (documented, not just hoped-for)
  - model assumptions and guardrails
  - user-prompt builder function

This keeps prompts out of business logic, makes them inspectable, testable,
and versionable.  Every AI result can trace back to the exact prompt template
and version that produced it.

Registry access:
  get_prompt(name, version)  — look up a specific prompt
  list_prompts()             — list all registered prompts
  SUMMARISE_V1               — standalone summarisation
  GROUNDED_SUMMARISE_V1      — grounded by pre-extracted fields
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Callable

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────


class TaskType(StrEnum):
    SUMMARISATION = "summarisation"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    MATCHING = "matching"


# ── PromptTemplate model ──────────────────────────────────────────────────


class PromptTemplate(BaseModel):
    """A prompt as a first-class, inspectable, versionable component.

    Separates *what the prompt says* from *how it gets called*.
    The summariser (or any future AI task) consumes this object,
    never a bare string.
    """

    # ── Identity ──────────────────────────────────────────────────────
    name: str
    version: str
    task_type: TaskType
    description: str

    # ── Prompt text ───────────────────────────────────────────────────
    system_prompt: str

    # ── Expected output contract ──────────────────────────────────────
    expected_output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON schema documenting the expected LLM output structure",
    )

    # ── Model assumptions ─────────────────────────────────────────────
    model_assumptions: list[str] = Field(
        default_factory=list,
        description="Models/providers this prompt was designed and tested for",
    )

    # ── Explicit prompt goals (Module 1C) ─────────────────────────────
    evidence_requirements: list[str] = Field(
        default_factory=list,
        description="What evidence behavior is required",
    )
    uncertainty_instructions: list[str] = Field(
        default_factory=list,
        description="How the model should behave when uncertain",
    )
    guardrails: list[str] = Field(
        default_factory=list,
        description="What the model must NOT do",
    )


# ── Expected output schema (shared documentation) ─────────────────────────

SUMMARISATION_OUTPUT_SCHEMA: dict[str, Any] = {
    "summary_text": {
        "type": "string",
        "description": "A concise 2-4 sentence summary of the document",
        "required": True,
    },
    "key_points": {
        "type": "array",
        "items": {
            "point": {"type": "string", "description": "A factual statement"},
            "chunk_ids": {"type": "array", "items": "string", "description": "IDs of chunks supporting this point"},
        },
        "required": True,
    },
    "structured_fields": {
        "type": "array",
        "items": {
            "field_name": {"type": "string"},
            "field_value": {"type": "string"},
            "confidence": {"type": "number", "range": "0.0-1.0"},
        },
        "required": True,
    },
    "chunk_ids_used": {
        "type": "array",
        "items": "string",
        "description": "Union of all chunk_ids referenced across all key_points",
        "required": True,
    },
}


# ── System prompt texts ───────────────────────────────────────────────────

_SUMMARISE_SYSTEM_TEXT = """\
You are a document analysis assistant.
You receive text chunks from a document and produce a structured JSON summary.

Return ONLY valid JSON with this exact schema:
{
  "summary_text": "A concise 2-4 sentence summary of the document.",
  "key_points": [
    {"point": "A factual statement supported by the text.", "chunk_ids": ["id1", "id2"]},
    {"point": "Another factual statement.", "chunk_ids": ["id3"]}
  ],
  "structured_fields": [
    {
      "field_name": "document_type",
      "field_value": "the detected document type",
      "confidence": 0.0-1.0
    }
  ],
  "chunk_ids_used": ["id1", "id2", "id3"]
}

Rules:
- Be factual.  Only state what the text supports.
- For each key_point, list the specific chunk_ids that support that point.
- chunk_ids_used is the union of all chunk_ids referenced across all key_points.
- Do NOT make claims that no chunk supports.
- If evidence for a point is weak or ambiguous, say so in the point text rather than asserting confidently.
- If the document type is unclear, set confidence below 0.5.
- Do NOT invent information that is not present in the provided chunks.
- Do NOT speculate about content that might exist outside the provided chunks.\
"""

_GROUNDED_SUMMARISE_SYSTEM_TEXT = """\
You are a document analysis assistant.
You receive text chunks from a document along with fields that have already been
deterministically extracted with high confidence.

IMPORTANT: The pre-extracted fields below are ground truth.  Your summary MUST
be consistent with them.  Do NOT contradict, alter, or re-interpret these values.
Incorporate them naturally into your summary and key points.

Return ONLY valid JSON with this exact schema:
{
  "summary_text": "A concise 2-4 sentence summary of the document.",
  "key_points": [
    {"point": "A factual statement supported by the text.", "chunk_ids": ["id1", "id2"]},
    {"point": "Another factual statement.", "chunk_ids": ["id3"]}
  ],
  "structured_fields": [
    {
      "field_name": "document_type",
      "field_value": "the detected document type",
      "confidence": 0.0-1.0
    }
  ],
  "chunk_ids_used": ["id1", "id2", "id3"]
}

Rules:
- Be factual.  Only state what the text supports.
- For each key_point, list the specific chunk_ids that support that point.
- chunk_ids_used is the union of all chunk_ids referenced across all key_points.
- Do NOT make claims that no chunk supports.
- Do NOT contradict the pre-extracted fields.
- If evidence for a point is weak or ambiguous, say so in the point text rather than asserting confidently.
- If the document type is unclear, set confidence below 0.5.
- Do NOT invent information that is not present in the provided chunks.
- Do NOT speculate about content that might exist outside the provided chunks.\
"""


# ── Registered prompt templates ───────────────────────────────────────────

SUMMARISE_V1 = PromptTemplate(
    name="summarise",
    version="1.0",
    task_type=TaskType.SUMMARISATION,
    description=(
        "Standalone document summarisation from chunks only.  "
        "Produces a concise summary, evidence-backed key points, "
        "and optional structured fields."
    ),
    system_prompt=_SUMMARISE_SYSTEM_TEXT,
    expected_output_schema=SUMMARISATION_OUTPUT_SCHEMA,
    model_assumptions=[
        "gpt-4o-mini (primary, tested)",
        "gpt-4o (supported, higher quality)",
        "Any LiteLLM-compatible model with JSON-mode support",
    ],
    evidence_requirements=[
        "Every key_point MUST cite the chunk_ids that support it",
        "chunk_ids_used MUST be the union of all cited chunk_ids",
        "Only chunks actually provided in the context may be cited",
    ],
    uncertainty_instructions=[
        "If evidence for a claim is weak, qualify the statement",
        "If the document type is unclear, set confidence below 0.5",
        "Prefer omitting a point over stating an unsupported claim",
    ],
    guardrails=[
        "Do NOT make claims unsupported by provided chunks",
        "Do NOT invent content not present in the provided text",
        "Do NOT speculate about content outside the provided chunks",
        "Do NOT cite chunk IDs that were not provided",
    ],
)

GROUNDED_SUMMARISE_V1 = PromptTemplate(
    name="grounded_summarise",
    version="1.0",
    task_type=TaskType.SUMMARISATION,
    description=(
        "Grounded document summarisation.  Pre-extracted deterministic "
        "fields are injected as ground truth constraints so the LLM "
        "summary stays consistent with known facts (dates, amounts, names)."
    ),
    system_prompt=_GROUNDED_SUMMARISE_SYSTEM_TEXT,
    expected_output_schema=SUMMARISATION_OUTPUT_SCHEMA,
    model_assumptions=[
        "gpt-4o-mini (primary, tested)",
        "gpt-4o (supported, higher quality)",
        "Any LiteLLM-compatible model with JSON-mode support",
    ],
    evidence_requirements=[
        "Every key_point MUST cite the chunk_ids that support it",
        "chunk_ids_used MUST be the union of all cited chunk_ids",
        "Only chunks actually provided in the context may be cited",
        "Pre-extracted fields are ground truth — summary must not contradict them",
    ],
    uncertainty_instructions=[
        "If evidence for a claim is weak, qualify the statement",
        "If the document type is unclear, set confidence below 0.5",
        "Prefer omitting a point over stating an unsupported claim",
    ],
    guardrails=[
        "Do NOT make claims unsupported by provided chunks",
        "Do NOT contradict pre-extracted deterministic fields",
        "Do NOT re-interpret or alter pre-extracted field values",
        "Do NOT invent content not present in the provided text",
        "Do NOT speculate about content outside the provided chunks",
        "Do NOT cite chunk IDs that were not provided",
    ],
)


# ── Backward-compatible aliases (used by summariser until migration) ──────

SUMMARISE_SYSTEM = SUMMARISE_V1.system_prompt
GROUNDED_SUMMARISE_SYSTEM = GROUNDED_SUMMARISE_V1.system_prompt


# ── Prompt registry ──────────────────────────────────────────────────────

_REGISTRY: dict[tuple[str, str], PromptTemplate] = {
    (SUMMARISE_V1.name, SUMMARISE_V1.version): SUMMARISE_V1,
    (GROUNDED_SUMMARISE_V1.name, GROUNDED_SUMMARISE_V1.version): GROUNDED_SUMMARISE_V1,
}


def get_prompt(name: str, version: str = "1.0") -> PromptTemplate:
    """Look up a prompt template by name and version."""
    key = (name, version)
    if key not in _REGISTRY:
        available = [f"{n}@{v}" for n, v in _REGISTRY]
        raise KeyError(
            f"Prompt '{name}@{version}' not found. "
            f"Available: {', '.join(available)}"
        )
    return _REGISTRY[key]


def list_prompts() -> list[PromptTemplate]:
    """Return all registered prompt templates."""
    return list(_REGISTRY.values())


def register_prompt(template: PromptTemplate) -> None:
    """Register a new prompt template (or overwrite an existing version)."""
    _REGISTRY[(template.name, template.version)] = template


# ── User prompt builder ──────────────────────────────────────────────────


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
