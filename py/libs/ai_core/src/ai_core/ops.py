"""Operational metrics for the Applied AI runtime (Phase 13).

This module intentionally keeps the first productionization slice simple:
  - in-memory counters only (single-process prototype)
  - small, inspectable metrics surface
  - explicit sync-vs-async recommendations for the current architecture

Future production evolution would move these counters to shared telemetry
backends and collect them across worker processes.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from threading import Lock

from pydantic import BaseModel, Field

from data_model import ExtractionResult


SYNC_PATHS = [
    "document_search",
    "retrieval_compare",
    "deterministic_extract",
    "interactive_summarise_small_docs",
]

ASYNC_CANDIDATES = [
    "hierarchical_summarise_large_docs",
    "batch_evaluation_runs",
    "embedding_index_builds",
    "prompt_experiment_regressions",
]


class ProviderErrorEvent(BaseModel):
    provider: str = ""
    model: str = ""
    retryable: bool = False
    error_type: str = ""
    message: str = ""
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AIOpsSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    provider_calls_total: int = 0
    provider_errors_total: int = 0
    retryable_provider_errors: int = 0
    provider_error_rate: float = 0.0

    task_runs_total: int = 0
    retrieval_requests_total: int = 0

    avg_model_latency_ms: float = 0.0
    max_model_latency_ms: int = 0
    avg_generation_latency_ms: float = 0.0
    max_generation_latency_ms: int = 0
    avg_retrieval_latency_ms: float = 0.0
    max_retrieval_latency_ms: int = 0

    output_valid_rate: float = 1.0
    grounding_failure_rate: float = 0.0
    unsupported_claim_rate: float = 0.0
    review_needed_rate: float = 0.0

    sync_paths: list[str] = Field(default_factory=lambda: list(SYNC_PATHS))
    async_candidates: list[str] = Field(default_factory=lambda: list(ASYNC_CANDIDATES))
    recent_provider_errors: list[ProviderErrorEvent] = Field(default_factory=list)


class _AIOpsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._recent_provider_errors: deque[ProviderErrorEvent] = deque(maxlen=12)
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.provider_calls_total = 0
            self.provider_errors_total = 0
            self.retryable_provider_errors = 0

            self.task_runs_total = 0
            self.retrieval_requests_total = 0

            self.model_latency_sum_ms = 0
            self.max_model_latency_ms = 0
            self.generation_latency_sum_ms = 0
            self.max_generation_latency_ms = 0
            self.retrieval_latency_sum_ms = 0
            self.max_retrieval_latency_ms = 0

            self.valid_outputs = 0
            self.grounding_failures = 0
            self.unsupported_claim_runs = 0
            self.review_needed_runs = 0

            self._recent_provider_errors.clear()

    def record_provider_call(
        self,
        *,
        provider: str,
        model: str,
        latency_ms: int,
        success: bool,
        retryable: bool = False,
        error_type: str = "",
        message: str = "",
    ) -> None:
        with self._lock:
            self.provider_calls_total += 1
            self.model_latency_sum_ms += latency_ms
            self.max_model_latency_ms = max(self.max_model_latency_ms, latency_ms)

            if success:
                return

            self.provider_errors_total += 1
            if retryable:
                self.retryable_provider_errors += 1

            self._recent_provider_errors.appendleft(ProviderErrorEvent(
                provider=provider,
                model=model,
                retryable=retryable,
                error_type=error_type,
                message=message[:200],
            ))

    def record_task_result(self, result: ExtractionResult) -> None:
        uncertainty = result.uncertainty_assessment
        audit = result.grounding_audit

        with self._lock:
            self.task_runs_total += 1
            self.generation_latency_sum_ms += result.processing_time_ms
            self.max_generation_latency_ms = max(
                self.max_generation_latency_ms,
                result.processing_time_ms,
            )

            if result.validation_status == "valid":
                self.valid_outputs += 1

            if audit and (audit.needs_review or audit.grounding_score < 0.7):
                self.grounding_failures += 1

            unsupported_claims = 0
            if uncertainty:
                unsupported_claims = uncertainty.unsupported_claim_count
            elif audit:
                unsupported_claims = audit.key_points_ungrounded + audit.chunks_cited_invalid

            if unsupported_claims > 0:
                self.unsupported_claim_runs += 1

            if (
                result.validation_status != "valid"
                or (uncertainty and uncertainty.review_recommended)
                or (audit and audit.needs_review)
            ):
                self.review_needed_runs += 1

    def record_retrieval_latency(self, latency_ms: int) -> None:
        with self._lock:
            self.retrieval_requests_total += 1
            self.retrieval_latency_sum_ms += latency_ms
            self.max_retrieval_latency_ms = max(self.max_retrieval_latency_ms, latency_ms)

    def snapshot(self) -> AIOpsSnapshot:
        with self._lock:
            provider_error_rate = (
                self.provider_errors_total / self.provider_calls_total
                if self.provider_calls_total > 0 else 0.0
            )
            output_valid_rate = (
                self.valid_outputs / self.task_runs_total
                if self.task_runs_total > 0 else 1.0
            )
            grounding_failure_rate = (
                self.grounding_failures / self.task_runs_total
                if self.task_runs_total > 0 else 0.0
            )
            unsupported_claim_rate = (
                self.unsupported_claim_runs / self.task_runs_total
                if self.task_runs_total > 0 else 0.0
            )
            review_needed_rate = (
                self.review_needed_runs / self.task_runs_total
                if self.task_runs_total > 0 else 0.0
            )
            avg_model_latency_ms = (
                self.model_latency_sum_ms / self.provider_calls_total
                if self.provider_calls_total > 0 else 0.0
            )
            avg_generation_latency_ms = (
                self.generation_latency_sum_ms / self.task_runs_total
                if self.task_runs_total > 0 else 0.0
            )
            avg_retrieval_latency_ms = (
                self.retrieval_latency_sum_ms / self.retrieval_requests_total
                if self.retrieval_requests_total > 0 else 0.0
            )

            return AIOpsSnapshot(
                provider_calls_total=self.provider_calls_total,
                provider_errors_total=self.provider_errors_total,
                retryable_provider_errors=self.retryable_provider_errors,
                provider_error_rate=round(provider_error_rate, 4),
                task_runs_total=self.task_runs_total,
                retrieval_requests_total=self.retrieval_requests_total,
                avg_model_latency_ms=round(avg_model_latency_ms, 2),
                max_model_latency_ms=self.max_model_latency_ms,
                avg_generation_latency_ms=round(avg_generation_latency_ms, 2),
                max_generation_latency_ms=self.max_generation_latency_ms,
                avg_retrieval_latency_ms=round(avg_retrieval_latency_ms, 2),
                max_retrieval_latency_ms=self.max_retrieval_latency_ms,
                output_valid_rate=round(output_valid_rate, 4),
                grounding_failure_rate=round(grounding_failure_rate, 4),
                unsupported_claim_rate=round(unsupported_claim_rate, 4),
                review_needed_rate=round(review_needed_rate, 4),
                recent_provider_errors=list(self._recent_provider_errors),
            )


_REGISTRY = _AIOpsRegistry()


def record_provider_call(**kwargs) -> None:  # noqa: ANN003
    _REGISTRY.record_provider_call(**kwargs)


def record_ai_task_result(result: ExtractionResult) -> None:
    _REGISTRY.record_task_result(result)


def record_retrieval_latency(latency_ms: int) -> None:
    _REGISTRY.record_retrieval_latency(latency_ms)


def get_ai_ops_snapshot() -> AIOpsSnapshot:
    return _REGISTRY.snapshot()


def reset_ai_ops_metrics() -> None:
    _REGISTRY.reset()
