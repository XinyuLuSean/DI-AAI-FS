"""Smoke tests: document type routing — heuristic classification.

Run with:  uv run pytest tests/smoke/test_routing.py -v
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from py_api.main import app

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def _upload(client: TestClient, filename: str) -> dict:
    with open(FIXTURES / filename, "rb") as f:
        resp = client.post(
            "/documents/upload",
            files={"file": (filename, f, "text/plain")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestRoutingPresent:
    """Routing result is always attached to the document."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_routing_field_exists(self) -> None:
        data = _upload(self.client, "sample.txt")
        assert "routing" in data
        routing = data["routing"]
        assert routing is not None
        assert "predicted_type" in routing
        assert "confidence" in routing
        assert "matched_rules" in routing
        assert "is_fallback" in routing

    def test_routing_has_rules(self) -> None:
        data = _upload(self.client, "sample.txt")
        routing = data["routing"]
        assert len(routing["matched_rules"]) > 0
        rule = routing["matched_rules"][0]
        assert "source" in rule
        assert "pattern" in rule
        assert "matched_type" in rule
        assert "weight" in rule


class TestDocumentTypeClassification:
    """Each fixture is routed to the expected type."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_insurance_claim_routes_to_legal(self) -> None:
        data = _upload(self.client, "sample.txt")
        routing = data["routing"]
        assert routing["predicted_type"] == "legal"
        assert routing["confidence"] > 0
        assert routing["is_fallback"] is False

    def test_medical_record_routes_to_medical(self) -> None:
        data = _upload(self.client, "medical_record.txt")
        routing = data["routing"]
        assert routing["predicted_type"] == "medical"
        assert routing["confidence"] > 0.3

    def test_invoice_routes_to_billing(self) -> None:
        data = _upload(self.client, "invoice_plumbing.txt")
        routing = data["routing"]
        assert routing["predicted_type"] == "billing"
        assert routing["confidence"] > 0.3

    def test_attorney_letter_routes_to_legal_or_correspondence(self) -> None:
        data = _upload(self.client, "attorney_letter.txt")
        routing = data["routing"]
        assert routing["predicted_type"] in ("legal", "correspondence")
        assert routing["confidence"] > 0


class TestFilenameHeuristics:
    """Filename patterns contribute to routing."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_filename_with_invoice_keyword(self) -> None:
        data = _upload(self.client, "invoice_plumbing.txt")
        routing = data["routing"]
        filename_rules = [r for r in routing["matched_rules"] if r["source"] == "filename"]
        assert len(filename_rules) >= 1
        assert any(r["matched_type"] == "billing" for r in filename_rules)

    def test_filename_with_medical_keyword(self) -> None:
        data = _upload(self.client, "medical_record.txt")
        routing = data["routing"]
        filename_rules = [r for r in routing["matched_rules"] if r["source"] == "filename"]
        assert len(filename_rules) >= 1
        assert any(r["matched_type"] == "medical" for r in filename_rules)


class TestFallbackBehaviour:
    """Documents with no matching heuristics get unknown type."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_generic_file_falls_back(self) -> None:
        generic = FIXTURES / "_generic_test.txt"
        generic.write_text("Hello world. This is a simple test file with no domain keywords.")
        try:
            with open(generic, "rb") as f:
                resp = self.client.post(
                    "/documents/upload",
                    files={"file": ("readme.txt", f, "text/plain")},
                )
            assert resp.status_code == 200
            routing = resp.json()["routing"]
            assert routing["predicted_type"] == "unknown"
            assert routing["is_fallback"] is True
            assert routing["confidence"] == 0.0
        finally:
            generic.unlink(missing_ok=True)


class TestRoutingExplainability:
    """Matched rules and warnings are populated for debugging."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_content_rules_carry_keywords(self) -> None:
        data = _upload(self.client, "medical_record.txt")
        routing = data["routing"]
        content_rules = [r for r in routing["matched_rules"] if r["source"] == "content"]
        assert len(content_rules) >= 1
        assert "keywords:" in content_rules[0]["pattern"]

    def test_ambiguous_doc_has_runner_up_warning(self) -> None:
        data = _upload(self.client, "attorney_letter.txt")
        routing = data["routing"]
        has_close_types = len({r["matched_type"] for r in routing["matched_rules"]}) > 1
        if has_close_types:
            assert any("runner-up" in w.lower() for w in routing["warnings"]) or routing["confidence"] > 0.7
