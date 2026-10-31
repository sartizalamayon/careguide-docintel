"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageImage } from "@/components/page-image";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/states";
import { Pagination } from "@/components/pagination";
import { api } from "@/lib/api";
import { TONE_CLASS, type Tone } from "@/lib/tone";
import type { PageText } from "@/lib/types";

const CHUNK = 50;

export function confidenceTone(confidence: number): Tone {
  if (confidence >= 0.9) return "success";
  if (confidence >= 0.6) return "warning";
  return "danger";
}

function OcrBadge({ page }: { page: PageText }) {
  if (page.ocr_confidence === null) return <Badge variant="outline">{page.method}</Badge>;
  return (
    <Badge className={TONE_CLASS[confidenceTone(page.ocr_confidence)]}>
      OCR confidence {Math.round(page.ocr_confidence * 100)}%
    </Badge>
  );
}

function PageDialog({ documentId, page, onClose }: { documentId: string; page: PageText | null; onClose: () => void }) {
  return (
    <Dialog open={page !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-6xl">
        {page && (
          <>
            <DialogHeader>
              <DialogTitle>Page {page.page_no}</DialogTitle>
              <DialogDescription asChild>
                <div className="flex items-center gap-2"><OcrBadge page={page} /><span>{page.word_count} words</span></div>
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 lg:grid-cols-2">
              <PageImage src={api.pageImageUrl(documentId, page.page_no, 110)} alt={`Page ${page.page_no}`} />
              <pre className="max-h-[70vh] overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap">{page.text || "No text was extracted."}</pre>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function SheetList({ pages }: { pages: PageText[] }) {
  return (
    <div className="space-y-4">
      {pages.map((p) => (
        <Card key={p.page_no} className="px-4">
          <div className="flex items-center justify-between">
            <h3 className="font-heading text-sm font-medium">{p.sheet_name ?? `Sheet ${p.page_no}`}</h3>
            <span className="text-xs text-muted-foreground">{p.word_count} words</span>
          </div>
          <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap">{p.text || "This sheet is empty."}</pre>
        </Card>
      ))}
    </div>
  );
}

export function PagesTab({ documentId, family, pagesTotal }: { documentId: string; family: "document" | "spreadsheet"; pagesTotal: number | null }) {
  const [chunk, setChunk] = useState(1);
  const [selected, setSelected] = useState<PageText | null>(null);
  const from = (chunk - 1) * CHUNK + 1;
  const pages = useQuery({
    queryKey: ["document", documentId, "pages", from],
    queryFn: () => api.documentPages(documentId, from, from + CHUNK - 1),
  });

  if (pages.isLoading) return <ListSkeleton rows={3} className="h-40" />;
  if (pages.isError) return <Card><ErrorState error={pages.error} onRetry={() => void pages.refetch()} /></Card>;
  if (!pages.data?.length) return <Card><EmptyState message="No pages have been read yet." /></Card>;

  return (
    <>
      {family === "spreadsheet" ? (
        <SheetList pages={pages.data} />
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
          {pages.data.map((p) => (
            <button
              key={p.page_no}
              type="button"
              onClick={() => setSelected(p)}
              className="space-y-1.5 rounded-lg text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <PageImage src={api.pageImageUrl(documentId, p.page_no, 60)} alt={`Page ${p.page_no}`} className="transition-shadow hover:shadow-md" />
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Page {p.page_no}</span>
                {p.ocr_confidence !== null && <span>{Math.round(p.ocr_confidence * 100)}%</span>}
              </div>
            </button>
          ))}
        </div>
      )}
      <Pagination page={chunk} pageSize={CHUNK} total={pagesTotal ?? 0} onPageChange={setChunk} />
      <PageDialog documentId={documentId} page={selected} onClose={() => setSelected(null)} />
    </>
  );
}
