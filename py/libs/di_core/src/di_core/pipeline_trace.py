"""Pipeline observability helpers (Phase 10D).

Provides a context-manager-style stage timer that automatically records
elapsed time and converts exceptions into classified StageOutcomes.

Usage in the API layer:

    trace = PipelineTrace()
    with trace_stage(trace, PipelineStage.PARSE):
        doc = parse_document(doc, path)

    # trace.stages now contains a StageOutcome with elapsed_ms
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator

import structlog

from data_model.pipeline import (
    FailureKind,
    PipelineStage,
    PipelineTrace,
    StageOutcome,
)

logger = structlog.get_logger()


@contextmanager
def trace_stage(
    trace: PipelineTrace,
    stage: PipelineStage,
    *,
    failure_kind_on_error: FailureKind = FailureKind.HARD,
) -> Generator[StageOutcome, None, None]:
    """Time a pipeline stage and record the outcome.

    On success, a passing StageOutcome is appended to the trace.
    On exception, the outcome is marked with the given failure_kind
    and the exception is re-raised so the caller can decide whether
    to continue or abort.

    The yielded StageOutcome can be mutated by the caller to set
    custom failure_kind / message before the context exits.
    """
    outcome = StageOutcome(stage=stage)
    start = time.perf_counter_ns()

    try:
        yield outcome
    except Exception as exc:
        elapsed = int((time.perf_counter_ns() - start) / 1_000_000)
        outcome.elapsed_ms = elapsed
        outcome.success = False
        outcome.failure_kind = failure_kind_on_error
        outcome.message = str(exc)[:200]
        trace.add(outcome)

        logger.warning(
            "pipeline.stage_failed",
            stage=stage.value,
            failure_kind=failure_kind_on_error.value,
            elapsed_ms=elapsed,
            error=str(exc)[:200],
        )
        raise
    else:
        elapsed = int((time.perf_counter_ns() - start) / 1_000_000)
        outcome.elapsed_ms = elapsed
        trace.add(outcome)

        logger.info(
            "pipeline.stage_completed",
            stage=stage.value,
            success=outcome.success,
            failure_kind=outcome.failure_kind.value,
            elapsed_ms=elapsed,
        )


def log_pipeline_summary(trace: PipelineTrace, doc_id: str) -> None:
    """Emit a single structured log line summarizing the full pipeline run."""
    stage_summary = {
        s.stage.value: {
            "ok": s.success,
            "ms": s.elapsed_ms,
            "kind": s.failure_kind.value,
        }
        for s in trace.stages
    }

    logger.info(
        "pipeline.complete",
        doc_id=doc_id,
        total_ms=trace.total_elapsed_ms,
        stages=len(trace.stages),
        hard_failure=trace.has_hard_failure,
        soft_warnings=trace.has_soft_warnings,
        needs_review=trace.needs_review,
        retryable=trace.has_retryable,
        warnings=trace.warnings,
        breakdown=stage_summary,
    )
