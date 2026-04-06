"use client";

import { useCallback, useEffect, useState } from "react";
import { UploadPanel } from "@/components/upload-panel";
import { DocumentViewer } from "@/components/document-viewer";
import { ExtractionResult } from "@/components/extraction-result";
import { RetrievalCompare } from "@/components/retrieval-compare";
import {
  classifyDocument,
  extractChronology,
  extractDocument,
  fetchDocument,
  fetchDocumentExtractions,
  fetchDocuments,
  getExtraction,
  hierarchicalSummarise,
  semanticMatchDocument,
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

type ExtractionDisplayInput = {
  output_type: string;
  prompt_name?: string | null;
};

function getSummaryVariant(promptName?: string | null): "hierarchical" | "grounded" | "standard" {
  if (promptName === "hierarchical_v1") return "hierarchical";
  if (promptName === "grounded_summarise") return "grounded";
  return "standard";
}

function getExtractionDisplayMeta(extraction: ExtractionDisplayInput): {
  badge: string;
  label: string;
  subtitle: string;
} {
  if (extraction.output_type === "ai_summary") {
    const variant = getSummaryVariant(extraction.prompt_name);
    if (variant === "hierarchical") {
      return {
        badge: "bg-teal-100 text-teal-700",
        label: "Hierarchical Summary",
        subtitle: "map-reduce over all chunks",
      };
    }
    if (variant === "grounded") {
      return {
        badge: "bg-blue-100 text-blue-700",
        label: "Grounded Summary",
        subtitle: "grounded by deterministic extraction",
      };
    }
    return {
      badge: "bg-purple-100 text-purple-700",
      label: "AI Summary",
      subtitle: "ungrounded summarisation",
    };
  }

  if (extraction.output_type === "deterministic") {
    return {
      badge: "bg-gray-100 text-gray-700",
      label: "Extraction",
      subtitle: "regex and heuristics",
    };
  }
  if (extraction.output_type === "ai_chronology") {
    return {
      badge: "bg-indigo-100 text-indigo-700",
      label: "AI Chronology",
      subtitle: "timeline extraction",
    };
  }
  if (extraction.output_type === "ai_classification") {
    return {
      badge: "bg-emerald-100 text-emerald-700",
      label: "Readiness Classifier",
      subtitle: "explainable AI decision",
    };
  }
  return {
    badge: "bg-amber-100 text-amber-700",
    label: "Semantic Match",
    subtitle: "fact-to-evidence alignment",
  };
}

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
  const [activeClassification, setActiveClassification] = useState<ExtractionResponse | null>(null);
  const [activeSemanticMatch, setActiveSemanticMatch] = useState<ExtractionResponse | null>(null);

  const [extracting, setExtracting] = useState(false);
  const [summarising, setSummarising] = useState(false);
  const [chronologising, setChronologising] = useState(false);
  const [classifying, setClassifying] = useState(false);
  const [matching, setMatching] = useState(false);
  const [hierarchicalising, setHierarchicalising] = useState(false);
  const loading = extracting || summarising || chronologising || classifying || matching || hierarchicalising;
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

  const applyExtractionResult = useCallback((result: ExtractionResponse) => {
    if (result.output_type === "deterministic") {
      setActiveExtraction(result);
      return;
    }
    if (result.output_type === "ai_summary") {
      setActiveSummary(result);
      return;
    }
    if (result.output_type === "ai_chronology") {
      setActiveChronology(result);
      return;
    }
    if (result.output_type === "ai_classification") {
      setActiveClassification(result);
      return;
    }
    if (result.output_type === "semantic_match") {
      setActiveSemanticMatch(result);
    }
  }, []);

  const loadExtractionDetail = useCallback(
    async (docId: string, extraction: ExtractionListItem) => {
      try {
        setError(null);
        const full = await getExtraction(docId, extraction.id);
        applyExtractionResult(full);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to load extraction");
      }
    },
    [applyExtractionResult],
  );

  const selectDocument = async (docId: string) => {
    setSelectedDocId(docId);
    setActiveExtraction(null);
    setActiveSummary(null);
    setActiveChronology(null);
    setActiveClassification(null);
    setActiveSemanticMatch(null);
    setError(null);
    try {
      const [doc, exts] = await Promise.all([
        fetchDocument(docId),
        fetchDocumentExtractions(docId),
      ]);
      setDocument(doc);
      setExtractions(exts);

      if (exts.length > 0) {
        const targets = [
          exts.find((e: ExtractionListItem) => e.output_type === "deterministic"),
          exts.find((e: ExtractionListItem) => e.output_type === "ai_summary"),
          exts.find((e: ExtractionListItem) => e.output_type === "ai_chronology"),
          exts.find((e: ExtractionListItem) => e.output_type === "ai_classification"),
          exts.find((e: ExtractionListItem) => e.output_type === "semantic_match"),
        ].filter((value): value is ExtractionListItem => value !== undefined);

        const fullResults = await Promise.all(
          targets.map((target) => getExtraction(docId, target.id)),
        );
        fullResults.forEach(applyExtractionResult);
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

  const activeResultIds = new Set(
    [
      activeExtraction?.id,
      activeSummary?.id,
      activeChronology?.id,
      activeClassification?.id,
      activeSemanticMatch?.id,
    ].filter((id): id is string => Boolean(id)),
  );
  const hasGroundedSummary = extractions.some(
    (extraction) =>
      extraction.output_type === "ai_summary"
      && getSummaryVariant(extraction.prompt_name) !== "hierarchical",
  );
  const hasHierarchicalSummary = extractions.some(
    (extraction) =>
      extraction.output_type === "ai_summary"
      && getSummaryVariant(extraction.prompt_name) === "hierarchical",
  );
  const activeSummaryMeta = activeSummary ? getExtractionDisplayMeta(activeSummary) : null;

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
                    const display = getExtractionDisplayMeta(ext);
                    const rs = ext.review_status ? REVIEW_STATUS_STYLES[ext.review_status] : null;
                    return (
                      <button
                        key={ext.id}
                        type="button"
                        onClick={() => {
                          if (document) {
                            void loadExtractionDetail(document.id, ext);
                          }
                        }}
                        className={`rounded-lg border bg-white p-4 text-left transition ${
                          activeResultIds.has(ext.id)
                            ? "border-blue-300 ring-2 ring-blue-100"
                            : "border-gray-200 hover:border-gray-300 hover:bg-gray-50/50"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${display.badge}`}>
                            {display.label}
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
                        <p className="mt-2 text-xs text-gray-400">
                          {display.subtitle}
                          {ext.prompt_name && ` · ${ext.prompt_name}@${ext.prompt_version}`}
                        </p>
                        {ext.review_triggers.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {ext.review_triggers.map((t) => (
                              <span key={t} className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-600">
                                {t.replace(/_/g, " ")}
                              </span>
                            ))}
                          </div>
                        )}
                      </button>
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

            {activeExtraction && !activeClassification && (
              <section className="rounded-xl border border-emerald-100 bg-emerald-50/50 p-6">
                <h2 className="mb-2 text-xl font-semibold">Classify Readiness</h2>
                <p className="mb-4 text-sm text-gray-600">
                  Combine parse quality, routing confidence, chunk coverage, and extracted fields
                  into an explainable readiness label for downstream AI review decisions.
                </p>
                <button
                  onClick={async () => {
                    setClassifying(true);
                    setError(null);
                    try {
                      const data: ExtractionResponse = await classifyDocument(
                        document.id,
                        activeExtraction.id,
                      );
                      setActiveClassification(data);
                      await loadDocuments();
                      await refreshExtractions();
                    } catch (e: unknown) {
                      setError(e instanceof Error ? e.message : "Classification failed");
                    } finally {
                      setClassifying(false);
                    }
                  }}
                  disabled={classifying}
                  className="rounded-lg bg-emerald-600 px-6 py-3 font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
                >
                  {classifying ? "Classifying..." : "Run Readiness Classification"}
                </button>
              </section>
            )}

            {activeClassification && (
              <section>
                <h2 className="mb-4 text-xl font-semibold">
                  Readiness Classification
                  <span className="ml-2 text-sm font-normal text-gray-400">
                    {activeClassification.model_used} · {activeClassification.processing_time_ms}ms
                  </span>
                </h2>
                <ExtractionResult result={activeClassification} />
              </section>
            )}

            {activeExtraction && !activeSemanticMatch && (
              <section className="rounded-xl border border-amber-100 bg-amber-50/50 p-6">
                <h2 className="mb-2 text-xl font-semibold">Align Facts To Evidence</h2>
                <p className="mb-4 text-sm text-gray-600">
                  Match deterministic extracted fields back to the most relevant chunks using lexical
                  overlap plus embeddings. This is a QA-oriented Applied AI task, not free-form generation.
                </p>
                <button
                  onClick={async () => {
                    setMatching(true);
                    setError(null);
                    try {
                      const data: ExtractionResponse = await semanticMatchDocument(
                        document.id,
                        activeExtraction.id,
                      );
                      setActiveSemanticMatch(data);
                      await loadDocuments();
                      await refreshExtractions();
                    } catch (e: unknown) {
                      setError(e instanceof Error ? e.message : "Semantic matching failed");
                    } finally {
                      setMatching(false);
                    }
                  }}
                  disabled={matching}
                  className="rounded-lg bg-amber-600 px-6 py-3 font-medium text-white transition hover:bg-amber-700 disabled:opacity-50"
                >
                  {matching ? "Matching..." : "Run Semantic Matching"}
                </button>
              </section>
            )}

            {activeSemanticMatch && (
              <section>
                <h2 className="mb-4 text-xl font-semibold">
                  Semantic Matching
                  <span className="ml-2 text-sm font-normal text-gray-400">
                    {activeSemanticMatch.model_used} · {activeSemanticMatch.processing_time_ms}ms
                  </span>
                </h2>
                <ExtractionResult result={activeSemanticMatch} />
              </section>
            )}

            {/* Summarise button */}
            {activeExtraction && !hasGroundedSummary && (
              <section className="rounded-xl border border-blue-100 bg-blue-50/50 p-6">
                <h2 className="mb-2 text-xl font-semibold">Generate Grounded Summary</h2>
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
                  {activeSummaryMeta?.label ?? "LLM Summary"}
                  {(activeSummaryMeta || activeSummary.model_used) && (
                    <span className="ml-2 text-sm font-normal text-gray-400">
                      {activeSummary.model_used} · {activeSummary.processing_time_ms}ms
                      {activeSummaryMeta?.subtitle ? ` · ${activeSummaryMeta.subtitle}` : ""}
                    </span>
                  )}
                </h2>
                <ExtractionResult result={activeSummary} />
              </section>
            )}

            {/* Hierarchical summarisation — uses all chunks via MapReduce */}
            {activeExtraction && !hasHierarchicalSummary && (
              <section className="rounded-xl border border-teal-100 bg-teal-50/50 p-6">
                <h2 className="mb-2 text-xl font-semibold">Hierarchical Summarise</h2>
                <p className="mb-4 text-sm text-gray-600">
                  Processes ALL chunks through a 3-stage pipeline (chunk → section → document).
                  Best for long documents where standard summarisation only sees a small subset.
                </p>
                <button
                  onClick={async () => {
                    setHierarchicalising(true);
                    setError(null);
                    try {
                      const data: ExtractionResponse = await hierarchicalSummarise(document.id);
                      setActiveSummary(data);
                      await loadDocuments();
                      await refreshExtractions();
                    } catch (e: unknown) {
                      setError(e instanceof Error ? e.message : "Hierarchical summarisation failed");
                    } finally {
                      setHierarchicalising(false);
                    }
                  }}
                  disabled={hierarchicalising}
                  className="rounded-lg bg-teal-600 px-6 py-3 font-medium text-white transition hover:bg-teal-700 disabled:opacity-50"
                >
                  {hierarchicalising ? "Summarising (hierarchical)..." : "Hierarchical Summarise"}
                </button>
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
