"use client";

import { useState } from "react";
import { UploadPanel } from "@/components/upload-panel";
import { DocumentViewer } from "@/components/document-viewer";
import { ExtractionResult } from "@/components/extraction-result";
import { extractDocument, summariseDocument } from "@/lib/api";
import type { DocumentResponse, ExtractionResponse } from "@/lib/types";

export default function Home() {
  const [document, setDocument] = useState<DocumentResponse | null>(null);
  const [extraction, setExtraction] = useState<ExtractionResponse | null>(null);
  const [summary, setSummary] = useState<ExtractionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleReset = () => {
    setDocument(null);
    setExtraction(null);
    setSummary(null);
    setError(null);
  };

  return (
    <div className="space-y-8">
      {/* Step 1: Upload */}
      {document === null && (
        <section>
          <h2 className="mb-4 text-xl font-semibold">Upload a Document</h2>
          <UploadPanel
            onUploaded={(doc) => {
              setDocument(doc);
              setExtraction(null);
              setSummary(null);
              setError(null);
            }}
            onError={setError}
            disabled={loading}
          />
        </section>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Step 2: Document info + chunks */}
      {document && (
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-xl font-semibold">Parsed Document</h2>
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

      {/* Step 3: Extract Fields (always first) */}
      {document && !extraction && (
        <section>
          <h2 className="mb-4 text-xl font-semibold">
            Extract Fields
          </h2>
          <button
            onClick={async () => {
              setLoading(true);
              setError(null);
              try {
                const data: ExtractionResponse =
                  await extractDocument(document.id);
                setExtraction(data);
              } catch (e: unknown) {
                setError(e instanceof Error ? e.message : "Extraction failed");
              } finally {
                setLoading(false);
              }
            }}
            disabled={loading}
            className="rounded-lg bg-gray-900 px-6 py-3 font-medium text-white transition hover:bg-gray-800 disabled:opacity-50"
          >
            {loading ? "Extracting…" : "Extract Fields (instant)"}
          </button>
          <p className="mt-2 text-xs text-gray-400">
            Regex/heuristic extraction — no LLM, no cost, instant results.
          </p>
        </section>
      )}

      {/* Step 4: Show extraction results + Summarise button */}
      {extraction && (
        <section>
          <h2 className="mb-4 text-xl font-semibold">
            Extracted Fields
            <span className="ml-2 text-sm font-normal text-gray-400">
              deterministic · {extraction.structured_fields.length} fields · {extraction.processing_time_ms}ms
            </span>
          </h2>
          <ExtractionResult result={extraction} />
        </section>
      )}

      {/* Step 5: Summarise with grounding */}
      {extraction && !summary && (
        <section className="rounded-xl border border-blue-100 bg-blue-50/50 p-6">
          <h2 className="mb-2 text-xl font-semibold">
            Summarise with LLM
          </h2>
          <p className="mb-4 text-sm text-gray-600">
            The {extraction.structured_fields.length} extracted field{extraction.structured_fields.length !== 1 ? "s" : ""} above
            will be injected as grounding constraints so the LLM summary stays
            consistent with known facts.
          </p>
          <button
            onClick={async () => {
              setLoading(true);
              setError(null);
              try {
                const data: ExtractionResponse = await summariseDocument(
                  document!.id,
                  extraction.id,
                );
                setSummary(data);
              } catch (e: unknown) {
                setError(
                  e instanceof Error ? e.message : "Summarisation failed",
                );
              } finally {
                setLoading(false);
              }
            }}
            disabled={loading}
            className="rounded-lg bg-blue-600 px-6 py-3 font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Summarising…" : "Summarise (LLM, grounded)"}
          </button>
        </section>
      )}

      {/* Step 6: Show LLM summary results */}
      {summary && (
        <section>
          <h2 className="mb-4 text-xl font-semibold">
            LLM Summary
            <span className="ml-2 text-sm font-normal text-gray-400">
              {summary.model_used} · {summary.processing_time_ms}ms · grounded by extraction
            </span>
          </h2>
          <ExtractionResult result={summary} />
        </section>
      )}
    </div>
  );
}
