"""Smoke test: verify the py-api health endpoint is reachable.

Run with:  uv run pytest tests/smoke/test_health.py -v
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from py_api.main import app


class TestHealthEndpoint:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_health_returns_ok(self) -> None:
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "py-api"

    def test_health_has_version(self) -> None:
        response = self.client.get("/health")
        data = response.json()
        assert "version" in data
