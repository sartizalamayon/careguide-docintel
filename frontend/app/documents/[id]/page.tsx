"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CircleAlert, Download } from "lucide-react";
import { HistoryTab } from "@/components/documents/history-tab";
import { InvoicesTab } from "@/components/documents/invoices-tab";
import { PagesTab } from "@/components/documents/pages-tab";
import { ReprocessButton } from "@/components/documents/reprocess-button";
import { PageHeader } from "@/components/page-header";
import { ErrorState, ListSkeleton } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, pollWhileActive } from "@/lib/api";
import { formatBytes, formatDateTime, formatSeconds, humanize } from "@/lib/format";

export default function DocumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const doc = useQuery({
    queryKey: ["document", id],
    queryFn: () => api.document(id),
    refetchInterval: (q) => pollWhileActive([q.state.data?.status]),
  });

  if (doc.isLoading) return <div className="mx-auto max-w-6xl"><ListSkeleton rows={3} className="h-24" /></div>;
  if (doc.isError || !doc.data) return <ErrorState error={doc.error} onRetry={() => void doc.refetch()} />;

  const d = doc.data;
  const active = d.status === "queued" || d.status === "processing";

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <Button variant="ghost" size="sm" asChild>
        <Link href="/documents"><ArrowLeft /> All documents</Link>
      </Button>
      <PageHeader
        title={d.filename}
        description={`${d.file_type.toUpperCase()} · ${formatBytes(d.size_bytes)} · uploaded ${formatDateTime(d.created_at)} · processed in ${formatSeconds(d.processing_ms)}`}
        actions={
          <>
            <StatusBadge status={d.status} />
            <Button variant="outline" size="sm" asChild>
              <a href={api.fileUrl(d.id)} target="_blank" rel="noreferrer"><Download /> Original</a>
            </Button>
          </>
        }
      />

      {active && (
        <div className="space-y-1.5 rounded-lg bg-card p-4 ring-1 ring-foreground/10">
          <div className="flex justify-between text-sm">
            <span>{humanize(d.stage) || "Waiting"}</span>
            <span className="text-muted-foreground">{d.progress}%</span>
          </div>
          <Progress value={d.progress} className="h-1.5" />
        </div>
      )}

      {d.status === "failed" && (
        <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <div className="flex gap-3">
            <CircleAlert className="mt-0.5 size-5 shrink-0 text-destructive" />
            <div>
              <div className="font-mono text-sm font-medium text-destructive">{d.error_code ?? "ERROR"}</div>
              <p className="mt-0.5 text-sm">{d.error_message ?? "Processing failed."}</p>
            </div>
          </div>
          <ReprocessButton id={d.id} size="default" />
        </div>
      )}

      <Tabs defaultValue="invoices">
        <TabsList>
          <TabsTrigger value="invoices">Invoices ({d.invoices.length})</TabsTrigger>
          <TabsTrigger value="pages">Pages{d.pages_total ? ` (${d.pages_total})` : ""}</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>
        <TabsContent value="invoices"><InvoicesTab invoices={d.invoices} /></TabsContent>
        <TabsContent value="pages"><PagesTab documentId={d.id} family={d.family} pagesTotal={d.pages_total} /></TabsContent>
        <TabsContent value="history"><HistoryTab documentId={d.id} polling={active} /></TabsContent>
      </Tabs>
    </div>
  );
}
