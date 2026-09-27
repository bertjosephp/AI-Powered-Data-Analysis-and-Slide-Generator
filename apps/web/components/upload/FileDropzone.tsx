"use client";

import { FileSpreadsheet, UploadCloud, X } from "lucide-react";
import { type FileRejection, useDropzone } from "react-dropzone";

import { cn, formatBytes } from "@/lib/utils";

export const MAX_UPLOAD_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? 25);

const ACCEPT = {
  "text/csv": [".csv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/vnd.ms-excel": [".xls"],
};

type Props = {
  file: File | null;
  onFileChange: (file: File | null) => void;
  onReject: (message: string) => void;
  disabled?: boolean;
};

export function FileDropzone({ file, onFileChange, onReject, disabled }: Props) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPT,
    maxFiles: 1,
    maxSize: MAX_UPLOAD_MB * 1024 * 1024,
    disabled,
    onDropAccepted: ([accepted]) => onFileChange(accepted),
    onDropRejected: (rejections) => onReject(describeRejection(rejections)),
  });

  if (file) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-border bg-surface-muted p-4">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent">
          <FileSpreadsheet className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{file.name}</p>
          <p className="text-sm text-muted">{formatBytes(file.size)}</p>
        </div>
        <button
          type="button"
          onClick={() => onFileChange(null)}
          disabled={disabled}
          className="rounded-md p-1.5 text-muted hover:bg-border hover:text-foreground disabled:opacity-50"
          aria-label="Remove file"
        >
          <X className="size-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      {...getRootProps()}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border bg-surface-muted/40 px-6 py-10 text-center transition-colors",
        "hover:border-accent/60 hover:bg-accent-soft/40 focus-visible:outline-2 focus-visible:outline-accent",
        isDragActive && "border-accent bg-accent-soft/60",
        disabled && "pointer-events-none opacity-60",
      )}
    >
      <input {...getInputProps()} aria-label="Upload dataset" />
      <span className="grid size-12 place-items-center rounded-full bg-accent-soft text-accent">
        <UploadCloud className="size-6" aria-hidden />
      </span>
      <div>
        <p className="font-medium">
          {isDragActive ? "Drop the file here" : "Drag a file here, or click to browse"}
        </p>
        <p className="mt-1 text-sm text-muted">CSV, XLSX or XLS · up to {MAX_UPLOAD_MB} MB</p>
      </div>
    </div>
  );
}

function describeRejection(rejections: FileRejection[]): string {
  if (rejections.length > 1) return "Upload one file at a time.";
  const code = rejections[0]?.errors[0]?.code;
  if (code === "file-too-large") return `That file is larger than ${MAX_UPLOAD_MB} MB.`;
  if (code === "file-invalid-type") return "Only CSV and Excel files (.csv, .xlsx, .xls) are supported.";
  return rejections[0]?.errors[0]?.message ?? "That file can't be used.";
}
