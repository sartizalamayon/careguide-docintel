// Mirrors backend schemas (docs/SPEC.md §10). Money values are strings with 2 decimals.
export type DocumentStatus = "queued" | "processing" | "completed" | "needs_review" | "failed";
export type InvoiceStatus = "ok" | "needs_review" | "approved";
export type FileType = "pdf" | "png" | "jpg" | "tiff" | "xlsx" | "xls" | "csv";

export interface Page<T> { items: T[]; total: number; page: number; page_size: number }

export interface DocumentSummary {
  id: string; batch_id: string; filename: string; file_type: FileType; family: "document" | "spreadsheet";
  size_bytes: number; status: DocumentStatus; stage: string | null; progress: number;
  pages_total: number | null; pages_done: number; invoice_count: number; issue_count: number;
  needs_review_count: number; error_code: string | null; error_message: string | null; attempts: number;
  duplicate_of: string | null; processing_ms: number | null; created_at: string; updated_at: string;
}

export interface ProcessingEvent {
  id: number; event: string; stage: string | null; message: string | null; data: Record<string, unknown>; created_at: string;
}

export interface DocumentDetail extends DocumentSummary { invoices: InvoiceSummary[]; events: ProcessingEvent[] }

export interface UploadResponse {
  batch_id: string;
  documents: Pick<DocumentSummary, "id" | "filename" | "file_type" | "status" | "duplicate_of">[];
  rejected: { filename: string; code: string; message: string }[];
}

export interface InvoiceSummary {
  id: string; document_id: string; filename: string; seq: number; page_start: number | null; page_end: number | null;
  source_ref: string | null; invoice_number: string | null; invoice_date: string | null; supplier_name: string | null;
  customer_name: string | null; currency: string | null; subtotal: string | null; tax: string | null; total: string | null;
  status: InvoiceStatus; issue_count: number; error_count: number; extraction_method: "llm" | "table";
}

export type FieldName =
  | "invoice_number" | "invoice_date" | "supplier_name" | "customer_name" | "currency" | "subtotal" | "tax" | "total";

export interface FieldValue { value: string | null; confidence: number; grounded: boolean; source: "llm" | "table" | "manual" }
export interface LineItem { position?: number; description: string | null; quantity: string | null; unit_price: string | null; amount: string | null }
export interface Issue { code: string; severity: "error" | "warning"; field: string | null; message: string; details: Record<string, unknown> }
export interface Correction { field: string; old_value: unknown; new_value: unknown; corrected_by: string; note: string | null; created_at: string }

export interface InvoiceDetail extends InvoiceSummary {
  fields: Record<FieldName, FieldValue>; line_items: LineItem[]; issues: Issue[]; corrections: Correction[];
  llm_model: string | null; prompt_version: string | null; raw_text: string;
}

export interface SearchHit extends InvoiceSummary { score: number; matched_by: ("keyword" | "semantic")[]; snippet: string }

export interface CrossCheck {
  id: string; document_a_id: string; document_b_id: string; created_at: string;
  summary: {
    counts: { matched: number; mismatched: number; only_in_a: number; only_in_b: number };
    matched: { invoice_number: string; a_invoice_id: string; b_invoice_id: string }[];
    mismatched: { invoice_number: string; a_invoice_id: string; b_invoice_id: string; differences: { field: string; a: string; b: string }[] }[];
    only_in_a: { invoice_number: string; invoice_id: string }[];
    only_in_b: { invoice_number: string; invoice_id: string }[];
  };
}

export interface Stats {
  documents: Record<"total" | DocumentStatus, number>;
  invoices: Record<"total" | InvoiceStatus, number>;
  pages_processed: number; avg_processing_ms: number; top_issue_codes: { code: string; count: number }[];
}
