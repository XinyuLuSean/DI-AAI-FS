"use client";

import { useState } from "react";
import type { DocumentResponse } from "@/lib/types";

interface Props {
  document: DocumentResponse;
}

export function DocumentViewer({ document: doc }: Props) {
  const [showChunks, setShowChunks] = useState(false);

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
