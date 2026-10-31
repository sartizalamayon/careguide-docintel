export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

/** Badge colour classes per tone. Orange is reserved for primary actions. */
export const TONE_CLASS: Record<Tone, string> = {
  success: "bg-success/15 text-[#0E7C69]",
  warning: "bg-warning/15 text-[#A85A05]",
  danger: "bg-destructive/10 text-destructive",
  info: "bg-brand-navy/10 text-brand-navy",
  neutral: "bg-muted text-muted-foreground",
};

export const TONE_BORDER: Record<Tone, string> = {
  success: "border-success/40",
  warning: "border-warning/40",
  danger: "border-destructive/40",
  info: "border-brand-navy/30",
  neutral: "border-border",
};
