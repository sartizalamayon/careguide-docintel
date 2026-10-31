"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { IssueBadges } from "@/components/issue-badges";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatMoney, plural } from "@/lib/format";
import { sortReviewQueue } from "@/lib/review-queue";

export default function ReviewQueuePage() {
  const router = useRouter();
  const queue = useQuery({
    queryKey: ["review-queue"],
    queryFn: () => api.invoices({ status: "needs_review", page_size: 100 }),
  });
  const items = useMemo(() => sortReviewQueue(queue.data?.items ?? []), [queue.data]);
  const total = queue.data?.total ?? 0;

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Review queue"
        description={
          queue.data
            ? total === 0
              ? "Nothing to review."
              : `${plural(total, "invoice")} need review${total > items.length ? `. Showing the first ${items.length}.` : "."}`
            : "Invoices that need a person to check them."
        }
      />
      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Invoice number</TableHead>
              <TableHead>Supplier</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead>Issues</TableHead>
              <TableHead>Document</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {queue.isLoading && <TableSkeleton columns={5} />}
            {items.map((inv) => (
              <TableRow key={inv.id} className="cursor-pointer" onClick={() => router.push(`/invoices/${inv.id}`)}>
                <TableCell className="font-medium">
                  <Link href={`/invoices/${inv.id}`} className="text-brand-navy hover:underline" onClick={(e) => e.stopPropagation()}>
                    {inv.invoice_number ?? "No number"}
                  </Link>
                </TableCell>
                <TableCell className="max-w-56 truncate">{inv.supplier_name ?? "—"}</TableCell>
                <TableCell className="text-right tabular-nums">{formatMoney(inv.total, inv.currency)}</TableCell>
                <TableCell><IssueBadges issueCount={inv.issue_count} errorCount={inv.error_count} /></TableCell>
                <TableCell className="max-w-56 truncate">
                  <Link href={`/documents/${inv.document_id}`} className="hover:underline" onClick={(e) => e.stopPropagation()}>
                    {inv.filename}
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {queue.isError && <ErrorState error={queue.error} onRetry={() => void queue.refetch()} />}
        {!queue.isLoading && !queue.isError && items.length === 0 && <EmptyState message="No invoices need review. Nice work." />}
      </Card>
    </div>
  );
}
