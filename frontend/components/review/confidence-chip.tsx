import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { TONE_CLASS, type Tone } from "@/lib/tone";
import type { FieldValue } from "@/lib/types";

export function fieldTone(meta: FieldValue): Tone {
  if (!meta.grounded || meta.confidence < 0.6) return "danger";
  return meta.confidence >= 0.9 ? "success" : "warning";
}

export function ConfidenceChip({ meta }: { meta: FieldValue | undefined }) {
  if (!meta) return null;
  const label = meta.source === "manual" ? "Manual" : `${Math.round(meta.confidence * 100)}%`;
  const detail = meta.grounded ? `Found in the text. Source: ${meta.source}.` : `Not found in the document text. Source: ${meta.source}.`;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge className={TONE_CLASS[fieldTone(meta)]}>{label}</Badge>
      </TooltipTrigger>
      <TooltipContent>{detail}</TooltipContent>
    </Tooltip>
  );
}
