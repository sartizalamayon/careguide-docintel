import { Badge } from "@/components/ui/badge";
import { plural } from "@/lib/format";
import { TONE_CLASS } from "@/lib/tone";

export function IssueBadges({ issueCount, errorCount }: { issueCount: number; errorCount: number }) {
  const warnings = issueCount - errorCount;
  if (issueCount === 0) return <span className="text-xs text-muted-foreground">None</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {errorCount > 0 && <Badge className={TONE_CLASS.danger}>{plural(errorCount, "error")}</Badge>}
      {warnings > 0 && <Badge className={TONE_CLASS.warning}>{plural(warnings, "warning")}</Badge>}
    </div>
  );
}
