"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  HelpCircle,
  ShieldCheck,
  Code,
  Loader2,
} from "lucide-react";
import {
  CredibilityResponse,
  getDocumentCredibility,
} from "@/lib/api";

export interface CredibilityCardProps {
  docHash?: string | null;
}

const POLLING_INTERVAL_MS = 2000;
const POLLING_TIMEOUT_MS = 30000;

export function CredibilityCard({ docHash }: CredibilityCardProps) {
  const [data, setData] = useState<CredibilityResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isTimeout, setIsTimeout] = useState<boolean>(false);
  const [hasError, setHasError] = useState<boolean>(false);

  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!docHash) {
      setData(null);
      setIsLoading(false);
      setIsTimeout(false);
      setHasError(false);
      return;
    }

    setIsLoading(true);
    setIsTimeout(false);
    setHasError(false);
    setData(null);

    // Strict 30-second polling timeout
    timeoutRef.current = setTimeout(() => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      setIsLoading(false);
      setIsTimeout(true);
    }, POLLING_TIMEOUT_MS);

    const fetchStatus = async () => {
      try {
        const res = await getDocumentCredibility(docHash);
        setData(res);

        if (res.status === "completed" || res.status === "error") {
          if (intervalRef.current) clearInterval(intervalRef.current);
          if (timeoutRef.current) clearTimeout(timeoutRef.current);
          setIsLoading(false);
        }
      } catch {
        // In case of network errors during poll, fail gracefully
        if (intervalRef.current) clearInterval(intervalRef.current);
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        setIsLoading(false);
        setHasError(true);
      }
    };

    fetchStatus();
    intervalRef.current = setInterval(fetchStatus, POLLING_INTERVAL_MS);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [docHash]);

  // Empty state: completely hidden when no document uploaded
  if (!docHash) {
    return null;
  }

  // Timeout or Error State
  if (isTimeout || hasError) {
    return (
      <div
        data-testid="credibility-card-error"
        className="bg-surface-elevated border border-border-subtle rounded-2xl p-4 text-xs text-text-secondary space-y-2 transition-colors"
      >
        <div className="flex items-center gap-2 text-text-muted">
          <AlertCircle className="w-4 h-4 text-amber-500" />
          <span className="font-semibold text-text-primary">
            Analysis unavailable
          </span>
        </div>
        <p className="text-[11px] text-text-muted">
          {isTimeout
            ? "Signal verification timed out (> 30s). Document remains fully usable for Q&A and summary."
            : "Could not retrieve credibility signals at this time."}
        </p>
      </div>
    );
  }

  // Processing State (Skeleton / Spinner)
  if (isLoading || !data || data.status === "processing") {
    return (
      <div
        data-testid="credibility-card-processing"
        className="bg-surface-elevated border border-border-subtle rounded-2xl p-4 space-y-3 transition-colors animate-pulse"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
            <span className="text-xs font-semibold text-text-primary">
              Analyzing publication signals...
            </span>
          </div>
        </div>
        <div className="space-y-2 pt-1">
          <div className="h-3 bg-surface-pill rounded-md w-3/4" />
          <div className="h-3 bg-surface-pill rounded-md w-1/2" />
          <div className="h-3 bg-surface-pill rounded-md w-2/3" />
        </div>
      </div>
    );
  }

  // Completed State
  const { signals, badge_label, badge_variant, score, disclaimer } = data;

  const badgeStyles =
    badge_variant === "success"
      ? "text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800/60"
      : badge_variant === "warning"
      ? "text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800/60"
      : "text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700";

  return (
    <div
      data-testid="credibility-card"
      className="bg-surface-elevated border border-border-subtle rounded-2xl p-4 text-xs space-y-3 transition-colors"
    >
      {/* Header with Shield Icon & Badge */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-semibold text-text-primary">
          <ShieldCheck className="w-4 h-4 text-blue-600 dark:text-accent-blue" />
          <span>Credibility Signals</span>
        </div>
        <span
          data-testid="credibility-badge"
          className={`inline-flex items-center px-2 py-0.5 text-[10px] font-semibold border rounded-full truncate max-w-[150px] ${badgeStyles}`}
          title={badge_label}
        >
          {badge_label}
        </span>
      </div>

      {/* 5-Row Signal Checklist */}
      <div className="space-y-2 pt-1 border-t border-border-subtle/60 text-text-secondary">
        {/* 1. Venue */}
        <div className="flex items-start justify-between gap-2">
          <span className="flex items-center gap-1.5 text-text-secondary">
            {(signals.venue_points ?? 0) > 0 ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
            ) : (
              <XCircle className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
            )}
            Venue
          </span>
          <span
            className="font-medium text-text-primary text-right truncate max-w-[130px]"
            title={signals.matched_venue || "Unverified"}
          >
            {signals.matched_venue || "Unverified"}
          </span>
        </div>

        {/* 2. References */}
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-text-secondary whitespace-nowrap">
            {(signals.reference_points ?? 0) >= 10 ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
            )}
            References
          </span>
          <div className="flex items-center gap-1 text-right flex-shrink-0">
            <span
              data-testid="ref-count-text"
              className="font-medium text-text-primary whitespace-nowrap"
            >
              {(signals.reference_count_estimated ?? signals.estimated_references ?? 0)} detected
            </span>
            {(signals.reference_count_estimated ?? signals.estimated_references ?? 0) < 20 && (
              <span
                data-testid="ref-estimate-tooltip"
                title="Estimated from layout"
                className="cursor-help inline-flex items-center text-text-muted hover:text-text-primary flex-shrink-0"
              >
                <HelpCircle className="w-3 h-3 text-amber-500" />
              </span>
            )}
          </div>
        </div>

        {/* 3. Citations */}
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-text-secondary whitespace-nowrap">
            {(signals.citation_points ?? 0) >= 15 ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
            )}
            Citations
          </span>
          <span className="font-medium text-text-primary text-right whitespace-nowrap flex-shrink-0">
            {badge_label === "Indexed in OpenAlex" || (signals.citation_count ?? signals.recorded_citations ?? 0) > 0
              ? `${signals.citation_count ?? signals.recorded_citations ?? 0} recorded`
              : "Recent baseline"}
          </span>
        </div>

        {/* 4. Affiliation */}
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-text-secondary whitespace-nowrap">
            {(signals.author_academic_affiliation ?? signals.has_academic_affiliation) ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
            ) : (
              <XCircle className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
            )}
            Affiliation
          </span>
          <span className="font-medium text-text-primary text-right truncate max-w-[130px]">
            {(signals.author_academic_affiliation ?? signals.has_academic_affiliation)
              ? "Academic (.edu / ac)"
              : "No academic domain"}
          </span>
        </div>

        {/* 5. Structure */}
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-text-secondary whitespace-nowrap">
            {(signals.structure_sections_found ?? (signals.structure_points ? Math.round(signals.structure_points / 2.5) : 0)) >= 3 ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
            )}
            Structure
          </span>
          <span
            data-testid="section-count-text"
            className="font-medium text-text-primary text-right whitespace-nowrap flex-shrink-0"
          >
            {(signals.structure_sections_found ?? (signals.structure_points ? Math.round(signals.structure_points / 2.5) : 0))}/4 sections
          </span>
        </div>
      </div>

      {/* Bonus points row if open artifacts detected */}
      {signals.open_artifacts_detected && (
        <div
          data-testid="credibility-bonus"
          className="flex items-center gap-1.5 pt-1.5 border-t border-border-subtle/50 text-[11px] text-emerald-600 dark:text-emerald-400 font-medium"
        >
          <Code className="w-3.5 h-3.5" />
          <span>+5 bonus: Public code/data repo detected</span>
        </div>
      )}

      {/* Secondary composite score display */}
      <div className="pt-2 border-t border-border-subtle flex items-center justify-between text-[11px]">
        <span className="text-text-muted">Reporting signals score</span>
        <span
          data-testid="credibility-score-figure"
          className="font-bold text-text-primary"
        >
          {score}/100
        </span>
      </div>

      {/* Required Disclaimer Subtext */}
      <p className="text-[10px] text-text-muted leading-relaxed italic pt-0.5">
        {disclaimer ||
          "Reporting signals score. Does not verify experimental correctness or research quality."}
      </p>
    </div>
  );
}
