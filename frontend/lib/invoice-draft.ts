import { FIELD_NAMES, type FieldName, type InvoiceDetail, type InvoicePatch, type LineItem } from "./types";

export interface LineDraft { key: number; description: string; quantity: string; unit_price: string; amount: string }
export interface Draft { fields: Record<FieldName, string>; lines: LineDraft[] }
export type DraftErrors = { fields: Partial<Record<FieldName, string>>; lines: Record<string, string> };

export const FIELD_LABEL: Record<FieldName, string> = {
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  supplier_name: "Supplier",
  customer_name: "Customer",
  currency: "Currency",
  subtotal: "Subtotal",
  tax: "Tax",
  total: "Total",
};

const MONEY = /^\d+(\.\d{1,2})?$/;
const NUMBER = /^\d+(\.\d+)?$/;
let nextKey = 0;

export const emptyLine = (): LineDraft => ({ key: nextKey++, description: "", quantity: "", unit_price: "", amount: "" });

export function toDraft(invoice: InvoiceDetail): Draft {
  const fields = Object.fromEntries(FIELD_NAMES.map((n) => [n, invoice[n] ?? ""])) as Record<FieldName, string>;
  const lines = invoice.line_items.map((l) => ({
    key: nextKey++,
    description: l.description ?? "",
    quantity: l.quantity ?? "",
    unit_price: l.unit_price ?? "",
    amount: l.amount ?? "",
  }));
  return { fields, lines };
}

const orNull = (v: string): string | null => (v.trim() === "" ? null : v.trim());
const isBlank = (l: LineDraft) => !l.description.trim() && !l.quantity.trim() && !l.unit_price.trim() && !l.amount.trim();

function cleanLines(lines: LineDraft[]): LineItem[] {
  return lines.filter((l) => !isBlank(l)).map((l) => ({
    description: orNull(l.description), quantity: orNull(l.quantity), unit_price: orNull(l.unit_price), amount: orNull(l.amount),
  }));
}

export function changedFields(initial: Draft, current: Draft): FieldName[] {
  return FIELD_NAMES.filter((n) => initial.fields[n].trim() !== current.fields[n].trim());
}

export function linesChanged(initial: Draft, current: Draft): boolean {
  return JSON.stringify(cleanLines(initial.lines)) !== JSON.stringify(cleanLines(current.lines));
}

export function isDirty(initial: Draft, current: Draft): boolean {
  return changedFields(initial, current).length > 0 || linesChanged(initial, current);
}

export function buildPatch(initial: Draft, current: Draft, reviewer: string, note: string): InvoicePatch {
  const fields: InvoicePatch["fields"] = {};
  for (const n of changedFields(initial, current)) fields[n] = orNull(current.fields[n]);
  return {
    reviewer,
    note: note.trim() || undefined,
    fields,
    line_items: linesChanged(initial, current) ? cleanLines(current.lines) : undefined,
  };
}

function validDate(v: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const d = new Date(`${v}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().startsWith(v);
}

export function validate(draft: Draft): DraftErrors {
  const fields: DraftErrors["fields"] = {};
  const lines: DraftErrors["lines"] = {};
  const f = (n: FieldName) => draft.fields[n].trim();
  if (f("invoice_date") && !validDate(f("invoice_date"))) fields.invoice_date = "Use the format YYYY-MM-DD.";
  if (f("currency") && !/^[A-Z]{3}$/.test(f("currency"))) fields.currency = "Use a 3-letter code, e.g. USD.";
  for (const n of ["subtotal", "tax", "total"] as const) {
    if (f(n) && !MONEY.test(f(n))) fields[n] = "Use a number with up to 2 decimals.";
  }
  for (const l of draft.lines) {
    if (l.amount.trim() && !MONEY.test(l.amount.trim())) lines[`${l.key}.amount`] = "Amount must have up to 2 decimals.";
    if (l.quantity.trim() && !NUMBER.test(l.quantity.trim())) lines[`${l.key}.quantity`] = "Quantity must be a number.";
    if (l.unit_price.trim() && !NUMBER.test(l.unit_price.trim())) lines[`${l.key}.unit_price`] = "Unit price must be a number.";
  }
  return { fields, lines };
}

export const hasErrors = (e: DraftErrors) => Object.keys(e.fields).length > 0 || Object.keys(e.lines).length > 0;
