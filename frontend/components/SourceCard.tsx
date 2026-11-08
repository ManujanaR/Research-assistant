"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronUp, BookOpen } from "lucide-react";
import { ChatSource } from "@/lib/api";

export interface SourceCardProps {
  source?: ChatSource;
  sources?: ChatSource[];
  index?: number;
  initiallyExpanded?: boolean;
}

export function SourceCard({
  source,
  sources,
  index,
  initiallyExpanded = false,
}: SourceCardProps) {
  const [isExpanded, setIsExpanded] = useState(initiallyExpanded);

  // If a sources list is passed directly, do not render when empty
  if (sources !== undefined) {
    if (sources.length === 0) {
      return null;
    }
    return (
      <div data-testid="citation-block" className="space-y-2">
        {sources.map((s, idx) => (
          <SourceCard
            key={idx}
            source={s}
            index={idx}
            initiallyExpanded={initiallyExpanded}
          />
        ))}
      </div>
    );
  }

  if (!source) {
    return null;
  }

  const citationLabel =
    index !== undefined ? `Source [${index + 1}]` : "Source";

  return (
    <div
      data-testid={index !== undefined ? `source-card-${index + 1}` : "source-card"}
      className="border border-slate-200 dark:border-slate-800 rounded-lg p-3 bg-white dark:bg-slate-900 text-xs shadow-sm transition-colors duration-150"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <BookOpen className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500" />
          <span className="font-medium text-slate-700 dark:text-slate-300">
            {citationLabel}
          </span>
        </div>

        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          aria-expanded={isExpanded}
          className="flex items-center gap-1 text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 font-medium transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-blue-500 rounded py-1 px-1.5"
        >
          <span>{isExpanded ? "Hide passage" : "Show passage"}</span>
          {isExpanded ? (
            <ChevronUp className="w-3.5 h-3.5" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5" />
          )}
        </button>
      </div>

      {isExpanded && (
        <div
          data-testid="source-passage"
          className="mt-2.5 pt-2 border-t border-slate-200 dark:border-slate-800 text-xs"
        >
          {source.page_number !== null && (
            <div className="mb-1.5">
              <span
                data-testid="page-badge"
                className="px-1.5 py-0.5 text-[10px] font-semibold bg-blue-100 dark:bg-blue-950/80 text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-800/80 rounded"
              >
                Page {source.page_number}
              </span>
            </div>
          )}
          <div
            data-testid="source-snippet"
            className="text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed"
          >
            {source.snippet}
          </div>
        </div>
      )}
    </div>
  );
}
