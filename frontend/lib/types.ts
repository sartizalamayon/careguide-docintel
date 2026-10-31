// Mirrors backend/app/schemas.py (docs/SPEC.md §10). Money values are strings with 2 decimals.
export type DocStatus = "queued" | "processing" | "completed" | "needs_review" | "failed";
export type InvoiceStatus = "ok" | "needs_review" | "approved";
export type FileType = "pdf" | "png" | "jpg" | "tiff" | "xlsx" | "xls" | "csv";
export type SearchMode = "hybrid" | "keyword" | "semantic";

export interface Page<T> { items: T[]; total: number; page: number; page_size: number }

export interface DocumentSummary {
  id: string; batch_id: string; filename: string; file_type: FileType; family: "document" | "spreadsheet";
  size_bytes: number; status: DocStatus; stage: string | null; progress: number;
  pages_total: number | null; pages_done: number; invoice_count: number; issue_count: number;
  needs_review_count: number; error_code: string | null; error_message: string | null; attempts: number;
  duplicate_of: string | null; processing_ms: number | null; created_at: string; updated_at: string;
}

export interface ProcessingEvent {
  id: number; event: string; stage: string | null; message: string | null; data: Record<string, unknown>; created_at: string;
}

export interface DocumentDetail extends DocumentSummary { invoices: InvoiceSummary[]; events: ProcessingEvent[] }

export interface DocumentStatus {
  id: string; status: DocStatus; stage: string | null; progress: number; pages_done: number; pages_total: number | null;
  error_code: string | null; error_message: string | null; updated_at: string;
}

export interface PageText {
  page_no: number; sheet_name: string | null; method: string; ocr_confidence: number | null; word_count: number; text: string;
}

export interface RejectedFile { filename: string; code: string; message: string }

export interface UploadResponse {
  batch_id: string;
  documents: { id: string; filename: string; file_type: string; status: string; duplicate_of: string | null }[];
  rejected: RejectedFile[];
}

export interface InvoiceSummary {
  id: string; document_id: string; filename: string; seq: number; page_start: number | null; page_end: number | null;
  source_ref: string | null; invoice_number: string | null; invoice_date: string | null; supplier_name: string | null;
  customer_name: string | null; currency: string | null; subtotal: string | null; tax: string | null; total: string | null;
  status: InvoiceStatus; issue_count: number; error_count: number; extraction_method: string;
}

export const FIELD_NAMES = [
  "invoice_number", "invoice_date", "supplier_name", "customer_name", "currency", "subtotal", "tax", "total",
] as const;
export type FieldName = (typeof FIELD_NAMES)[number];

export interface FieldValue { value: string | null; confidence: number; grounded: boolean; source: string }
export interface LineItem { position?: number; description: string | null; quantity: string | null; unit_price: string | null; amount: string | null }
export interface Issue { code: string; severity: "error" | "warning"; field: string | null; message: string; details: Record<string, unknown> }
export interface Correction { field: string; old_value: unknown; new_value: unknown; corrected_by: string; note: string | null; created_at: string }

export interface InvoiceDetail extends InvoiceSummary {
  fields: Partial<Record<FieldName, FieldValue>>; line_items: LineItem[]; issues: Issue[]; corrections: Correction[];
  llm_model: string | null; prompt_version: string | null; raw_text: string;
}

export interface InvoicePatch {
  reviewer: string; note?: string; fields?: Partial<Record<FieldName, string | null>>; line_items?: LineItem[];
}

export interface SearchHit extends InvoiceSummary { score: number; matched_by: string[]; snippet: string }

export interface CrossCheckDifference { field: string; a: string | number | null; b: string | number | null }

export interface CrossCheck {
  id: string; document_a_id: string; document_b_id: string; created_at: string;
  summary: {
    counts: { matched: number; mismatched: number; only_in_a: number; only_in_b: number };
    matched: { invoice_number: string; a_invoice_id: string; b_invoice_id: string }[];
    mismatched: { invoice_number: string; a_invoice_id: string; b_invoice_id: string; differences: CrossCheckDifference[] }[];
    only_in_a: { invoice_number: string; invoice_id: string }[];
    only_in_b: { invoice_number: string; invoice_id: string }[];
  };
}

export interface Stats {
  documents: Record<"total" | DocStatus, number>;
  invoices: Record<"total" | InvoiceStatus, number>;
  pages_processed: number; avg_processing_ms: number; top_issue_codes: { code: string; count: number }[];
}

export interface LlmKey {
  provider: "groq";
  model: string;
  key_hint: string;
  updated_at: string;
}

export interface AccountLlmStatus {
  email: string;
  key: LlmKey | null;
  models: string[];
  server_model: string;
}
