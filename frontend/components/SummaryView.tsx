"use client";

import React, { useState } from "react";
import {
  AlertCircle,
  FileText,
  ChevronDown,
  Copy,
  Check,
} from "lucide-react";
import { SummaryResponse } from "@/lib/api";

export interface SummaryViewProps {
  summary: SummaryResponse | null;
  isLoading: boolean;
  error: string | null;
}

interface SummarySectionConfig {
  key: "header" | "problem_statement" | "methodology" | "key_results" | "conclusion";
  title: string;
}

const SECTIONS: readonly SummarySectionConfig[] = [
  { key: "header", title: "Title, Authors & Abstract" },
  { key: "problem_statement", title: "Problem Statement" },
  { key: "methodology", title: "Methodology" },
  { key: "key_results", title: "Key Results" },
  { key: "conclusion", title: "Conclusion" },
] as const;

export function SummaryView({ summary, isLoading, error }: SummaryViewProps) {
  // First section expanded by default; remaining sections start collapsed
  const [expandedSections, setExpandedSections] = useState<
    Record<string, boolean>
  >({
    header: true,
    problem_statement: false,
    methodology: false,
    key_results: false,
    conclusion: false,
  });

  const [copiedSection, setCopiedSection] = useState<string | null>(null);
  const [copyErrorSection, setCopyErrorSection] = useState<string | null>(null);

  const toggleSection = (key: string) => {
    setExpandedSections((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleCopy = async (
    key: string,
    text: string,
    e: React.MouseEvent
  ) => {
    e.stopPropagation();
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(text);
      setCopiedSection(key);
      setCopyErrorSection(null);
      setTimeout(() => {
        setCopiedSection((current) => (current === key ? null : current));
      }, 2000);
    } catch (_err) {
      setCopyErrorSection(key);
      setCopiedSection(null);
      setTimeout(() => {
        setCopyErrorSection((current) => (current === key ? null : current));
      }, 2000);
    }
  };

  if (isLoading) {
    return (
      <div data-testid="summary-loading" className="space-y-3 animate-pulse">
        {[1, 2, 3, 4, 5].map((index) => (
          <div
            key={index}
            className="p-4 border border-border-subtle rounded-2xl bg-surface-elevated space-y-2.5"
          >
            <div className="h-4 w-1/3 bg-surface-pill rounded" />
            <div className="h-3.5 w-full bg-surface-pill rounded" />
            <div className="h-3.5 w-5/6 bg-surface-pill rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        className="flex items-start gap-3 p-4 text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-2xl"
      >
        <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-600 dark:text-red-400" />
        <div className="space-y-1">
          <p className="font-semibold text-red-800 dark:text-red-200">
            Error loading summary
          </p>
          <p className="whitespace-pre-wrap">{error}</p>
        </div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="flex flex-col items-center justify-center p-8 border border-dashed border-border-subtle rounded-2xl text-center text-text-secondary bg-surface-elevated">
        <FileText className="w-8 h-8 text-text-muted mb-2" />
        <p className="text-sm font-medium">No summary available</p>
        <p className="text-xs text-text-muted mt-1">
          Upload a research paper to generate a structured five-part summary.
        </p>
      </div>
    );
  }

  const getCopyText = (key: SummarySectionConfig["key"]): string => {
    if (key === "header") {
      if (summary.header) {
        return `${summary.header.title}\n${summary.header.authors}\n\n${summary.header.abstract}`.trim();
      }
      return summary.title_authors_abstract || "";
    }
    return summary[key];
  };

  return (
    <div className="space-y-3">
      {SECTIONS.map((section) => {
        const isExpanded = Boolean(expandedSections[section.key]);
        const copyText = getCopyText(section.key);
        const isCopied = copiedSection === section.key;
        const hasCopyError = copyErrorSection === section.key;

        return (
          <article
            key={section.key}
            data-testid={`summary-card-${section.key}`}
            className="border border-border-subtle rounded-2xl bg-surface-panel shadow-sm overflow-hidden transition-all hover:border-slate-300 dark:hover:border-slate-700"
          >
            {/* Collapsible Header */}
            <div
              role="button"
              tabIndex={0}
              onClick={() => toggleSection(section.key)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  toggleSection(section.key);
                }
              }}
              aria-expanded={isExpanded}
              aria-controls={`section-body-${section.key}`}
              className="w-full flex items-center justify-between p-3.5 cursor-pointer select-none bg-surface-panel hover:bg-surface-elevated transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 min-h-[44px]"
            >
              <div className="flex items-center gap-2 min-w-0 pr-2">
                <ChevronDown
                  className={`w-4 h-4 text-text-muted flex-shrink-0 transition-transform duration-200 ${
                    isExpanded ? "rotate-180" : ""
                  }`}
                />
                <h3 className="text-xs font-bold uppercase tracking-wider text-blue-600 dark:text-accent-blue truncate">
                  {section.title}
                </h3>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                {hasCopyError && (
                  <span
                    role="status"
                    className="text-[11px] font-medium text-red-600 dark:text-red-300 bg-red-50 dark:bg-red-950/60 px-2 py-0.5 rounded border border-red-200 dark:border-red-800"
                  >
                    Failed to copy
                  </span>
                )}
                <button
                  type="button"
                  onClick={(e) => handleCopy(section.key, copyText, e)}
                  aria-label={`Copy ${section.title}`}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-text-primary bg-surface-pill hover:bg-surface-pill-hover border border-border-subtle rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 min-h-[32px]"
                >
                  {isCopied ? (
                    <>
                      <Check className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                      <span className="text-emerald-700 dark:text-emerald-300 font-semibold">
                        Copied
                      </span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3 text-text-secondary" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Collapsible Content */}
            {isExpanded && (
              <div
                id={`section-body-${section.key}`}
                data-testid={`section-content-${section.key}`}
                className="px-4 pb-4 pt-2 text-xs sm:text-sm leading-relaxed text-text-secondary whitespace-pre-wrap font-normal border-t border-border-subtle"
              >
                {section.key === "header" ? (
                  summary.header ? (
                    <div className="space-y-2">
                      <h4
                        data-testid="header-title"
                        className="text-sm sm:text-base font-semibold text-text-primary leading-snug"
                      >
                        {summary.header.title}
                      </h4>
                      <p
                        data-testid="header-authors"
                        className="text-xs text-text-muted font-medium"
                      >
                        {summary.header.authors}
                      </p>
                      <p
                        data-testid="header-abstract"
                        className="text-xs sm:text-sm text-text-secondary leading-relaxed whitespace-pre-wrap pt-1"
                      >
                        {summary.header.abstract}
                      </p>
                    </div>
                  ) : (
                    <div>{summary.title_authors_abstract}</div>
                  )
                ) : (
                  <div>{summary[section.key]}</div>
                )}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
