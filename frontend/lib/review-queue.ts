import type { InvoiceSummary } from "./types";

/** Most errors first, then most issues; the sort is stable so the backend order breaks ties. */
export function sortReviewQueue(items: InvoiceSummary[]): InvoiceSummary[] {
  return [...items].sort((a, b) => b.error_count - a.error_count || b.issue_count - a.issue_count);
}
