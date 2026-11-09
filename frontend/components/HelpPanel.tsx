"use client";

import React, { useEffect, useRef, useCallback, useState } from "react";
import { createPortal } from "react-dom";
import {
  X,
  BookOpen,
  FileText,
  MessageSquare,
  Quote,
  FileDown,
  User,
  AlertTriangle,
} from "lucide-react";

export interface HelpPanelProps {
  isOpen: boolean;
  onClose: () => void;
  triggerRef?: React.RefObject<HTMLButtonElement | null>;
}

export function HelpPanel({ isOpen, onClose, triggerRef }: HelpPanelProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  const triggerElementRef = useRef<HTMLElement | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleClose = useCallback(() => {
    onClose();
    // Restore focus to HelpButton
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
        data-testid="help-panel-backdrop"
        aria-hidden="true"
        onClick={handleClose}
        className="fixed inset-0 bg-black/50 backdrop-blur-sm transition-opacity animate-in fade-in duration-200"
      />

      {/* Responsive Dialog Panel: Bottom sheet below lg (1024px), Right drawer on lg and above */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-panel-title"
        data-testid="help-panel"
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className="fixed z-50 bg-surface-panel text-text-primary shadow-2xl transition-all duration-200 flex flex-col overflow-hidden outline-none
          inset-x-0 bottom-0 max-h-[85vh] w-full rounded-t-2xl border-t border-border-subtle
          lg:inset-y-0 lg:right-0 lg:left-auto lg:bottom-auto lg:h-full lg:max-h-full lg:w-[440px] lg:rounded-none lg:border-t-0 lg:border-l"
      >
        {/* Mobile handle indicator */}
        <div className="pt-2.5 pb-1 flex justify-center lg:hidden flex-shrink-0">
          <div className="w-12 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-accent-blue/10 flex items-center justify-center text-blue-600 dark:text-accent-blue flex-shrink-0">
              <BookOpen className="w-4 h-4" />
            </div>
            <h2
              id="help-panel-title"
              data-testid="help-panel-title"
              className="text-lg font-semibold text-text-primary tracking-tight"
            >
              How to use this
            </h2>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={handleClose}
            aria-label="Close"
            data-testid="help-panel-close-btn"
            className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-pill-hover transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body: Seven Ordered Sections */}
        <div className="flex-1 overflow-y-auto px-5 py-6 space-y-6">
          {/* Section 1: Getting started */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-accent-blue flex items-center justify-center flex-shrink-0">
                <FileText className="w-3.5 h-3.5" />
              </div>
              <h3 className="text-sm font-semibold text-text-primary">
                Getting started
              </h3>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed pl-8">
              Upload a text-based PDF up to 20 MB. Once uploaded, the assistant automatically processes the document and generates a structured summary in seconds.
            </p>
          </section>

          {/* Section 2: Reading the summary */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 flex items-center justify-center flex-shrink-0">
                <BookOpen className="w-3.5 h-3.5" />
              </div>
              <h3 className="text-sm font-semibold text-text-primary">
                Reading the summary
              </h3>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed pl-8">
              The summary is organized into 5 sections: Title & Authors & Abstract, Problem Statement, Methodology, Key Results, and Conclusion. Click the copy button in any section to quickly copy its text. If a section is not discussed in the paper, the summary explicitly notes &ldquo;Not stated in the paper.&rdquo;
            </p>
          </section>

          {/* Section 3: Asking questions */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 flex items-center justify-center flex-shrink-0">
                <MessageSquare className="w-3.5 h-3.5" />
              </div>
              <h3 className="text-sm font-semibold text-text-primary">
                Asking questions
              </h3>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed pl-8">
              Ask plain language questions in the chat panel. Answers are strictly document-grounded in the uploaded paper. If the paper does not contain the answer, the assistant will inform you directly.
            </p>
          </section>

          {/* Section 4: Citations */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-amber-50 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 flex items-center justify-center flex-shrink-0">
                <Quote className="w-3.5 h-3.5" />
              </div>
              <h3 className="text-sm font-semibold text-text-primary">
                Citations
              </h3>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed pl-8">
              Every answer features a sources line with page number and paper excerpt referencing the exact context used to answer your query.
            </p>
          </section>

          {/* Section 5: Exporting */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-cyan-50 dark:bg-cyan-900/30 text-cyan-600 dark:text-cyan-400 flex items-center justify-center flex-shrink-0">
                <FileDown className="w-3.5 h-3.5" />
              </div>
              <h3 className="text-sm font-semibold text-text-primary">
                Exporting
              </h3>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed pl-8">
              Generate an editable Word .docx export with summary, transcript, and &ldquo;Your notes&rdquo; areas by clicking the Export button in the top navigation bar.
            </p>
          </section>

          {/* Section 6: Account */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 flex items-center justify-center flex-shrink-0">
                <User className="w-3.5 h-3.5" />
              </div>
              <h3 className="text-sm font-semibold text-text-primary">
                Account
              </h3>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed pl-8">
              Your research sessions are private and scoped to your profile. You can sign in, password change, sign out from avatar menu in the top bar anytime.
            </p>
          </section>

          {/* Section 7: Limits */}
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-md bg-rose-50 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400 flex items-center justify-center flex-shrink-0">
                <AlertTriangle className="w-3.5 h-3.5" />
              </div>
              <h3 className="text-sm font-semibold text-text-primary">
                Limits
              </h3>
            </div>
            <ul className="text-sm text-text-secondary space-y-1.5 list-disc pl-12 leading-relaxed">
              <li>Upload one paper at a time</li>
              <li>20 MB maximum per file</li>
              <li>2000 characters per message</li>
              <li>No web search capability</li>
              <li>Scanned PDFs require OCR</li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );

  if (mounted && typeof document !== "undefined") {
    return createPortal(content, document.body);
  }

  return content;
}
