"use client";

import React from "react";
import {
  FileText,
  BookOpen,
  Layers,
  CheckCircle2,
} from "lucide-react";
import { UploadZone } from "./UploadZone";
import { ConvertLink } from "./ConvertLink";
import { CredibilityCard } from "./CredibilityCard";
import { UploadResponse } from "@/lib/api";

export interface SourcePanelProps {
  docHash?: string | null;
  filename?: string | null;
  pageCount?: number | null;
  chunkCount?: number | null;
  onReset: () => void;
  isReady?: boolean;
  onUploaded?: (result: UploadResponse) => void;
}

export function SourcePanel({
  docHash,
  filename,
  pageCount,
  chunkCount,
  onReset,
  isReady = true,
  onUploaded,
}: SourcePanelProps) {
  const hasDocument = Boolean(filename);

  return (
    <div
      data-testid="source-panel"
      className="flex flex-col h-full w-full p-4 sm:p-6 lg:p-4 bg-surface-panel text-text-primary space-y-5 transition-colors duration-150 overflow-y-auto"
    >
      {hasDocument ? (
        <>
          {/* Header */}
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-text-secondary">
              Document
            </span>
            {isReady && (
              <span
                data-testid="ready-badge"
                className="inline-flex items-center gap-1 px-2.5 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/60 rounded-full"
              >
                <CheckCircle2 className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                Ready
              </span>
            )}
          </div>

          {/* Compact row showing filename and 'Upload another paper' link */}
          <UploadZone
            filename={filename}
            onReset={onReset}
            onUploaded={onUploaded || (() => {})}
          />

          {/* Document Stats */}
          <div className="bg-surface-elevated border border-border-subtle rounded-2xl p-3.5 space-y-2.5 text-xs text-text-secondary">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-text-secondary">
                <BookOpen className="w-3.5 h-3.5 text-text-muted" />
                Pages
              </span>
              <span className="font-semibold text-text-primary">
                {pageCount ?? 0} {pageCount === 1 ? "page" : "pages"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-text-secondary">
                <Layers className="w-3.5 h-3.5 text-text-muted" />
                Chunks
              </span>
              <span className="font-semibold text-text-primary">
                {chunkCount ?? 0} indexed
              </span>
            </div>
          </div>

          {/* Credibility & Publication Signals Card */}
          <CredibilityCard docHash={docHash} />
        </>
      ) : (
        <>
          {/* Header */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-blue-600 dark:text-accent-blue" />
              <h2 className="text-sm font-semibold text-text-primary">
                Sources
              </h2>
            </div>
            <span className="text-[11px] font-medium text-text-muted">
              0 / 1
            </span>
          </div>

          {/* Integrated UploadZone as single upload control */}
          <div className="flex-1 min-h-0">
            <UploadZone
              filename={null}
              onUploaded={onUploaded || (() => {})}
            />
          </div>

          <ConvertLink />

          <div className="text-center pt-1">
            <p className="text-xs text-text-muted">
              Uploaded sources will appear here.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
