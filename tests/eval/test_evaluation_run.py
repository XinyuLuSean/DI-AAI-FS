"""Phase 9 — Full evaluation run against the fixture set.

Exercises the complete DI pipeline (upload → extract) for every fixture in
ground_truth.json that exists on disk, then scores and reports results.

Run with:
  uv run pytest tests/eval/test_evaluation_run.py -v -s

The -s flag is important — the evaluation reports are printed to stdout
as part of the test output so you can inspect them.

This test does NOT run summarisation by default (requires OPENAI_API_KEY).
To include summary evaluation:
  EVAL_SUMMARISE=1 uv run pytest tests/eval/test_evaluation_run.py -v -s
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from py_api.main import app

from di_eval.report import (
    format_deterministic_report,
    format_retrieval_report,
    format_slice_report,
    format_summary_report,
    format_system_metrics_report,
)
from di_eval.runner import EvalConfig, EvalRunner

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "data" / "fixtures"
GROUND_TRUTH = FIXTURES_DIR / "ground_truth.json"


@pytest.fixture(scope="module")
def eval_result():
    """Run the full evaluation once and share across tests."""
    client = TestClient(app)
    config = EvalConfig(
        fixtures_dir=FIXTURES_DIR,
        ground_truth_path=GROUND_TRUTH,
        run_summarisation=os.environ.get("EVAL_SUMMARISE", "") == "1",
        skip_missing=True,
    )
    runner = EvalRunner(client, config)
    return runner.run()


class TestDeterministicEvaluation:
    """Module 9A — deterministic field extraction scoring."""

    def test_all_available_fixtures_processed(self, eval_result) -> None:
        assert len(eval_result.field_metrics) > 0, "No fixtures were processed"
        print(f"\n  Processed {len(eval_result.field_metrics)} fixtures, "
              f"skipped {len(eval_result.skipped)}")
        if eval_result.skipped:
            print(f"  Skipped (missing): {eval_result.skipped}")

    def test_aggregate_precision_above_threshold(self, eval_result) -> None:
        total_tp = sum(m.true_positives for m in eval_result.field_metrics.values())
        total_fp = sum(m.false_positives for m in eval_result.field_metrics.values())
        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
        print(f"\n  Aggregate precision: {precision:.3f}")
        assert precision >= 0.5, f"Aggregate precision too low: {precision:.3f}"

    def test_aggregate_recall_above_threshold(self, eval_result) -> None:
        total_tp = sum(m.true_positives for m in eval_result.field_metrics.values())
        total_fn = sum(m.false_negatives for m in eval_result.field_metrics.values())
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
        print(f"\n  Aggregate recall: {recall:.3f}")
        assert recall >= 0.5, f"Aggregate recall too low: {recall:.3f}"

    def test_per_fixture_reports(self, eval_result) -> None:
        report = format_deterministic_report(
            eval_result.field_metrics,
            eval_result.pipeline_metrics,
        )
        print(report)

    def test_sample_txt_extraction_quality(self, eval_result) -> None:
        fm = eval_result.field_metrics.get("sample.txt")
        if fm is None:
            pytest.skip("sample.txt not in evaluation set")
        assert fm.f1 >= 0.7, f"sample.txt F1 too low: {fm.f1:.3f}"

    def test_medical_record_extraction_quality(self, eval_result) -> None:
        fm = eval_result.field_metrics.get("medical_record.txt")
        if fm is None:
            pytest.skip("medical_record.txt not in evaluation set")
        assert fm.recall >= 0.7, f"medical_record.txt recall too low: {fm.recall:.3f}"


class TestSummaryEvaluation:
    """Module 9B — summary evaluation dimensions (only when EVAL_SUMMARISE=1)."""

    def test_summary_report(self, eval_result) -> None:
        report = format_summary_report(eval_result.summary_dims)
        print(report)
        if not eval_result.summary_dims:
            pytest.skip("Summary evaluation not run (set EVAL_SUMMARISE=1)")


class TestRetrievalAwareEvaluation:
    """Module 9C — retrieval-aware evaluation."""

    def test_retrieval_report(self, eval_result) -> None:
        report = format_retrieval_report(eval_result.retrieval_metrics)
        print(report)
        assert len(eval_result.retrieval_metrics) > 0

    def test_retrieval_metrics_have_latency(self, eval_result) -> None:
        assert all(rm.retrieval_latency_ms >= 0 for rm in eval_result.retrieval_metrics.values())


class TestSliceBreakdown:
    """Module 9D — evaluation broken down by document slices."""

    def test_slice_report(self, eval_result) -> None:
        report = format_slice_report(eval_result.slice_breakdown)
        print(report)

    def test_has_document_type_slices(self, eval_result) -> None:
        if eval_result.slice_breakdown is None:
            pytest.skip("No slice breakdown")
        assert len(eval_result.slice_breakdown.by_document_type) > 0

    def test_has_size_category_slices(self, eval_result) -> None:
        if eval_result.slice_breakdown is None:
            pytest.skip("No slice breakdown")
        assert len(eval_result.slice_breakdown.by_size_category) > 0

    def test_has_runtime_parse_quality_slices(self, eval_result) -> None:
        if eval_result.slice_breakdown is None:
            pytest.skip("No slice breakdown")
        assert len(eval_result.slice_breakdown.by_parse_quality) > 0


class TestSystemMetrics:
    """System-level operational metrics."""

    def test_system_metrics_report(self, eval_result) -> None:
        report = format_system_metrics_report(eval_result.pipeline_metrics)
        print(report)

    def test_no_failures(self, eval_result) -> None:
        pm = eval_result.pipeline_metrics
        assert pm is not None
        if pm.failures:
            print(f"\n  Failures: {pm.failures}")
        assert pm.fixtures_failed == 0, f"{pm.fixtures_failed} fixture(s) failed"

    def test_routing_accuracy(self, eval_result) -> None:
        pm = eval_result.pipeline_metrics
        assert pm is not None
        print(f"\n  Routing accuracy: {pm.routing_accuracy:.1%}")
        assert pm.routing_accuracy >= 0.5, f"Routing accuracy too low: {pm.routing_accuracy:.1%}"

    def test_evidence_attachment_rate(self, eval_result) -> None:
        pm = eval_result.pipeline_metrics
        assert pm is not None
        print(f"\n  Evidence attachment: {pm.evidence_attachment_rate:.1%}")
        assert pm.evidence_attachment_rate >= 0.8, (
            f"Evidence attachment too low: {pm.evidence_attachment_rate:.1%}"
        )
