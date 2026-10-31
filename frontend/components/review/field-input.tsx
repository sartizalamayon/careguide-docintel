import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfidenceChip } from "@/components/review/confidence-chip";
import { FIELD_LABEL } from "@/lib/invoice-draft";
import type { FieldName, FieldValue, Issue } from "@/lib/types";

interface FieldInputProps {
  name: FieldName;
  value: string;
  meta: FieldValue | undefined;
  issues: Issue[];
  error: string | undefined;
  onChange: (value: string) => void;
}

export function FieldInput({ name, value, meta, issues, error, onChange }: FieldInputProps) {
  const messages = error ? [error] : issues.map((i) => i.message);
  return (
    <div className="grid gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={`field-${name}`}>{FIELD_LABEL[name]}</Label>
        <ConfidenceChip meta={meta} />
      </div>
      <Input
        id={`field-${name}`}
        value={value}
        placeholder={name === "invoice_date" ? "YYYY-MM-DD" : undefined}
        aria-invalid={messages.length > 0}
        onChange={(e) => onChange(e.target.value)}
      />
      {messages.map((m, i) => <p key={i} className="text-xs text-destructive">{m}</p>)}
    </div>
  );
}
