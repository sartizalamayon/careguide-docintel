"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, ChevronLeft, ChevronRight, Save } from "lucide-react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ActionDialog, type ReviewAction } from "@/components/review/action-dialog";
import { CorrectionsList } from "@/components/review/corrections-list";
import { FieldInput } from "@/components/review/field-input";
import { IssuesPanel } from "@/components/review/issues-panel";
import { LineItemsEditor } from "@/components/review/line-items-editor";
import { SourcePane } from "@/components/review/source-pane";
import { useReviewer } from "@/components/review/use-reviewer";
import { api, errorMessage } from "@/lib/api";
import { buildPatch, hasErrors, isDirty, toDraft, validate, type Draft } from "@/lib/invoice-draft";
import { sortReviewQueue } from "@/lib/review-queue";
import { FIELD_NAMES, type InvoiceDetail } from "@/lib/types";

interface ReviewViewProps {
  invoice: InvoiceDetail;
  onUpdated: () => void;
}

function useQueueNeighbours(currentId: string) {
  const queue = useQuery({
    queryKey: ["review-queue"],
    queryFn: () => api.invoices({ status: "needs_review", page_size: 100 }),
  });
  const items = useMemo(() => sortReviewQueue(queue.data?.items ?? []), [queue.data]);
  const index = items.findIndex((i) => i.id === currentId);
  return {
    position: index >= 0 ? `${index + 1} of ${items.length}` : `${items.length} in queue`,
    prevId: index > 0 ? items[index - 1].id : null,
    nextId: index >= 0 ? items[index + 1]?.id ?? null : items[0]?.id ?? null,
  };
}

export function ReviewView({ invoice, onUpdated }: ReviewViewProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [reviewer, rememberReviewer] = useReviewer();
  const initial = useMemo(() => toDraft(invoice), [invoice]);
  const [draft, setDraft] = useState<Draft>(initial);
  const [action, setAction] = useState<ReviewAction | null>(null);
  const { position, prevId, nextId } = useQueueNeighbours(invoice.id);

  const dirty = isDirty(initial, draft);
  const errors = useMemo(() => validate(draft), [draft]);

  const refreshLists = () => {
    for (const key of ["review-queue", "stats", "documents", "invoices"]) void queryClient.invalidateQueries({ queryKey: [key] });
    void queryClient.invalidateQueries({ queryKey: ["document", invoice.document_id] });
  };

  const finish = (updated: InvoiceDetail) => {
    queryClient.setQueryData(["invoice", invoice.id], updated);
    refreshLists();
    setAction(null);
  };

  const save = useMutation({
    mutationFn: (v: { reviewer: string; note: string }) => api.correct(invoice.id, buildPatch(initial, draft, v.reviewer, v.note)),
    onSuccess: (updated) => {
      toast.success("Corrections saved");
      finish(updated);
      onUpdated();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const approve = useMutation({
    mutationFn: (v: { reviewer: string; note: string }) => api.approve(invoice.id, { reviewer: v.reviewer, note: v.note || undefined }),
    onSuccess: (updated) => {
      toast.success("Invoice approved");
      finish(updated);
      if (nextId) router.push(`/invoices/${nextId}`);
      else onUpdated();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const requestSave = () => {
    if (action) return;
    if (!dirty) toast.info("No changes to save");
    else if (hasErrors(errors)) toast.error("Fix the highlighted fields first");
    else setAction("save");
  };

  const saveShortcut = useRef(requestSave);
  useEffect(() => {
    saveShortcut.current = requestSave;
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        saveShortcut.current();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const confirm = (name: string, note: string) => {
    rememberReviewer(name);
    if (action === "save") save.mutate({ reviewer: name, note });
    else approve.mutate({ reviewer: name, note });
  };

  const setField = (name: (typeof FIELD_NAMES)[number], value: string) =>
    setDraft((d) => ({ ...d, fields: { ...d.fields, [name]: value } }));

  const approved = invoice.status === "approved";

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/review"><ArrowLeft /> Review queue</Link>
        </Button>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">{position}</span>
          <Button variant="outline" size="sm" disabled={!prevId} onClick={() => prevId && router.push(`/invoices/${prevId}`)}>
            <ChevronLeft /> Previous
          </Button>
          <Button variant="outline" size="sm" disabled={!nextId} onClick={() => nextId && router.push(`/invoices/${nextId}`)}>
            Next <ChevronRight />
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="font-heading text-2xl font-semibold">{invoice.invoice_number ?? "Invoice without a number"}</h1>
            <StatusBadge status={invoice.status} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            From <Link href={`/documents/${invoice.document_id}`} className="text-brand-navy hover:underline">{invoice.filename}</Link>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant={dirty ? "default" : "outline"} disabled={!dirty || save.isPending} onClick={requestSave}>
            <Save /> Save corrections
          </Button>
          <Button variant={dirty ? "outline" : "default"} disabled={approved || dirty || approve.isPending} onClick={() => setAction("approve")}>
            <Check /> {approved ? "Approved" : "Approve"}
          </Button>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto">
          <SourcePane invoice={invoice} />
        </div>
        <div className="space-y-5">
          <Card>
            <CardHeader><CardTitle>Invoice fields</CardTitle></CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              {FIELD_NAMES.map((name) => (
                <FieldInput
                  key={name}
                  name={name}
                  value={draft.fields[name]}
                  meta={invoice.fields[name]}
                  issues={invoice.issues.filter((i) => i.field === name)}
                  error={errors.fields[name]}
                  onChange={(v) => setField(name, v)}
                />
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Line items</CardTitle></CardHeader>
            <CardContent>
              <LineItemsEditor
                lines={draft.lines}
                subtotal={draft.fields.subtotal}
                errors={errors.lines}
                onChange={(lines) => setDraft((d) => ({ ...d, lines }))}
              />
            </CardContent>
          </Card>
          <IssuesPanel issues={invoice.issues} />
          <CorrectionsList corrections={invoice.corrections} />
        </div>
      </div>

      <ActionDialog action={action} reviewer={reviewer} pending={save.isPending || approve.isPending} onConfirm={confirm} onClose={() => setAction(null)} />
    </div>
  );
}
