"""Smoke tests: deterministic field extraction (Phase 4).

Run with:  uv run pytest tests/smoke/test_extraction.py -v
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from py_api.main import app

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def fixture_path(name: str) -> Path:
    direct = FIXTURES / name
    if direct.exists():
        return direct
    matches = sorted(FIXTURES.rglob(name))
    if not matches:
        raise FileNotFoundError(f"Fixture not found: {name}")
    if len(matches) > 1:
        raise ValueError(f"Fixture name is ambiguous: {name} -> {matches}")
    return matches[0]


def _upload(client: TestClient, filename: str) -> dict:
    with open(fixture_path(filename), "rb") as f:
        resp = client.post(
            "/documents/upload",
            files={"file": (filename, f, "text/plain")},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _extract(client: TestClient, doc_id: str) -> dict:
    resp = client.post(f"/documents/{doc_id}/extract")
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestExtractionEndpoint:
    """The /extract endpoint returns structured fields, no summary."""

    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_extract_returns_result(self) -> None:
        doc = _upload(self.client, "sample.txt")
        result = _extract(self.client, doc["id"])
        assert result["document_id"] == doc["id"]
        assert result["model_used"] == "deterministic"
        assert result["summary"] is None
        assert len(result["structured_fields"]) >= 1

    def test_extract_not_found(self) -> None:
        resp = self.client.post("/documents/nonexistent/extract")
        assert resp.status_code == 404


class TestInsuranceClaimExtraction:
    """sample.txt contains claim number, policy, claimant, amount, adjuster, date."""

    def setup_method(self) -> None:
        self.client = TestClient(app)
        doc = _upload(self.client, "sample.txt")
        self.result = _extract(self.client, doc["id"])
        self.fields = {f["field_name"]: f for f in self.result["structured_fields"]}

    def test_claim_number_extracted(self) -> None:
        assert "claim_number" in self.fields
        assert "2024-INS-00142" in self.fields["claim_number"]["field_value"]

    def test_policy_number_extracted(self) -> None:
        assert "policy_number" in self.fields
        assert "POL-889921" in self.fields["policy_number"]["field_value"]

    def test_total_amount_extracted(self) -> None:
        assert "total_amount" in self.fields
        assert "20,600" in self.fields["total_amount"]["field_value"] or \
               "19,600" in self.fields["total_amount"]["field_value"]

    def test_patient_name_extracted(self) -> None:
        assert "patient_name" in self.fields
        assert "Jane Doe" in self.fields["patient_name"]["field_value"]

    def test_provider_name_extracted(self) -> None:
        assert "provider_name" in self.fields
        assert "John Smith" in self.fields["provider_name"]["field_value"]

    def test_service_date_extracted(self) -> None:
        assert "service_date" in self.fields
        assert "January 15, 2024" in self.fields["service_date"]["field_value"]


class TestInvoiceExtraction:
    """invoice_plumbing.txt contains invoice number, total, account number."""

    def setup_method(self) -> None:
        self.client = TestClient(app)
        doc = _upload(self.client, "invoice_plumbing.txt")
        self.result = _extract(self.client, doc["id"])
        self.fields = {f["field_name"]: f for f in self.result["structured_fields"]}

    def test_invoice_number_extracted(self) -> None:
        assert "invoice_number" in self.fields
        assert "INV-2024-0283" in self.fields["invoice_number"]["field_value"]

    def test_total_amount_extracted(self) -> None:
        assert "total_amount" in self.fields
        assert "6,258.13" in self.fields["total_amount"]["field_value"]

    def test_account_number_extracted(self) -> None:
        assert "account_number" in self.fields
        assert "ACCT-DOE-2024" in self.fields["account_number"]["field_value"]


class TestMedicalRecordExtraction:
    """medical_record.txt contains MRN, patient name, provider, date."""

    def setup_method(self) -> None:
        self.client = TestClient(app)
        doc = _upload(self.client, "medical_record.txt")
        self.result = _extract(self.client, doc["id"])
        self.fields = {f["field_name"]: f for f in self.result["structured_fields"]}

    def test_mrn_extracted(self) -> None:
        assert "mrn" in self.fields
        assert "MED-2024-5567" in self.fields["mrn"]["field_value"]

    def test_patient_name_extracted(self) -> None:
        assert "patient_name" in self.fields
        assert "Robert Thompson" in self.fields["patient_name"]["field_value"]

    def test_provider_extracted(self) -> None:
        assert "provider_name" in self.fields
        assert "Sarah Williams" in self.fields["provider_name"]["field_value"]


class TestFieldEvidenceAndMethod:
    """Every extracted field carries evidence and extraction method."""

    def setup_method(self) -> None:
        self.client = TestClient(app)
        doc = _upload(self.client, "sample.txt")
        self.result = _extract(self.client, doc["id"])

    def test_every_field_has_method(self) -> None:
        for field in self.result["structured_fields"]:
            assert field["extraction_method"] in ("regex", "keyword_window")

    def test_every_field_has_evidence(self) -> None:
        for field in self.result["structured_fields"]:
            assert len(field["evidence"]) >= 1

    def test_every_field_has_snippet(self) -> None:
        for field in self.result["structured_fields"]:
            assert len(field["source_snippet"]) > 0

    def test_evidence_has_page_numbers(self) -> None:
        for field in self.result["structured_fields"]:
            for ev in field["evidence"]:
                assert len(ev["page_numbers"]) >= 1

    def test_confidence_is_conservative(self) -> None:
        for field in self.result["structured_fields"]:
            assert 0.0 < field["confidence"] <= 1.0
