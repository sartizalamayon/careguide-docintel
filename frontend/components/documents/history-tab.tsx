"use client";

import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/states";
import { api } from "@/lib/api";
import { formatDateTime, humanize } from "@/lib/format";

export function HistoryTab({ documentId, polling }: { documentId: string; polling: boolean }) {
  const events = useQuery({
    queryKey: ["document", documentId, "events"],
    queryFn: () => api.documentEvents(documentId),
    refetchInterval: polling ? 2000 : false,
  });

  if (events.isLoading) return <ListSkeleton rows={4} className="h-12" />;
  if (events.isError) return <Card><ErrorState error={events.error} onRetry={() => void events.refetch()} /></Card>;
  if (!events.data?.length) return <Card><EmptyState message="No processing events yet." /></Card>;

  return (
    <Card className="px-6">
      <ol className="relative space-y-5 border-l border-border pl-6">
        {events.data.map((e) => {
          const ms = e.data.ms;
          return (
            <li key={e.id} className="relative">
              <span className="absolute top-1.5 -left-[1.9rem] size-2.5 rounded-full bg-brand-navy ring-4 ring-card" />
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="font-medium text-brand-navy">
                  {humanize(e.stage ?? e.event)}
                  {e.stage && e.event !== e.stage && <span className="ml-2 text-xs font-normal text-muted-foreground">{humanize(e.event)}</span>}
                </div>
                <div className="text-xs text-muted-foreground">
                  {typeof ms === "number" && <span className="mr-3 font-mono">{ms} ms</span>}
                  {formatDateTime(e.created_at)}
                </div>
              </div>
              {e.message && <p className="mt-0.5 text-sm text-muted-foreground">{e.message}</p>}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
