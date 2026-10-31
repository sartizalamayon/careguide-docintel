import Link from "next/link";
import { IssueBadges } from "@/components/issue-badges";
import { Snippet } from "@/components/search/snippet";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { formatDate, formatMoney } from "@/lib/format";
import type { SearchHit } from "@/lib/types";

export function ResultCard({ hit }: { hit: SearchHit }) {
  return (
    <Card className="gap-2 px-4 transition-shadow hover:shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Link href={`/invoices/${hit.id}`} className="font-heading text-base font-medium text-brand-navy hover:underline">
            {hit.invoice_number ?? "No number"}
          </Link>
          <div className="text-sm text-muted-foreground">
            {hit.supplier_name ?? "Unknown supplier"} · {formatDate(hit.invoice_date)}
          </div>
        </div>
        <div className="text-right">
          <div className="font-medium tabular-nums">{formatMoney(hit.total, hit.currency)}</div>
          <div className="mt-1 flex justify-end gap-1.5">
            <StatusBadge status={hit.status} />
          </div>
        </div>
      </div>
      {hit.snippet && <Snippet text={hit.snippet} />}
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>Score {hit.score.toFixed(3)}</span>
        {hit.matched_by.map((m) => <Badge key={m} variant="outline">{m}</Badge>)}
        <IssueBadges issueCount={hit.issue_count} errorCount={hit.error_count} />
        <Link href={`/documents/${hit.document_id}`} className="ml-auto truncate hover:underline">{hit.filename}</Link>
      </div>
    </Card>
  );
}
