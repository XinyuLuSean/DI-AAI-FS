"use client";

import { useState } from "react";
import type {
  ExtractionResponse,
  EvidenceReference,
  GroundedKeyPoint,
  GroundingAudit,
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
              : "bg-purple-100 text-purple-700"
          }`}
        >
          {result.output_type === "deterministic" ? "Deterministic" : "AI Summary"}
        </span>
        <span>Model: {result.model_used}</span>
        {result.prompt_name && (
          <span>Prompt: {result.prompt_name}@{result.prompt_version}</span>
        )}
        <span>Time: {result.processing_time_ms}ms</span>
        <span>ID: {result.id}</span>
      </div>

      {/* Grounding audit banner (Phase 8C) */}
      {result.grounding_audit && (
        <GroundingAuditPanel audit={result.grounding_audit} />
      )}

      {/* Summarisation meta (Phase 8D) */}
      {result.summarisation_meta && (
        <SummarisationMetaPanel meta={result.summarisation_meta} />
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

function GroundedKeyPointsList({ points }: { points: GroundedKeyPoint[] }) {
  return (
    <div className="mt-4">
      <h4 className="mb-2 text-sm font-medium text-gray-500">
        Key Points
      </h4>
      <ul className="space-y-2 text-sm">
        {points.map((gkp, i) => (
          <li key={i} className="flex items-start gap-2">
            <span
              className={`mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full ${
                gkp.grounded ? "bg-emerald-500" : "bg-red-400"
              }`}
            />
            <div>
              <span className="text-gray-700">{gkp.text}</span>
              {gkp.chunk_ids.length > 0 && (
                <span className="ml-2 text-[10px] font-mono text-gray-400">
                  [{gkp.chunk_ids.join(", ")}]
                </span>
              )}
              {!gkp.grounded && (
                <span className="ml-2 rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-600">
                  ungrounded
                </span>
              )}
            </div>
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
