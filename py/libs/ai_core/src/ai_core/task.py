"""AI task abstraction — the interface every AI task must implement.

This module defines a Protocol that captures the shared contract across all
AI tasks (summarisation, chronology, future: classification, matching, etc).

The pattern every task follows:
  select chunks → build prompt → call LLM → validate output → audit grounding → package result

The task-specific parts are:
  - prompt template selection
  - user prompt construction
  - output validation schema
  - result assembly (which ExtractionResult fields to populate)

Shared orchestration (chunk selection, LLM call, timing) lives in `run_ai_task`.
Task implementations only define the hooks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from data_model import (
    ChunkSelectionStrategy,
    Document,
    DocumentChunk,
    ExtractionResult,
    OutputType,
    SummarisationMeta,
)

from ai_core.adapter import LLMAdapter
from ai_core.prompts import PromptTemplate, TaskType
from ai_core.validation import ValidationResult


@dataclass(frozen=True)
class TaskContext:
    """Shared context available to every task during execution.

    Created by run_ai_task after chunk selection, before the task builds its prompt.
    """

    doc: Document
    selected_chunks: list[DocumentChunk]
    chunk_map: dict[str, DocumentChunk] = field(repr=False)
    provided_ids: set[str] = field(repr=False)
    summarisation_meta: SummarisationMeta = field(repr=False)
    grounding_field_dicts: list[dict[str, str]] | None = None


@runtime_checkable
class AITask(Protocol):
    """Interface every AI task must implement.

    The task defines *what* to ask the LLM and *how* to interpret the response.
    The shared orchestrator handles *how* to call the LLM and select chunks.
    """

    @property
    def task_type(self) -> TaskType: ...

    @property
    def output_type(self) -> OutputType: ...

    @property
    def prompt_template(self) -> PromptTemplate: ...

    def build_user_prompt(self, ctx: TaskContext) -> str:
        """Build the user-facing prompt from chunks and optional context."""
        ...

    def validate_output(self, raw: dict[str, Any]) -> ValidationResult:
        """Validate and clean the raw LLM JSON response."""
        ...

    def build_result(
        self,
        ctx: TaskContext,
        validated_output: Any,
        vr: ValidationResult,
        llm: LLMAdapter,
        elapsed_ms: int,
    ) -> ExtractionResult:
        """Assemble the task-specific ExtractionResult from validated output."""
        ...


# ── Task registry ─────────────────────────────────────────────────────────

_TASK_REGISTRY: dict[str, type] = {}


def register_task(task_cls: type) -> type:
    """Register an AITask implementation by its task_type."""
    instance = task_cls()
    _TASK_REGISTRY[instance.task_type] = task_cls
    return task_cls


def get_task(task_type: str) -> AITask:
    """Look up a registered task by type string."""
    if task_type not in _TASK_REGISTRY:
        available = list(_TASK_REGISTRY.keys())
        raise KeyError(
            f"Task '{task_type}' not found. Available: {', '.join(available)}"
        )
    return _TASK_REGISTRY[task_type]()


def list_tasks() -> list[str]:
    """Return all registered task type strings."""
    return list(_TASK_REGISTRY.keys())


# ── Shared orchestration ──────────────────────────────────────────────────

import time

import structlog

from di_core.chunk_selector import select_chunks_for_llm

logger = structlog.get_logger()


def run_ai_task(
    task: AITask,
    doc: Document,
    llm: LLMAdapter | None = None,
    max_chunks: int = 10,
    chunk_selection: ChunkSelectionStrategy = ChunkSelectionStrategy.HEAD,
    grounding_fields: list[Any] | None = None,
) -> ExtractionResult:
    """Shared orchestration for any AI task.

    Pipeline: select chunks → build ctx → build prompt → LLM call
    → validate → delegate result building to task.
    """
    llm = llm or LLMAdapter()
    start = time.perf_counter_ns()

    selected, summarisation_meta = select_chunks_for_llm(
        doc, max_chunks=max_chunks, strategy=chunk_selection,
    )

    chunk_map = {c.chunk_id: c for c in selected}
    provided_ids = set(chunk_map.keys())

    grounding_field_dicts: list[dict[str, str]] | None = None
    if grounding_fields:
        grounding_field_dicts = [
            {
                "field_name": f.field_name,
                "field_value": f.field_value,
                "confidence": str(f.confidence),
            }
            for f in grounding_fields
        ]

    ctx = TaskContext(
        doc=doc,
        selected_chunks=selected,
        chunk_map=chunk_map,
        provided_ids=provided_ids,
        summarisation_meta=summarisation_meta,
        grounding_field_dicts=grounding_field_dicts,
    )

    user_prompt = task.build_user_prompt(ctx)

    raw: dict[str, Any] = llm.complete_json(
        system_prompt=task.prompt_template.system_prompt,
        user_prompt=user_prompt,
    )

    vr = task.validate_output(raw)

    elapsed_ms = int((time.perf_counter_ns() - start) / 1_000_000)

    logger.info(
        "ai_task.completed",
        task_type=task.task_type,
        doc_id=doc.id,
        model=llm.model,
        elapsed_ms=elapsed_ms,
        validation_status=vr.status.value,
    )

    return task.build_result(ctx, vr.output, vr, llm, elapsed_ms)
