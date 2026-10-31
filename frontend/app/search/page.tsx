"use client";

import { Suspense, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Pagination } from "@/components/pagination";
import { ResultCard } from "@/components/search/result-card";
import { EMPTY_FILTERS, SearchFilters, type SearchFilterValues } from "@/components/search/search-filters";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type SearchParams } from "@/lib/api";
import { plural } from "@/lib/format";
import type { SearchMode } from "@/lib/types";

const PAGE_SIZE = 20;

interface Submitted {
  q: string;
  mode: SearchMode;
  filters: SearchFilterValues;
  page: number;
}

function toParams({ q, mode, filters: f, page }: Submitted): SearchParams {
  return {
    q: q.trim() || undefined,
    mode,
    status: f.status === "all" ? undefined : f.status,
    currency: f.currency.trim().toUpperCase() || undefined,
    supplier: f.supplier.trim() || undefined,
    date_from: f.date_from || undefined,
    date_to: f.date_to || undefined,
    total_min: f.total_min.trim() || undefined,
    total_max: f.total_max.trim() || undefined,
    has_issues: f.has_issues || undefined,
    page,
    page_size: PAGE_SIZE,
  };
}

const MODES: SearchMode[] = ["hybrid", "keyword", "semantic"];

export default function SearchPage() {
  return (
    <Suspense>
      <SearchView />
    </Suspense>
  );
}

/** The query and mode live in the URL (?q=&mode=), so a search can be bookmarked or shared. */
function SearchView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const initialQ = params.get("q") ?? "";
  const initialMode = MODES.find((m) => m === params.get("mode")) ?? "hybrid";
  const [q, setQ] = useState(initialQ);
  const [mode, setMode] = useState<SearchMode>(initialMode);
  const [filters, setFilters] = useState<SearchFilterValues>(EMPTY_FILTERS);
  const [submitted, setSubmitted] = useState<Submitted>({ q: initialQ, mode: initialMode, filters: EMPTY_FILTERS, page: 1 });

  const syncUrl = (nextQ: string, nextMode: SearchMode) => {
    const next = new URLSearchParams();
    if (nextQ.trim()) next.set("q", nextQ.trim());
    if (nextMode !== "hybrid") next.set("mode", nextMode);
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };

  const results = useQuery({
    queryKey: ["search", submitted],
    queryFn: () => api.search(toParams(submitted)),
    placeholderData: (previous) => previous,
  });

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault();
    setSubmitted({ q, mode, filters, page: 1 });
    syncUrl(q, mode);
  };

  const clear = () => {
    setQ("");
    setFilters(EMPTY_FILTERS);
    setSubmitted({ q: "", mode, filters: EMPTY_FILTERS, page: 1 });
    syncUrl("", mode);
  };

  const hits = results.data?.items ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <PageHeader title="Search" description="Find invoices by number, supplier, content or meaning." />

      <Card className="px-4">
        <form onSubmit={submit} className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <div className="relative min-w-64 flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                aria-label="Search query"
                placeholder="Invoice number, supplier or words from the invoice"
                value={q}
                className="h-9 pl-8"
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
            <Tabs value={mode} onValueChange={(v) => setMode(v as SearchMode)}>
              <TabsList aria-label="Search mode">
                <TabsTrigger value="hybrid">Hybrid</TabsTrigger>
                <TabsTrigger value="keyword">Keyword</TabsTrigger>
                <TabsTrigger value="semantic">Semantic</TabsTrigger>
              </TabsList>
            </Tabs>
            <Button type="submit" size="lg">Search</Button>
            <Button type="button" variant="outline" size="lg" onClick={clear}>Clear</Button>
          </div>
          <SearchFilters values={filters} onChange={setFilters} />
        </form>
      </Card>

      {results.isLoading && <ListSkeleton rows={4} />}
      {results.isError && <Card><ErrorState error={results.error} onRetry={() => void results.refetch()} /></Card>}
      {results.data && (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{plural(results.data.total, "invoice")} found</p>
          {hits.length === 0 ? (
            <Card><EmptyState message="No invoices match. Try fewer filters or different words." /></Card>
          ) : (
            hits.map((hit) => <ResultCard key={hit.id} hit={hit} />)
          )}
          <Pagination
            page={submitted.page}
            pageSize={PAGE_SIZE}
            total={results.data.total}
            onPageChange={(page) => setSubmitted({ ...submitted, page })}
          />
        </div>
      )}
    </div>
  );
}
