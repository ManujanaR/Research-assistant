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
      className="flex flex-col h-full p-4 bg-white space-y-5"
    >
      {/* Header / Document title */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
            Document
          </span>
          {isReady && (
            <span
              data-testid="ready-badge"
              className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full"
            >
              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
              Ready
            </span>
          )}
        </div>

        <div className="flex items-start gap-2.5">
          <div className="p-2 bg-blue-50 text-blue-600 rounded-lg flex-shrink-0 mt-0.5">
            <FileText className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <h2
              title={filename}
              className="text-sm font-semibold text-slate-900 truncate"
            >
              {filename}
            </h2>
          </div>
        </div>
      </div>

      {/* Document Stats */}
      <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3 space-y-2.5 text-xs text-slate-600">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-500">
            <BookOpen className="w-3.5 h-3.5 text-slate-400" />
            Pages
          </span>
          <span className="font-semibold text-slate-800">
            {pageCount} {pageCount === 1 ? "page" : "pages"}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-slate-500">
            <Layers className="w-3.5 h-3.5 text-slate-400" />
            Chunks
          </span>
          <span className="font-semibold text-slate-800">
            {chunkCount} indexed
          </span>
        </div>
      </div>

      {/* Action: Upload another paper */}
      <div className="pt-2">
        <button
          type="button"
          onClick={onReset}
          className="w-full inline-flex items-center justify-center gap-2 px-3.5 py-2 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 active:bg-slate-300 rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Upload another paper
        </button>
      </div>
    </div>
  );
}
