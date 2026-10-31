"use client";

import { useDropzone, type FileRejection } from "react-dropzone";
import { Loader2, UploadCloud } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RejectedFile } from "@/lib/types";

export const MAX_FILE_BYTES = 200 * 1024 * 1024;

const ACCEPT = {
  "application/pdf": [".pdf"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/tiff": [".tif", ".tiff"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/vnd.ms-excel": [".xls"],
  "text/csv": [".csv"],
};

const UNSUPPORTED = "Only PDF, PNG, JPG, TIFF, XLSX, XLS and CSV files are accepted.";

export function splitDropped(accepted: File[], rejections: FileRejection[]): { files: File[]; rejected: RejectedFile[] } {
  const rejected: RejectedFile[] = rejections.map(({ file }) => ({
    filename: file.name, code: "UNSUPPORTED_FILE_TYPE", message: UNSUPPORTED,
  }));
  const files: File[] = [];
  for (const file of accepted) {
    if (file.size > MAX_FILE_BYTES) {
      rejected.push({ filename: file.name, code: "FILE_TOO_LARGE", message: "Files can be up to 200 MB." });
    } else {
      files.push(file);
    }
  }
  return { files, rejected };
}

interface DropzoneProps {
  uploading: boolean;
  onFiles: (files: File[], rejected: RejectedFile[]) => void;
}

export function Dropzone({ uploading, onFiles }: DropzoneProps) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPT,
    multiple: true,
    disabled: uploading,
    onDrop: (accepted, rejections) => {
      const { files, rejected } = splitDropped(accepted, rejections);
      onFiles(files, rejected);
    },
  });

  return (
    <div
      {...getRootProps()}
      className={cn(
        "flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-brand-navy/25 bg-card px-6 py-10 text-center transition-colors",
        "hover:border-brand-orange hover:bg-brand-orange/5",
        isDragActive && "border-brand-orange bg-brand-orange/10",
        uploading && "pointer-events-none opacity-70",
      )}
    >
      <input {...getInputProps()} />
      {uploading ? <Loader2 className="size-8 animate-spin text-brand-navy" /> : <UploadCloud className="size-8 text-brand-navy" />}
      <p className="font-heading text-base font-medium text-brand-navy">
        {uploading ? "Uploading…" : isDragActive ? "Drop the files here" : "Drop invoices here, or click to choose"}
      </p>
      <p className="text-xs text-muted-foreground">PDF, PNG, JPG, TIFF, XLSX, XLS or CSV. Up to 200 MB each.</p>
    </div>
  );
}
