"use client";

import type { ReviewableOutput, ReviewStatus, ReviewTriggerReason } from "@/lib/types";

interface Props {
  items: ReviewableOutput[];
  selectedId: string | null;
  onSelect: (item: ReviewableOutput) => void;
}

const STATUS_STYLES: Record<ReviewStatus, { bg: string; text: string; label: string }> = {
  pending_review: { bg: "bg-amber-100", text: "text-amber-700", label: "Pending" },
  in_review: { bg: "bg-blue-100", text: "text-blue-700", label: "In Review" },
  approved: { bg: "bg-emerald-100", text: "text-emerald-700", label: "Approved" },
  corrected: { bg: "bg-purple-100", text: "text-purple-700", label: "Corrected" },
  rejected: { bg: "bg-red-100", text: "text-red-700", label: "Rejected" },
  auto_accepted: { bg: "bg-gray-100", text: "text-gray-500", label: "Auto" },
};

const TRIGGER_LABELS: Record<ReviewTriggerReason, string> = {
  low_confidence_field: "Low confidence",
  no_fields_extracted: "No fields",
  weak_grounding: "Weak grounding",
  ungrounded_key_points: "Ungrounded claims",
  hallucinated_chunk_ids: "Hallucinated IDs",
  partial_coverage: "Partial coverage",
  degraded_parse_quality: "Degraded parse",
  low_routing_confidence: "Low routing",
  safe_failure: "Safe failure",
  deterministic_contradiction: "Contradiction",
  manual_request: "Manual",
};

function priorityColor(score: number) {
  if (score >= 0.8) return "bg-red-500";
  if (score >= 0.6) return "bg-amber-500";
  if (score >= 0.3) return "bg-yellow-400";
  return "bg-gray-300";
}

export function ReviewQueue({ items, selectedId, onSelect }: Props) {
  const pending = items.filter((i) => i.status === "pending_review");
  const rest = items.filter((i) => i.status !== "pending_review");

  return (
    <div className="space-y-1">
      {pending.length > 0 && (
        <div className="mb-3 px-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Needs Review ({pending.length})
          </h3>
        </div>
      )}
      {pending.map((item) => (
        <QueueItem
          key={item.id}
          item={item}
          isSelected={item.extraction_id === selectedId}
          onSelect={onSelect}
        />
      ))}

      {rest.length > 0 && (
        <div className="mb-3 mt-4 px-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Resolved ({rest.length})
          </h3>
        </div>
      )}
      {rest.map((item) => (
        <QueueItem
          key={item.id}
          item={item}
          isSelected={item.extraction_id === selectedId}
          onSelect={onSelect}
        />
      ))}

      {items.length === 0 && (
        <div className="px-3 py-8 text-center text-sm text-gray-400">
          No items in the review queue.
          <br />
          Upload a document and run extraction first.
        </div>
      )}
    </div>
  );
}

function QueueItem({
  item,
  isSelected,
  onSelect,
}: {
  item: ReviewableOutput;
  isSelected: boolean;
  onSelect: (item: ReviewableOutput) => void;
}) {
  const status = STATUS_STYLES[item.status] ?? { bg: "bg-gray-100", text: "text-gray-600", label: item.status };

  return (
    <button
      onClick={() => onSelect(item)}
      className={`w-full rounded-lg px-3 py-3 text-left transition ${
        isSelected
          ? "bg-blue-50 ring-1 ring-blue-200"
          : "hover:bg-gray-50"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`h-2.5 w-2.5 shrink-0 rounded-full ${priorityColor(item.priority_score)}`}
            title={`Priority: ${(item.priority_score * 100).toFixed(0)}%`}
          />
          <span className="truncate text-sm font-medium text-gray-900">
            {item.document_id.slice(0, 10)}...
          </span>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${status.bg} ${status.text}`}>
          {status.label}
        </span>
      </div>

      {/* Trigger tags */}
      {item.trigger_reasons.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {item.trigger_reasons.map((t) => (
            <span
              key={t}
              className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500"
            >
              {TRIGGER_LABELS[t] ?? t}
            </span>
          ))}
        </div>
      )}

      <div className="mt-1 flex items-center gap-3 text-[10px] text-gray-400">
        <span>ext: {item.extraction_id.slice(0, 8)}</span>
        <span>priority: {(item.priority_score * 100).toFixed(0)}%</span>
      </div>
    </button>
  );
}
