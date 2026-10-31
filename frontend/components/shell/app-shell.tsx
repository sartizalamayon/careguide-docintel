"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileStack, GitCompareArrows, LayoutDashboard, ListChecks, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { AccountMenu } from "./account-menu";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", icon: FileStack },
  { href: "/review", label: "Review queue", icon: ListChecks },
  { href: "/search", label: "Search", icon: Search },
  { href: "/compare", label: "Cross-check", icon: GitCompareArrows },
];

function isActive(href: string, pathname: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function MobileNav({ pathname }: { pathname: string }) {
  return (
    <header className="flex items-center gap-4 bg-sidebar px-4 py-3 text-sidebar-foreground lg:hidden">
      <div className="font-heading text-lg font-semibold text-white">
        Doc<span className="text-brand-orange">Intel</span>
      </div>
      <nav className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex shrink-0 items-center gap-2 rounded-md px-3 py-1.5 text-sm",
              isActive(href, pathname) ? "bg-sidebar-accent font-medium text-white" : "hover:bg-sidebar-accent/60",
            )}
          >
            <Icon className="size-4" />
            {label}
          </Link>
        ))}
      </nav>
      <AccountMenu compact />
    </header>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <MobileNav pathname={pathname} />
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground lg:flex">
        <div className="px-5 py-6">
          <div className="font-heading text-xl font-semibold text-white">
            Doc<span className="text-brand-orange">Intel</span>
          </div>
          <div className="mt-0.5 text-xs text-sidebar-foreground/70">for Care Guide</div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = isActive(href, pathname);
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
        <div className="border-t border-sidebar-border/60 p-3">
          <AccountMenu />
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-6 py-6 lg:px-10">{children}</main>
    </div>
  );
}
