"use client";

import { useState } from "react";
import { useMutation, useQueries } from "@tanstack/react-query";
import { GitCompareArrows } from "lucide-react";
import { toast } from "sonner";
import { DocumentPicker } from "@/components/compare/document-picker";
import { CompareResult } from "@/components/compare/result";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, errorMessage } from "@/lib/api";
import type { DocStatus } from "@/lib/types";

const READY: DocStatus[] = ["completed", "needs_review"];

export default function ComparePage() {
  const [a, setA] = useState("");
  const [b, setB] = useState("");

  const lists = useQueries({
    queries: READY.map((status) => ({
      queryKey: ["documents", "ready", status],
      queryFn: () => api.documents({ status, page_size: 100 }),
    })),
  });
  const loading = lists.some((l) => l.isLoading);
  const documents = lists.flatMap((l) => l.data?.items ?? []).sort((x, y) => y.created_at.localeCompare(x.created_at));

  const compare = useMutation({
    mutationFn: () => api.crossCheck(a, b),
    onSuccess: (res) => {
      const { mismatched, only_in_a, only_in_b } = res.summary.counts;
      toast.success(mismatched + only_in_a + only_in_b === 0 ? "The documents agree" : "Comparison ready");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const sameDocument = a !== "" && a === b;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <PageHeader title="Cross-check" description="Compare two documents invoice by invoice." />
      <Card className="px-4">
        <div className="flex flex-wrap items-end gap-4">
          <DocumentPicker id="doc-a" label="Document A" documents={documents} value={a} loading={loading} onChange={setA} />
          <DocumentPicker id="doc-b" label="Document B" documents={documents} value={b} loading={loading} onChange={setB} />
          <Button size="lg" disabled={!a || !b || sameDocument || compare.isPending} onClick={() => compare.mutate()}>
            <GitCompareArrows /> Compare
          </Button>
        </div>
        {sameDocument && <p className="text-xs text-destructive">Pick two different documents.</p>}
      </Card>
      {compare.data && <CompareResult result={compare.data} />}
    </div>
  );
}
