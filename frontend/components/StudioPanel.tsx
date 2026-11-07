"use client";

import React from "react";
import { Sparkles } from "lucide-react";
import { SummaryResponse } from "@/lib/api";
import { SummaryView } from "./SummaryView";

export interface StudioPanelProps {
  summary: SummaryResponse | null;
  isLoading: boolean;
  error: string | null;
}

export function StudioPanel({ summary, isLoading, error }: StudioPanelProps) {
  return (
    <div
      data-testid="studio-panel"
      className="flex flex-col h-full w-full p-4 sm:p-6 lg:p-4 bg-surface-panel text-text-primary space-y-4 transition-colors duration-150"
    >
      <div className="flex items-center justify-between pb-3 border-b border-border-subtle flex-shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-blue-600 dark:text-accent-blue" />
          <h2 className="text-sm font-semibold text-text-primary">
            Summary
          </h2>
        </div>
        {isLoading && (
          <span className="text-xs text-blue-600 dark:text-accent-blue font-medium animate-pulse">
            Generating summary...
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        <SummaryView summary={summary} isLoading={isLoading} error={error} />
      </div>
    </div>
  );
}
