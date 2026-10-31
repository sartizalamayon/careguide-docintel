"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileStack, GitCompareArrows, LayoutDashboard, ListChecks, Search } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", icon: FileStack },
  { href: "/review", label: "Review queue", icon: ListChecks },
  { href: "/search", label: "Search", icon: Search },
  { href: "/compare", label: "Cross-check", icon: GitCompareArrows },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground lg:flex">
        <div className="px-5 py-6">
          <div className="font-heading text-xl font-semibold text-white">
            Doc<span className="text-brand-orange">Intel</span>
          </div>
          <div className="mt-0.5 text-xs text-sidebar-foreground/70">for Care Guide</div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  active ? "bg-sidebar-accent font-medium text-white" : "hover:bg-sidebar-accent/60",
                )}
              >
                <Icon className={cn("size-4", active && "text-brand-orange")} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="px-5 py-4 text-xs text-sidebar-foreground/60">Invoices · Receipts · Spreadsheets</div>
      </aside>
      <main className="min-w-0 flex-1 px-6 py-6 lg:px-10">{children}</main>
    </div>
  );
}
