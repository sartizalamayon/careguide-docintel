"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleAlert, FileStack, FileText, Hourglass, Loader2, ShieldCheck, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { StatCard } from "@/components/stat-card";
import { BatchList } from "@/components/upload/batch-list";
import { Dropzone } from "@/components/upload/dropzone";
import { api, errorMessage } from "@/lib/api";
import { plural } from "@/lib/format";
import type { RejectedFile, UploadResponse } from "@/lib/types";

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const [batch, setBatch] = useState<UploadResponse | null>(null);
  const [clientRejected, setClientRejected] = useState<RejectedFile[]>([]);

  const stats = useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
    refetchInterval: (q) => {
      const d = q.state.data?.documents;
      return d && d.queued + d.processing > 0 ? 2000 : false;
    },
  });

  const upload = useMutation({
    mutationFn: api.upload,
    onSuccess: (res) => {
      setBatch(res);
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      if (res.documents.length) toast.success(`${plural(res.documents.length, "file")} uploaded`);
      else toast.error("No files were accepted.");
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const handleFiles = (files: File[], rejected: RejectedFile[]) => {
    setClientRejected(rejected);
    if (rejected.length) toast.error(`${plural(rejected.length, "file")} skipped`);
    if (files.length) {
      setBatch(null);
      upload.mutate(files);
    }
  };

  const d = stats.data?.documents;
  const i = stats.data?.invoices;
  const needsReview = i?.needs_review ?? 0;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader title="Dashboard" description="Upload invoices, receipts and spreadsheets to extract and check their data." />

      {needsReview > 0 && (
        <Link
          href="/review"
          className="flex items-center gap-2 rounded-lg bg-warning/10 px-4 py-3 text-sm font-medium text-[#A85A05] hover:bg-warning/15"
        >
          <TriangleAlert className="size-4" />
          {plural(needsReview, "invoice")} need review
        </Link>
      )}

      <section aria-label="Documents" className="space-y-2">
        <h2 className="font-heading text-sm font-medium">Documents</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <StatCard label="Total" value={d?.total} icon={FileStack} href="/documents" />
          <StatCard label="Queued" value={d?.queued} icon={Hourglass} />
          <StatCard label="Processing" value={d?.processing} icon={Loader2} tone="info" />
          <StatCard label="Completed" value={d?.completed} icon={CheckCircle2} tone="success" />
          <StatCard label="Needs review" value={d?.needs_review} icon={TriangleAlert} tone="warning" />
          <StatCard label="Failed" value={d?.failed} icon={CircleAlert} tone="danger" />
        </div>
      </section>

      <section aria-label="Invoices" className="space-y-2">
        <h2 className="font-heading text-sm font-medium">Invoices</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard label="Total" value={i?.total} icon={FileText} href="/search" />
          <StatCard label="OK" value={i?.ok} icon={CheckCircle2} tone="success" />
          <StatCard label="Needs review" value={i?.needs_review} icon={TriangleAlert} tone="warning" href="/review" />
          <StatCard label="Approved" value={i?.approved} icon={ShieldCheck} tone="success" />
        </div>
      </section>

      <Dropzone uploading={upload.isPending} onFiles={handleFiles} />
      <BatchList batch={batch} clientRejected={clientRejected} />
    </div>
  );
}
