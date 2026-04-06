"use client";

import { useCallback, useEffect, useState } from "react";
import { UploadPanel } from "@/components/upload-panel";
import { DocumentViewer } from "@/components/document-viewer";
import { ExtractionResult } from "@/components/extraction-result";
import { RetrievalCompare } from "@/components/retrieval-compare";
import {
  extractChronology,
  extractDocument,
  fetchDocument,
  fetchDocumentExtractions,
  fetchDocuments,
  getExtraction,
  summariseDocument,
} from "@/lib/api";
import type {
  DocumentListItem,
  DocumentResponse,
  ExtractionListItem,
  ExtractionResponse,
} from "@/lib/types";

const REVIEW_STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  pending_review: { bg: "bg-amber-100", text: "text-amber-700", label: "Pending Review" },
  in_review: { bg: "bg-blue-100", text: "text-blue-700", label: "In Review" },
  approved: { bg: "bg-emerald-100", text: "text-emerald-700", label: "Approved" },
  corrected: { bg: "bg-purple-100", text: "text-purple-700", label: "Corrected" },
  rejected: { bg: "bg-red-100", text: "text-red-700", label: "Rejected" },
  auto_accepted: { bg: "bg-gray-100", text: "text-gray-500", label: "Auto-Accepted" },
};

