import Link from "next/link";
import { Card } from "@/components/ui/card";
import { TONE_CLASS, type Tone } from "@/lib/tone";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: number | undefined;
  icon: LucideIcon;
  tone?: Tone;
  href?: string;
}

export function StatCard({ label, value, icon: Icon, tone = "neutral", href }: StatCardProps) {
  const body = (
    <Card className="flex-row items-center gap-3 px-4 transition-shadow hover:shadow-sm">
      <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg", TONE_CLASS[tone])}>
        <Icon className="size-4" />
      </span>
      <div className="min-w-0">
        <div className="font-heading text-2xl leading-none font-semibold text-brand-navy">{value ?? "–"}</div>
        <div className="mt-1 truncate text-xs text-muted-foreground">{label}</div>
      </div>
    </Card>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}
