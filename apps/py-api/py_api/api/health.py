"""Health endpoint — every service must expose one (Build Rule #9)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ai_core import get_ai_ops_snapshot

from py_api.core.config import get_settings

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "py-api", "version": "0.1.0"}


@router.get("/health/ai-ops")
async def ai_ops_health() -> dict[str, Any]:
    """Operational health summary for the Applied AI runtime."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": "py-api",
        "version": "0.1.0",
        "deployment_mode": "synchronous_single_process",
        "llm_runtime": {
            "provider": settings.llm_provider,
            "default_model": settings.llm_model,
            "timeout_s": settings.llm_timeout_s,
            "max_retries": settings.llm_max_retries,
            "retry_backoff_ms": settings.llm_retry_backoff_ms,
        },
        "ai_ops": get_ai_ops_snapshot().model_dump(mode="json"),
    }
