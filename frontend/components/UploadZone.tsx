"use client";

import React, { useRef, useState } from "react";
import { UploadCloud, Loader2, AlertCircle } from "lucide-react";
import { ApiError, UploadResponse, uploadPdf } from "@/lib/api";

export interface UploadZoneProps {
  onUploaded: (result: UploadResponse) => void;
  disabled?: boolean;
}

const MAX_UPLOAD_MB =
  Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB) > 0
    ? Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB)
    : 20;

export function UploadZone({ onUploaded, disabled = false }: UploadZoneProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const validateFile = (file: File): string | null => {
    const isPdfMime = file.type === "application/pdf";
    const isPdfExt = file.name.toLowerCase().endsWith(".pdf");
    if (!isPdfMime || !isPdfExt) {
      return "Invalid file type: only application/pdf is accepted.";
    }
    const maxBytes = MAX_UPLOAD_MB * 1024 * 1024;
    if (file.size > maxBytes) {
      return `File exceeds maximum allowed size of ${MAX_UPLOAD_MB}MB.`;
    }
    return null;
  };

  const handleFileProcess = async (file: File) => {
    if (disabled || isLoading) {
      return;
    }
    setError(null);

    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsLoading(true);
    try {
      const response = await uploadPdf(file);
      onUploaded(response);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred during upload.");
      }
    } finally {
      setIsLoading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled || isLoading) return;

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      void handleFileProcess(files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!disabled && !isLoading) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleClick = () => {
    if (!disabled && !isLoading) {
      fileInputRef.current?.click();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (disabled || isLoading) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInputRef.current?.click();
    }
  };

  return (
    <div className="w-full">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        disabled={disabled || isLoading}
        onChange={(e) => {
          const files = e.target.files;
          if (files && files.length > 0) {
            void handleFileProcess(files[0]);
          }
        }}
      />

      <div
        role="button"
        tabIndex={disabled || isLoading ? -1 : 0}
        aria-disabled={disabled || isLoading}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-xl transition-colors cursor-pointer select-none text-center outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
          disabled
            ? "border-slate-300 bg-slate-50 cursor-not-allowed opacity-60 text-slate-400"
            : isDragging
            ? "border-blue-500 bg-blue-50/50 text-blue-600"
            : "border-slate-300 hover:border-slate-400 bg-white hover:bg-slate-50/50 text-slate-600"
        }`}
      >
        {isLoading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-10 h-10 animate-spin text-blue-600" />
            <p className="text-sm font-medium text-slate-700">
              Uploading and analyzing research paper...
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="p-3 bg-blue-50 text-blue-600 rounded-full">
              <UploadCloud className="w-8 h-8" />
            </div>
            <div>
              <p className="text-base font-semibold text-slate-800">
                Click to upload or drag and drop
              </p>
              <p className="text-xs text-slate-500 mt-1">
                PDF documents only (up to {MAX_UPLOAD_MB}MB)
              </p>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div
          role="alert"
          className="mt-3 flex items-start gap-2 p-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg"
        >
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
