"use client";

import { useState } from "react";
import { UploadPanel } from "@/components/upload-panel";
import { DocumentViewer } from "@/components/document-viewer";
import { ExtractionResult } from "@/components/extraction-result";
import { summariseDocument } from "@/lib/api";
import type { DocumentResponse, ExtractionResponse } from "@/lib/types";

export default function Home() {
  const [document, setDocument] = useState<DocumentResponse | null>(null);
  const [extraction, setExtraction] = useState<ExtractionResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleReset = () => {
    setDocument(null);
    setExtraction(null);
    setError(null);
  };

  return (
    <div className="space-y-8">
      {/* Step 1: Upload */}
      <section>
        <h2 className="mb-4 text-xl font-semibold">1. Upload a Document</h2>
        <UploadPanel
          onUploaded={(doc) => {
            setDocument(doc);
            setExtraction(null);
            setError(null);
          }}
          onError={setError}
          disabled={loading}
        />
      </section>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Step 2: Document info + chunks */}
      {document && (
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-xl font-semibold">2. Parsed Document</h2>
            <button
              onClick={handleReset}
              className="text-sm text-gray-500 underline hover:text-gray-700"
            >
              Start over
            </button>
          </div>
          <DocumentViewer document={document} />
        </section>
      )}

      {/* Step 3: Run AI summarisation */}
      {document && !extraction && (
        <section>
          <h2 className="mb-4 text-xl font-semibold">
            3. Run AI Summarisation
          </h2>
          <button
            onClick={async () => {
              setLoading(true);
              setError(null);
              try {
                const data: ExtractionResponse =
                  await summariseDocument(document.id);
                setExtraction(data);
              } catch (e: unknown) {
                setError(e instanceof Error ? e.message : "Summarisation failed");
              } finally {
                setLoading(false);
              }
            }}
            disabled={loading}
            className="rounded-lg bg-blue-600 px-6 py-3 font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Processing…" : "Summarise Document"}
          </button>
        </section>
      )}

      {/* Step 4: Show results with evidence */}
      {extraction && (
        <section>
          <h2 className="mb-4 text-xl font-semibold">
            4. Extraction Results
          </h2>
          <ExtractionResult result={extraction} />
        </section>
      )}
    </div>
  );
}