export default function Home() {
  // Document list (persists across navigation via API reload)
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);

  // Selected document detail
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [document, setDocument] = useState<DocumentResponse | null>(null);
  const [extractions, setExtractions] = useState<ExtractionListItem[]>([]);

  // Active extraction view
  const [activeExtraction, setActiveExtraction] = useState<ExtractionResponse | null>(null);
  const [activeSummary, setActiveSummary] = useState<ExtractionResponse | null>(null);
  const [activeChronology, setActiveChronology] = useState<ExtractionResponse | null>(null);

  const [extracting, setExtracting] = useState(false);
  const [summarising, setSummarising] = useState(false);
  const [chronologising, setChronologising] = useState(false);
  const loading = extracting || summarising || chronologising;
  const [error, setError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);

  const loadDocuments = useCallback(async () => {
    try {
      setDocsLoading(true);
      const docs: DocumentListItem[] = await fetchDocuments();
      setDocuments(docs);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load documents");
    } finally {
      setDocsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const selectDocument = async (docId: string) => {
    setSelectedDocId(docId);
    setActiveExtraction(null);
    setActiveSummary(null);
    setActiveChronology(null);
    setError(null);
    try {
      const [doc, exts] = await Promise.all([
        fetchDocument(docId),
        fetchDocumentExtractions(docId),
      ]);
      setDocument(doc);
      setExtractions(exts);

      if (exts.length > 0) {
        const det = exts.find((e: ExtractionListItem) => e.output_type === "deterministic");
        const sum = exts.find((e: ExtractionListItem) => e.output_type === "ai_summary");
        const chr = exts.find((e: ExtractionListItem) => e.output_type === "ai_chronology");
        if (det) {
          const full = await getExtraction(docId, det.id);
          setActiveExtraction(full);
        }
        if (sum) {
          const full = await getExtraction(docId, sum.id);
          setActiveSummary(full);
        }
        if (chr) {
          const full = await getExtraction(docId, chr.id);
          setActiveChronology(full);
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load document");
    }
  };

  const refreshExtractions = async () => {
    if (!selectedDocId) return;
    try {
      const exts: ExtractionListItem[] = await fetchDocumentExtractions(selectedDocId);
      setExtractions(exts);
    } catch {
      /* non-critical refresh — extraction results still visible */
    }
  };

  const handleUploaded = async (doc: DocumentResponse) => {
    setShowUpload(false);
    await loadDocuments();
    await selectDocument(doc.id);
  };

  return (
    <div className="flex gap-6 min-h-[calc(100vh-8rem)]">
      {/* Left sidebar — document list */}
      <aside className="w-72 shrink-0 overflow-y-auto rounded-xl border border-gray-200 bg-white">
        <div className="sticky top-0 z-10 border-b border-gray-100 bg-white px-4 py-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-800">Documents</h2>
            <button
              onClick={() => { setShowUpload(true); setSelectedDocId(null); setDocument(null); }}
              className="rounded-md bg-gray-900 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-gray-800"
            >
              + Upload
            </button>
          </div>
          <p className="mt-1 text-[10px] text-gray-400">
            {docsLoading ? "Loading..." : `${documents.length} document${documents.length !== 1 ? "s" : ""}`}
          </p>
        </div>

        <div className="p-2 space-y-1">
          {documents.map((d) => (
            <button
              key={d.id}
              onClick={() => { setShowUpload(false); selectDocument(d.id); }}
              className={`w-full rounded-lg px-3 py-2.5 text-left transition ${
                selectedDocId === d.id
                  ? "bg-blue-50 ring-1 ring-blue-200"
                  : "hover:bg-gray-50"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-gray-900">
                  {d.filename}
                </span>
                {d.extraction_count > 0 && (
                  <span className="shrink-0 rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-600">
                    {d.extraction_count} ext
                  </span>
                )}
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[10px] text-gray-400">
                <span>{d.page_count} pg</span>
                <span>{d.chunk_count} chunks</span>
                {d.doc_type && d.doc_type !== "unknown" && (
                  <span className="rounded bg-indigo-50 px-1 py-0.5 text-indigo-500">
                    {d.doc_type}
                  </span>
                )}
              </div>
            </button>
          ))}

          {!docsLoading && documents.length === 0 && !showUpload && (
            <div className="px-3 py-6 text-center text-xs text-gray-400">
              No documents yet.
              <br />
            </div>
          )}
        </div>
      </aside>

      {/* Right main area */}
      <main className="flex-1 overflow-y-auto space-y-6">
        {/* Upload panel */}
        {(showUpload || (!selectedDocId && documents.length === 0)) && (
          <section>
            <h2 className="mb-4 text-xl font-semibold">Upload a Document</h2>
            <UploadPanel
              onUploaded={handleUploaded}
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

        {/* Document detail */}
        {document && !showUpload && (
          <>
            <section>
              <h2 className="mb-4 text-xl font-semibold">
                Parsed Document
                <span className="ml-2 text-sm font-normal text-gray-400">
                  {document.filename}
                </span>
              </h2>
              <DocumentViewer document={document} />
            </section>

            {/* Extraction status cards */}
            {extractions.length > 0 && (
              <section>
                <h3 className="mb-3 text-sm font-semibold text-gray-600">
                  Extractions & Review Status
                </h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  {extractions.map((ext) => {
                    const rs = ext.review_status ? REVIEW_STATUS_STYLES[ext.review_status] : null;
                    return (
                      <div
                        key={ext.id}
                        className="rounded-lg border border-gray-200 bg-white p-4"
                      >
                        <div className="flex items-center justify-between">
                          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            ext.output_type === "deterministic"
                              ? "bg-gray-100 text-gray-700"
                              : ext.output_type === "ai_chronology"
                                ? "bg-indigo-100 text-indigo-700"
                                : "bg-purple-100 text-purple-700"
                          }`}>
                            {ext.output_type === "deterministic"
                              ? "Extraction"
                              : ext.output_type === "ai_chronology"
                                ? "AI Chronology"
                                : "AI Summary"}
                          </span>
                          {rs && (
                            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${rs.bg} ${rs.text}`}>
                              {rs.label}
                            </span>
                          )}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-500">
                          <span>{ext.field_count} fields</span>
                          <span>{ext.processing_time_ms}ms</span>
                          <span className="font-mono text-gray-400">{ext.model_used}</span>
                        </div>
                        {ext.review_triggers.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {ext.review_triggers.map((t) => (
                              <span key={t} className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-600">
                                {t.replace(/_/g, " ")}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {/* Extract button */}
            {!activeExtraction && (
              <section>
                <button
                  onClick={async () => {
                    setExtracting(true);
                    setError(null);
                    try {
                      const data: ExtractionResponse = await extractDocument(document.id);
                      setActiveExtraction(data);
                      await loadDocuments();
                      await refreshExtractions();
                    } catch (e: unknown) {
                      setError(e instanceof Error ? e.message : "Extraction failed");
                    } finally {
                      setExtracting(false);
                    }
                  }}
                  disabled={extracting}
                  className="rounded-lg bg-gray-900 px-6 py-3 font-medium text-white transition hover:bg-gray-800 disabled:opacity-50"
                >
                  {extracting ? "Extracting..." : "Extract Fields (instant)"}
                </button>
                <p className="mt-2 text-xs text-gray-400">
                  Regex/heuristic extraction — no LLM, no cost, instant results.
                </p>
              </section>
            )}

            {/* Extraction results */}
            {activeExtraction && (
              <section>
                <h2 className="mb-4 text-xl font-semibold">
                  Extracted Fields
                  <span className="ml-2 text-sm font-normal text-gray-400">
                    deterministic · {activeExtraction.structured_fields.length} fields · {activeExtraction.processing_time_ms}ms
                  </span>
                </h2>
                <ExtractionResult result={activeExtraction} />
              </section>
            )}

            {/* Summarise button */}
            {activeExtraction && !activeSummary && (
              <section className="rounded-xl border border-blue-100 bg-blue-50/50 p-6">
                <h2 className="mb-2 text-xl font-semibold">Summarise with LLM</h2>
                <p className="mb-4 text-sm text-gray-600">
                  The {activeExtraction.structured_fields.length} extracted field{activeExtraction.structured_fields.length !== 1 ? "s" : ""} above
                  will be injected as grounding constraints so the LLM summary stays
                  consistent with known facts.
                </p>
                <button
                  onClick={async () => {
                    setSummarising(true);
                    setError(null);
                    try {
                      const data: ExtractionResponse = await summariseDocument(
                        document.id,
                        activeExtraction.id,
                      );
                      setActiveSummary(data);
                      await loadDocuments();
                      await refreshExtractions();
                    } catch (e: unknown) {
                      setError(e instanceof Error ? e.message : "Summarisation failed");
                    } finally {
                      setSummarising(false);
                    }
                  }}
                  disabled={summarising}
                  className="rounded-lg bg-blue-600 px-6 py-3 font-medium text-white transition hover:bg-blue-700 disabled:opacity-50"
                >
                  {summarising ? "Summarising..." : "Summarise (LLM, grounded)"}
                </button>
              </section>
            )}

            {/* LLM summary results */}
            {activeSummary && (
              <section>
                <h2 className="mb-4 text-xl font-semibold">
                  LLM Summary
                  <span className="ml-2 text-sm font-normal text-gray-400">
                    {activeSummary.model_used} · {activeSummary.processing_time_ms}ms · grounded by extraction
                  </span>
                </h2>
                <ExtractionResult result={activeSummary} />
              </section>
            )}

            {/* Chronology button — available once we have chunks */}
            {activeExtraction && !activeChronology && (
              <section className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-6">
                <h2 className="mb-2 text-xl font-semibold">Extract Timeline</h2>
                <p className="mb-4 text-sm text-gray-600">
                  Extract a chronological timeline of dated events from the document.
                  This is a separate AI task with its own prompt, schema, and evaluation criteria.
                </p>
                <button
                  onClick={async () => {
                    setChronologising(true);
                    setError(null);
                    try {
                      const data: ExtractionResponse = await extractChronology(document.id);
                      setActiveChronology(data);
                      await loadDocuments();
                      await refreshExtractions();
                    } catch (e: unknown) {
                      setError(e instanceof Error ? e.message : "Chronology extraction failed");
                    } finally {
                      setChronologising(false);
                    }
                  }}
                  disabled={chronologising}
                  className="rounded-lg bg-indigo-600 px-6 py-3 font-medium text-white transition hover:bg-indigo-700 disabled:opacity-50"
                >
                  {chronologising ? "Extracting timeline..." : "Extract Timeline (LLM)"}
                </button>
              </section>
            )}

            {/* Chronology results */}
            {activeChronology && (
              <section>
                <h2 className="mb-4 text-xl font-semibold">
                  Document Timeline
                  <span className="ml-2 text-sm font-normal text-gray-400">
                    {activeChronology.model_used} · {activeChronology.processing_time_ms}ms
                  </span>
                </h2>
                <ExtractionResult result={activeChronology} />
              </section>
            )}

            {/* Retrieval strategy comparison (Phase 5) */}
            <section>
              <RetrievalCompare documentId={document.id} />
            </section>
          </>
        )}

        {/* Empty state when nothing selected */}
        {!showUpload && !selectedDocId && documents.length > 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <p className="text-sm text-gray-500">Select a document from the sidebar</p>
              <p className="mt-1 text-xs text-gray-400">
                or upload a new one with the + Upload button
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
