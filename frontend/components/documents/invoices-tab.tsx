import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { IssueBadges } from "@/components/issue-badges";
import { EmptyState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatMoney } from "@/lib/format";
import type { InvoiceSummary } from "@/lib/types";

export function InvoicesTab({ invoices }: { invoices: InvoiceSummary[] }) {
  if (invoices.length === 0) return <Card><EmptyState message="No invoices were found in this document yet." /></Card>;
  return (
    <Card className="py-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>#</TableHead>
            <TableHead>Invoice number</TableHead>
            <TableHead>Supplier</TableHead>
            <TableHead>Date</TableHead>
            <TableHead className="text-right">Total</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Issues</TableHead>
            <TableHead className="text-right">Review</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {invoices.map((inv) => (
            <TableRow key={inv.id}>
              <TableCell>{inv.seq}</TableCell>
              <TableCell className="font-medium">
                <Link href={`/invoices/${inv.id}`} className="text-brand-navy hover:underline">
                  {inv.invoice_number ?? "No number"}
                </Link>
              </TableCell>
              <TableCell className="max-w-56 truncate">{inv.supplier_name ?? "—"}</TableCell>
              <TableCell>{formatDate(inv.invoice_date)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatMoney(inv.total, inv.currency)}</TableCell>
              <TableCell><StatusBadge status={inv.status} /></TableCell>
              <TableCell><IssueBadges issueCount={inv.issue_count} errorCount={inv.error_count} /></TableCell>
              <TableCell className="text-right">
                <Button variant="ghost" size="sm" asChild>
                  <Link href={`/invoices/${inv.id}`}>Open <ArrowRight /></Link>
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
