// Typed client for the FastAPI backend, always via the same-origin proxy (/api/backend).
import type {
  CrossCheck, DocumentDetail, DocumentStatus, DocumentSummary, InvoiceDetail, InvoiceSummary, LineItem, Page,
  ProcessingEvent, SearchHit, Stats, UploadResponse,
} from "./types";

const BASE = "/api/backend";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

function qs(params?: Query): string {
  if (!params) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    let body: { error?: { code?: string; message?: string; details?: unknown }; detail?: unknown } = {};
    try { body = await res.json(); } catch { /* not json */ }
    throw new ApiError(res.status, body.error?.code ?? `HTTP_${res.status}`, body.error?.message ?? res.statusText, body.error?.details ?? body.detail);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const api = {
  stats: () => request<Stats>("/stats"),

  upload: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<UploadResponse>("/documents", { method: "POST", body: fd });
  },
  documents: (q?: Query & { status?: DocumentStatus }) => request<Page<DocumentSummary>>(`/documents${qs(q)}`),
  document: (id: string) => request<DocumentDetail>(`/documents/${id}`),
  documentEvents: (id: string) => request<ProcessingEvent[]>(`/documents/${id}/events`),
  documentPages: (id: string, from = 1, to = 50) =>
    request<{ page_no: number; sheet_name: string | null; method: string; ocr_confidence: number | null; word_count: number; text: string }[]>(
      `/documents/${id}/pages${qs({ from, to })}`),
  pageImageUrl: (id: string, page: number, dpi = 110) => `${BASE}/documents/${id}/pages/${page}/image?dpi=${dpi}`,
  fileUrl: (id: string) => `${BASE}/documents/${id}/file`,
  reprocess: (id: string, from_stage?: "parse" | "extract") => request<DocumentSummary>(`/documents/${id}/reprocess`, json("POST", { from_stage: from_stage ?? null })),
  reprocessFailed: () => request<{ requeued: number }>("/documents/reprocess-failed", json("POST", {})),

  invoices: (q?: Query) => request<Page<InvoiceSummary>>(`/invoices${qs(q)}`),
  invoice: (id: string) => request<InvoiceDetail>(`/invoices/${id}`),
  correct: (id: string, body: { reviewer: string; note?: string; fields?: Record<string, string | null>; line_items?: LineItem[] }) =>
    request<InvoiceDetail>(`/invoices/${id}`, json("PATCH", body)),
  approve: (id: string, body: { reviewer: string; note?: string }) => request<InvoiceDetail>(`/invoices/${id}/approve`, json("POST", body)),

  search: (q: Query & { q?: string; mode?: "hybrid" | "keyword" | "semantic" }) => request<Page<SearchHit>>(`/search${qs(q)}`),

  crossCheck: (document_a_id: string, document_b_id: string) => request<CrossCheck>("/cross-checks", json("POST", { document_a_id, document_b_id })),
};

/** Poll while anything is still moving (TanStack Query refetchInterval helper). */
export const pollWhileActive = (statuses: (DocumentStatus | undefined)[]) =>
  statuses.some((s) => s === "queued" || s === "processing") ? 2000 : false;
