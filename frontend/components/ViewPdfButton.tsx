"use client";

import React, { useEffect, useState, forwardRef } from "react";
import { createPortal } from "react-dom";
import { FileText } from "lucide-react";

export interface ViewPdfButtonProps {
  hasDocument: boolean;
  isOpen?: boolean;
  onClick: () => void;
  className?: string;
  buttonRef?: React.RefObject<HTMLButtonElement | null>;
}

export const ViewPdfButton = forwardRef<HTMLButtonElement, ViewPdfButtonProps>(
  ({ hasDocument, isOpen = false, onClick, className = "", buttonRef }, forwardedRef) => {
    const [portalTarget, setPortalTarget] = useState<Element | null>(null);

    useEffect(() => {
      if (!hasDocument) {
        setPortalTarget(null);
        return;
      }

      const headerActions =
        document.querySelector('[data-testid="top-bar-actions"]') ||
        document.querySelector("header.bg-surface-panel .flex.items-center.gap-2\\.5") ||
        document.querySelector("header .flex.items-center.gap-2\\.5");

      if (headerActions) {
        // Place between Export and Help controls
        const helpControl =
          headerActions.querySelector('[data-testid="help-button-container"]') ||
          headerActions.querySelector('button[aria-label="Help"]') ||
          headerActions.querySelector('button[data-testid="help-button"]') ||
          headerActions.querySelector('[data-testid="theme-toggle"]') ||
          headerActions.lastElementChild;

        const container = document.createElement("div");
        container.className = "flex items-center shrink-0 min-w-0";
        container.setAttribute("data-testid", "view-pdf-button-container");

        if (helpControl && helpControl.parentNode === headerActions) {
          headerActions.insertBefore(container, helpControl);
        } else {
          headerActions.appendChild(container);
        }

        setPortalTarget(container);

        return () => {
          container.remove();
        };
      }
    }, [hasDocument]);

    if (!hasDocument) {
      return null;
    }

    const setRef = (node: HTMLButtonElement | null) => {
      if (typeof forwardedRef === "function") {
        forwardedRef(node);
      } else if (forwardedRef) {
        (forwardedRef as React.MutableRefObject<HTMLButtonElement | null>).current = node;
      }
      if (buttonRef) {
        (buttonRef as React.MutableRefObject<HTMLButtonElement | null>).current = node;
      }
    };

    const button = (
      <button
        ref={setRef}
        type="button"
        onClick={onClick}
        aria-label="View PDF"
        aria-expanded={isOpen}
        title="View PDF"
        data-testid="view-pdf-button"
        className={`flex items-center justify-center gap-1.5 px-2.5 sm:px-3 py-2 rounded-xl border border-border-subtle bg-surface-panel text-text-secondary hover:bg-surface-pill-hover hover:text-text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 min-h-[44px] min-w-[44px] shrink-0 ${
          isOpen ? "bg-surface-pill text-blue-600 dark:text-accent-blue border-blue-500/30" : ""
        } ${className}`}
      >
        <FileText className="w-4 h-4 text-blue-600 dark:text-accent-blue shrink-0" />
        <span className="hidden sm:inline text-xs font-medium text-text-primary">
          View PDF
        </span>
      </button>
    );

    if (portalTarget) {
      return createPortal(button, portalTarget);
    }

    return button;
  }
);

ViewPdfButton.displayName = "ViewPdfButton";
