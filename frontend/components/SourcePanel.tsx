"use client";

import React from "react";
import {
  FileText,
  ArrowLeft,
  BookOpen,
  Layers,
  CheckCircle2,
} from "lucide-react";

export interface SourcePanelProps {
  filename: string;
  pageCount: number;
  chunkCount: number;
  onReset: () => void;
  isReady?: boolean;
}

export function SourcePanel({
  filename,
  pageCount,
  chunkCount,
  onReset,
  isReady = true,
}: SourcePanelProps) {
  return (
    <div
      data-testid="source-panel"
      className="flex flex-col h-full p-4 sm:p-5 bg-surface-panel text-text-primary space-y-5 transition-colors duration-150"
    >
      {/* Header / Document title */}
      <div className="space-y-2">
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

        <div className="flex items-start gap-2.5">
          <div className="p-2.5 bg-surface-pill text-blue-600 dark:text-accent-blue rounded-xl flex-shrink-0 mt-0.5 border border-border-subtle">
            <FileText className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <h2
              title={filename}
              className="text-sm font-semibold text-text-primary truncate"
            >
              {filename}
            </h2>
          </div>
        </div>
      </div>

      {/* Document Stats */}
      <div className="bg-surface-elevated border border-border-subtle rounded-2xl p-3.5 space-y-2.5 text-xs text-text-secondary">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-text-secondary">
            <BookOpen className="w-3.5 h-3.5 text-text-muted" />
            Pages
          </span>
          <span className="font-semibold text-text-primary">
            {pageCount} {pageCount === 1 ? "page" : "pages"}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-text-secondary">
            <Layers className="w-3.5 h-3.5 text-text-muted" />
            Chunks
          </span>
          <span className="font-semibold text-text-primary">
            {chunkCount} indexed
          </span>
        </div>
      </div>

      {/* Action: Upload another paper */}
      <div className="pt-2">
        <button
          type="button"
          onClick={onReset}
          className="w-full inline-flex items-center justify-center gap-2 px-3.5 py-2.5 text-xs font-medium text-text-primary bg-surface-pill hover:bg-surface-pill-hover border border-border-subtle rounded-xl transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 min-h-[42px]"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Upload another paper
        </button>
      </div>
    </div>
  );
}
