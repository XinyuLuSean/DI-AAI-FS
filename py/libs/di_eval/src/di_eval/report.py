"""Evaluation report formatting.

Converts structured evaluation results into human-readable text reports.
Three report types:
  1. Deterministic metrics report — per-fixture field extraction results
  2. Summary evaluation report — per-fixture summary dimension scores
  3. Retrieval-aware report — relevance, grounding, latency, token efficiency
  4. Slice breakdown report — aggregated metrics per document slice
"""

from __future__ import annotations

from di_eval.field_eval import FieldSetMetrics
from di_eval.experiment import ExperimentComparison
from di_eval.retrieval_eval import RetrievalMetrics
from di_eval.slice_eval import SliceBreakdown, SliceStats
from di_eval.summary_eval import SummaryDimensions
from di_eval.system_metrics import PipelineMetrics

SEPARATOR = "─" * 72


def format_deterministic_report(
    field_metrics: dict[str, FieldSetMetrics],
    pipeline_metrics: PipelineMetrics | None = None,
) -> str:
    """Produce a per-fixture deterministic field extraction report."""
    lines: list[str] = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════════════════╗")
    lines.append("║          DETERMINISTIC FIELD EXTRACTION — EVALUATION REPORT         ║")
    lines.append("╚══════════════════════════════════════════════════════════════════════╝")
    lines.append("")

    if pipeline_metrics:
        lines.append(f"Fixtures processed: {pipeline_metrics.fixtures_processed}")
        lines.append(f"Fixtures failed:    {pipeline_metrics.fixtures_failed}")
        lines.append(f"Routing accuracy:   {pipeline_metrics.routing_accuracy:.1%}")
        lines.append(f"Evidence attach %:  {pipeline_metrics.evidence_attachment_rate:.1%}")
        lines.append("")
        lines.append(SEPARATOR)

    # Aggregate P/R/F1
    total_tp = sum(m.true_positives for m in field_metrics.values())
    total_fp = sum(m.false_positives for m in field_metrics.values())
    total_fn = sum(m.false_negatives for m in field_metrics.values())
    agg_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
    agg_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
    agg_f1 = 2 * agg_p * agg_r / (agg_p + agg_r) if (agg_p + agg_r) > 0 else 0.0

    lines.append("")
    lines.append(f"  AGGREGATE  Precision={agg_p:.3f}  Recall={agg_r:.3f}  F1={agg_f1:.3f}")
    lines.append(f"             TP={total_tp}  FP={total_fp}  FN={total_fn}")
    lines.append("")
    lines.append(SEPARATOR)

    for fixture, fm in sorted(field_metrics.items()):
        lines.append("")
        lines.append(f"  [{fixture}]")
        lines.append(f"  P={fm.precision:.3f}  R={fm.recall:.3f}  F1={fm.f1:.3f}  "
                      f"({fm.extraction_time_ms}ms)")
        lines.append("")

        for fr in fm.field_results:
            status = _field_status_icon(fr.must_extract, fr.best_match, fr.actual_value)
            exp_display = repr(fr.expected_value) if fr.expected_value else "—"
            act_display = repr(fr.actual_value) if fr.actual_value else "—"
            match_type = _match_type_label(fr)

            lines.append(f"    {status} {fr.field_name:<18} "
                          f"exp={exp_display:<24} "
                          f"act={act_display:<24} "
                          f"{match_type}")

        lines.append("")
        lines.append(SEPARATOR)

    return "\n".join(lines)


def format_summary_report(summary_dims: dict[str, SummaryDimensions]) -> str:
    """Produce a per-fixture summary evaluation report."""
    lines: list[str] = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════════════════╗")
    lines.append("║           SUMMARY EVALUATION — MULTI-DIMENSION REPORT              ║")
    lines.append("╚══════════════════════════════════════════════════════════════════════╝")
    lines.append("")

    if not summary_dims:
        lines.append("  (No summary evaluation results — summarisation was not run)")
        return "\n".join(lines)

    for fixture, sd in sorted(summary_dims.items()):
        lines.append(f"  [{fixture}]")
        lines.append(f"    Factual coverage:  {sd.factual_coverage:.1%}  "
                      f"({sum(1 for f in sd.fact_details if f.covered)}/{len(sd.fact_details)} facts)")
        lines.append(f"    Grounding score:   {sd.grounding_score:.1%}  "
                      f"({sd.key_points_grounded}/{sd.key_points_total} grounded)")
        lines.append(f"    Contradictions:    {sd.contradiction_count}")
        lines.append(f"    Evidence support:  {sd.evidence_support:.1%}")
        lines.append(f"    Actionability:     {sd.actionability:.2f}")
        lines.append(f"    Needs review:      {sd.needs_review}")
        lines.append(f"    Latency:           {sd.summarisation_time_ms}ms")
        lines.append("")

        missed = [f for f in sd.fact_details if not f.covered]
        if missed:
            lines.append("    Uncovered facts:")
            for f in missed:
                lines.append(f"      ✗ {f.fact[:80]}")
            lines.append("")

        lines.append(SEPARATOR)

    return "\n".join(lines)


