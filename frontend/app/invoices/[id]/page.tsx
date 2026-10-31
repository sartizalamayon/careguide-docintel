"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ErrorState, ListSkeleton } from "@/components/states";
import { ReviewView } from "@/components/review/review-view";
import { api } from "@/lib/api";

export default function InvoiceReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [version, setVersion] = useState(0);
  const invoice = useQuery({ queryKey: ["invoice", id], queryFn: () => api.invoice(id) });

  if (invoice.isLoading) return <div className="mx-auto max-w-7xl"><ListSkeleton rows={3} className="h-40" /></div>;
  if (invoice.isError || !invoice.data) return <ErrorState error={invoice.error} onRetry={() => void invoice.refetch()} />;

  return <ReviewView key={`${id}:${version}`} invoice={invoice.data} onUpdated={() => setVersion((v) => v + 1)} />;
}
