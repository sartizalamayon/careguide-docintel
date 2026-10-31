import { CircleAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FIELD_LABEL } from "@/lib/invoice-draft";
import { humanize } from "@/lib/format";
import type { FieldName, Issue } from "@/lib/types";

export const sortIssues = (issues: Issue[]): Issue[] =>
  [...issues].sort((a, b) => Number(b.severity === "error") - Number(a.severity === "error"));

export function IssuesPanel({ issues }: { issues: Issue[] }) {
  const sorted = sortIssues(issues);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Issues ({issues.length})</CardTitle>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <ShieldCheck className="size-4 text-success" /> No issues found.
          </p>
        ) : (
          <ul className="space-y-3">
            {sorted.map((issue, i) => {
              const isError = issue.severity === "error";
              const Icon = isError ? CircleAlert : TriangleAlert;
              return (
                <li key={`${issue.code}-${i}`} className="flex gap-2.5 text-sm">
                  <Icon className={`mt-0.5 size-4 shrink-0 ${isError ? "text-destructive" : "text-warning"}`} />
                  <div className="min-w-0 space-y-0.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs font-medium">{issue.code}</span>
                      {issue.field && (
                        <Badge variant="outline">{FIELD_LABEL[issue.field as FieldName] ?? humanize(issue.field)}</Badge>
                      )}
                    </div>
                    <p className="text-muted-foreground">{issue.message}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
