"use client";

import React, { useEffect, useRef, useState } from "react";
import { BookOpen, MessageSquare, Sparkles } from "lucide-react";
import { AuthPanel } from "@/components/AuthPanel";
import { ProfileMenu } from "@/components/ProfileMenu";
import { SourcePanel } from "@/components/SourcePanel";
import { StudioPanel } from "@/components/StudioPanel";
import { ChatPanel } from "@/components/ChatPanel";
import { ExportButton } from "@/components/ExportButton";
import { ViewPdfButton } from "@/components/ViewPdfButton";
import { PdfViewerDrawer } from "@/components/PdfViewerDrawer";
import { HelpButton } from "@/components/HelpButton";
import { HelpPanel } from "@/components/HelpPanel";
import {
  ApiError,
  ExportMessage,
  SummaryResponse,
  UploadResponse,
  UserResponse,
  getMe,
  getProfile,
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
  { id: "studio", label: "Summary", icon: Sparkles },
] as const;

export default function Home() {
  const [currentUser, setCurrentUser] = useState<UserResponse | null>(null);
  const [isCheckingSession, setIsCheckingSession] = useState(true);

  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [isSummaryLoading, setIsSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [messages] = useState<ExportMessage[]>([]);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const helpButtonRef = useRef<HTMLButtonElement | null>(null);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [isPdfViewerOpen, setIsPdfViewerOpen] = useState(false);
  const currentBlobUrlRef = useRef<string | null>(null);
  const viewPdfButtonRef = useRef<HTMLButtonElement | null>(null);

  // Desktop summary panel adjustable width (default 380px, min 280px, max 700px)
  const [summaryWidth, setSummaryWidth] = useState(380);
  const isResizingRef = useRef(false);

  const startResizing = (mouseDownEvent: React.MouseEvent) => {
    mouseDownEvent.preventDefault();
    isResizingRef.current = true;
    const startX = mouseDownEvent.clientX;
    const startWidth = summaryWidth;

    const onMouseMove = (moveEvent: MouseEvent) => {
      if (!isResizingRef.current) return;
      const delta = startX - moveEvent.clientX;
      const newWidth = Math.min(Math.max(startWidth + delta, 280), 700);
      setSummaryWidth(newWidth);
    };

    const onMouseUp = () => {
      isResizingRef.current = false;
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  };

  // Mobile navigation state: default to 'chat' consistently on server and client
  const [activeTab, setActiveTab] = useState<MobileTab>("chat");
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    let isMounted = true;
    async function checkSession() {
      try {
        const user = await getMe();
        let fullUser: UserResponse = user;
        try {
          const profile = await getProfile();
          if (profile && profile.id) {
            fullUser = profile;
          }
        } catch {
          // Fall back to getMe user
        }
        if (isMounted) {
          setCurrentUser(fullUser);
        }
      } catch {
        if (isMounted) {
          setCurrentUser(null);
        }
      } finally {
        if (isMounted) {
          setIsCheckingSession(false);
        }
      }
    }

    checkSession();

    return () => {
      isMounted = false;
    };
  }, []);

  // Hydration & memory rule: capture file selection in onChange/drop, store blob URL in state,
  // and revoke previous blob URL safely when a new file is uploaded or session resets.
  useEffect(() => {
    const handleFileChange = (e: Event) => {
      const target = e.target as HTMLInputElement | null;
      if (target && target.type === "file" && target.files && target.files.length > 0) {
        const file = target.files[0];
        if (file && file.type === "application/pdf") {
          if (currentBlobUrlRef.current) {
            URL.revokeObjectURL(currentBlobUrlRef.current);
          }
          const url = URL.createObjectURL(file);
          currentBlobUrlRef.current = url;
          setPdfBlobUrl(url);
        }
      }
    };

    const handleFileDrop = (e: DragEvent) => {
      const files = e.dataTransfer?.files;
      if (files && files.length > 0 && files[0].type === "application/pdf") {
        if (currentBlobUrlRef.current) {
          URL.revokeObjectURL(currentBlobUrlRef.current);
        }
        const url = URL.createObjectURL(files[0]);
        currentBlobUrlRef.current = url;
        setPdfBlobUrl(url);
      }
    };

    document.addEventListener("change", handleFileChange, true);
    document.addEventListener("drop", handleFileDrop, true);
    return () => {
      document.removeEventListener("change", handleFileChange, true);
      document.removeEventListener("drop", handleFileDrop, true);
    };
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
    if (currentBlobUrlRef.current) {
      URL.revokeObjectURL(currentBlobUrlRef.current);
      currentBlobUrlRef.current = null;
    }
    setPdfBlobUrl(null);
    setIsPdfViewerOpen(false);
    setUploadResult(null);
    setSummary(null);
    setSummaryError(null);
    setIsSummaryLoading(false);
    setActiveTab("chat");
  };

  const handleSignOut = () => {
    setCurrentUser(null);
    handleReset();
  };

  const handleAuthSuccess = (user: UserResponse) => {
    setCurrentUser(user);
    handleReset();
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

  // 1. Startup screen while checking session
  if (isCheckingSession) {
    return (
      <div
        data-testid="startup-screen"
        className="w-full h-full flex flex-1 flex-col items-center justify-center bg-bg-base text-text-primary p-6 transition-colors"
      >
        <div className="flex flex-col items-center gap-4">
          <div className="flex items-center gap-2 select-none">
            <span className="text-3xl font-bold tracking-tight text-blue-600 dark:text-accent-blue">
              Research
            </span>
            <span className="text-3xl font-medium text-slate-700 dark:text-text-primary">
              Assistant
            </span>
          </div>
          <div className="flex items-center gap-2.5 text-text-secondary text-sm">
            <div className="w-4 h-4 border-2 border-blue-600 dark:border-accent-blue border-t-transparent rounded-full animate-spin" />
            <span>Loading...</span>
          </div>
        </div>
      </div>
    );
  }

  // 2. Unauthenticated: AuthPanel
  if (!currentUser) {
    return (
      <>
        <HelpButton
          ref={helpButtonRef}
          isOpen={isHelpOpen}
          onClick={() => setIsHelpOpen((prev) => !prev)}
        />
        <AuthPanel onSuccess={handleAuthSuccess} />
        <PdfViewerDrawer
        isOpen={isPdfViewerOpen}
        onClose={() => setIsPdfViewerOpen(false)}
        blobUrl={pdfBlobUrl}
        filename={uploadResult?.filename}
        triggerRef={viewPdfButtonRef}
      />

      <HelpPanel
          isOpen={isHelpOpen}
          onClose={() => setIsHelpOpen(false)}
          triggerRef={helpButtonRef}
        />
      </>
    );
  }

  // 3. Authenticated: Workspace
  return (
    <div className="w-full h-full flex flex-col flex-1 min-h-0 overflow-hidden bg-bg-base text-text-primary transition-colors duration-150">
      <ProfileMenu
        user={currentUser}
        onUserUpdate={(updated) => setCurrentUser(updated)}
        onSignOut={handleSignOut}
      />

      <ExportButton
        docHash={summary ? uploadResult?.doc_hash : null}
        messages={messages.slice(-200)}
      />

      <ViewPdfButton
        ref={viewPdfButtonRef}
        hasDocument={Boolean(uploadResult)}
        isOpen={isPdfViewerOpen}
        onClick={() => setIsPdfViewerOpen((prev) => !prev)}
      />

      <HelpButton
        ref={helpButtonRef}
        isOpen={isHelpOpen}
        onClick={() => setIsHelpOpen((prev) => !prev)}
      />

      {/* Desktop: Three columns (hidden on phone/tablet, flex on lg and above) */}
      <div
        data-testid="desktop-workspace"
        className="hidden lg:flex flex-1 min-h-0 flex-row overflow-hidden w-full h-full"
      >
        {/* Left Panel: Document Info & Upload reset */}
        <aside
          data-testid="desktop-source-panel"
          className="w-[280px] flex-shrink-0 h-full overflow-y-auto border-r border-border-subtle bg-surface-panel transition-colors"
        >
          <SourcePanel
            docHash={uploadResult?.doc_hash}
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

        {/* Right Column: Structured Summary */}
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

      {/* Mobile & Tablet: Single visible panel with bottom tab bar (flex on phone/tablet, hidden on lg and above) */}
      <div
        data-testid="mobile-workspace"
        className="flex lg:hidden flex-1 min-h-0 flex-col overflow-hidden w-full h-full"
      >
        {/* Active Panel View */}
        <div className="flex-1 min-h-0 overflow-y-auto w-full">
          {activeTab === "source" && (
            <div className="h-full w-full">
              <SourcePanel
                docHash={uploadResult?.doc_hash}
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
            <div className="h-full w-full p-2.5 sm:p-4 bg-bg-base">
              <ChatPanel docHash={uploadResult?.doc_hash ?? ""} />
            </div>
          )}
          {activeTab === "studio" && (
            <div className="h-full w-full">
              <StudioPanel
                summary={summary}
                isLoading={isSummaryLoading}
                error={summaryError}
              />
            </div>
          )}
        </div>

        {/* Mobile/Tablet Bottom Tab Bar */}
        <nav
          role="tablist"
          aria-label="Workspace tabs"
          className="w-full h-16 border-t border-border-subtle bg-surface-panel flex items-center justify-around flex-shrink-0 px-2 pb-[env(safe-area-inset-bottom)] shadow-lg transition-colors lg:hidden"
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
                className={`flex-1 flex flex-col items-center justify-center py-2 px-2 rounded-xl text-xs font-medium transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 min-h-[44px] ${
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

      <PdfViewerDrawer
        isOpen={isPdfViewerOpen}
        onClose={() => setIsPdfViewerOpen(false)}
        blobUrl={pdfBlobUrl}
        filename={uploadResult?.filename}
        triggerRef={viewPdfButtonRef}
      />

      <HelpPanel
        isOpen={isHelpOpen}
        onClose={() => setIsHelpOpen(false)}
        triggerRef={helpButtonRef}
      />
    </div>
  );
}
