export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function extractErrorMessage(detail: unknown, fallback: string): string {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && detail !== null && "message" in detail) {
    return (detail as { message: string }).message;
  }
  return fallback;
}

export async function uploadDocument(file: File) {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/documents/upload`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(body.detail, `Upload failed (${res.status})`));
  }

  return res.json();
}

export async function extractDocument(documentId: string) {
  const res = await fetch(`${API_BASE}/documents/${documentId}/extract`, {
    method: "POST",
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(body.detail, `Extraction failed (${res.status})`));
  }

  return res.json();
}

export async function summariseDocument(
  documentId: string,
  extractionId?: string,
) {
  const params = new URLSearchParams();
  if (extractionId) params.set("extraction_id", extractionId);
  const qs = params.toString();
  const url = `${API_BASE}/documents/${documentId}/summarise${qs ? `?${qs}` : ""}`;

  const res = await fetch(url, { method: "POST" });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(body.detail, `API returned ${res.status}`));
  }

  return res.json();
}

// ── Document & extraction list API ───────────────────────────────────────

export async function fetchDocuments() {
  const res = await fetch(`${API_BASE}/documents`);
  if (!res.ok) throw new Error(`Failed to fetch documents (${res.status})`);
  return res.json();
}

export async function fetchDocument(documentId: string) {
  const res = await fetch(`${API_BASE}/documents/${documentId}`);
  if (!res.ok) throw new Error(`Failed to fetch document (${res.status})`);
  return res.json();
}

export async function fetchDocumentExtractions(documentId: string) {
  const res = await fetch(`${API_BASE}/documents/${documentId}/extractions`);
  if (!res.ok) throw new Error(`Failed to fetch extractions (${res.status})`);
  return res.json();
}

// ── Phase 11: HITL Review API ────────────────────────────────────────────

export async function fetchReviewQueue() {
  const res = await fetch(`${API_BASE}/documents/review-queue`);
  if (!res.ok) throw new Error(`Failed to fetch review queue (${res.status})`);
  return res.json();
}

export async function getReviewStatus(documentId: string, extractionId: string) {
  const res = await fetch(
    `${API_BASE}/documents/${documentId}/extractions/${extractionId}/review`,
  );
  if (!res.ok) throw new Error(`Failed to get review status (${res.status})`);
  return res.json();
}

export async function getExtraction(documentId: string, extractionId: string) {
  const res = await fetch(
    `${API_BASE}/documents/${documentId}/extractions/${extractionId}`,
  );
  if (!res.ok) throw new Error(`Failed to get extraction (${res.status})`);
  return res.json();
}

export async function submitReview(
  documentId: string,
  extractionId: string,
  status: string,
  reviewerId: string,
  notes: string,
) {
  const res = await fetch(
    `${API_BASE}/documents/${documentId}/extractions/${extractionId}/review`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, reviewer_id: reviewerId, notes }),
    },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(body.detail, `Review failed (${res.status})`));
  }
  return res.json();
}

export async function submitCorrection(
  documentId: string,
  extractionId: string,
  payload: {
    reviewer_id: string;
    field_corrections: Array<{
      field_name: string;
      corrected_value: string;
      reason: string;
    }>;
    notes: string;
  },
) {
  const res = await fetch(
    `${API_BASE}/documents/${documentId}/extractions/${extractionId}/correct`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(body.detail, `Correction failed (${res.status})`));
  }
  return res.json();
}
