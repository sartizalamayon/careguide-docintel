"use client";

import Image from "next/image";
import { useState } from "react";
import { ImageOff } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function PageImage({ src, alt, className }: { src: string; alt: string; className?: string }) {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  if (state === "error") {
    return (
      <div className={cn("flex aspect-[3/4] items-center justify-center gap-2 rounded-md bg-muted text-xs text-muted-foreground", className)}>
        <ImageOff className="size-4" /> Preview unavailable
      </div>
    );
  }
  return (
    <div className={cn("relative", className)}>
      {state === "loading" && <Skeleton className="absolute inset-0 aspect-[3/4] w-full" />}
      <Image
        src={src}
        alt={alt}
        width={0}
        height={0}
        sizes="100vw"
        unoptimized
        onLoad={() => setState("ready")}
        onError={() => setState("error")}
        className={cn("h-auto w-full rounded-md bg-white ring-1 ring-foreground/10", state === "loading" && "invisible")}
      />
    </div>
  );
}
