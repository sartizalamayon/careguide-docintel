import { Checkbox } from "@/components/search/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { InvoiceStatus } from "@/lib/types";

export interface SearchFilterValues {
  status: InvoiceStatus | "all";
  currency: string;
  supplier: string;
  date_from: string;
  date_to: string;
  total_min: string;
  total_max: string;
  has_issues: boolean;
}

export const EMPTY_FILTERS: SearchFilterValues = {
  status: "all", currency: "", supplier: "", date_from: "", date_to: "", total_min: "", total_max: "", has_issues: false,
};

interface SearchFiltersProps {
  values: SearchFilterValues;
  onChange: (values: SearchFilterValues) => void;
}

export function SearchFilters({ values, onChange }: SearchFiltersProps) {
  const set = <K extends keyof SearchFilterValues>(key: K, value: SearchFilterValues[K]) => onChange({ ...values, [key]: value });
  const text = (key: "currency" | "supplier" | "date_from" | "date_to" | "total_min" | "total_max", label: string, props?: React.ComponentProps<typeof Input>) => (
    <div className="grid gap-1.5">
      <Label htmlFor={`filter-${key}`}>{label}</Label>
      <Input id={`filter-${key}`} value={values[key]} onChange={(e) => set(key, e.target.value)} {...props} />
    </div>
  );

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div className="grid gap-1.5">
        <Label htmlFor="filter-status">Status</Label>
        <Select value={values.status} onValueChange={(v) => set("status", v as SearchFilterValues["status"])}>
          <SelectTrigger id="filter-status" className="w-full"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any status</SelectItem>
            <SelectItem value="ok">OK</SelectItem>
            <SelectItem value="needs_review">Needs review</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {text("currency", "Currency", { placeholder: "USD", maxLength: 3 })}
      {text("supplier", "Supplier", { placeholder: "Name contains" })}
      <div className="flex items-end pb-1.5">
        <Checkbox id="filter-has-issues" label="Only invoices with issues" checked={values.has_issues} onChange={(v) => set("has_issues", v)} />
      </div>
      {text("date_from", "Date from", { type: "date" })}
      {text("date_to", "Date to", { type: "date" })}
      {text("total_min", "Total from", { inputMode: "decimal", placeholder: "0.00" })}
      {text("total_max", "Total to", { inputMode: "decimal", placeholder: "10000.00" })}
    </div>
  );
}
