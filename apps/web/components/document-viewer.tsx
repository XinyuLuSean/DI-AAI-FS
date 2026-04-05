"use client";

import { useState } from "react";
import type { DocumentResponse } from "@/lib/types";

interface Props {
  document: DocumentResponse;
}

const CONFIDENCE_COLORS: Record<string, string> = {
  high: "bg-emerald-100 text-emerald-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-red-100 text-red-700",
};

function confidenceBand(c: number) {
  if (c >= 0.7) return "high";
  if (c >= 0.4) return "medium";
  return "low";
}

export function DocumentViewer({ document: doc }: Props) {
  const [showChunks, setShowChunks] = useState(false);
  const [showRules, setShowRules] = useState(false);
  const parseMeta = doc.parse_meta;
  const routing = doc.routing;
  const chunkMeta = doc.chunk_meta;

  return (
    <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-6">
      {/* Metadata */}
      <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
        <div>
          <span className="text-gray-500">Filename</span>
          <p className="font-medium">{doc.filename}</p>
        </div>
        <div>
          <span className="text-gray-500">Status</span>
          <p className="font-medium capitalize">{doc.status}</p>
        </div>
        <div>
          <span className="text-gray-500">Pages</span>
          <p className="font-medium">{doc.pages.length}</p>
        </div>
        <div>
          <span className="text-gray-500">Chunks</span>
          <p className="font-medium">{doc.chunks.length}</p>
        </div>
      </div>

      {doc.source && (
        <div className="text-xs text-gray-400">
          Size: {(doc.source.size_bytes / 1024).toFixed(1)} KB | Type:{" "}
          {doc.source.content_type} | ID: {doc.id.slice(0, 12)}…
        </div>
      )}

      {/* Parse metadata */}
      {parseMeta && (
        <div className="rounded-lg border border-gray-100 bg-gray-50 p-4 text-xs">
          <h4 className="mb-2 text-sm font-medium text-gray-600">
            Parse Info
          </h4>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-gray-500">
            <span>Strategy: <span className="font-mono text-gray-700">{parseMeta.parse_strategy}</span></span>
            <span>Suffix: <span className="font-mono text-gray-700">{parseMeta.file_suffix}</span></span>
            <span>Chars: <span className="font-medium text-gray-700">{parseMeta.total_chars.toLocaleString()}</span></span>
            <span>Density: <span className="font-medium text-gray-700">{parseMeta.text_density.toFixed(1)} chars/page</span></span>
            <span>
              Quality:{" "}
              <span className={`rounded-full px-2 py-0.5 font-medium ${
                parseMeta.quality === "good"
                  ? "bg-emerald-100 text-emerald-700"
                  : parseMeta.quality === "degraded"
                    ? "bg-yellow-100 text-yellow-700"
                    : "bg-red-100 text-red-700"
              }`}>
                {parseMeta.quality}
              </span>
            </span>
            {parseMeta.empty_page_count > 0 && (
              <span className="text-amber-600">
                Empty pages: {parseMeta.empty_page_count}/{parseMeta.page_count}
              </span>
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {parseMeta.native_text_extracted && (
              <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-600">native text</span>
            )}
            {parseMeta.likely_scanned && (
              <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-600">likely scanned</span>
            )}
            {parseMeta.likely_needs_ocr && (
              <span className="rounded bg-red-50 px-1.5 py-0.5 text-red-600">needs OCR</span>
            )}
            {parseMeta.ocr_applied && (
              <span className="rounded bg-blue-50 px-1.5 py-0.5 text-blue-600">OCR applied</span>
            )}
          </div>
          {parseMeta.downstream_limitations.length > 0 && (
            <div className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 space-y-1">
              <p className="font-medium text-amber-700">Downstream limitations:</p>
              {parseMeta.downstream_limitations.map((lim, i) => (
                <p key={i} className="text-amber-600">• {lim}</p>
              ))}
            </div>
          )}
          {parseMeta.warnings.length > 0 && (
            <div className="mt-2 space-y-1">
              {parseMeta.warnings.map((w, i) => (
                <p key={i} className="text-amber-600">⚠ {w}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Routing result */}
      {routing && (
        <div className="rounded-lg border border-gray-100 bg-gray-50 p-4 text-xs">
          <h4 className="mb-2 text-sm font-medium text-gray-600">
            Document Routing
          </h4>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-gray-500">
            <span>
              Type:{" "}
              <span className="rounded-full bg-indigo-100 px-2 py-0.5 font-medium text-indigo-700">
                {routing.predicted_type}
              </span>
            </span>
            <span>
              Confidence:{" "}
              <span className={`rounded-full px-2 py-0.5 font-medium ${CONFIDENCE_COLORS[confidenceBand(routing.confidence)]}`}>
                {(routing.confidence * 100).toFixed(0)}%
              </span>
            </span>
            {routing.is_fallback && (
              <span className="text-amber-600">Fallback (no rules matched)</span>
            )}
            <span>Rules: {routing.matched_rules.length}</span>
          </div>
          {routing.matched_rules.length > 0 && (
            <div className="mt-2">
              <button
                onClick={() => setShowRules(!showRules)}
                className="text-xs font-medium text-blue-600 hover:underline"
              >
                {showRules ? "Hide rules" : "Show matched rules"}
              </button>
              {showRules && (
                <div className="mt-2 space-y-1">
                  {routing.matched_rules.map((r, i) => (
                    <div key={i} className="flex items-center gap-2 text-gray-500">
                      <span className="rounded bg-gray-200 px-1.5 py-0.5 font-mono text-gray-600">
                        {r.source}
                      </span>
                      <span className="truncate">{r.pattern}</span>
                      <span className="text-gray-400">→ {r.matched_type}</span>
                      <span className="text-gray-400">w={r.weight.toFixed(1)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {routing.warnings.length > 0 && (
            <div className="mt-2 space-y-1">
              {routing.warnings.map((w, i) => (
                <p key={i} className="text-amber-600">⚠ {w}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Chunk metadata */}
      {chunkMeta && (
        <div className="rounded-lg border border-gray-100 bg-gray-50 p-4 text-xs">
          <h4 className="mb-2 text-sm font-medium text-gray-600">
            Chunk Info
          </h4>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-gray-500">
            <span>Strategy: <span className="font-mono text-gray-700">{chunkMeta.strategy}</span></span>
            <span>Size/Overlap: <span className="font-medium text-gray-700">{chunkMeta.chunk_size}/{chunkMeta.overlap}</span></span>
            <span>Count: <span className="font-medium text-gray-700">{chunkMeta.chunk_count}</span></span>
            <span>Avg chars: <span className="font-medium text-gray-700">{chunkMeta.avg_chunk_chars.toFixed(0)}</span></span>
            <span>Pages covered: <span className="font-medium text-gray-700">{chunkMeta.page_coverage.length}/{doc.pages.length}</span></span>
            {chunkMeta.is_truncated && (
              <span className="font-medium text-amber-600">
                Truncated at {chunkMeta.max_chunks_limit} chunks
              </span>
            )}
          </div>
          {chunkMeta.warnings.length > 0 && (
            <div className="mt-2 space-y-1">
              {chunkMeta.warnings.map((w, i) => (
                <p key={i} className="text-amber-600">⚠ {w}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Chunk explorer */}
      <div>
        <button
          onClick={() => setShowChunks(!showChunks)}
          className="text-sm font-medium text-blue-600 hover:underline"
        >
          {showChunks
            ? "Hide chunks"
            : `Show ${doc.chunks.length} chunks`}
        </button>

        {showChunks && (
          <div className="mt-3 max-h-96 space-y-2 overflow-y-auto">
            {doc.chunks.map((chunk) => (
              <div
                key={chunk.chunk_id}
                className="rounded-lg border border-gray-100 bg-gray-50 p-3 text-xs"
              >
                <div className="mb-1 flex items-center gap-2 text-gray-400">
                  <span className="font-mono">#{chunk.index}</span>
                  <span>
                    pages {chunk.page_numbers.join(", ")}
                  </span>
                  <span>~{chunk.token_estimate} tokens</span>
                  <span className="font-mono text-gray-300">
                    {chunk.chunk_id}
                  </span>
                </div>
                <p className="whitespace-pre-wrap text-gray-700">
                  {chunk.text.slice(0, 300)}
                  {chunk.text.length > 300 ? "…" : ""}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
