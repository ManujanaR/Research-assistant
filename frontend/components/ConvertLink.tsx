"use client";

import React from "react";
import { ExternalLink } from "lucide-react";

export function ConvertLink() {
  return (
    <div data-testid="convert-link-container" className="w-full space-y-1.5 pt-1">
      <a
        href="https://www.ilovepdf.com"
        target="_blank"
        rel="noopener noreferrer"
        data-testid="convert-other-files-btn"
        className="w-full inline-flex items-center justify-center gap-2 px-3.5 py-2.5 text-xs font-medium text-text-primary bg-surface-pill hover:bg-surface-pill-hover border border-border-subtle rounded-xl transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 min-h-[44px]"
      >
        <span>Convert other files</span>
        <ExternalLink className="w-3.5 h-3.5 text-text-muted" />
      </a>
      <p
        data-testid="convert-link-caption"
        className="text-[11px] text-text-muted text-center leading-normal"
      >
        Opens iLovePDF in a new tab. Your file is sent to iLovePDF, not to us.
      </p>
    </div>
  );
}
