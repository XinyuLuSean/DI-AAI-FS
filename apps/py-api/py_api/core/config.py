"""Application settings — driven entirely by environment variables.

Uses pydantic-settings so every config value is validated on startup.
The .env.example file documents all expected variables.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    py_api_host: str = "0.0.0.0"
    py_api_port: int = 8000
    py_api_log_level: str = "info"

    storage_backend: str = "local"
    storage_local_path: str = "./uploads"

    llm_model: str = "gpt-4o-mini"
    llm_provider: str = "openai"
    openai_api_key: str = ""

    database_url: str = ""
    redis_url: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
