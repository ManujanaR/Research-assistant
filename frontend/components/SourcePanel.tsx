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
      className="flex flex-col h-full p-4 sm:p-5 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 space-y-5 transition-colors duration-150"
    >
      {/* Header / Document title */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Document
          </span>
          {isReady && (
            <span
              data-testid="ready-badge"
              className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800/80 rounded-full"
            >
              <CheckCircle2 className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
              Ready
            </span>
          )}
        </div>

        <div className="flex items-start gap-2.5">
          <div className="p-2 bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 rounded-lg flex-shrink-0 mt-0.5 border border-blue-100 dark:border-blue-900/60">
            <FileText className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <h2
              title={filename}
              className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate"
            >
              {filename}
            </h2>
          </div>
        </div>
      </div>

      {/* Document Stats */}
      <div className="bg-slate-50 dark:bg-slate-800/50 border border-slate-200/80 dark:border-slate-700/60 rounded-xl p-3.5 space-y-2.5 text-xs text-slate-600 dark:text-slate-300">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
            <BookOpen className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500" />
            Pages
          </span>
          <span className="font-semibold text-slate-800 dark:text-slate-100">
            {pageCount} {pageCount === 1 ? "page" : "pages"}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
            <Layers className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500" />
            Chunks
          </span>
          <span className="font-semibold text-slate-800 dark:text-slate-100">
            {chunkCount} indexed
          </span>
        </div>
      </div>

      {/* Action: Upload another paper */}
      <div className="pt-2">
        <button
          type="button"
          onClick={onReset}
          className="w-full inline-flex items-center justify-center gap-2 px-3.5 py-2.5 text-xs font-medium text-slate-700 dark:text-slate-200 bg-slate-100 hover:bg-slate-200 active:bg-slate-300 dark:bg-slate-800 dark:hover:bg-slate-700 dark:active:bg-slate-600 rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 min-h-[42px]"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Upload another paper
        </button>
      </div>
    </div>
  );
}
