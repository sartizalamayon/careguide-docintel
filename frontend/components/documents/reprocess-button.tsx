"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api, errorMessage } from "@/lib/api";

export function useReprocess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.reprocess(id),
    onSuccess: (doc) => {
      toast.success(`${doc.filename} queued again`);
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["document", doc.id] });
      void queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}

export function ReprocessButton({ id, size = "sm" }: { id: string; size?: "sm" | "default" }) {
  const reprocess = useReprocess();
  return (
    <Button variant="outline" size={size} disabled={reprocess.isPending} onClick={() => reprocess.mutate(id)}>
      <RotateCw className={reprocess.isPending ? "animate-spin" : undefined} /> Reprocess
    </Button>
  );
}
