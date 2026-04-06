"""LLM provider adapter — isolates all model-specific logic.

The adapter uses LiteLLM so we can swap between OpenAI, Anthropic, or local
models without changing calling code.  All provider-specific details stay here.

MVP scope: synchronous completion with JSON-mode response.
Future: streaming, function calling, batch, embeddings.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import litellm
import structlog

from ai_core.ops import record_provider_call

logger = structlog.get_logger()


class LLMProviderError(RuntimeError):
    """Typed provider failure carrying retryability for degraded-mode handling."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        retryable: bool,
        attempts: int,
        message: str,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.attempts = attempts


class LLMAdapter:
    """Thin wrapper around LiteLLM for structured JSON completions."""

    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.0,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        retry_backoff_ms: int | None = None,
        provider: str | None = None,
    ) -> None:
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.provider = provider or os.getenv("LLM_PROVIDER", "openai")
        self.temperature = temperature
        self.timeout_s = timeout_s if timeout_s is not None else float(os.getenv("LLM_TIMEOUT_S", "20"))
        self.max_retries = max_retries if max_retries is not None else int(os.getenv("LLM_MAX_RETRIES", "1"))
        self.retry_backoff_ms = (
            retry_backoff_ms if retry_backoff_ms is not None
            else int(os.getenv("LLM_RETRY_BACKOFF_MS", "250"))
        )

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a prompt and parse the response as JSON.

        If the provider supports JSON-mode / response_format we use it;
        otherwise we instruct the model via system prompt.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "timeout": self.timeout_s,
        }

        attempts = self.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            start = time.perf_counter_ns()
            try:
                response = litellm.completion(**kwargs)
            except Exception as exc:
                latency_ms = int((time.perf_counter_ns() - start) / 1_000_000)
                retryable = _is_retryable_error(exc)
                record_provider_call(
                    provider=self.provider,
                    model=self.model,
                    latency_ms=latency_ms,
                    success=False,
                    retryable=retryable,
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
                logger.warning(
                    "llm.provider_call_failed",
                    provider=self.provider,
                    model=self.model,
                    attempt=attempt,
                    latency_ms=latency_ms,
                    retryable=retryable,
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                )
                last_error = exc
                if retryable and attempt < attempts:
                    time.sleep((self.retry_backoff_ms * attempt) / 1000.0)
                    continue
                raise LLMProviderError(
                    provider=self.provider,
                    model=self.model,
                    retryable=retryable,
                    attempts=attempt,
                    message=str(exc),
                ) from exc

            latency_ms = int((time.perf_counter_ns() - start) / 1_000_000)
            record_provider_call(
                provider=self.provider,
                model=self.model,
                latency_ms=latency_ms,
                success=True,
            )
            raw = response.choices[0].message.content or "{}"
            return json.loads(raw)

        assert last_error is not None
        raise LLMProviderError(
            provider=self.provider,
            model=self.model,
            retryable=False,
            attempts=attempts,
            message=str(last_error),
        ) from last_error


def _is_retryable_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    retryable_markers = (
        "timeout",
        "timed out",
        "rate limit",
        "too many requests",
        "temporarily unavailable",
        "service unavailable",
        "connection",
        "unavailable",
        "retry",
    )
    return any(marker in text for marker in retryable_markers)
