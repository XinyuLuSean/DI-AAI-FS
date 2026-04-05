"use client";

import { useState } from "react";
import { submitCorrection, submitReview } from "@/lib/api";
import type {
  EvidenceReference,
  ExtractionResponse,
  ReviewableOutput,
  StructuredField,
} from "@/lib/types";

interface Props {
  reviewable: ReviewableOutput;
  extraction: ExtractionResponse | null;
  onReviewSubmitted: () => void;
}

export function ReviewPanel({ reviewable, extraction, onReviewSubmitted }: Props) {
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showCorrection, setShowCorrection] = useState(false);

  const handleDecision = async (status: "approved" | "rejected") => {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      await submitReview(
        reviewable.document_id,
        reviewable.extraction_id,
        status,
        "ui-reviewer",
        notes,
      );
      setSuccess(`Extraction ${status}`);
      setNotes("");
      onReviewSubmitted();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to submit review");
    } finally {
      setLoading(false);
    }
  };

  const isResolved = ["approved", "rejected", "corrected", "auto_accepted"].includes(
    reviewable.status,
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Review Extraction</h2>
          <p className="mt-0.5 text-xs text-gray-400">
            Doc: {reviewable.document_id.slice(0, 12)} | Ext: {reviewable.extraction_id}
          </p>
        </div>
        <StatusBadge status={reviewable.status} />
      </div>

      {/* Trigger reasons */}
      {reviewable.trigger_reasons.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h3 className="mb-2 text-sm font-medium text-amber-800">
            Review Triggers
          </h3>
          <div className="flex flex-wrap gap-2">
            {reviewable.trigger_reasons.map((t) => (
              <span
                key={t}
                className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-700"
              >
                {t.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Fields with diff capability */}
      {extraction && extraction.structured_fields.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h3 className="mb-4 text-sm font-semibold text-gray-700">
            Extracted Fields
            <span className="ml-2 font-normal text-gray-400">
              {extraction.structured_fields.length} fields
            </span>
          </h3>
          <div className="divide-y divide-gray-100">
            {extraction.structured_fields.map((field, i) => (
              <FieldRow key={i} field={field} />
            ))}
          </div>
        </div>
      )}

      {/* Summary */}
      {extraction?.summary && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <div className="mb-3 flex items-center gap-3">
            <h3 className="text-sm font-semibold text-gray-700">Summary</h3>
            {extraction.summary.grounding_coverage > 0 && (
              <GroundingBadge coverage={extraction.summary.grounding_coverage} />
            )}
          </div>
          <p className="text-sm leading-relaxed text-gray-700">
            {extraction.summary.summary_text}
          </p>

          {extraction.summary.grounded_key_points.length > 0 && (
            <div className="mt-4">
              <h4 className="mb-2 text-xs font-medium text-gray-500">Key Points</h4>
              <ul className="space-y-1.5">
                {extraction.summary.grounded_key_points.map((kp, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span
                      className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                        kp.grounded ? "bg-emerald-500" : "bg-red-400"
                      }`}
                    />
                    <span className={kp.grounded ? "text-gray-700" : "text-red-600"}>
                      {kp.text}
                      {!kp.grounded && (
                        <span className="ml-1.5 rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-600">
                          ungrounded
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {extraction.summary.evidence.length > 0 && (
            <EvidenceViewer evidence={extraction.summary.evidence} />
          )}
        </div>
      )}

      {/* Grounding audit */}
      {extraction?.grounding_audit && extraction.grounding_audit.needs_review && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm">
          <h4 className="mb-1 font-medium text-red-700">Grounding Issues</h4>
          <div className="space-y-1 text-xs text-red-600">
            {extraction.grounding_audit.warnings.map((w, i) => (
              <p key={i}>{w}</p>
            ))}
          </div>
        </div>
      )}

      {/* Decision history */}
      {reviewable.decisions.length > 0 && (
        <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
            Decision History
          </h3>
          <div className="space-y-2">
            {reviewable.decisions.map((d) => (
              <div key={d.id} className="flex items-center gap-3 text-xs text-gray-600">
                <StatusBadge status={d.status} small />
                <span>by {d.reviewer_id || "anonymous"}</span>
                <span className="text-gray-400">
                  {new Date(d.created_at).toLocaleString()}
                </span>
                {d.notes && <span className="italic text-gray-500">"{d.notes}"</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error / success banners */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {success && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {success}
        </div>
      )}

      {/* Actions */}
      {!isResolved && (
        <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-6">
          <h3 className="text-sm font-semibold text-gray-700">Decision</h3>

          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Add review notes (optional)..."
            className="w-full rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-700 placeholder:text-gray-400 focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-200"
            rows={2}
          />

          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => handleDecision("approved")}
              disabled={loading}
              className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
            >
              Approve
            </button>
            <button
              onClick={() => handleDecision("rejected")}
              disabled={loading}
              className="rounded-lg bg-red-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-red-700 disabled:opacity-50"
            >
              Reject
            </button>
            <button
              onClick={() => setShowCorrection(!showCorrection)}
              disabled={loading}
              className="rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50"
            >
              {showCorrection ? "Cancel Correction" : "Correct Fields"}
            </button>
          </div>

          {showCorrection && extraction && (
            <CorrectionForm
              reviewable={reviewable}
              fields={extraction.structured_fields}
              onSubmitted={() => {
                setShowCorrection(false);
                setError(null);
                setSuccess("Corrections submitted");
                onReviewSubmitted();
              }}
              onError={setError}
            />
          )}
        </div>
      )}
    </div>
  );
}

/* ── Sub-components ──────────────────────────────────────────────────── */

function StatusBadge({ status, small }: { status: string; small?: boolean }) {
  const styles: Record<string, string> = {
    pending_review: "bg-amber-100 text-amber-700",
    in_review: "bg-blue-100 text-blue-700",
    approved: "bg-emerald-100 text-emerald-700",
    corrected: "bg-purple-100 text-purple-700",
    rejected: "bg-red-100 text-red-700",
    auto_accepted: "bg-gray-100 text-gray-500",
  };
  const labels: Record<string, string> = {
    pending_review: "Pending Review",
    in_review: "In Review",
    approved: "Approved",
    corrected: "Corrected",
    rejected: "Rejected",
    auto_accepted: "Auto-Accepted",
  };

  return (
    <span
      className={`rounded-full font-semibold ${styles[status] ?? "bg-gray-100 text-gray-600"} ${
        small ? "px-2 py-0.5 text-[10px]" : "px-3 py-1 text-xs"
      }`}
    >
      {labels[status] ?? status}
    </span>
  );
}

function FieldRow({ field }: { field: StructuredField }) {
  const [showEvidence, setShowEvidence] = useState(false);

  return (
    <div className="py-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-medium text-gray-800 shrink-0">
            {field.field_name}
          </span>
          <span className="truncate text-sm text-gray-600 font-mono">
            {field.field_value}
          </span>
          <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-mono text-gray-400">
            {field.extraction_method}
          </span>
        </div>
        <ConfidenceBadge value={field.confidence} />
      </div>

      {field.source_snippet && (
        <p className="mt-1 text-xs text-gray-400 line-clamp-2">
          {field.source_snippet}
        </p>
      )}

      {field.evidence.length > 0 && (
        <div className="mt-1">
          <button
            onClick={() => setShowEvidence(!showEvidence)}
            className="text-[11px] font-medium text-blue-500 hover:underline"
          >
            {showEvidence ? "Hide evidence" : `${field.evidence.length} evidence`}
          </button>
          {showEvidence && (
            <div className="mt-2 space-y-1.5">
              {field.evidence.map((ev, i) => (
                <EvidenceCard key={i} evidence={ev} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ConfidenceBadge({ value }: { value: number }) {
  const color =
    value >= 0.8
      ? "bg-emerald-100 text-emerald-700"
      : value >= 0.5
        ? "bg-yellow-100 text-yellow-700"
        : "bg-red-100 text-red-700";

  return (
    <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}>
      {(value * 100).toFixed(0)}%
    </span>
  );
}

function GroundingBadge({ coverage }: { coverage: number }) {
  const color =
    coverage >= 0.8
      ? "bg-emerald-100 text-emerald-700"
      : coverage >= 0.5
        ? "bg-yellow-100 text-yellow-700"
        : "bg-red-100 text-red-700";

  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {(coverage * 100).toFixed(0)}% grounded
    </span>
  );
}

function EvidenceViewer({ evidence }: { evidence: EvidenceReference[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-4 border-t border-gray-100 pt-3">
      <button
        onClick={() => setOpen(!open)}
        className="text-xs font-medium text-blue-500 hover:underline"
      >
        {open ? "Hide evidence" : `Show ${evidence.length} evidence chunks`}
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          {evidence.map((ev, i) => (
            <EvidenceCard key={i} evidence={ev} />
          ))}
        </div>
      )}
    </div>
  );
}

function EvidenceCard({ evidence: ev }: { evidence: EvidenceReference }) {
  return (
    <div className="rounded-lg border border-blue-100 bg-blue-50/60 p-3 text-xs">
      <div className="mb-1.5 flex flex-wrap items-center gap-2 text-blue-400">
        <span className="font-mono font-medium">{ev.chunk_id}</span>
        <span>pp. {ev.page_numbers.join(", ")}</span>
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
      <p className="whitespace-pre-wrap leading-relaxed text-gray-700">
        {ev.chunk_text}
      </p>
    </div>
  );
}

/* ── Correction form ─────────────────────────────────────────────────── */

function CorrectionForm({
  reviewable,
  fields,
  onSubmitted,
  onError,
}: {
  reviewable: ReviewableOutput;
  fields: StructuredField[];
  onSubmitted: () => void;
  onError: (msg: string) => void;
}) {
  const [corrections, setCorrections] = useState<
    Record<string, { value: string; reason: string }>
  >({});
  const [correctionNotes, setCorrectionNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const updateCorrection = (fieldName: string, key: "value" | "reason", val: string) => {
    setCorrections((prev) => ({
      ...prev,
      [fieldName]: { ...prev[fieldName], [key]: val },
    }));
  };

  const handleSubmit = async () => {
    const fieldCorrections = Object.entries(corrections)
      .filter(([, c]) => c.value.trim() !== "")
      .map(([fieldName, c]) => ({
        field_name: fieldName,
        corrected_value: c.value,
        reason: c.reason || "",
      }));

    if (fieldCorrections.length === 0) {
      onError("Enter at least one corrected value");
      return;
    }

    setSubmitting(true);
    try {
      await submitCorrection(reviewable.document_id, reviewable.extraction_id, {
        reviewer_id: "ui-reviewer",
        field_corrections: fieldCorrections,
        notes: correctionNotes,
      });
      onSubmitted();
    } catch (e: unknown) {
      onError(e instanceof Error ? e.message : "Correction failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mt-4 rounded-lg border border-purple-200 bg-purple-50/50 p-5 space-y-4">
      <h4 className="text-sm font-semibold text-purple-800">Correct Field Values</h4>
      <p className="text-xs text-purple-600">
        Enter corrected values for fields that need fixing. Leave blank to skip.
      </p>

      <div className="space-y-3">
        {fields.map((field) => (
          <div key={field.field_name} className="rounded-lg bg-white p-3 border border-purple-100">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-semibold text-gray-700">
                {field.field_name}
              </span>
              <span className="text-xs text-gray-400">
                current: <span className="font-mono">{field.field_value}</span>
              </span>
              <ConfidenceBadge value={field.confidence} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="text"
                placeholder="Corrected value..."
                value={corrections[field.field_name]?.value ?? ""}
                onChange={(e) => updateCorrection(field.field_name, "value", e.target.value)}
                className="rounded border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-purple-300 focus:outline-none"
              />
              <input
                type="text"
                placeholder="Reason (optional)..."
                value={corrections[field.field_name]?.reason ?? ""}
                onChange={(e) => updateCorrection(field.field_name, "reason", e.target.value)}
                className="rounded border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-purple-300 focus:outline-none"
              />
            </div>
          </div>
        ))}
      </div>

      <textarea
        value={correctionNotes}
        onChange={(e) => setCorrectionNotes(e.target.value)}
        placeholder="Overall correction notes..."
        className="w-full rounded border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 placeholder:text-gray-400 focus:border-purple-300 focus:outline-none"
        rows={2}
      />

      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="rounded-lg bg-purple-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-purple-700 disabled:opacity-50"
      >
        {submitting ? "Submitting..." : "Submit Corrections"}
      </button>
    </div>
  );
}
