"use client";

import React, { useEffect, useRef, useState } from "react";
import { BookOpen, MessageSquare, Sparkles } from "lucide-react";
import { UploadZone } from "@/components/UploadZone";
import { SourcePanel } from "@/components/SourcePanel";
import { StudioPanel } from "@/components/StudioPanel";
import { ChatPanel } from "@/components/ChatPanel";
import {
  ApiError,
  SummaryResponse,
  UploadResponse,
  getSummary,
} from "@/lib/api";

type MobileTab = "source" | "chat" | "studio";

interface TabItem {
  id: MobileTab;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const MOBILE_TABS: readonly TabItem[] = [
  { id: "source", label: "Source", icon: BookOpen },
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "studio", label: "Studio", icon: Sparkles },
] as const;

export default function Home() {
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [isSummaryLoading, setIsSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  // Mobile navigation state
  const [activeTab, setActiveTab] = useState<MobileTab>("chat");
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Desktop vs Mobile viewport detection via window.matchMedia
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window !== "undefined" && window.matchMedia) {
      return window.matchMedia("(min-width: 1024px)").matches;
    }
    return false;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;

    const mql = window.matchMedia("(min-width: 1024px)");
    setIsDesktop(mql.matches);

    const onChange = (e: MediaQueryListEvent) => {
      setIsDesktop(e.matches);
    };

    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  const handleUploaded = async (result: UploadResponse) => {
    setUploadResult(result);
    setIsSummaryLoading(true);
    setSummaryError(null);
    setActiveTab("chat"); // Chat is the default tab after upload on mobile

    try {
      const summaryData = await getSummary(result.doc_hash);
      setSummary(summaryData);
    } catch (err) {
      if (err instanceof ApiError) {
        setSummaryError(err.detail);
      } else if (err instanceof Error) {
        setSummaryError(err.message);
      } else {
        setSummaryError("An unexpected error occurred while loading summary.");
      }
    } finally {
      setIsSummaryLoading(false);
    }
  };

  const handleReset = () => {
    setUploadResult(null);
    setSummary(null);
    setSummaryError(null);
    setIsSummaryLoading(false);
    setActiveTab("chat");
  };

  const handleTabKeyDown = (
    e: React.KeyboardEvent<HTMLButtonElement>,
    index: number
  ) => {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const nextIndex = (index + 1) % MOBILE_TABS.length;
      setActiveTab(MOBILE_TABS[nextIndex].id);
      tabRefs.current[nextIndex]?.focus();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prevIndex = (index - 1 + MOBILE_TABS.length) % MOBILE_TABS.length;
      setActiveTab(MOBILE_TABS[prevIndex].id);
      tabRefs.current[prevIndex]?.focus();
    }
  };

  return (
    <div className="w-full h-full flex flex-col flex-1 min-h-0 overflow-hidden bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors duration-150">
      {!uploadResult ? (
        <div className="flex-1 overflow-y-auto px-4 py-8 sm:py-12">
          <div className="max-w-2xl mx-auto">
            <div className="text-center mb-8">
              <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
                Research Paper Assistant
              </h1>
              <p className="mt-3 text-sm sm:text-base text-slate-600 dark:text-slate-400 max-w-lg mx-auto">
                Upload an academic paper to generate an instant 5-part structured
                summary and chat with answers strictly grounded in the document.
              </p>
            </div>

            <UploadZone onUploaded={handleUploaded} />
          </div>
        </div>
      ) : isDesktop ? (
        /* Desktop: Three columns (Source: 280px, Chat: flex-1, Studio: 360px) */
        <div
          data-testid="desktop-workspace"
          className="flex-1 min-h-0 flex flex-row overflow-hidden w-full h-full"
        >
          {/* Left Panel: Document Info & Upload reset */}
          <aside
            data-testid="desktop-source-panel"
            className="w-[280px] flex-shrink-0 h-full overflow-y-auto border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-colors"
          >
            <SourcePanel
              filename={uploadResult.filename}
              pageCount={uploadResult.page_count}
              chunkCount={uploadResult.chunk_count}
              onReset={handleReset}
              isReady={Boolean(summary && !isSummaryLoading)}
            />
          </aside>

          {/* Center Column: Q&A Chat */}
          <section
            data-testid="desktop-chat-panel"
            className="flex-1 min-w-0 h-full overflow-hidden p-3 sm:p-4 bg-slate-50 dark:bg-slate-950 transition-colors"
          >
            <ChatPanel docHash={uploadResult.doc_hash} />
          </section>

          {/* Right Column: Structured Summary Studio */}
          <aside
            data-testid="desktop-studio-panel"
            className="w-[360px] flex-shrink-0 h-full overflow-y-auto border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-colors"
          >
            <StudioPanel
              summary={summary}
              isLoading={isSummaryLoading}
              error={summaryError}
            />
          </aside>
        </div>
      ) : (
        /* Mobile: Single visible panel with bottom tab bar */
        <div
          data-testid="mobile-workspace"
          className="flex-1 min-h-0 flex flex-col overflow-hidden w-full h-full"
        >
          {/* Active Panel View */}
          <div className="flex-1 min-h-0 overflow-y-auto">
            {activeTab === "source" && (
              <div className="h-full">
                <SourcePanel
                  filename={uploadResult.filename}
                  pageCount={uploadResult.page_count}
                  chunkCount={uploadResult.chunk_count}
                  onReset={handleReset}
                  isReady={Boolean(summary && !isSummaryLoading)}
                />
              </div>
            )}
            {activeTab === "chat" && (
              <div className="h-full p-2.5 sm:p-3 bg-slate-50 dark:bg-slate-950">
                <ChatPanel docHash={uploadResult.doc_hash} />
              </div>
            )}
            {activeTab === "studio" && (
              <div className="h-full">
                <StudioPanel
                  summary={summary}
                  isLoading={isSummaryLoading}
                  error={summaryError}
                />
              </div>
            )}
          </div>

          {/* Mobile Bottom Tab Bar */}
          <nav
            role="tablist"
            aria-label="Workspace tabs"
            className="h-16 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-around flex-shrink-0 px-2 pb-safe shadow-lg transition-colors"
          >
            {MOBILE_TABS.map((tab, index) => {
              const isSelected = activeTab === tab.id;
              const Icon = tab.icon;

              return (
                <button
                  key={tab.id}
                  ref={(el) => {
                    tabRefs.current[index] = el;
                  }}
                  role="tab"
                  id={`tab-${tab.id}`}
                  aria-selected={isSelected}
                  aria-controls={`panel-${tab.id}`}
                  tabIndex={isSelected ? 0 : -1}
                  onClick={() => setActiveTab(tab.id)}
                  onKeyDown={(e) => handleTabKeyDown(e, index)}
                  className={`flex-1 flex flex-col items-center justify-center py-2 px-2 rounded-xl text-xs font-medium transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 min-h-[46px] ${
                    isSelected
                      ? "text-blue-600 dark:text-blue-400 bg-blue-50/80 dark:bg-blue-950/70 shadow-sm"
                      : "text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800/60"
                  }`}
                >
                  <Icon className="w-4 h-4 mb-1" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>
        </div>
      )}
    </div>
  );
}
