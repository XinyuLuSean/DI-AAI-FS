"use client";

import { useState } from "react";
import { compareRetrievalStrategies } from "@/lib/api";
import type { ComparisonReport, StrategyResult } from "@/lib/types";

interface Props {
  documentId: string;
}

const STRATEGY_LABELS: Record<string, string> = {
  head: "Head (first N)",
  head_tail: "Head + Tail",
  sampled: "Sampled",
  routing_aware: "Routing-Aware",
  query_ranked: "Query-Ranked",
};

const STRATEGY_COLORS: Record<string, string> = {
  head: "bg-gray-100 text-gray-700",
  head_tail: "bg-blue-100 text-blue-700",
  sampled: "bg-amber-100 text-amber-700",
  routing_aware: "bg-purple-100 text-purple-700",
  query_ranked: "bg-emerald-100 text-emerald-700",
};

export function RetrievalCompare({ documentId }: Props) {
  const [query, setQuery] = useState("");
  const [maxChunks, setMaxChunks] = useState(5);
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedStrategy, setExpandedStrategy] = useState<string | null>(null);

  const handleCompare = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await compareRetrievalStrategies(documentId, query, maxChunks);
      setReport(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Comparison failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <h3 className="mb-4 text-lg font-semibold">Retrieval Strategy Comparison</h3>
      <p className="mb-4 text-sm text-gray-500">
        Compare how different chunk selection strategies choose context for a given query.
        This shows why retrieval-based selection matters for long documents.
      </p>

      <div className="flex gap-3 mb-4">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleCompare(); }}
          placeholder="Enter a query (e.g., 'patient diagnosis treatment')"
          className="flex-1 rounded-lg border border-gray-200 px-4 py-2 text-sm focus:border-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-300"
        />
        <select
          value={maxChunks}
          onChange={(e) => setMaxChunks(Number(e.target.value))}
          className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
        >
          {[3, 5, 8, 10].map((n) => (
            <option key={n} value={n}>{n} chunks</option>
          ))}
        </select>
        <button
          onClick={handleCompare}
          disabled={loading || !query.trim()}
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-gray-800 disabled:opacity-50"
        >
          {loading ? "Comparing..." : "Compare"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {report && (
        <div className="space-y-4">
          {/* Recommendation */}
          <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-4 text-sm text-blue-800">
            {report.recommendation}
          </div>

          {/* Overview */}
          <div className="flex flex-wrap gap-4 text-xs text-gray-500">
            <span>Total chunks: <span className="font-medium text-gray-700">{report.total_chunks_available}</span></span>
            <span>Budget: <span className="font-medium text-gray-700">{report.max_chunks}</span></span>
            <span>Query: <span className="font-mono text-gray-700">{report.query}</span></span>
          </div>

          {/* Strategy cards */}
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {report.strategies.map((sr: StrategyResult) => {
              const isExpanded = expandedStrategy === sr.strategy;
              const avgScore = sr.chunks.length > 0
                ? sr.chunks.reduce((s, c) => s + c.relevance_score, 0) / sr.chunks.length
                : 0;
              const uniqueIds = report.unique_to[sr.strategy] || [];

              return (
                <div
                  key={sr.strategy}
                  className="rounded-lg border border-gray-200 p-4"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STRATEGY_COLORS[sr.strategy] || "bg-gray-100 text-gray-700"}`}>
                      {STRATEGY_LABELS[sr.strategy] || sr.strategy}
                    </span>
                    <span className="text-xs text-gray-400">
                      avg: {avgScore.toFixed(2)}
                    </span>
                  </div>

                  <div className="flex flex-wrap gap-1 mb-2">
                    {sr.chunks.map((c) => (
                      <span
                        key={c.chunk_id}
                        className={`rounded px-1.5 py-0.5 text-[10px] font-mono ${
                          uniqueIds.includes(c.chunk_id)
                            ? "bg-yellow-100 text-yellow-700 font-semibold"
                            : "bg-gray-100 text-gray-500"
                        }`}
                        title={`idx:${c.index} pg:${c.page_numbers.join(",")} score:${c.relevance_score.toFixed(2)} ${c.section_label}`}
                      >
                        #{c.index}
                      </span>
                    ))}
                  </div>

                  {uniqueIds.length > 0 && (
                    <p className="text-[10px] text-yellow-600 mb-1">
                      {uniqueIds.length} unique chunk{uniqueIds.length !== 1 ? "s" : ""} (highlighted)
                    </p>
                  )}

                  <button
                    onClick={() => setExpandedStrategy(isExpanded ? null : sr.strategy)}
                    className="text-[10px] text-blue-500 hover:underline"
                  >
                    {isExpanded ? "hide details" : "show details"}
                  </button>

                  {isExpanded && (
                    <div className="mt-2 space-y-1.5 max-h-48 overflow-y-auto">
                      {sr.chunks.map((c) => (
                        <div
                          key={c.chunk_id}
                          className="rounded border border-gray-100 bg-gray-50 p-2 text-[10px]"
                        >
                          <div className="flex items-center gap-2 mb-0.5 text-gray-400">
                            <span className="font-mono">#{c.index}</span>
                            <span>score: {c.relevance_score.toFixed(3)}</span>
                            {c.page_numbers.length > 0 && (
                              <span>pp. {c.page_numbers.join(", ")}</span>
                            )}
                            {c.section_label && (
                              <span className="rounded bg-indigo-50 px-1 py-0.5 text-indigo-500">
                                {c.section_label}
                              </span>
                            )}
                          </div>
                          <p className="text-gray-600 line-clamp-2">
                            {c.text_preview}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
