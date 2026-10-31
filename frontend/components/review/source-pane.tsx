"use client";

import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { PageImage } from "@/components/page-image";
import { ErrorState, ListSkeleton } from "@/components/states";
import { api } from "@/lib/api";
import type { InvoiceDetail } from "@/lib/types";

const MAX_PAGES = 10;

function SheetText({ invoice }: { invoice: InvoiceDetail }) {
  const from = invoice.page_start ?? 1;
  const to = Math.min(invoice.page_end ?? from, from + MAX_PAGES - 1);
  const pages = useQuery({
    queryKey: ["document", invoice.document_id, "pages", from, to],
    queryFn: () => api.documentPages(invoice.document_id, from, to),
  });
  if (pages.isLoading) return <ListSkeleton rows={2} className="h-48" />;
  if (pages.isError) return <ErrorState error={pages.error} onRetry={() => void pages.refetch()} />;
  return (
    <div className="space-y-3">
      {pages.data?.map((p) => (
        <div key={p.page_no} className="space-y-1">
          <h3 className="text-xs font-medium text-muted-foreground">{p.sheet_name ?? `Sheet ${p.page_no}`}</h3>
          <pre className="max-h-[70vh] overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap">{p.text}</pre>
        </div>
      ))}
    </div>
  );
}

function PageImages({ invoice }: { invoice: InvoiceDetail }) {
  const first = invoice.page_start ?? 1;
  const last = Math.min(invoice.page_end ?? first, first + MAX_PAGES - 1);
  const numbers = Array.from({ length: last - first + 1 }, (_, i) => first + i);
  return (
    <div className="space-y-3">
      {numbers.map((n) => (
        <div key={n} className="space-y-1">
          <h3 className="text-xs font-medium text-muted-foreground">Page {n}</h3>
          <PageImage src={api.pageImageUrl(invoice.document_id, n, 110)} alt={`Page ${n} of ${invoice.filename}`} />
        </div>
      ))}
    </div>
  );
}

export function SourcePane({ invoice }: { invoice: InvoiceDetail }) {
  const doc = useQuery({ queryKey: ["document", invoice.document_id], queryFn: () => api.document(invoice.document_id) });
  return (
    <Card className="px-4">
      <div className="text-sm font-medium text-brand-navy">{invoice.filename}</div>
      {doc.isLoading && <ListSkeleton rows={1} className="h-96" />}
      {doc.isError && <ErrorState error={doc.error} onRetry={() => void doc.refetch()} />}
      {doc.data && (doc.data.family === "spreadsheet" ? <SheetText invoice={invoice} /> : <PageImages invoice={invoice} />)}
      {invoice.source_ref && <p className="text-xs text-muted-foreground">Source: {invoice.source_ref}</p>}
    </Card>
  );
}
