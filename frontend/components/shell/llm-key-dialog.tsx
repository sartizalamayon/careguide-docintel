"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, KeyRound, Loader2, ShieldCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export const LLM_KEY_QUERY = ["llm-key"] as const;

export function LlmKeyDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: LLM_KEY_QUERY, queryFn: api.llmKey, enabled: open });
  const saved = status.data?.key ?? null;

  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [reveal, setReveal] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);

  useEffect(() => {
    if (!open) {
      setApiKey("");
      setReveal(false);
      setConfirmRemove(false);
    }
  }, [open]);

  useEffect(() => {
    if (status.data) setModel(status.data.key?.model ?? status.data.models[0] ?? "");
  }, [status.data]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: LLM_KEY_QUERY });

  const save = useMutation({
    mutationFn: () => (apiKey.trim() ? api.saveLlmKey(apiKey.trim(), model) : api.setLlmModel(model)),
    onSuccess: (key) => {
      toast.success(apiKey.trim() ? "Key checked with Groq and saved." : `Now using ${key.model}.`);
      setApiKey("");
      refresh();
    },
  });

  const remove = useMutation({
    mutationFn: api.removeLlmKey,
    onSuccess: () => {
      toast.success("Key removed. New uploads use the server model.");
      setConfirmRemove(false);
      refresh();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const modelChanged = saved !== null && model !== saved.model;
  const canSave = !save.isPending && model !== "" && (apiKey.trim().length >= 20 || modelChanged);
  const saveLabel = !saved ? "Check and save" : apiKey.trim() ? "Check and replace" : "Use this model";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="size-4 text-brand-orange" /> Your Groq API key
          </DialogTitle>
          <DialogDescription>
            Documents you upload while signed in are read with your own Groq key. If Groq is unavailable, the server
            model takes over.
          </DialogDescription>
        </DialogHeader>

        {status.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : status.isError ? (
          <p className="text-sm text-destructive">{errorMessage(status.error)}</p>
        ) : saved ? (
          <div className="rounded-lg border bg-muted/40 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-sm font-medium">
                  <ShieldCheck className="size-4 text-success" /> Key saved
                  <code className="rounded bg-background px-1.5 py-0.5 text-xs">{saved.key_hint}</code>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {saved.model} · updated {formatDateTime(saved.updated_at)}
                </div>
              </div>
              {confirmRemove ? (
                <div className="flex shrink-0 gap-1">
                  <Button size="sm" variant="ghost" onClick={() => setConfirmRemove(false)}>Keep</Button>
                  <Button size="sm" variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>
                    {remove.isPending && <Loader2 className="animate-spin" />} Remove
                  </Button>
                </div>
              ) : (
                <Button size="sm" variant="ghost" className="shrink-0 text-muted-foreground" onClick={() => setConfirmRemove(true)}>
                  <Trash2 /> Remove
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
            No key saved. Your uploads use the server model{" "}
            <code className="whitespace-nowrap text-xs">{status.data?.server_model}</code>.
          </div>
        )}

        {status.data && (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (canSave) save.mutate();
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="groq-key">{saved ? "Replace the key (optional)" : "API key"}</Label>
              <div className="relative">
                <Input
                  id="groq-key"
                  type={reveal ? "text" : "password"}
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="gsk_…"
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    if (save.isError) save.reset();
                  }}
                  className="pr-9 font-mono text-sm"
                />
                <button
                  type="button"
                  aria-label={reveal ? "Hide key" : "Show key"}
                  onClick={() => setReveal((v) => !v)}
                  className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-muted-foreground hover:text-foreground"
                >
                  {reveal ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              {save.isError && <p className="text-xs font-medium text-destructive">{errorMessage(save.error)}</p>}
              <p className="text-xs text-muted-foreground">
                Free key at{" "}
                <a href="https://console.groq.com/keys" target="_blank" rel="noreferrer" className="underline underline-offset-2">
                  console.groq.com/keys
                </a>
                . It is checked with Groq, stored encrypted, and never shown again.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label>Model</Label>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose a model" />
                </SelectTrigger>
                <SelectContent>
                  {status.data.models.map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Close</Button>
              <Button type="submit" disabled={!canSave}>
                {save.isPending && <Loader2 className="animate-spin" />} {save.isPending ? "Checking with Groq…" : saveLabel}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
