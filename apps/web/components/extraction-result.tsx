"use client";

import { useState } from "react";
import type { ExtractionResponse, EvidenceReference } from "@/lib/types";

interface Props {
  result: ExtractionResponse;
}

export function ExtractionResult({ result }: Props) {
  const [expandedEvidence, setExpandedEvidence] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      {/* Run metadata */}
      <div className="flex flex-wrap gap-4 text-xs text-gray-500">
        <span>Model: {result.model_used}</span>
        <span>Time: {result.processing_time_ms}ms</span>
        <span>ID: {result.id}</span>
      </div>

      {/* Summary */}
      {result.summary && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h3 className="mb-3 text-lg font-semibold">Summary</h3>
          <p className="leading-relaxed text-gray-700">
            {result.summary.summary_text}
          </p>

          {result.summary.key_points.length > 0 && (
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
              <div className="mb-1 flex items-center gap-2 text-blue-400">
                <span className="font-mono">{ev.chunk_id}</span>
                <span>pages {ev.page_numbers.join(", ")}</span>
                <span>score: {ev.relevance_score.toFixed(2)}</span>
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
