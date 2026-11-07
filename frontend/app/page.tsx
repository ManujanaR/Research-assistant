"use client";

import React, { useState } from "react";
import { FileText, ArrowLeft, Layers, BookOpen } from "lucide-react";
import { UploadZone } from "@/components/UploadZone";
import { SummaryView } from "@/components/SummaryView";
import { ChatPanel } from "@/components/ChatPanel";
import { ApiError, SummaryResponse, UploadResponse, getSummary } from "@/lib/api";

export default function Home() {
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [isSummaryLoading, setIsSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const handleUploaded = async (result: UploadResponse) => {
    setUploadResult(result);
    setIsSummaryLoading(true);
    setSummaryError(null);

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
  };

  return (
    <div className="w-full">
      {!uploadResult ? (
        <div className="max-w-2xl mx-auto py-8">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
              Research Paper Assistant
            </h1>
            <p className="mt-3 text-base text-slate-600 max-w-lg mx-auto">
              Upload an academic paper to generate an instant 5-part structured
              summary and chat with answers strictly grounded in the document.
            </p>
          </div>

          <UploadZone onUploaded={handleUploaded} />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Paper Info & Actions Bar */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm">
            <div className="flex items-center gap-3 min-w-0">
              <div className="p-2.5 bg-blue-50 text-blue-600 rounded-lg flex-shrink-0">
                <FileText className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <h2 className="text-sm sm:text-base font-semibold text-slate-900 truncate">
                  {uploadResult.filename}
                </h2>
                <div className="flex items-center gap-4 mt-1 text-xs text-slate-500">
                  <span className="flex items-center gap-1">
                    <BookOpen className="w-3.5 h-3.5" />
                    {uploadResult.page_count}{" "}
                    {uploadResult.page_count === 1 ? "page" : "pages"}
                  </span>
                  <span className="flex items-center gap-1">
                    <Layers className="w-3.5 h-3.5" />
                    {uploadResult.chunk_count} chunks indexed
                  </span>
                </div>
              </div>
            </div>

            <button
              type="button"
              onClick={handleReset}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors flex-shrink-0"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Upload another paper
            </button>
          </div>

          {/* Main Grid: Summary View & Chat Panel */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
            {/* Left Column: Structured Summary */}
            <section className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-slate-900">
                  Structured Paper Summary
                </h3>
                {isSummaryLoading && (
                  <span className="text-xs text-blue-600 font-medium animate-pulse">
                    Generating summary...
                  </span>
                )}
              </div>
              <SummaryView
                summary={summary}
                isLoading={isSummaryLoading}
                error={summaryError}
              />
            </section>

            {/* Right Column: Grounded Q&A Chat */}
            <section className="h-[750px] sticky top-20">
              <ChatPanel docHash={uploadResult.doc_hash} />
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
