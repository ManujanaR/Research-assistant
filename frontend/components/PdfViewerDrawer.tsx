"use client";

import React, { useEffect, useRef, useCallback, useState } from "react";
import { createPortal } from "react-dom";
import { X, ExternalLink, FileText, AlertCircle } from "lucide-react";

export interface PdfViewerDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  blobUrl: string | null;
  triggerRef?: React.RefObject<HTMLButtonElement | null>;
  filename?: string | null;
}

export function PdfViewerDrawer({
  isOpen,
  onClose,
  blobUrl,
  triggerRef,
  filename,
}: PdfViewerDrawerProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  const triggerElementRef = useRef<HTMLElement | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleClose = useCallback(() => {
    onClose();
    if (triggerRef?.current) {
      triggerRef.current.focus();
    } else if (triggerElementRef.current) {
      triggerElementRef.current.focus();
    }
  }, [onClose, triggerRef]);

  // Capture currently focused element on open and restore on close
  useEffect(() => {
    if (isOpen) {
      triggerElementRef.current = (triggerRef?.current || document.activeElement) as HTMLElement | null;
      const timer = setTimeout(() => {
        closeBtnRef.current?.focus();
      }, 30);
      return () => clearTimeout(timer);
    }
  }, [isOpen, triggerRef]);

  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        handleClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, handleClose]);

  // Focus trap for Tab key
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab" || !panelRef.current) return;

    const focusableElements = panelRef.current.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );

    if (!focusableElements || focusableElements.length === 0) {
      e.preventDefault();
      return;
    }

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === firstElement || document.activeElement === panelRef.current) {
        e.preventDefault();
        lastElement.focus();
      }
    } else {
      if (document.activeElement === lastElement) {
        e.preventDefault();
        firstElement.focus();
      }
    }
  };

  if (!isOpen) {
    return null;
  }

  const content = (
    <div className="fixed inset-0 z-50 overflow-hidden" role="presentation">
      {/* Backdrop */}
      <div
        data-testid="pdf-viewer-backdrop"
        aria-hidden="true"
        onClick={handleClose}
        className="fixed inset-0 bg-black/50 backdrop-blur-sm transition-opacity animate-in fade-in duration-200"
      />

      {/* Responsive Dialog: Full-height modal on <lg, right-hand half-screen drawer on lg+ */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Original PDF Document"
        data-testid="pdf-viewer-drawer"
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className="fixed z-50 bg-surface-panel text-text-primary shadow-2xl transition-all duration-200 flex flex-col overflow-hidden outline-none
          inset-0 w-full h-full rounded-none
          lg:inset-y-0 lg:right-0 lg:left-auto lg:h-full lg:w-1/2 lg:border-l lg:border-border-subtle"
      >
        {/* Header Area with Title, Privacy Statement, and Actions */}
        <div className="flex items-start justify-between px-5 py-3.5 border-b border-border-subtle bg-surface-elevated/40 flex-shrink-0">
          <div className="flex items-start gap-3 min-w-0 flex-1 pr-3">
            <div className="p-2 bg-surface-pill text-blue-600 dark:text-accent-blue rounded-xl flex-shrink-0 mt-0.5 border border-border-subtle">
              <FileText className="w-5 h-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-text-primary truncate">
                  {filename || "Original PDF Document"}
                </h2>
              </div>
              <p className="text-xs text-text-muted mt-0.5 leading-relaxed">
                The PDF is shown from memory in your browser. The server keeps only the extracted text and index, as before.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            {blobUrl && (
              <a
                href={blobUrl}
                target="_blank"
                rel="noopener noreferrer"
                title="Open in new tab"
                aria-label="Open PDF in new tab"
                className="p-2 rounded-xl text-text-secondary hover:text-text-primary hover:bg-surface-pill transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
            <button
              ref={closeBtnRef}
              type="button"
              onClick={handleClose}
              aria-label="Close"
              data-testid="pdf-viewer-close-btn"
              className="p-2 rounded-xl text-text-secondary hover:text-text-primary hover:bg-surface-pill transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* PDF Object Embed with Fallback */}
        <div className="flex-1 w-full h-full min-h-0 bg-slate-100 dark:bg-slate-900/60 p-2 sm:p-3 overflow-hidden flex flex-col">
          <object
            data={blobUrl || ""}
            type="application/pdf"
            aria-label="PDF Document Preview"
            className="w-full h-full flex-1 rounded-xl border border-border-subtle bg-surface-panel shadow-inner"
          >
            {/* Fallback displayed if inline rendering fails or browser does not support inline PDF object */}
            <div
              data-testid="pdf-viewer-fallback"
              className="flex flex-col items-center justify-center p-8 text-center h-full w-full space-y-4"
            >
              <div className="p-3 bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 rounded-full border border-amber-200 dark:border-amber-800/60">
                <AlertCircle className="w-8 h-8" />
              </div>
              <div className="max-w-sm space-y-1">
                <p className="text-sm font-medium text-text-primary">
                  Your browser can’t show this PDF inline.
                </p>
                <p className="text-xs text-text-secondary">
                  You can still open and read the complete document in a separate browser window.
                </p>
              </div>
              {blobUrl ? (
                <a
                  href={blobUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 dark:bg-accent-blue dark:text-black rounded-xl transition-colors shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Open in new tab
                </a>
              ) : (
                <span className="text-xs text-text-muted">No document URL available</span>
              )}
            </div>
          </object>
        </div>
      </div>
    </div>
  );

  if (mounted && typeof document !== "undefined") {
    return createPortal(content, document.body);
  }

  return content;
}
