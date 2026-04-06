"""Phase 10 — prompt optimization and experiment tracking.

Runs controlled summarisation comparisons across prompt/model/retrieval
variants and returns structured rows that can be reported or persisted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from data_model import ChunkSelectionStrategy, Document, ExtractionResult, StructuredField

from ai_core.adapter import LLMAdapter
from ai_core.prompts import get_prompt
from ai_core.summariser import summarise_document
from di_eval.summary_eval import score_summary


class SupportsCompleteJson(Protocol):
    model: str

    def complete_json(self, system_prompt: str, user_prompt: str, response_schema=None): ...


@dataclass(frozen=True)
class ExperimentVariant:
    """One controlled experiment configuration."""

    label: str
    prompt_name: str
    prompt_version: str
    model: str = "gpt-4o-mini"
    chunk_selection: ChunkSelectionStrategy = ChunkSelectionStrategy.HEAD
    max_chunks: int = 10
    query: str = ""
    use_grounding_fields: bool = False


@dataclass
class ExperimentRow:
    """One scored experiment run."""

    label: str
    prompt_ref: str
    model: str
    chunk_selection: str
    max_chunks: int
    validation_status: str
    processing_time_ms: int
    factual_coverage: float = 0.0
    grounding_score: float = 0.0
    evidence_support: float = 0.0
    actionability: float = 0.0
    notes: list[str] = field(default_factory=list)
    result: ExtractionResult | None = None


@dataclass
class ExperimentComparison:
    """Full side-by-side comparison result."""

    task_type: str
    rows: list[ExperimentRow] = field(default_factory=list)
    best_factual_coverage: str = ""
    best_grounding: str = ""
    fastest_variant: str = ""
    recommendation: str = ""


def run_summary_experiment(
    doc: Document,
    expected_key_facts: list[str],
    variants: list[ExperimentVariant],
    grounding_fields: list[StructuredField] | None = None,
    llm_factory: Callable[[ExperimentVariant], SupportsCompleteJson] | None = None,
) -> ExperimentComparison:
    """Run a controlled summarisation comparison over a shared document."""
    rows: list[ExperimentRow] = []

    for variant in variants:
        prompt = get_prompt(variant.prompt_name, variant.prompt_version)
        llm = llm_factory(variant) if llm_factory else LLMAdapter(model=variant.model)
        result = summarise_document(
            doc,
            llm=llm,
            max_chunks=variant.max_chunks,
            chunk_selection=variant.chunk_selection,
            grounding_fields=grounding_fields if variant.use_grounding_fields else None,
            prompt_template=prompt,
            query=variant.query or None,
            run_label=variant.label,
        )
        full_text = _collect_summary_text(result)
        dims = score_summary(
            fixture=variant.label,
            expected_key_facts=expected_key_facts,
            summary_text=full_text,
            grounding_audit=result.grounding_audit.model_dump() if result.grounding_audit else None,
            summarisation_meta=result.summarisation_meta.model_dump() if result.summarisation_meta else None,
            processing_time_ms=result.processing_time_ms,
        )
        rows.append(ExperimentRow(
            label=variant.label,
            prompt_ref=f"{variant.prompt_name}@{variant.prompt_version}",
            model=result.model_used,
            chunk_selection=variant.chunk_selection.value,
            max_chunks=variant.max_chunks,
            validation_status=result.validation_status,
            processing_time_ms=result.processing_time_ms,
            factual_coverage=dims.factual_coverage,
            grounding_score=dims.grounding_score,
            evidence_support=dims.evidence_support,
            actionability=dims.actionability,
            notes=list(result.experiment_meta.notes) if result.experiment_meta else [],
            result=result,
        ))

    comparison = ExperimentComparison(task_type="summarisation", rows=rows)
    if rows:
        comparison.best_factual_coverage = max(rows, key=lambda row: row.factual_coverage).label
        comparison.best_grounding = max(rows, key=lambda row: row.grounding_score).label
        comparison.fastest_variant = min(rows, key=lambda row: row.processing_time_ms).label
        comparison.recommendation = _recommend(rows)
    return comparison


def _collect_summary_text(result: ExtractionResult) -> str:
    parts: list[str] = []
    if result.summary:
        if result.summary.summary_text:
            parts.append(result.summary.summary_text)
        parts.extend(result.summary.key_points)
        parts.extend(point.text for point in result.summary.grounded_key_points)
    return "\n".join(parts)


def _recommend(rows: list[ExperimentRow]) -> str:
    best = max(rows, key=lambda row: (row.factual_coverage, row.grounding_score, -row.processing_time_ms))
    return (
        f"{best.label} is the strongest overall tradeoff: "
        f"coverage={best.factual_coverage:.2f}, grounding={best.grounding_score:.2f}, "
        f"latency={best.processing_time_ms}ms."
    )
