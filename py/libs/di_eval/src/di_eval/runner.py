"""Evaluation runner — orchestrates fixture-based DI evaluation.

Loads ground_truth.json, uploads each fixture through the API, runs
extraction (and optionally summarisation), then scores against expected
values.  Produces structured results that the report module formats.

The runner is API-first: it exercises the *real* upload/extract/summarise
endpoints via FastAPI TestClient, so evaluation covers the full stack.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from di_eval.field_eval import FieldSetMetrics, score_field_set
from di_eval.slice_eval import SliceBreakdown, compute_slice_breakdown
from di_eval.summary_eval import SummaryDimensions, score_summary
from di_eval.system_metrics import (
    FixtureTimings,
    PipelineMetrics,
    collect_pipeline_metrics,
)


@dataclass
class EvalConfig:
    """Configuration for an evaluation run."""

    fixtures_dir: Path
    ground_truth_path: Path
    run_summarisation: bool = False
    max_summary_chunks: int = 10
    skip_missing: bool = True


@dataclass
class EvalResult:
    """Complete output of one evaluation run."""

    config: EvalConfig

    field_metrics: dict[str, FieldSetMetrics] = field(default_factory=dict)
    summary_dims: dict[str, SummaryDimensions] = field(default_factory=dict)
    pipeline_metrics: PipelineMetrics | None = None
    slice_breakdown: SliceBreakdown | None = None

    skipped: list[str] = field(default_factory=list)


class EvalRunner:
    """Runs a full evaluation pass over the fixture set."""

    def __init__(self, client: TestClient, config: EvalConfig) -> None:
        self.client = client
        self.config = config
        self._ground_truth = self._load_ground_truth()

    def run(self) -> EvalResult:
        result = EvalResult(config=self.config)

        fixtures = self._ground_truth.get("fixtures", {})
        slices = self._ground_truth.get("evaluation_slices", {})

        timings: list[FixtureTimings] = []
        routing_results: dict[str, dict] = {}
        expected_routings: dict[str, dict] = {}
        extraction_results: dict[str, dict] = {}
        failures: list[str] = []

        for fixture_name, fixture_gt in fixtures.items():
            fixture_path = self.config.fixtures_dir / fixture_name
            if not fixture_path.exists():
                if self.config.skip_missing:
                    result.skipped.append(fixture_name)
                    continue
                raise FileNotFoundError(f"Fixture not found: {fixture_path}")

            try:
                timing, doc, ext, summ = self._process_fixture(fixture_name, fixture_path)
            except Exception as e:
                failures.append(f"{fixture_name}: {e}")
                continue

            timings.append(timing)

            # ── Routing ──────────────────────────────────────────────
            if doc.get("routing"):
                routing_results[fixture_name] = doc["routing"]
            if fixture_gt.get("expected_routing"):
                expected_routings[fixture_name] = fixture_gt["expected_routing"]

            # ── Field evaluation (9A) ────────────────────────────────
            expected_fields = fixture_gt.get("expected_fields", {})
            actual_fields = self._fields_to_dict(ext)
            extraction_results[fixture_name] = ext

            fm = score_field_set(
                fixture=fixture_name,
                expected_fields=expected_fields,
                actual_fields=actual_fields,
                extraction_time_ms=ext.get("processing_time_ms", 0),
            )
            result.field_metrics[fixture_name] = fm

            # ── Summary evaluation (9B) ──────────────────────────────
            if summ and fixture_gt.get("summary_evaluation"):
                key_facts = fixture_gt["summary_evaluation"].get("key_facts", [])
                full_text = self._collect_summary_text(summ)
                sd = score_summary(
                    fixture=fixture_name,
                    expected_key_facts=key_facts,
                    summary_text=full_text,
                    grounding_audit=summ.get("grounding_audit"),
                    summarisation_meta=summ.get("summarisation_meta"),
                    processing_time_ms=summ.get("processing_time_ms", 0),
                )
                result.summary_dims[fixture_name] = sd

        # ── System metrics (9D) ──────────────────────────────────────
        result.pipeline_metrics = collect_pipeline_metrics(
            timings=timings,
            routing_results=routing_results,
            expected_routings=expected_routings,
            extraction_results=extraction_results,
            failures=failures,
        )

        # ── Slice breakdown (9C) ─────────────────────────────────────
        result.slice_breakdown = compute_slice_breakdown(
            field_metrics=result.field_metrics,
            summary_dims=result.summary_dims,
            evaluation_slices=slices,
        )

        return result

    # ── Internal helpers ─────────────────────────────────────────────

    def _load_ground_truth(self) -> dict:
        with open(self.config.ground_truth_path) as f:
            return json.load(f)

    def _process_fixture(
        self,
        name: str,
        path: Path,
    ) -> tuple[FixtureTimings, dict, dict, dict | None]:
        """Upload → extract → (optional) summarise.  Returns (timings, doc, extraction, summary_or_None)."""
        timing = FixtureTimings(fixture=name)

        # Upload
        t0 = time.perf_counter_ns()
        with open(path, "rb") as f:
            resp = self.client.post(
                "/documents/upload",
                files={"file": (name, f, "text/plain")},
            )
        timing.upload_time_ms = int((time.perf_counter_ns() - t0) / 1_000_000)

        if resp.status_code != 200:
            raise RuntimeError(f"Upload failed ({resp.status_code}): {resp.text[:200]}")
        doc = resp.json()
        doc_id = doc["id"]

        # Extract
        t0 = time.perf_counter_ns()
        resp = self.client.post(f"/documents/{doc_id}/extract")
        timing.extraction_time_ms = int((time.perf_counter_ns() - t0) / 1_000_000)

        if resp.status_code != 200:
            raise RuntimeError(f"Extract failed ({resp.status_code}): {resp.text[:200]}")
        ext = resp.json()

        # Summarise (optional)
        summ = None
        if self.config.run_summarisation:
            t0 = time.perf_counter_ns()
            resp = self.client.post(
                f"/documents/{doc_id}/summarise",
                params={
                    "max_chunks": self.config.max_summary_chunks,
                    "extraction_id": ext.get("id", ""),
                },
            )
            timing.summarisation_time_ms = int((time.perf_counter_ns() - t0) / 1_000_000)

            if resp.status_code == 200:
                summ = resp.json()

        return timing, doc, ext, summ

    @staticmethod
    def _fields_to_dict(extraction: dict) -> dict[str, str | None]:
        """Convert ExtractionResult.structured_fields list to {name: value}."""
        return {
            f["field_name"]: f["field_value"]
            for f in extraction.get("structured_fields", [])
        }

    @staticmethod
    def _collect_summary_text(summ: dict) -> str:
        """Combine summary_text + key_points into a single text for fact matching.

        The LLM often puts specific factual details in key_points rather than
        the narrative summary_text, so both must be included for fair coverage
        measurement.
        """
        parts: list[str] = []
        summary = summ.get("summary", {})
        if summary.get("summary_text"):
            parts.append(summary["summary_text"])
        for kp in summary.get("key_points", []):
            parts.append(kp)
        for gkp in summary.get("grounded_key_points", []):
            if isinstance(gkp, dict) and gkp.get("text"):
                parts.append(gkp["text"])
        return "\n".join(parts)