def format_retrieval_report(retrieval_metrics: dict[str, RetrievalMetrics]) -> str:
    """Produce a retrieval-aware evaluation report."""
    lines: list[str] = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════════════════╗")
    lines.append("║            RETRIEVAL-AWARE EVALUATION REPORT                        ║")
    lines.append("╚══════════════════════════════════════════════════════════════════════╝")
    lines.append("")

    if not retrieval_metrics:
        lines.append("  (No retrieval-aware evaluation results available)")
        return "\n".join(lines)

    for fixture, rm in sorted(retrieval_metrics.items()):
        lines.append(f"  [{fixture}]")
        lines.append(f"    Query:              {rm.query[:72]}")
        lines.append(f"    Head avg relevance: {rm.head_avg_relevance:.3f}")
        lines.append(f"    Ranked relevance:   {rm.query_ranked_avg_relevance:.3f}")
        lines.append(f"    Relevance lift:     {rm.relevance_lift:+.3f}")
        lines.append(f"    Overlap:            {rm.selected_overlap:.1%}")
        lines.append(f"    Retrieval latency:  {rm.retrieval_latency_ms}ms")
        lines.append(f"    Token efficiency:   {rm.token_efficiency:.1%}")
        lines.append(f"    Evidence usefulness:{rm.evidence_usefulness:.1%}")
        lines.append(f"    Answer grounding:   {rm.answer_grounding:.1%}")
        if rm.notes:
            lines.append("    Notes:")
            for note in rm.notes:
                lines.append(f"      - {note[:120]}")
        lines.append("")
        lines.append(SEPARATOR)

    return "\n".join(lines)


def format_experiment_report(comparison: ExperimentComparison) -> str:
    """Produce a side-by-side prompt/model/retrieval comparison report."""
    lines: list[str] = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════════════════╗")
    lines.append("║             PROMPT EXPERIMENT COMPARISON REPORT                     ║")
    lines.append("╚══════════════════════════════════════════════════════════════════════╝")
    lines.append("")

    if not comparison.rows:
        lines.append("  (No experiment rows available)")
        return "\n".join(lines)

    lines.append(
        f"  Best coverage: {comparison.best_factual_coverage} | "
        f"Best grounding: {comparison.best_grounding} | "
        f"Fastest: {comparison.fastest_variant}"
    )
    lines.append(f"  Recommendation: {comparison.recommendation}")
    lines.append("")
    lines.append(
        f"  {'Label':<18} {'Prompt':<24} {'Model':<12} {'Ret':<12} "
        f"{'Cov':>5} {'Gnd':>5} {'Evd':>5} {'Act':>5} {'ms':>5}"
    )
    lines.append(f"  {'─' * 68}")
    for row in comparison.rows:
        lines.append(
            f"  {row.label[:18]:<18} {row.prompt_ref[:24]:<24} {row.model[:12]:<12} "
            f"{row.chunk_selection[:12]:<12} {row.factual_coverage:>5.2f} "
            f"{row.grounding_score:>5.2f} {row.evidence_support:>5.2f} "
            f"{row.actionability:>5.2f} {row.processing_time_ms:>5}"
        )
    lines.append("")
    return "\n".join(lines)


