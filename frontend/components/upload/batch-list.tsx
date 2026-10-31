"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileWarning } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/status-badge";
import { api, pollWhileActive } from "@/lib/api";
import { humanize, plural } from "@/lib/format";
import type { DocStatus, DocumentSummary, RejectedFile, UploadResponse } from "@/lib/types";

const isStatus = (s: string): s is DocStatus => ["queued", "processing", "completed", "needs_review", "failed"].includes(s);

function summarize(docs: DocumentSummary[]): { message: string; failed: boolean } {
  const review = docs.filter((d) => d.status === "needs_review").length;
  const failed = docs.filter((d) => d.status === "failed").length;
  const parts = [`${plural(docs.length, "document")} processed`];
  if (review) parts.push(`${review} need review`);
  if (failed) parts.push(`${failed} failed`);
  return { message: parts.join(", "), failed: failed > 0 };
}

function BatchRow({ doc, fallback }: { doc: DocumentSummary | undefined; fallback: UploadResponse["documents"][number] }) {
  const status = doc?.status ?? (isStatus(fallback.status) ? fallback.status : "queued");
  return (
    <li className="space-y-1.5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href={`/documents/${fallback.id}`} className="min-w-0 truncate text-sm font-medium text-brand-navy hover:underline">
          {fallback.filename}
        </Link>
        <div className="flex items-center gap-2">
          {fallback.duplicate_of && <Badge variant="outline">Duplicate</Badge>}
          <StatusBadge status={status} />
        </div>
      </div>
      <Progress value={doc?.progress ?? 0} className="h-1.5" />
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{humanize(doc?.stage ?? null) || "Waiting"}</span>
        <span>{doc?.progress ?? 0}%</span>
      </div>
      {doc?.error_message && <p className="text-xs text-destructive">{doc.error_message}</p>}
    </li>
  );
}

function RejectedRow({ file }: { file: RejectedFile }) {
  return (
    <li className="flex items-start gap-2 py-3 text-sm">
      <FileWarning className="mt-0.5 size-4 shrink-0 text-destructive" />
      <div className="min-w-0">
        <div className="truncate font-medium">{file.filename}</div>
        <div className="text-xs text-muted-foreground">
          <span className="font-mono">{file.code}</span> · {file.message}
        </div>
      </div>
    </li>
  );
}

export function BatchList({ batch, clientRejected }: { batch: UploadResponse | null; clientRejected: RejectedFile[] }) {
  const batchId = batch?.documents.length ? batch.batch_id : undefined;
  const live = useQuery({
    queryKey: ["documents", "batch", batchId],
    queryFn: () => api.documents({ batch_id: batchId, page_size: 100 }),
    enabled: Boolean(batchId),
    refetchInterval: (q) => pollWhileActive(q.state.data?.items.map((d) => d.status) ?? []),
  });

  const items = live.data?.items;
  const notified = useRef<string | null>(null);
  useEffect(() => {
    if (!batchId || !items?.length || notified.current === batchId) return;
    if (items.some((d) => d.status === "queued" || d.status === "processing")) return;
    notified.current = batchId;
    const { message, failed } = summarize(items);
    if (failed) toast.warning(message);
    else toast.success(message);
  }, [batchId, items]);

  if (!batch && clientRejected.length === 0) return null;
  const byId = new Map((items ?? []).map((d) => [d.id, d]));
  const rejected = [...(batch?.rejected ?? []), ...clientRejected];

  return (
    <Card>
      <CardHeader>
        <CardTitle>This batch</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="divide-y">
          {batch?.documents.map((d) => <BatchRow key={d.id} doc={byId.get(d.id)} fallback={d} />)}
          {rejected.map((f, i) => <RejectedRow key={`${f.filename}-${i}`} file={f} />)}
        </ul>
      </CardContent>
    </Card>
  );
}
