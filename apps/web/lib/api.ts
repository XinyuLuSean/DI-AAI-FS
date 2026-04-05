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
