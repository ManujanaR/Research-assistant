"use client";

import React, { useEffect, useRef, useState } from "react";
import { BookOpen, MessageSquare, Sparkles } from "lucide-react";
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

  // Mobile navigation state: default to 'source' before upload, switch to 'chat' after upload
  const [activeTab, setActiveTab] = useState<MobileTab>("source");
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
    setActiveTab("source");
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
    <div className="w-full h-full flex flex-col flex-1 min-h-0 overflow-hidden bg-bg-base text-text-primary transition-colors duration-150">
      {isDesktop ? (
        /* Desktop: Three columns (Source: 280px, Chat: flex-1, Studio: 360px) */
        <div
          data-testid="desktop-workspace"
          className="flex-1 min-h-0 flex flex-row overflow-hidden w-full h-full"
        >
          {/* Left Panel: Document Info & Upload reset */}
          <aside
            data-testid="desktop-source-panel"
            className="w-[280px] flex-shrink-0 h-full overflow-y-auto border-r border-border-subtle bg-surface-panel transition-colors"
          >
            <SourcePanel
              filename={uploadResult?.filename}
              pageCount={uploadResult?.page_count}
              chunkCount={uploadResult?.chunk_count}
              onReset={handleReset}
              isReady={Boolean(summary && !isSummaryLoading)}
              onUploaded={handleUploaded}
            />
          </aside>

          {/* Center Column: Q&A Chat */}
          <section
            data-testid="desktop-chat-panel"
            className="flex-1 min-w-0 h-full overflow-hidden p-3 sm:p-4 bg-bg-base transition-colors"
          >
            <ChatPanel docHash={uploadResult?.doc_hash ?? ""} />
          </section>

          {/* Right Column: Structured Summary Studio */}
          <aside
            data-testid="desktop-studio-panel"
            className="w-[360px] flex-shrink-0 h-full overflow-y-auto border-l border-border-subtle bg-surface-panel transition-colors"
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
                  filename={uploadResult?.filename}
                  pageCount={uploadResult?.page_count}
                  chunkCount={uploadResult?.chunk_count}
                  onReset={handleReset}
                  isReady={Boolean(summary && !isSummaryLoading)}
                  onUploaded={handleUploaded}
                />
              </div>
            )}
            {activeTab === "chat" && (
              <div className="h-full p-2.5 sm:p-3 bg-bg-base">
                <ChatPanel docHash={uploadResult?.doc_hash ?? ""} />
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
            className="h-16 border-t border-border-subtle bg-surface-panel flex items-center justify-around flex-shrink-0 px-2 pb-safe shadow-lg transition-colors"
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
                      ? "text-blue-600 dark:text-accent-blue bg-surface-pill shadow-sm"
                      : "text-text-muted hover:text-text-primary hover:bg-surface-pill-hover"
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
