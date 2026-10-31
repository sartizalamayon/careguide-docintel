const dateTime = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });
const date = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" });

const withThousands = (digits: string) => digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

export function formatMoney(value: string | null, currency?: string | null): string {
  if (value === null) return "—";
  const [whole, frac] = value.split(".");
  const num = frac === undefined ? withThousands(whole) : `${withThousands(whole)}.${frac}`;
  return currency ? `${currency} ${num}` : num;
}

export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return date.format(new Date(iso.length === 10 ? `${iso}T00:00:00` : iso));
}

export function formatSeconds(ms: number | null): string {
  return ms === null ? "—" : `${(ms / 1000).toFixed(1)} s`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function humanize(text: string | null): string {
  if (!text) return "";
  const spaced = text.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

const STAGE_LABELS: Record<string, string> = {
  parsing: "Reading pages",
  ocr: "Reading scanned pages (OCR)",
  segmenting: "Finding invoices",
  extracting: "Extracting fields with AI, this can take a minute",
  validating: "Checking totals and rules",
  indexing: "Making it searchable",
};

/** Plain-language label for a pipeline stage; empty when there is no stage yet. */
export function stageLabel(stage: string | null | undefined): string {
  if (!stage) return "";
  return STAGE_LABELS[stage] ?? humanize(stage);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** Parses "12.5" or "1380.00" to integer cents; null when blank or not a plain amount. */
export function toCents(value: string): number | null {
  const m = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value.trim());
  return m ? Number(m[1]) * 100 + Number((m[2] ?? "").padEnd(2, "0")) : null;
}

export function fromCents(cents: number): string {
  const abs = Math.abs(cents);
  const text = `${withThousands(String(Math.floor(abs / 100)))}.${String(abs % 100).padStart(2, "0")}`;
  return cents < 0 ? `-${text}` : text;
}
