import { ArrowRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FIELD_LABEL } from "@/lib/invoice-draft";
import { formatDateTime, humanize } from "@/lib/format";
import type { Correction, FieldName } from "@/lib/types";

const show = (value: unknown): string => (value === null || value === undefined || value === "" ? "empty" : String(value));

export function CorrectionsList({ corrections }: { corrections: Correction[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Correction history</CardTitle>
      </CardHeader>
      <CardContent>
        {corrections.length === 0 ? (
          <p className="text-sm text-muted-foreground">No corrections yet.</p>
        ) : (
          <ul className="space-y-3">
            {corrections.map((c, i) => (
              <li key={`${c.created_at}-${c.field}-${i}`} className="space-y-0.5 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{FIELD_LABEL[c.field as FieldName] ?? humanize(c.field)}</span>
                  <span className="flex items-center gap-1.5 text-muted-foreground">
                    <span className="line-through">{show(c.old_value)}</span>
                    <ArrowRight className="size-3" />
                    <span className="text-foreground">{show(c.new_value)}</span>
                  </span>
                </div>
                <div className="text-xs text-muted-foreground">
                  {c.corrected_by} · {formatDateTime(c.created_at)}
                  {c.note && <> · {c.note}</>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
