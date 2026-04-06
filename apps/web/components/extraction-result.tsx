"use client";

import { useState } from "react";
import type {
  ClassificationResult,
  ChronologyEvent,
  CoverageReportData,
  EvidenceGapAnalysis,
  ExtractionResponse,
  EvidenceReference,
  GroundedKeyPoint,
  GroundingAudit,
  SemanticMatchResult,
  SummarisationMeta,
} from "@/lib/types";

interface Props {
  result: ExtractionResponse;
}

export function ExtractionResult({ result }: Props) {
  return (
    <div className="space-y-6">
      {/* Run metadata + output type badge */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500">
        <span
          className={`rounded-full px-2.5 py-0.5 font-medium ${
            result.output_type === "deterministic"
              ? "bg-gray-100 text-gray-700"
              : result.output_type === "ai_chronology"
                ? "bg-indigo-100 text-indigo-700"
                : result.output_type === "ai_classification"
                  ? "bg-emerald-100 text-emerald-700"
                  : result.output_type === "semantic_match"
                    ? "bg-amber-100 text-amber-700"
                    : "bg-purple-100 text-purple-700"
          }`}
        >
          {result.output_type === "deterministic"
            ? "Deterministic"
            : result.output_type === "ai_chronology"
              ? "AI Chronology"
              : result.output_type === "ai_classification"
                ? "Readiness Classification"
                : result.output_type === "semantic_match"
                  ? "Semantic Match"
                  : "AI Summary"}
        </span>
        <span>Model: {result.model_used}</span>
        {result.prompt_name && (
          <span>Prompt: {result.prompt_name}@{result.prompt_version}</span>
        )}
        <span>Time: {result.processing_time_ms}ms</span>
        <span>ID: {result.id}</span>
      </div>

      {/* Validation status banner (Phase 2) */}
      {result.validation_status && result.validation_status !== "valid" && (
        <div
          className={`rounded-lg border p-4 text-xs ${
            result.validation_status === "missing_required" || result.validation_status === "wrong_structure"
              ? "border-red-200 bg-red-50"
              : "border-amber-200 bg-amber-50"
          }`}
        >
          <h4
            className={`text-sm font-medium ${
              result.validation_status === "missing_required" || result.validation_status === "wrong_structure"
                ? "text-red-700"
                : "text-amber-700"
            }`}
          >
            Schema Validation: {result.validation_status.replace(/_/g, " ")}
          </h4>
          {result.validation_warnings.length > 0 && (
            <div className="mt-2 space-y-1">
              {result.validation_warnings.map((w, i) => (
                <p
                  key={i}
                  className={
                    result.validation_status === "missing_required" || result.validation_status === "wrong_structure"
                      ? "text-red-600"
                      : "text-amber-600"
                  }
                >
                  {w}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Grounding audit banner (Phase 8C) */}
      {result.grounding_audit && (
        <GroundingAuditPanel audit={result.grounding_audit} />
      )}

      {/* Summarisation meta (Phase 8D) */}
      {result.summarisation_meta && (
        <SummarisationMetaPanel meta={result.summarisation_meta} />
      )}

      {/* Evidence gap analysis (Phase 3C) */}
      {result.evidence_gap && (
        <EvidenceGapPanel gap={result.evidence_gap} />
      )}

      {/* Coverage report (Phase 7) */}
      {result.coverage_report && result.coverage_report.coverage_level && (
        <CoveragePanel report={result.coverage_report} />
      )}

      {/* Summary */}
      {result.summary && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <div className="mb-3 flex items-center gap-3">
            <h3 className="text-lg font-semibold">Summary</h3>
            {result.summary.grounding_coverage > 0 && (
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  result.summary.grounding_coverage >= 0.8
                    ? "bg-emerald-100 text-emerald-700"
                    : result.summary.grounding_coverage >= 0.5
                      ? "bg-yellow-100 text-yellow-700"
                      : "bg-red-100 text-red-700"
                }`}
              >
                {(result.summary.grounding_coverage * 100).toFixed(0)}% grounded
              </span>
            )}
          </div>
          <p className="leading-relaxed text-gray-700">
            {result.summary.summary_text}
          </p>

          {/* Grounded key points (Phase 8A) */}
          {result.summary.grounded_key_points.length > 0 && (
            <GroundedKeyPointsList points={result.summary.grounded_key_points} />
          )}

          {/* Fallback: plain key points when grounded points are absent */}
          {result.summary.grounded_key_points.length === 0 &&
            result.summary.key_points.length > 0 && (
              <div className="mt-4">
                <h4 className="mb-2 text-sm font-medium text-gray-500">
                  Key Points
                </h4>
                <ul className="list-inside list-disc space-y-1 text-sm text-gray-700">
                  {result.summary.key_points.map((point, i) => (
                    <li key={i}>{point}</li>
                  ))}
                </ul>
              </div>
            )}

          {/* Evidence panel */}
          {result.summary.evidence.length > 0 && (
            <EvidencePanel evidence={result.summary.evidence} />
          )}
        </div>
      )}

      {result.classification && (
        <ClassificationPanel classification={result.classification} />
      )}

      {result.semantic_match && (
        <SemanticMatchPanel semanticMatch={result.semantic_match} />
      )}

      {/* Chronology timeline (Phase 4) */}
      {result.chronology && result.chronology.events.length > 0 && (
        <ChronologyPanel events={result.chronology.events} coverage={result.chronology.grounding_coverage} />
      )}

      {/* Structured fields */}
      {result.structured_fields.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h3 className="mb-3 text-lg font-semibold">Extracted Fields</h3>
          <div className="divide-y divide-gray-100">
            {result.structured_fields.map((field, i) => (
              <div key={i} className="py-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900">
                      {field.field_name}
                    </span>
                    <span className="text-sm text-gray-600">
                      {field.field_value}
                    </span>
                    {field.extraction_method && (
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-mono text-gray-500">
                        {field.extraction_method}
                      </span>
                    )}
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      field.confidence >= 0.8
                        ? "bg-emerald-100 text-emerald-700"
                        : field.confidence >= 0.5
                          ? "bg-yellow-100 text-yellow-700"
                          : "bg-red-100 text-red-700"
                    }`}
                  >
                    {(field.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                {field.source_snippet && (
                  <p className="mt-1 text-xs text-gray-400 line-clamp-2">
                    {field.source_snippet}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ClassificationPanel({ classification }: { classification: ClassificationResult }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <div className="mb-3 flex items-center gap-3">
        <h3 className="text-lg font-semibold">Classification</h3>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            classification.label === "ready"
              ? "bg-emerald-100 text-emerald-700"
              : classification.label === "blocked"
                ? "bg-red-100 text-red-700"
                : "bg-amber-100 text-amber-700"
          }`}
        >
          {classification.label}
        </span>
        <span className="text-xs text-gray-500">
          {(classification.confidence * 100).toFixed(0)}% confidence
        </span>
      </div>

      {classification.rationale.length > 0 && (
        <div className="space-y-1 text-sm text-gray-700">
          {classification.rationale.map((item, idx) => (
            <p key={idx}>{item}</p>
          ))}
        </div>
      )}

      {classification.signals.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {classification.signals.map((signal, idx) => (
            <span
              key={`${signal.name}-${idx}`}
              className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600"
            >
              {signal.name}: {signal.value} ({signal.weight.toFixed(1)})
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function SemanticMatchPanel({ semanticMatch }: { semanticMatch: SemanticMatchResult }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h3 className="text-lg font-semibold">Semantic Matching</h3>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
          {semanticMatch.matched_count} matched
        </span>
        {semanticMatch.unmatched_count > 0 && (
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
            {semanticMatch.unmatched_count} below threshold
          </span>
        )}
      </div>

      <div className="space-y-3">
        {semanticMatch.matches.map((match, idx) => (
          <div key={`${match.field_name}-${idx}`} className="rounded-lg border border-gray-100 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-gray-900">{match.field_name}</span>
              <span className="text-sm text-gray-600">{match.field_value}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  match.grounded ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
                }`}
              >
                {match.grounded ? "grounded" : "not grounded"}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-500">
              <span>combined {match.combined_score.toFixed(2)}</span>
              <span>lexical {match.lexical_score.toFixed(2)}</span>
              <span>vector {match.vector_score.toFixed(2)}</span>
              {match.matched_chunk_id && <span className="font-mono">{match.matched_chunk_id}</span>}
              {match.page_numbers.length > 0 && <span>pp. {match.page_numbers.join(", ")}</span>}
              {match.section_label && <span>{match.section_label}</span>}
            </div>
            {match.snippet && (
              <p className="mt-2 rounded border border-amber-100 bg-amber-50/50 px-3 py-2 text-xs text-gray-700">
                {match.snippet}
              </p>
            )}
          </div>
        ))}
      </div>

      {semanticMatch.clusters.length > 0 && (
        <div className="mt-4">
          <h4 className="mb-2 text-sm font-medium text-gray-500">Topic Groups</h4>
          <div className="flex flex-wrap gap-2">
            {semanticMatch.clusters.map((cluster, idx) => (
              <span key={`${cluster.cluster_label}-${idx}`} className="rounded-full bg-blue-50 px-2.5 py-1 text-xs text-blue-700">
                {cluster.cluster_label} · {cluster.member_count} chunk{cluster.member_count !== 1 ? "s" : ""}
              </span>
            ))}
          </div>
        </div>
      )}

      {semanticMatch.notes.length > 0 && (
        <div className="mt-4 space-y-1 text-xs text-gray-500">
          {semanticMatch.notes.map((note, idx) => (
            <p key={idx}>{note}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function GroundedKeyPointsList({ points }: { points: GroundedKeyPoint[] }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  return (
    <div className="mt-4">
      <h4 className="mb-2 text-sm font-medium text-gray-500">
        Key Points
      </h4>
      <ul className="space-y-2 text-sm">
        {points.map((gkp, i) => (
          <li key={i}>
            <div className="flex items-start gap-2">
              <span
                className={`mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full ${
                  gkp.grounded ? "bg-emerald-500" : "bg-red-400"
                }`}
              />
              <div className="flex-1">
                <span className="text-gray-700">{gkp.text}</span>
                {gkp.chunk_ids.length > 0 && (
                  <span className="ml-2 text-[10px] font-mono text-gray-400">
                    [{gkp.chunk_ids.join(", ")}]
                  </span>
                )}
                {gkp.page_numbers && gkp.page_numbers.length > 0 && (
                  <span className="ml-2 text-[10px] text-blue-400">
                    pp. {gkp.page_numbers.join(", ")}
                  </span>
                )}
                {!gkp.grounded && (
                  <span className="ml-2 rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-600">
                    ungrounded
                  </span>
                )}
                {gkp.evidence_snippets && gkp.evidence_snippets.length > 0 && (
                  <button
                    onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                    className="ml-2 text-[10px] text-blue-500 hover:underline"
                  >
                    {expandedIdx === i ? "hide evidence" : "show evidence"}
                  </button>
                )}
              </div>
            </div>
            {expandedIdx === i && gkp.evidence_snippets && gkp.evidence_snippets.length > 0 && (
              <div className="ml-4 mt-1 space-y-1">
                {gkp.evidence_snippets.map((snippet, j) => (
                  <div
                    key={j}
                    className="rounded border border-blue-100 bg-blue-50/50 px-2.5 py-1.5 text-xs text-gray-600"
                  >
                    {snippet}
                  </div>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function GroundingAuditPanel({ audit }: { audit: GroundingAudit }) {
  const hasIssues = audit.needs_review || audit.warnings.length > 0;
  if (!hasIssues && audit.grounding_score >= 0.8) return null;

  return (
    <div
      className={`rounded-lg border p-4 text-xs ${
        audit.needs_review
          ? "border-red-200 bg-red-50"
          : "border-amber-200 bg-amber-50"
      }`}
    >
      <div className="mb-2 flex items-center gap-3">
        <h4
          className={`text-sm font-medium ${
            audit.needs_review ? "text-red-700" : "text-amber-700"
          }`}
        >
          Grounding Audit
          {audit.needs_review && (
            <span className="ml-2 rounded bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-red-700">
              Review needed
            </span>
          )}
        </h4>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-gray-600">
        <span>
          Score:{" "}
          <span className="font-medium">
            {(audit.grounding_score * 100).toFixed(0)}%
          </span>
        </span>
        <span>
          Key points: {audit.key_points_grounded}/{audit.key_points_total}{" "}
          grounded
        </span>
        <span>
          Chunks cited: {audit.chunks_cited_valid} valid
          {audit.chunks_cited_invalid > 0 && (
            <span className="text-red-600">
              , {audit.chunks_cited_invalid} invalid
            </span>
          )}
        </span>
      </div>
      {audit.warnings.length > 0 && (
        <div className="mt-2 space-y-1">
          {audit.warnings.map((w, i) => (
            <p
              key={i}
              className={
                audit.needs_review ? "text-red-600" : "text-amber-600"
              }
            >
              {w}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function SummarisationMetaPanel({ meta }: { meta: SummarisationMeta }) {
  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 p-4 text-xs">
      <h4 className="mb-2 text-sm font-medium text-gray-600">
        Coverage Report
      </h4>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-gray-500">
        <span>
          Chunks:{" "}
          <span className="font-medium text-gray-700">
            {meta.chunks_sent_to_llm}/{meta.total_chunks_available} sent
          </span>
        </span>
        <span>
          Coverage:{" "}
          <span className="font-medium text-gray-700">
            {(meta.coverage_ratio * 100).toFixed(0)}%
          </span>
        </span>
        {meta.chunks_cited_by_llm > 0 && (
          <span>
            Evidence usage:{" "}
            <span className="font-medium text-gray-700">
              {meta.chunks_cited_by_llm} cited (
              {(meta.evidence_usage_ratio * 100).toFixed(0)}%)
            </span>
          </span>
        )}
        <span>
          Pages covered:{" "}
          <span className="font-medium text-gray-700">
            {meta.pages_covered_by_selection.length}/{meta.total_pages_available}
          </span>
        </span>
        <span>
          Strategy:{" "}
          <span className="font-mono text-gray-700">
            {meta.selection_strategy}
          </span>
        </span>
        {meta.is_partial && (
          <span className="font-medium text-amber-600">Partial summary</span>
        )}
      </div>
      {meta.warnings.length > 0 && (
        <div className="mt-2 space-y-1">
          {meta.warnings.map((w, i) => (
            <p key={i} className="text-amber-600">
              {w}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

const STRENGTH_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  strong: { bg: "bg-emerald-100", text: "text-emerald-700", label: "Strong" },
  moderate: { bg: "bg-blue-100", text: "text-blue-700", label: "Moderate" },
  weak: { bg: "bg-amber-100", text: "text-amber-700", label: "Weak" },
  none: { bg: "bg-red-100", text: "text-red-700", label: "No Evidence" },
};

function EvidenceGapPanel({ gap }: { gap: EvidenceGapAnalysis }) {
  const style = STRENGTH_STYLES[gap.overall_strength] ?? STRENGTH_STYLES.none;

  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 p-4 text-xs">
      <div className="mb-2 flex items-center gap-3">
        <h4 className="text-sm font-medium text-gray-600">Evidence Analysis</h4>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style.bg} ${style.text}`}>
          {style.label}
        </span>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-gray-500">
        <span>
          Claims:{" "}
          <span className="font-medium text-gray-700">
            {gap.grounded_claims}/{gap.total_claims} grounded
          </span>
        </span>
        {gap.strong_evidence_claims > 0 && (
          <span>
            Strong:{" "}
            <span className="font-medium text-emerald-600">{gap.strong_evidence_claims}</span>
          </span>
        )}
        {gap.weak_evidence_claims > 0 && (
          <span>
            Weak:{" "}
            <span className="font-medium text-amber-600">{gap.weak_evidence_claims}</span>
          </span>
        )}
        {gap.no_evidence_claims > 0 && (
          <span>
            Unsupported:{" "}
            <span className="font-medium text-red-600">{gap.no_evidence_claims}</span>
          </span>
        )}
        <span>
          Chunks:{" "}
          <span className="font-medium text-gray-700">
            {gap.chunks_cited}/{gap.chunks_provided} cited
          </span>
        </span>
        {gap.chunks_unused > 0 && (
          <span className="text-gray-400">
            {gap.chunks_unused} unused
          </span>
        )}
      </div>
      {gap.summary && (
        <p className="mt-2 text-gray-500">{gap.summary}</p>
      )}
    </div>
  );
}

function ChronologyPanel({
  events,
  coverage,
}: {
  events: ChronologyEvent[];
  coverage: number;
}) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <div className="mb-4 flex items-center gap-3">
        <h3 className="text-lg font-semibold">Timeline</h3>
        <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
          {events.length} event{events.length !== 1 ? "s" : ""}
        </span>
        {coverage > 0 && (
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              coverage >= 0.8
                ? "bg-emerald-100 text-emerald-700"
                : coverage >= 0.5
                  ? "bg-yellow-100 text-yellow-700"
                  : "bg-red-100 text-red-700"
            }`}
          >
            {(coverage * 100).toFixed(0)}% grounded
          </span>
        )}
      </div>

      <div className="relative ml-3 border-l-2 border-indigo-200">
        {events.map((ev, i) => (
          <div key={i} className="relative mb-4 pl-6">
            <span
              className={`absolute -left-[7px] top-1.5 h-3 w-3 rounded-full border-2 border-white ${
                ev.grounded ? "bg-indigo-500" : "bg-red-400"
              }`}
            />
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-semibold text-indigo-700">
                {ev.date_normalised || ev.date_raw || "No date"}
              </span>
              {ev.date_normalised && ev.date_raw !== ev.date_normalised && (
                <span className="text-[10px] text-gray-400">
                  ({ev.date_raw})
                </span>
              )}
              {ev.page_numbers && ev.page_numbers.length > 0 && (
                <span className="text-[10px] text-blue-400">
                  pp. {ev.page_numbers.join(", ")}
                </span>
              )}
              {!ev.grounded && (
                <span className="rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-600">
                  ungrounded
                </span>
              )}
            </div>
            <p className="mt-0.5 text-sm text-gray-700">{ev.description}</p>
            {ev.chunk_ids.length > 0 && (
              <span className="text-[10px] font-mono text-gray-400">
                [{ev.chunk_ids.join(", ")}]
              </span>
            )}
            {ev.evidence_snippets && ev.evidence_snippets.length > 0 && (
              <>
                <button
                  onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                  className="ml-1 text-[10px] text-blue-500 hover:underline"
                >
                  {expandedIdx === i ? "hide evidence" : "show evidence"}
                </button>
                {expandedIdx === i && (
                  <div className="mt-1 space-y-1">
                    {ev.evidence_snippets.map((snippet, j) => (
                      <div
                        key={j}
                        className="rounded border border-indigo-100 bg-indigo-50/50 px-2.5 py-1.5 text-xs text-gray-600"
                      >
                        {snippet}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function EvidencePanel({ evidence }: { evidence: EvidenceReference[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-4 border-t border-gray-100 pt-4">
      <button
        onClick={() => setOpen(!open)}
        className="text-sm font-medium text-blue-600 hover:underline"
      >
        {open ? "Hide evidence" : `Show ${evidence.length} evidence chunks`}
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          {evidence.map((ev, i) => (
            <div
              key={i}
              className="rounded-lg border border-blue-100 bg-blue-50 p-3 text-xs"
            >
              <div className="mb-1 flex flex-wrap items-center gap-2 text-blue-400">
                <span className="font-mono">{ev.chunk_id}</span>
                <span>pages {ev.page_numbers.join(", ")}</span>
                <span>score: {ev.relevance_score.toFixed(2)}</span>
                {ev.section_label && (
                  <span className="rounded bg-blue-100 px-1.5 py-0.5 text-blue-600">
                    {ev.section_label}
                  </span>
                )}
                {ev.parse_quality && ev.parse_quality !== "good" && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-600">
                    {ev.parse_quality}
                  </span>
                )}
              </div>
              <p className="whitespace-pre-wrap text-gray-700">
                {ev.chunk_text}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ── Coverage Panel (Phase 7D) ───────────────────────────────────────────

const COVERAGE_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  comprehensive: { bg: "bg-green-50 border-green-200", text: "text-green-700", label: "Comprehensive" },
  good: { bg: "bg-blue-50 border-blue-200", text: "text-blue-700", label: "Good" },
  partial: { bg: "bg-amber-50 border-amber-200", text: "text-amber-700", label: "Partial" },
  minimal: { bg: "bg-red-50 border-red-200", text: "text-red-700", label: "Minimal" },
  unknown: { bg: "bg-gray-50 border-gray-200", text: "text-gray-700", label: "Unknown" },
};

function CoveragePanel({ report }: { report: CoverageReportData }) {
  const [expanded, setExpanded] = useState(false);
  const style = COVERAGE_STYLES[report.coverage_level] ?? COVERAGE_STYLES.unknown;

  const showWarning = report.coverage_level === "minimal" || report.coverage_level === "partial";

  const pagesCovered = report.pages_covered ?? [];
  const pagesMissing = report.pages_missing ?? [];
  const sectionsCovered = report.sections_covered ?? [];
  const sectionsMissing = report.sections_missing ?? [];

  return (
    <div className={`rounded-xl border p-4 ${style.bg}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <h4 className="font-semibold text-sm">Document Coverage</h4>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${style.text} ${style.bg}`}>
            {style.label}
          </span>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-gray-500 hover:underline"
        >
          {expanded ? "collapse" : "details"}
        </button>
      </div>

      {showWarning && (
        <p className={`text-xs mb-2 ${style.text}`}>
          {report.coverage_level === "minimal"
            ? "This analysis is based on a very small subset of the document. Results may be incomplete."
            : "Some sections or pages are not covered. Findings in uncovered areas may be missing."}
        </p>
      )}

      <div className="flex flex-wrap gap-4 text-xs text-gray-600">
        <span>
          Chunks: <span className="font-medium">{report.selected_chunks ?? 0}/{report.total_chunks ?? 0}</span>
          <span className="ml-1 text-gray-400">({((report.chunk_coverage_ratio ?? 0) * 100).toFixed(0)}%)</span>
        </span>
        <span>
          Pages: <span className="font-medium">{pagesCovered.length}/{report.total_pages ?? 0}</span>
          <span className="ml-1 text-gray-400">({((report.page_coverage_ratio ?? 0) * 100).toFixed(0)}%)</span>
        </span>
        {(report.total_sections ?? 0) > 0 && (
          <span>
            Sections: <span className="font-medium">{sectionsCovered.length}/{report.total_sections}</span>
            <span className="ml-1 text-gray-400">({((report.section_coverage_ratio ?? 0) * 100).toFixed(0)}%)</span>
          </span>
        )}
      </div>

      {expanded && (
        <div className="mt-3 space-y-2 text-xs">
          {sectionsCovered.length > 0 && (
            <div>
              <span className="font-medium text-gray-500">Sections covered: </span>
              <span className="text-gray-700">{sectionsCovered.join(", ")}</span>
            </div>
          )}
          {sectionsMissing.length > 0 && (
            <div>
              <span className="font-medium text-amber-600">Sections missing: </span>
              <span className="text-amber-700">{sectionsMissing.join(", ")}</span>
            </div>
          )}
          {pagesMissing.length > 0 && pagesMissing.length <= 20 && (
            <div>
              <span className="font-medium text-amber-600">Pages missing: </span>
              <span className="text-amber-700">{pagesMissing.join(", ")}</span>
            </div>
          )}
          {pagesMissing.length > 20 && (
            <div>
              <span className="font-medium text-amber-600">{pagesMissing.length} pages not covered</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
