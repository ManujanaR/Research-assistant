"use client";

import React from "react";
import { AlertCircle, FileText } from "lucide-react";
import { SummaryResponse } from "@/lib/api";

export interface SummaryViewProps {
  summary: SummaryResponse | null;
  isLoading: boolean;
  error: string | null;
}

interface SummarySectionConfig {
  key: keyof SummaryResponse;
  title: string;
}

const SECTIONS: readonly SummarySectionConfig[] = [
  { key: "title_authors_abstract", title: "Title, Authors & Abstract" },
  { key: "problem_statement", title: "Problem Statement" },
  { key: "methodology", title: "Methodology" },
  { key: "key_results", title: "Key Results" },
  { key: "conclusion", title: "Conclusion" },
] as const;

export function SummaryView({ summary, isLoading, error }: SummaryViewProps) {
  if (isLoading) {
    return (
      <div
        data-testid="summary-loading"
        className="space-y-4 animate-pulse"
      >
        {[1, 2, 3, 4, 5].map((index) => (
          <div
            key={index}
            className="p-5 border border-slate-200 rounded-xl bg-slate-50 space-y-3"
          >
            <div className="h-5 w-1/3 bg-slate-200 rounded" />
            <div className="h-4 w-full bg-slate-200 rounded" />
            <div className="h-4 w-5/6 bg-slate-200 rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        className="flex items-start gap-3 p-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl"
      >
        <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-600" />
        <div className="space-y-1">
          <p className="font-semibold text-red-800">Error loading summary</p>
          <p className="whitespace-pre-wrap">{error}</p>
        </div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="flex flex-col items-center justify-center p-8 border border-dashed border-slate-200 rounded-xl text-center text-slate-500 bg-slate-50/50">
        <FileText className="w-8 h-8 text-slate-400 mb-2" />
        <p className="text-sm font-medium">No summary available</p>
        <p className="text-xs text-slate-400 mt-1">
          Upload a research paper to generate a structured five-part summary.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {SECTIONS.map((section) => (
        <article
          key={section.key}
          className="p-5 border border-slate-200 rounded-xl bg-white shadow-sm hover:shadow-md transition-shadow"
        >
          <h3 className="text-sm font-bold uppercase tracking-wider text-blue-700 mb-2">
            {section.title}
          </h3>
          <div className="text-sm leading-relaxed text-slate-700 whitespace-pre-wrap font-normal">
            {summary[section.key]}
          </div>
        </article>
      ))}
    </div>
  );
}
