import Link from "next/link";
import { CheckCircle2, CircleAlert, FileMinus, FilePlus } from "lucide-react";
import { EmptyState } from "@/components/states";
import { StatCard } from "@/components/stat-card";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { humanize } from "@/lib/format";
import type { CrossCheck } from "@/lib/types";

const invoiceLink = (id: string, text: string) => (
  <Link href={`/invoices/${id}`} className="text-brand-navy hover:underline">{text}</Link>
);

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <Card className="py-0">
      <CardHeader className="pt-4">
        <CardTitle>{title} ({count})</CardTitle>
      </CardHeader>
      {count === 0 ? <EmptyState message="Nothing here." /> : children}
    </Card>
  );
}

function OnlyTable({ rows }: { rows: { invoice_number: string; invoice_id: string }[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow><TableHead>Invoice number</TableHead></TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.invoice_id}>
            <TableCell className="font-medium">{invoiceLink(r.invoice_id, r.invoice_number)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function CompareResult({ result }: { result: CrossCheck }) {
  const { counts, matched, mismatched, only_in_a, only_in_b } = result.summary;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Matched" value={counts.matched} icon={CheckCircle2} tone="success" />
        <StatCard label="Mismatched" value={counts.mismatched} icon={CircleAlert} tone="warning" />
        <StatCard label="Only in A" value={counts.only_in_a} icon={FileMinus} tone="info" />
        <StatCard label="Only in B" value={counts.only_in_b} icon={FilePlus} tone="info" />
      </div>

      <Section title="Matched" count={matched.length}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Invoice number</TableHead>
              <TableHead>In A</TableHead>
              <TableHead>In B</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {matched.map((m) => (
              <TableRow key={`${m.a_invoice_id}-${m.b_invoice_id}`}>
                <TableCell className="font-medium">{m.invoice_number}</TableCell>
                <TableCell>{invoiceLink(m.a_invoice_id, "Open")}</TableCell>
                <TableCell>{invoiceLink(m.b_invoice_id, "Open")}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      <Section title="Mismatched" count={mismatched.length}>
        <div className="divide-y">
          {mismatched.map((m) => (
            <div key={`${m.a_invoice_id}-${m.b_invoice_id}`} className="space-y-2 px-4 py-4">
              <div className="flex items-center gap-4 text-sm">
                <span className="font-medium">{m.invoice_number}</span>
                {invoiceLink(m.a_invoice_id, "Open A")}
                {invoiceLink(m.b_invoice_id, "Open B")}
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Field</TableHead>
                    <TableHead>A</TableHead>
                    <TableHead>B</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {m.differences.map((d) => (
                    <TableRow key={d.field}>
                      <TableCell>{humanize(d.field)}</TableCell>
                      <TableCell className="tabular-nums text-destructive">{String(d.a ?? "—")}</TableCell>
                      <TableCell className="tabular-nums text-destructive">{String(d.b ?? "—")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Only in A" count={only_in_a.length}><OnlyTable rows={only_in_a} /></Section>
      <Section title="Only in B" count={only_in_b.length}><OnlyTable rows={only_in_b} /></Section>
    </div>
  );
}
