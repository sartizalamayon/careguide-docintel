"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { ReprocessButton } from "@/components/documents/reprocess-button";
import { PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage, pollWhileActive } from "@/lib/api";
import { formatDateTime, formatSeconds, plural } from "@/lib/format";
import type { DocStatus, FileType } from "@/lib/types";

const PAGE_SIZE = 20;
const ALL = "all";
const STATUSES: DocStatus[] = ["queued", "processing", "completed", "needs_review", "failed"];
const FILE_TYPES: FileType[] = ["pdf", "png", "jpg", "tiff", "xlsx", "xls", "csv"];
const STATUS_LABEL: Record<DocStatus, string> = {
  queued: "Queued", processing: "Processing", completed: "Completed", needs_review: "Needs review", failed: "Failed",
};

export default function DocumentsPage() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<DocStatus | typeof ALL>(ALL);
  const [fileType, setFileType] = useState<FileType | typeof ALL>(ALL);
  const [page, setPage] = useState(1);

  const docs = useQuery({
    queryKey: ["documents", "list", status, fileType, page],
    queryFn: () =>
      api.documents({
        status: status === ALL ? undefined : status,
        file_type: fileType === ALL ? undefined : fileType,
        page,
        page_size: PAGE_SIZE,
      }),
    refetchInterval: (q) => pollWhileActive(q.state.data?.items.map((d) => d.status) ?? []),
  });

  const retryAll = useMutation({
    mutationFn: api.reprocessFailed,
    onSuccess: ({ requeued }) => {
      toast.success(requeued ? `${plural(requeued, "document")} queued again` : "No failed documents to retry");
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const items = docs.data?.items ?? [];

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Documents"
        description="Every uploaded file and where it is in the pipeline."
        actions={
          <Button variant="outline" disabled={retryAll.isPending} onClick={() => retryAll.mutate()}>
            <RotateCcw /> Retry all failed
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <Select value={status} onValueChange={(v) => { setStatus(v as DocStatus | typeof ALL); setPage(1); }}>
          <SelectTrigger className="w-44" aria-label="Filter by status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            {STATUSES.map((s) => <SelectItem key={s} value={s}>{STATUS_LABEL[s]}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={fileType} onValueChange={(v) => { setFileType(v as FileType | typeof ALL); setPage(1); }}>
          <SelectTrigger className="w-40" aria-label="Filter by file type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All file types</SelectItem>
            {FILE_TYPES.map((t) => <SelectItem key={t} value={t}>{t.toUpperCase()}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Filename</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Pages</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-32">Progress</TableHead>
              <TableHead className="text-right">Invoices</TableHead>
              <TableHead className="text-right">Issues</TableHead>
              <TableHead className="text-right">Processed in</TableHead>
              <TableHead>Uploaded</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {docs.isLoading && <TableSkeleton columns={10} />}
            {items.map((d) => (
              <TableRow key={d.id}>
                <TableCell className="max-w-64 truncate font-medium">
                  <Link href={`/documents/${d.id}`} className="text-brand-navy hover:underline">{d.filename}</Link>
                </TableCell>
                <TableCell className="uppercase">{d.file_type}</TableCell>
                <TableCell>{d.pages_done}/{d.pages_total ?? "?"}</TableCell>
                <TableCell><StatusBadge status={d.status} /></TableCell>
                <TableCell><Progress value={d.progress} className="h-1.5" /></TableCell>
                <TableCell className="text-right">{d.invoice_count}</TableCell>
                <TableCell className="text-right">{d.issue_count}</TableCell>
                <TableCell className="text-right">{formatSeconds(d.processing_ms)}</TableCell>
                <TableCell className="whitespace-nowrap">{formatDateTime(d.created_at)}</TableCell>
                <TableCell>
                  <div className="flex justify-end gap-2">
                    {(d.status === "failed" || d.status === "needs_review") && <ReprocessButton id={d.id} />}
                    <Button variant="ghost" size="sm" asChild>
                      <Link href={`/documents/${d.id}`}><ExternalLink /> Open</Link>
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {docs.isError && <ErrorState error={docs.error} onRetry={() => void docs.refetch()} />}
        {!docs.isLoading && !docs.isError && items.length === 0 && <EmptyState message="No documents match these filters." />}
      </Card>
      <Pagination page={page} pageSize={PAGE_SIZE} total={docs.data?.total ?? 0} onPageChange={setPage} />
    </div>
  );
}
