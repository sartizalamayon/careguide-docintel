"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getProviders, signIn, signOut, useSession } from "next-auth/react";
import { ChevronsUpDown, Cpu, KeyRound, LogOut } from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { LLM_KEY_QUERY, LlmKeyDialog } from "./llm-key-dialog";

function GoogleMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" aria-hidden className={className}>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

function Avatar({ name, image }: { name: string; image?: string | null }) {
  const initials = name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  return image ? (
    // eslint-disable-next-line @next/next/no-img-element -- Google avatar URL, no Next image config needed
    <img src={image} alt="" referrerPolicy="no-referrer" className="size-8 shrink-0 rounded-full" />
  ) : (
    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-orange text-xs font-semibold text-white">
      {initials || "?"}
    </span>
  );
}

function useGoogleAvailable(): boolean | null {
  const [available, setAvailable] = useState<boolean | null>(null);
  useEffect(() => {
    getProviders()
      .then((p) => setAvailable(Boolean(p?.google)))
      .catch(() => setAvailable(false));
  }, []);
  return available;
}

/** Bottom of the sidebar: Google sign-in, then the user's name, the model in use and the Groq key dialog. */
export function AccountMenu({ compact = false }: { compact?: boolean }) {
  const { data: session, status } = useSession();
  const google = useGoogleAvailable();
  const [keyOpen, setKeyOpen] = useState(false);
  const signedIn = status === "authenticated";
  const llm = useQuery({ queryKey: LLM_KEY_QUERY, queryFn: api.llmKey, enabled: signedIn });

  if (status === "loading" || (status === "unauthenticated" && google === null)) {
    return compact ? null : <Skeleton className="h-10 w-full bg-sidebar-accent/60" />;
  }

  if (!signedIn) {
    const button = (
      <button
        type="button"
        disabled={!google}
        onClick={() => signIn("google")}
        className={cn(
          "flex w-full items-center justify-center gap-2 rounded-md bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition",
          "hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50",
          compact && "w-auto shrink-0 px-2.5 py-1.5 text-xs",
        )}
      >
        <GoogleMark className="size-4" /> {compact ? "Sign in" : "Sign in with Google"}
      </button>
    );
    if (google) return button;
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={cn("block", compact && "shrink-0")}>{button}</span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-60">
          Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET for the web app.
        </TooltipContent>
      </Tooltip>
    );
  }

  const user = session.user ?? {};
  const name = user.name || user.email || "Signed in";
  const own = llm.data?.key;
  const modelLine = llm.isLoading ? "…" : own ? "Your Groq key" : "Server model";
  const modelName = own?.model ?? llm.data?.server_model;

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          className={cn(
            "flex w-full items-center gap-2.5 rounded-md p-2 text-left transition-colors hover:bg-sidebar-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-orange/60 data-[state=open]:bg-sidebar-accent",
            compact && "w-auto shrink-0 p-1",
          )}
        >
          <Avatar name={name} image={user.image} />
          {!compact && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-white">{name}</span>
                <span className="flex items-center gap-1 truncate text-xs text-sidebar-foreground/70">
                  <Cpu className={cn("size-3 shrink-0", own && "text-brand-orange")} /> {modelLine}
                </span>
              </span>
              <ChevronsUpDown className="size-4 shrink-0 text-sidebar-foreground/60" />
            </>
          )}
        </DropdownMenuTrigger>
        <DropdownMenuContent side={compact ? "bottom" : "top"} align={compact ? "end" : "start"} className="w-64">
          <DropdownMenuLabel className="font-normal">
            <div className="truncate text-sm font-medium">{name}</div>
            <div className="truncate text-xs text-muted-foreground">{user.email}</div>
            {modelName && (
              <div className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
                <Cpu className="mt-0.5 size-3 shrink-0" />
                <span className="min-w-0">
                  {own ? "Your Groq key" : "Server model"}
                  <code className="block break-all text-foreground/80">{modelName}</code>
                </span>
              </div>
            )}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setKeyOpen(true)}>
            <KeyRound /> {own ? "Manage Groq API key" : "Add your Groq API key"}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => signOut()}>
            <LogOut /> Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <LlmKeyDialog open={keyOpen} onOpenChange={setKeyOpen} />
    </>
  );
}
