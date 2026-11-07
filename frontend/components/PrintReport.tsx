"use client";

import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Printer } from "lucide-react";
import { SummaryResponse } from "@/lib/api";

export interface PrintReportSource {
  page_number: number | null;
  snippet: string;
}

export interface PrintReportMessage {
  role: "user" | "assistant";
  content: string;
  sources?: PrintReportSource[];
}

export interface PrintReportProps {
  summary: SummaryResponse | null;
  messages?: PrintReportMessage[];
  filename?: string | null;
}

export function PrintReport({
  summary,
  messages = [],
  filename,
}: PrintReportProps) {
  const [generatedDate, setGeneratedDate] = useState<string | null>(null);
  const [portalTarget, setPortalTarget] = useState<Element | null>(null);
  const [domMessages, setDomMessages] = useState<PrintReportMessage[]>([]);

  useEffect(() => {
    // Mount the button into the top bar header actions area to the left of the theme toggle
    const headerActions =
      document.querySelector("header .flex.items-center.gap-2\\.5") ||
      document.querySelector("header > div > div:last-child");
    if (headerActions) {
      const themeToggle =
        headerActions.querySelector('button[aria-label*="theme" i]') ||
        headerActions.querySelector('button[data-testid="theme-toggle"]') ||
        headerActions.lastElementChild;

      const container = document.createElement("div");
      container.className = "flex items-center";
      if (themeToggle && themeToggle.parentNode === headerActions) {
        headerActions.insertBefore(container, themeToggle);
      } else {
        headerActions.appendChild(container);
      }
      setPortalTarget(container);
      return () => {
        container.remove();
      };
    }
  }, []);

  const effectiveMessages =
    messages && messages.length > 0 ? messages : domMessages;
  const hasSummary = Boolean(summary);
  const hasMessages = Boolean(effectiveMessages && effectiveMessages.length > 0);
  const isDisabled = !hasSummary && !hasMessages;

  const handlePrint = () => {
    const now = new Date();
    setGeneratedDate(
      now.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      }) +
        " " +
        now.toLocaleTimeString(undefined, {
          hour: "2-digit",
          minute: "2-digit",
        })
    );

    // If props.messages was empty, inspect active ChatPanel in DOM for conversation
    if (
      (!messages || messages.length === 0) &&
      typeof document !== "undefined"
    ) {
      const chatContainer =
        document.querySelector('[data-testid="desktop-chat-panel"]') ||
        document.querySelector('[data-testid="mobile-workspace"]');
      if (chatContainer) {
        const messageElements = chatContainer.querySelectorAll(
          ".flex.flex-col.gap-2.items-start, .flex.flex-col.gap-2.items-end"
        );
        const extracted: PrintReportMessage[] = [];
        messageElements.forEach((el) => {
          const isUser = el.classList.contains("items-end");
          const bubble = el.querySelector(".whitespace-pre-wrap");
          // Strip out citation numbers from bubble text if present
          let text = bubble ? bubble.textContent?.trim() || "" : "";
          text = text.replace(/\[\d+\]/g, "").trim();
          if (!text) return;

          const sources: PrintReportSource[] = [];
          const sourceCards = el.querySelectorAll(
            '[data-testid^="source-card-"]'
          );
          sourceCards.forEach((card) => {
            const pageBadge = card.querySelector('[data-testid="page-badge"]');
            let pageNum: number | null = null;
            if (pageBadge && pageBadge.textContent) {
              const m = pageBadge.textContent.match(/Page\s+(\d+)/i);
              if (m) pageNum = parseInt(m[1], 10);
            }
            const passageEl = card.querySelector(
              '[data-testid="source-passage"]'
            );
            let snippet = "";
            if (passageEl && passageEl.textContent) {
              snippet = passageEl.textContent.replace(/^Passage.*?:/i, "").trim();
            }
            sources.push({ page_number: pageNum, snippet });
          });

          extracted.push({
            role: isUser ? "user" : "assistant",
            content: text,
            sources: sources.length > 0 ? sources : undefined,
          });
        });
        if (extracted.length > 0) {
          setDomMessages(extracted);
        }
      }
    }

    if (typeof window !== "undefined" && typeof window.print === "function") {
      window.print();
    }
  };

  const buttonContent = (
    <div className="flex items-center gap-2 flex-shrink-0 no-print print:hidden">
      <button
        type="button"
        onClick={handlePrint}
        disabled={isDisabled}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-border-subtle bg-surface-panel hover:bg-surface-pill-hover text-text-primary disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 shadow-sm min-h-[36px]"
      >
        <Printer className="w-3.5 h-3.5 text-text-secondary" />
        <span>Print report</span>
      </button>
      {isDisabled && (
        <span className="text-xs text-text-muted hidden sm:inline">
          Upload a paper first.
        </span>
      )}
    </div>
  );

  return (
    <>
      {portalTarget ? createPortal(buttonContent, portalTarget) : buttonContent}

      {/* Print-only document */}
      <div
        id="print-report-document"
        className="print-report-document hidden print:block bg-white text-black font-sans p-8 max-w-4xl mx-auto"
      >
        {/* 1. Header */}
        <header className="border-b-2 border-black pb-4 mb-6">
          <div className="flex justify-between items-start">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-black">
                Research Assistant
              </h1>
              {filename && (
                <p className="text-sm font-medium text-gray-700 mt-1">
                  Document: {filename}
                </p>
              )}
            </div>
            {generatedDate && (
              <div className="text-xs text-gray-600 text-right">
                Generated {generatedDate}
              </div>
            )}
          </div>
        </header>

        {/* 2. Structured Summary */}
        {summary && (
          <section className="mb-8 space-y-5">
            <h2 className="text-base font-bold uppercase tracking-wider text-black border-b border-gray-300 pb-1">
              Structured Summary
            </h2>
            <div className="space-y-4">
              <div>
                <h3 className="text-xs font-bold uppercase text-gray-900 tracking-wide">
                  Title, Authors &amp; Abstract
                </h3>
                <p className="text-sm leading-relaxed text-gray-800 whitespace-pre-wrap mt-1">
                  {summary.title_authors_abstract}
                </p>
              </div>

              <div>
                <h3 className="text-xs font-bold uppercase text-gray-900 tracking-wide">
                  Problem Statement
                </h3>
                <p className="text-sm leading-relaxed text-gray-800 whitespace-pre-wrap mt-1">
                  {summary.problem_statement}
                </p>
              </div>

              <div>
                <h3 className="text-xs font-bold uppercase text-gray-900 tracking-wide">
                  Methodology
                </h3>
                <p className="text-sm leading-relaxed text-gray-800 whitespace-pre-wrap mt-1">
                  {summary.methodology}
                </p>
              </div>

              <div>
                <h3 className="text-xs font-bold uppercase text-gray-900 tracking-wide">
                  Key Results
                </h3>
                <p className="text-sm leading-relaxed text-gray-800 whitespace-pre-wrap mt-1">
                  {summary.key_results}
                </p>
              </div>

              <div>
                <h3 className="text-xs font-bold uppercase text-gray-900 tracking-wide">
                  Conclusion
                </h3>
                <p className="text-sm leading-relaxed text-gray-800 whitespace-pre-wrap mt-1">
                  {summary.conclusion}
                </p>
              </div>
            </div>
          </section>
        )}

        {/* 3. Conversation */}
        {hasMessages && (
          <section className="mb-8 space-y-4">
            <h2 className="text-base font-bold uppercase tracking-wider text-black border-b border-gray-300 pb-1">
              Conversation
            </h2>
            <div className="space-y-4">
              {effectiveMessages.map((msg, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="text-xs font-bold uppercase text-gray-900">
                    {msg.role === "user" ? "Question:" : "Answer:"}
                  </div>
                  <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed pl-2">
                    {msg.content}
                  </p>

                  {msg.sources && msg.sources.length > 0 && (
                    <div className="pl-4 mt-2">
                      <div className="text-xs font-semibold text-gray-700">
                        Retrieved passages:
                      </div>
                      <div className="space-y-1 mt-1">
                        {msg.sources.map((source, sIdx) => (
                          <div key={sIdx} className="text-xs text-gray-700">
                            <span className="font-medium">[{sIdx + 1}]</span>
                            {source.page_number !== null
                              ? ` (Page ${source.page_number})`
                              : ""}
                            {source.snippet ? `: ${source.snippet}` : ""}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* 4. Footer */}
        <footer className="border-t border-gray-400 pt-4 mt-8 text-xs text-gray-600">
          <p>
            Answers are grounded in retrieved passages of the uploaded paper. Verify against the source.
          </p>
        </footer>
      </div>
    </>
  );
}
