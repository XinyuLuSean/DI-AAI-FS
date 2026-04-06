"""Phase 13 tests — productionization guardrails and AI ops visibility."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ai_core import LLMAdapter, LLMProviderError, get_ai_ops_snapshot, reset_ai_ops_metrics
from ai_core.ops import record_ai_task_result
from data_model import ExtractionResult, GroundingAudit, OutputType, UncertaintyAssessment
from py_api.main import app

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def fixture_path(name: str) -> Path:
    direct = FIXTURES / name
    if direct.exists():
        return direct
    matches = sorted(FIXTURES.rglob(name))
    if not matches:
        raise FileNotFoundError(f"Fixture not found: {name}")
    return matches[0]


def _upload(client: TestClient, filename: str) -> dict:
    with open(fixture_path(filename), "rb") as f:
        resp = client.post(
            "/documents/upload",
            files={"file": (filename, f, "text/plain")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _fake_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


class TestPhase13Health:
    def setup_method(self) -> None:
        reset_ai_ops_metrics()
        self.client = TestClient(app)

    def test_ai_ops_health_exposes_runtime_profile(self) -> None:
        resp = self.client.get("/health/ai-ops")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deployment_mode"] == "synchronous_single_process"
        assert "llm_runtime" in data
        assert "ai_ops" in data
        assert "sync_paths" in data["ai_ops"]
        assert "async_candidates" in data["ai_ops"]

    def test_ai_ops_health_reflects_recorded_task_metrics(self) -> None:
        record_ai_task_result(ExtractionResult(
            document_id="doc1",
            output_type=OutputType.AI_SUMMARY,
            validation_status="partial_recovery",
            processing_time_ms=180,
            grounding_audit=GroundingAudit(grounding_score=0.4, needs_review=True),
            uncertainty_assessment=UncertaintyAssessment(
                unsupported_claim_count=2,
                review_recommended=True,
            ),
        ))

        resp = self.client.get("/health/ai-ops")
        data = resp.json()["ai_ops"]
        assert data["task_runs_total"] == 1
        assert data["output_valid_rate"] == 0.0
        assert data["grounding_failure_rate"] == 1.0
        assert data["unsupported_claim_rate"] == 1.0
        assert data["review_needed_rate"] == 1.0


class TestLLMAdapterReliability:
    def setup_method(self) -> None:
        reset_ai_ops_metrics()

    def test_adapter_retries_retryable_provider_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"count": 0}

        def fake_completion(**kwargs):  # noqa: ANN003
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("Rate limit exceeded")
            return _fake_response('{"ok": true}')

        monkeypatch.setattr("ai_core.adapter.litellm.completion", fake_completion)

        adapter = LLMAdapter(
            model="fake-model",
            provider="fake-provider",
            max_retries=1,
            retry_backoff_ms=0,
            timeout_s=1.0,
        )

        result = adapter.complete_json("system", "user")
        snapshot = get_ai_ops_snapshot()

        assert result == {"ok": True}
        assert calls["count"] == 2
        assert snapshot.provider_calls_total == 2
        assert snapshot.provider_errors_total == 1

    def test_adapter_raises_typed_error_after_retry_exhaustion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_completion(**kwargs):  # noqa: ANN003
            raise RuntimeError("Connection timeout to provider")

        monkeypatch.setattr("ai_core.adapter.litellm.completion", fake_completion)

        adapter = LLMAdapter(
            model="fake-model",
            provider="fake-provider",
            max_retries=1,
            retry_backoff_ms=0,
            timeout_s=1.0,
        )

        with pytest.raises(LLMProviderError) as exc:
            adapter.complete_json("system", "user")

        snapshot = get_ai_ops_snapshot()
        assert exc.value.retryable is True
        assert exc.value.attempts == 2
        assert snapshot.provider_errors_total == 2


class TestPhase13DegradedMode:
    def setup_method(self) -> None:
        reset_ai_ops_metrics()
        self.client = TestClient(app)

    def test_summarise_rejects_unknown_extraction_id(self) -> None:
        doc = _upload(self.client, "sample.txt")
        resp = self.client.post(
            f"/documents/{doc['id']}/summarise",
            params={"extraction_id": "missing-extraction"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Extraction not found"

    def test_summarise_rejects_unknown_prompt(self) -> None:
        doc = _upload(self.client, "sample.txt")
        resp = self.client.post(
            f"/documents/{doc['id']}/summarise",
            params={"prompt_name": "does_not_exist"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Prompt 'does_not_exist@1.0' not found"

    def test_summarise_returns_503_on_provider_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_completion(**kwargs):  # noqa: ANN003
            raise RuntimeError("Service unavailable from provider")

        monkeypatch.setattr("ai_core.adapter.litellm.completion", fake_completion)

        doc = _upload(self.client, "sample.txt")
        resp = self.client.post(f"/documents/{doc['id']}/summarise")

        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert detail["retryable"] is True
        assert detail["provider"] != ""

    def test_retrieval_requests_show_up_in_ai_ops_snapshot(self) -> None:
        doc = _upload(self.client, "sample.txt")
        resp = self.client.post(
            f"/documents/{doc['id']}/search",
            json={"query": "water damage repair", "top_k": 3, "ranker": "salience"},
        )
        assert resp.status_code == 200

        health = self.client.get("/health/ai-ops")
        ai_ops = health.json()["ai_ops"]
        assert ai_ops["retrieval_requests_total"] >= 1
        assert ai_ops["avg_retrieval_latency_ms"] >= 0

    def test_list_extractions_includes_prompt_metadata_for_summaries(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "ai_core.adapter.litellm.completion",
            lambda **kwargs: _fake_response(
                '{"summary_text":"A grounded summary.","key_points":[{"point":"Claim","chunk_ids":["c1"]}],"structured_fields":[],"chunk_ids_used":["c1"]}',
            ),
        )

        doc = _upload(self.client, "sample.txt")
        extraction = self.client.post(f"/documents/{doc['id']}/extract").json()
        summary = self.client.post(
            f"/documents/{doc['id']}/summarise",
            params={"extraction_id": extraction["id"]},
        ).json()

        resp = self.client.get(f"/documents/{doc['id']}/extractions")
        assert resp.status_code == 200

        items = resp.json()
        summary_item = next(item for item in items if item["id"] == summary["id"])
        assert summary_item["prompt_name"] == "grounded_summarise"
        assert summary_item["prompt_version"] == "1.0"
