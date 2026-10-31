// Typed client for the FastAPI backend, always via the same-origin proxy (/api/backend).
import type {
  CrossCheck, DocStatus, DocumentDetail, DocumentStatus, DocumentSummary, FileType, InvoiceDetail, InvoicePatch,
  InvoiceStatus, InvoiceSummary, Page, PageText, ProcessingEvent, SearchHit, SearchMode, Stats, UploadResponse,
} from "./types";

const BASE = "/api/backend";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

export type DocumentFilters = {
  status?: DocStatus; file_type?: FileType; batch_id?: string; q?: string; page?: number; page_size?: number;
};

export type InvoiceFilters = {
  status?: InvoiceStatus; currency?: string; supplier?: string; customer?: string; date_from?: string; date_to?: string;
  total_min?: string; total_max?: string; has_issues?: boolean; document_id?: string; page?: number; page_size?: number;
};

export type SearchParams = InvoiceFilters & { q?: string; mode?: SearchMode };

function qs(params?: Query): string {
  if (!params) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

interface ErrorBody { error?: { code?: string; message?: string; details?: unknown }; detail?: unknown }

async function readBody<T>(res: Response): Promise<T | undefined> {
  try {
    return (await res.json()) as T;
  } catch {
    return undefined;
  }
}

function toApiError(res: Response, body: ErrorBody | undefined): ApiError {
  return new ApiError(res.status, body?.error?.code ?? `HTTP_${res.status}`, body?.error?.message ?? res.statusText, body?.error?.details ?? body?.detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) throw toApiError(res, await readBody<ErrorBody>(res));
  return (res.status === 204 ? undefined : await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

/** The upload answers 422 with a normal UploadResponse when every file is rejected. */
async function upload(files: File[]): Promise<UploadResponse> {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  const res = await fetch(`${BASE}/documents`, { method: "POST", body: fd, cache: "no-store" });
  const body = await readBody<UploadResponse & ErrorBody>(res);
  if (res.ok || (res.status === 422 && body && Array.isArray(body.rejected))) return body as UploadResponse;
  throw toApiError(res, body);
}

export const api = {
  stats: () => request<Stats>("/stats"),

  upload,
  documents: (q?: DocumentFilters) => request<Page<DocumentSummary>>(`/documents${qs(q)}`),
  document: (id: string) => request<DocumentDetail>(`/documents/${id}`),
  documentStatus: (id: string) => request<DocumentStatus>(`/documents/${id}/status`),
  documentEvents: (id: string) => request<ProcessingEvent[]>(`/documents/${id}/events`),
  documentPages: (id: string, from = 1, to = 50) => request<PageText[]>(`/documents/${id}/pages${qs({ from, to })}`),
  pageImageUrl: (id: string, page: number, dpi = 110) => `${BASE}/documents/${id}/pages/${page}/image?dpi=${dpi}`,
  fileUrl: (id: string) => `${BASE}/documents/${id}/file`,
  reprocess: (id: string, from_stage?: "parse" | "extract") =>
    request<DocumentSummary>(`/documents/${id}/reprocess`, json("POST", { from_stage: from_stage ?? null })),
  reprocessFailed: () => request<{ requeued: number }>("/documents/reprocess-failed", json("POST", {})),

  invoices: (q?: InvoiceFilters) => request<Page<InvoiceSummary>>(`/invoices${qs(q)}`),
  invoice: (id: string) => request<InvoiceDetail>(`/invoices/${id}`),
  correct: (id: string, body: InvoicePatch) => request<InvoiceDetail>(`/invoices/${id}`, json("PATCH", body)),
  approve: (id: string, body: { reviewer: string; note?: string }) =>
    request<InvoiceDetail>(`/invoices/${id}/approve`, json("POST", body)),

  search: (q: SearchParams) => request<Page<SearchHit>>(`/search${qs(q)}`),

  crossCheck: (document_a_id: string, document_b_id: string) =>
    request<CrossCheck>("/cross-checks", json("POST", { document_a_id, document_b_id })),
};

export const errorMessage = (e: unknown): string => (e instanceof Error ? e.message : "Something went wrong.");

/** Poll every 2 s while anything is still moving (TanStack Query refetchInterval helper). */
export const pollWhileActive = (statuses: (DocStatus | undefined)[]) =>
  statuses.some((s) => s === "queued" || s === "processing") ? 2000 : false;
