"use client";

import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Download, Loader2 } from "lucide-react";
import { ApiError, ExportMessage, ExportSource, exportReport } from "@/lib/api";

export interface ExportButtonProps {
  docHash?: string | null;
  messages?: ExportMessage[];
}

export function ExportButton({ docHash, messages = [] }: ExportButtonProps) {
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [portalTarget, setPortalTarget] = useState<Element | null>(null);

  useEffect(() => {
    // Mount the button into the top bar header actions area to the left of the theme toggle
    const headerActions =
      document.querySelector('[data-testid="top-bar-actions"]') ||
      document.querySelector("header.bg-surface-panel .flex.items-center.gap-2\\.5") ||
      document.querySelector("header .flex.items-center.gap-2\\.5");
    if (headerActions) {
      const themeToggle =
        headerActions.querySelector('button[aria-label*="theme" i]') ||
        headerActions.querySelector('button[data-testid="theme-toggle"]') ||
        headerActions.lastElementChild;

      const container = document.createElement("div");
      container.className = "flex items-center flex-shrink-0 min-w-0";
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

  const hasSummary = Boolean(docHash);
  const isDisabled = !hasSummary || isExporting;

  const handleExport = async () => {
    if (!docHash || isExporting) return;
    setIsExporting(true);
    setError(null);

    // Extract DOM messages if props.messages is empty and DOM exists
    let effectiveMessages = messages;
    if (
      (!effectiveMessages || effectiveMessages.length === 0) &&
      typeof document !== "undefined"
    ) {
      const chatContainer =
        document.querySelector('[data-testid="desktop-chat-panel"]') ||
        document.querySelector('[data-testid="mobile-workspace"]');
      if (chatContainer) {
        const messageElements = chatContainer.querySelectorAll(
          ".flex.flex-col.gap-2.items-start, .flex.flex-col.gap-2.items-end"
        );
        const extracted: ExportMessage[] = [];
        messageElements.forEach((el) => {
          const isUser = el.classList.contains("items-end");
          const bubble = el.querySelector(".whitespace-pre-wrap");
          let text = bubble ? bubble.textContent?.trim() || "" : "";
          text = text.replace(/\[\d+\]/g, "").trim();
          if (!text) return;

          const sources: ExportSource[] = [];
          const sourceCards = el.querySelectorAll('[data-testid^="source-card-"]');
          sourceCards.forEach((card) => {
            const pageBadge = card.querySelector('[data-testid="page-badge"]');
            let pageNum: number | null = null;
            if (pageBadge?.textContent) {
              const m = pageBadge.textContent.match(/\d+/);
              if (m) pageNum = parseInt(m[0], 10);
            }
            const passageEl = card.querySelector('[data-testid="source-passage"]');
            const snippet = passageEl?.textContent?.trim() || undefined;
            sources.push({ page_number: pageNum, snippet });
          });

          extracted.push({
            role: isUser ? "user" : "assistant",
            text,
            sources: sources.length > 0 ? sources : undefined,
          });
        });
        if (extracted.length > 0) {
          effectiveMessages = extracted;
        }
      }
    }

    try {
      const { blob, filename } = await exportReport(
        docHash,
        effectiveMessages.slice(-200)
      );

      if (typeof window !== "undefined" && typeof window.URL?.createObjectURL === "function") {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        if (typeof window.URL?.revokeObjectURL === "function") {
          window.URL.revokeObjectURL(url);
        }
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Export failed.");
      }
    } finally {
      setIsExporting(false);
    }
  };

  const buttonContent = (
    <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
      <button
        type="button"
        data-testid="export-btn"
        onClick={handleExport}
        disabled={isDisabled}
        aria-label={isExporting ? "Preparing file" : "Export"}
        title="Downloads an editable Word file."
        className="inline-flex items-center justify-center gap-1.5 px-2.5 sm:px-3 py-1.5 text-xs font-medium rounded-xl border border-border-subtle bg-surface-panel hover:bg-surface-pill-hover text-text-primary disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 shadow-sm min-h-[44px] min-w-[44px] sm:min-w-0 flex-shrink-0"
      >
        {isExporting ? (
          <Loader2 className="w-4 h-4 text-text-secondary animate-spin flex-shrink-0" />
        ) : (
          <Download className="w-4 h-4 text-text-secondary flex-shrink-0" />
        )}
        <span className="hidden sm:inline">
          {isExporting ? "Preparing file" : "Export"}
        </span>
      </button>

      {!hasSummary && (
        <span
          data-testid="export-disabled-reason"
          className="text-xs text-text-muted hidden sm:inline"
        >
          Upload a paper first.
        </span>
      )}

      {error && (
        <span
          data-testid="export-error"
          role="alert"
          className="text-xs text-red-500 font-medium max-w-[200px] truncate"
        >
          {error}
        </span>
      )}
    </div>
  );

  if (portalTarget) {
    return createPortal(buttonContent, portalTarget);
  }

  return buttonContent;
}
