"use client";

import { useCallback, useEffect, useState } from "react";
import { ReviewQueue } from "@/components/review-queue";
import { ReviewPanel } from "@/components/review-panel";
import { fetchReviewQueue, getExtraction, getReviewStatus } from "@/lib/api";
import type {
  ExtractionResponse,
  ReviewableOutput,
  ReviewQueueResponse,
} from "@/lib/types";

export default function ReviewPage() {
  const [queue, setQueue] = useState<ReviewQueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<ReviewableOutput | null>(null);
  const [extraction, setExtraction] = useState<ExtractionResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadQueue = useCallback(async () => {
    try {
      setLoading(true);
      const data: ReviewQueueResponse = await fetchReviewQueue();
      setQueue(data);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load review queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadQueue();
  }, [loadQueue]);

  const handleSelect = async (item: ReviewableOutput) => {
    setSelected(item);
    setExtraction(null);
    setDetailLoading(true);
    try {
      const [ext, review] = await Promise.all([
        getExtraction(item.document_id, item.extraction_id),
        getReviewStatus(item.document_id, item.extraction_id),
      ]);
      setExtraction(ext);
      setSelected(review);
    } catch (e: unknown) {
      setExtraction(null);
      setError(e instanceof Error ? e.message : "Failed to load extraction details");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleReviewSubmitted = async () => {
    await loadQueue();
    if (selected) {
      try {
        const fresh = await getReviewStatus(
          selected.document_id,
          selected.extraction_id,
        );
        setSelected(fresh);
      } catch {
        /* keep stale */
      }
    }
  };

  return (
    <div className="flex gap-6 min-h-[calc(100vh-8rem)]">
      {/* Left panel — Queue list */}
      <aside className="w-80 shrink-0 overflow-y-auto rounded-xl border border-gray-200 bg-white">
        <div className="sticky top-0 z-10 border-b border-gray-100 bg-white px-4 py-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-800">Review Queue</h2>
            <button
              onClick={loadQueue}
              disabled={loading}
              className="rounded-md border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:bg-gray-100 disabled:opacity-50"
            >
              {loading ? "..." : "Refresh"}
            </button>
          </div>
          {queue && (
            <div className="mt-1.5 flex gap-3 text-[10px] text-gray-400">
              <span>{queue.total} total</span>
              <span>{queue.pending_count} pending</span>
              <span>{queue.auto_accepted_count} auto-accepted</span>
            </div>
          )}
        </div>

        {error && (
          <div className="m-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </div>
        )}

        {queue && (
          <div className="p-2">
            <ReviewQueue
              items={queue.items}
              selectedId={selected?.extraction_id ?? null}
              onSelect={handleSelect}
            />
          </div>
        )}
      </aside>

      {/* Right panel — Detail / review */}
      <main className="flex-1 overflow-y-auto">
        {!selected && !detailLoading && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <div className="mx-auto mb-4 h-16 w-16 rounded-full bg-gray-100 flex items-center justify-center">
                <svg className="h-8 w-8 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z" />
                </svg>
              </div>
              <p className="text-sm text-gray-500">
                Select an item from the queue to start reviewing
              </p>
            </div>
          </div>
        )}

        {detailLoading && (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-gray-400">Loading extraction details...</p>
          </div>
        )}

        {selected && !detailLoading && (
          <ReviewPanel
            reviewable={selected}
            extraction={extraction}
            onReviewSubmitted={handleReviewSubmitted}
          />
        )}
      </main>
    </div>
  );
}
