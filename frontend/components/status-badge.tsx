import { CheckCircle2, CircleAlert, Clock, Loader2, ShieldCheck, TriangleAlert, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { humanize } from "@/lib/format";
import { TONE_CLASS, type Tone } from "@/lib/tone";
import type { DocStatus, InvoiceStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS: Record<DocStatus | InvoiceStatus, { tone: Tone; icon: LucideIcon; label: string }> = {
  queued: { tone: "neutral", icon: Clock, label: "Queued" },
  processing: { tone: "info", icon: Loader2, label: "Processing" },
  completed: { tone: "success", icon: CheckCircle2, label: "Completed" },
  needs_review: { tone: "warning", icon: TriangleAlert, label: "Needs review" },
  failed: { tone: "danger", icon: CircleAlert, label: "Failed" },
  ok: { tone: "success", icon: CheckCircle2, label: "OK" },
  approved: { tone: "success", icon: ShieldCheck, label: "Approved" },
};

export function StatusBadge({ status, className }: { status: DocStatus | InvoiceStatus; className?: string }) {
  const { tone, icon: Icon, label } = STATUS[status] ?? { tone: "neutral", icon: Clock, label: humanize(status) };
  return (
    <Badge className={cn(TONE_CLASS[tone], className)}>
      <Icon className={cn(status === "processing" && "animate-spin")} />
      {label}
    </Badge>
  );
}
