"""FastAPI application entry point.

This is the single Python service for the MVP.  It handles:
  - health checks
  - document upload + parsing + chunking
  - AI summarisation

In the final architecture these would split across py-api, worker-ingest,
and worker-ai.  For now, everything runs synchronously in one process.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from py_api.api.documents import router as documents_router
from py_api.api.health import router as health_router
from py_api.core.config import get_settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("py-api starting", storage_backend=settings.storage_backend)
    yield
    logger.info("py-api shutting down")


app = FastAPI(
    title="DI-AAI-FS API",
    description="Document Intelligence + Applied AI backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(documents_router, prefix="/documents", tags=["documents"])
