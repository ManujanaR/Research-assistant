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
      className="flex flex-col h-full p-4 bg-white space-y-4"
    >
      <div className="flex items-center justify-between pb-2 border-b border-slate-100 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-blue-600" />
          <h2 className="text-sm font-semibold text-slate-900">Studio</h2>
        </div>
        {isLoading && (
          <span className="text-xs text-blue-600 font-medium animate-pulse">
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
