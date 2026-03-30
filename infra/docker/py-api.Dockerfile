FROM python:3.12-slim AS base

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .python-version ./
COPY py/libs/data_model py/libs/data_model
COPY py/libs/di_core py/libs/di_core
COPY py/libs/ai_core py/libs/ai_core
COPY py/libs/storage py/libs/storage
COPY apps/py-api apps/py-api

RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "py_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
