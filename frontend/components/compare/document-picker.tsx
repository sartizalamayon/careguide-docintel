import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { DocumentSummary } from "@/lib/types";

interface DocumentPickerProps {
  id: string;
  label: string;
  documents: DocumentSummary[];
  value: string;
  loading: boolean;
  onChange: (id: string) => void;
}

export function DocumentPicker({ id, label, documents, value, loading, onChange }: DocumentPickerProps) {
  return (
    <div className="grid min-w-60 flex-1 gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onChange} disabled={loading || documents.length === 0}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder={loading ? "Loading documents" : documents.length === 0 ? "No documents ready" : "Choose a document"} />
        </SelectTrigger>
        <SelectContent>
          {documents.map((d) => (
            <SelectItem key={d.id} value={d.id}>{d.filename}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
