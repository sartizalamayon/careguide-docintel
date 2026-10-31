import { Plus, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fromCents, toCents } from "@/lib/format";
import { emptyLine, type LineDraft } from "@/lib/invoice-draft";
import { TONE_CLASS } from "@/lib/tone";

type Column = "description" | "quantity" | "unit_price" | "amount";

interface LineItemsEditorProps {
  lines: LineDraft[];
  subtotal: string;
  errors: Record<string, string>;
  onChange: (lines: LineDraft[]) => void;
}

function SumCheck({ lines, subtotal }: { lines: LineDraft[]; subtotal: string }) {
  const amounts = lines.map((l) => toCents(l.amount)).filter((c): c is number => c !== null);
  const sum = amounts.reduce((a, b) => a + b, 0);
  const sub = toCents(subtotal);
  let badge = <Badge className={TONE_CLASS.neutral}>No subtotal to compare</Badge>;
  if (sub !== null && sub === sum) badge = <Badge className={TONE_CLASS.success}>Matches subtotal</Badge>;
  else if (sub !== null) badge = <Badge className={TONE_CLASS.warning}>Differs from subtotal by {fromCents(Math.abs(sum - sub))}</Badge>;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t px-3 pt-3 text-sm">
      <span>
        Lines add up to <strong className="tabular-nums">{fromCents(sum)}</strong>
        {sub !== null && <span className="text-muted-foreground"> · subtotal {fromCents(sub)}</span>}
      </span>
      {badge}
    </div>
  );
}

export function LineItemsEditor({ lines, subtotal, errors, onChange }: LineItemsEditorProps) {
  const update = (key: number, column: Column, value: string) =>
    onChange(lines.map((l) => (l.key === key ? { ...l, [column]: value } : l)));
  const cell = (l: LineDraft, column: Column, label: string, className?: string) => (
    <Input
      aria-label={`${label}, line ${lines.indexOf(l) + 1}`}
      value={l[column]}
      aria-invalid={Boolean(errors[`${l.key}.${column}`])}
      title={errors[`${l.key}.${column}`]}
      className={className}
      onChange={(e) => update(l.key, column, e.target.value)}
    />
  );

  return (
    <div className="space-y-3">
      {lines.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Description</TableHead>
              <TableHead className="w-20">Qty</TableHead>
              <TableHead className="w-28">Unit price</TableHead>
              <TableHead className="w-28">Amount</TableHead>
              <TableHead className="w-10"><span className="sr-only">Remove</span></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {lines.map((l) => (
              <TableRow key={l.key}>
                <TableCell>{cell(l, "description", "Description")}</TableCell>
                <TableCell>{cell(l, "quantity", "Quantity", "text-right")}</TableCell>
                <TableCell>{cell(l, "unit_price", "Unit price", "text-right")}</TableCell>
                <TableCell>{cell(l, "amount", "Amount", "text-right")}</TableCell>
                <TableCell>
                  <Button variant="ghost" size="icon-sm" aria-label={`Remove line ${lines.indexOf(l) + 1}`} onClick={() => onChange(lines.filter((x) => x.key !== l.key))}>
                    <Trash2 />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {lines.length === 0 && <p className="px-1 text-sm text-muted-foreground">No line items.</p>}
      <div className="px-1">
        <Button variant="outline" size="sm" onClick={() => onChange([...lines, emptyLine()])}>
          <Plus /> Add line
        </Button>
      </div>
      {lines.length > 0 && <SumCheck lines={lines} subtotal={subtotal} />}
    </div>
  );
}