def format_slice_report(breakdown: SliceBreakdown | None) -> str:
    """Produce a slice-based evaluation breakdown report."""
    lines: list[str] = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════════════════╗")
    lines.append("║              SLICE-BASED EVALUATION BREAKDOWN                       ║")
    lines.append("╚══════════════════════════════════════════════════════════════════════╝")

    if breakdown is None:
        lines.append("  (No slice breakdown available)")
        return "\n".join(lines)

    for label, stats_list in [
        ("By Document Type", breakdown.by_document_type),
        ("By Size Category", breakdown.by_size_category),
        ("By File Format", breakdown.by_file_format),
        ("By Extraction Density", breakdown.by_extraction_density),
        ("By Section Richness", breakdown.by_section_richness),
        ("By Content Style", breakdown.by_content_style),
        ("By Parse Quality", breakdown.by_parse_quality),
        ("By Page Count Bucket", breakdown.by_page_count_bucket),
        ("By Text Cleanliness", breakdown.by_text_cleanliness),
        ("By Task Type", breakdown.by_task_type),
        ("By Model Prompt", breakdown.by_model_prompt),
    ]:
        lines.append("")
        lines.append(f"  {label}")
        lines.append(f"  {'─' * 60}")

        if not stats_list:
            lines.append("    (no data)")
            continue

        lines.append(f"    {'Slice':<22} {'N':>3}  {'P':>6}  {'R':>6}  {'F1':>6}  "
                      f"{'Cov':>6}  {'Gnd':>6}  {'Ret':>6}  {'Lift':>6}")
        lines.append(f"    {'─' * 62}")

        for s in sorted(stats_list, key=lambda x: x.slice_value):
            lines.append(
                f"    {s.slice_value[:22]:<22} {s.fixture_count:>3}  "
                f"{s.avg_precision:>6.3f}  {s.avg_recall:>6.3f}  {s.avg_f1:>6.3f}  "
                f"{s.avg_factual_coverage:>6.3f}  {s.avg_grounding_score:>6.3f}  "
                f"{s.avg_retrieval_relevance:>6.3f}  {s.avg_retrieval_lift:>6.3f}"
            )

    for slice_name, stats_list in sorted(breakdown.other_slices.items()):
        lines.append("")
        lines.append(f"  {slice_name}")
        lines.append(f"  {'─' * 60}")
        if not stats_list:
            lines.append("    (no data)")
            continue
        for s in sorted(stats_list, key=lambda x: x.slice_value):
            lines.append(f"    {s.slice_value}: n={s.fixture_count} f1={s.avg_f1:.3f}")

    lines.append("")
    return "\n".join(lines)


def format_system_metrics_report(metrics: PipelineMetrics | None) -> str:
    """Produce a system-level metrics report."""
    lines: list[str] = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════════════════╗")
    lines.append("║                   DI SYSTEM METRICS REPORT                          ║")
    lines.append("╚══════════════════════════════════════════════════════════════════════╝")

    if metrics is None:
        lines.append("  (No system metrics available)")
        return "\n".join(lines)

    lines.append("")
    lines.append("  Pipeline Health")
    lines.append(f"    Processed:           {metrics.fixtures_processed}/{metrics.total_fixtures}")
    lines.append(f"    Failed:              {metrics.fixtures_failed}")
    lines.append(f"    Failure rate:        {metrics.extraction_failure_rate:.1%}")
    lines.append("")
    lines.append("  Routing")
    lines.append(f"    Correct:             {metrics.routing_correct}")
    lines.append(f"    Incorrect:           {metrics.routing_incorrect}")
    lines.append(f"    Accuracy:            {metrics.routing_accuracy:.1%}")
    lines.append("")
    lines.append("  Extraction Quality")
    lines.append(f"    Fields extracted:    {metrics.total_fields_extracted}")
    lines.append(f"    With evidence:       {metrics.total_fields_with_evidence}")
    lines.append(f"    Evidence attach %:   {metrics.evidence_attachment_rate:.1%}")
    lines.append("")
    lines.append("  Latency (ms)")
    lines.append(f"    Upload       avg={metrics.avg_upload_ms:>7.0f}  max={metrics.max_upload_ms}")
    lines.append(f"    Extraction   avg={metrics.avg_extraction_ms:>7.0f}  max={metrics.max_extraction_ms}")
    lines.append(f"    Summarise    avg={metrics.avg_summarisation_ms:>7.0f}  max={metrics.max_summarisation_ms}")
    lines.append("")

    if metrics.failures:
        lines.append("  Failures:")
        for f in metrics.failures:
            lines.append(f"    ✗ {f}")
        lines.append("")

    return "\n".join(lines)


# ── Helpers ──────────────────────────────────────────────────────────────

def _field_status_icon(must_extract: bool, matched: bool, actual: str | None) -> str:
    if must_extract:
        return "✓" if matched else "✗"
    if actual is None:
        return "·"
    return "?"


def _match_type_label(fr) -> str:  # noqa: ANN001
    if fr.exact_match:
        return "[exact]"
    if fr.normalized_match:
        return "[normalized]"
    if fr.numeric_close:
        return "[numeric]"
    if fr.date_close:
        return "[date]"
    if fr.must_extract and fr.actual_value is not None:
        return "[MISMATCH]"
    if fr.must_extract and fr.actual_value is None:
        return "[MISSING]"
    if not fr.must_extract and fr.actual_value is not None:
        return "[SPURIOUS]"
    return ""
