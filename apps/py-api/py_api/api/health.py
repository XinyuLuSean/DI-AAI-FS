"""Health endpoint — every service must expose one (Build Rule #9)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "py-api", "version": "0.1.0"}
