"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronUp, BookOpen } from "lucide-react";
import { ChatSource } from "@/lib/api";

export interface SourceCardProps {
  source?: ChatSource;
  sources?: ChatSource[];
}

export function SourceCard({ source, sources }: SourceCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // If a sources list is passed directly, do not render when empty
  if (sources !== undefined) {
    if (sources.length === 0) {
      return null;
    }
    return (
      <div data-testid="citation-block" className="space-y-2">
        {sources.map((s, idx) => (
          <SourceCard key={idx} source={s} />
        ))}
      </div>
    );
  }

  if (!source) {
    return null;
  }

  return (
    <div className="border border-slate-200 rounded-lg p-3 bg-white text-xs shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <BookOpen className="w-3.5 h-3.5 text-slate-400" />
          <span className="font-medium text-slate-700">Source Excerpt</span>
          {source.page_number !== null && (
            <span
              data-testid="page-badge"
              className="px-1.5 py-0.5 text-[10px] font-semibold bg-blue-100 text-blue-800 rounded"
            >
              Page {source.page_number}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          aria-expanded={isExpanded}
          className="flex items-center gap-1 text-slate-500 hover:text-slate-800 font-medium transition-colors"
        >
          <span>{isExpanded ? "Hide snippet" : "Show snippet"}</span>
          {isExpanded ? (
            <ChevronUp className="w-3.5 h-3.5" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5" />
          )}
        </button>
      </div>

      {isExpanded && (
        <div
          data-testid="source-snippet"
          className="mt-2.5 pt-2.5 border-t border-slate-100 text-slate-600 whitespace-pre-wrap leading-relaxed font-mono text-[11px]"
        >
          {source.snippet}
        </div>
      )}
    </div>
  );
}
