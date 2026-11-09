"use client";

import React, { useEffect, useState, forwardRef } from "react";
import { createPortal } from "react-dom";
import { CircleHelp } from "lucide-react";

export interface HelpButtonProps {
  isOpen: boolean;
  onClick: () => void;
  className?: string;
  buttonRef?: React.RefObject<HTMLButtonElement | null>;
}

export const HelpButton = forwardRef<HTMLButtonElement, HelpButtonProps>(
  ({ isOpen, onClick, className = "", buttonRef }, forwardedRef) => {
    const [portalTarget, setPortalTarget] = useState<Element | null>(null);

    useEffect(() => {
      const headerActions =
        document.querySelector('[data-testid="top-bar-actions"]') ||
        document.querySelector("header.bg-surface-panel .flex.items-center.gap-2\\.5") ||
        document.querySelector("header .flex.items-center.gap-2\\.5");

      if (headerActions) {
        const themeToggle =
          headerActions.querySelector('button[data-testid="theme-toggle"]') ||
          headerActions.querySelector('button[aria-label*="theme" i]') ||
          headerActions.lastElementChild;

        const container = document.createElement("div");
        container.className = "flex items-center shrink-0 min-w-0";
        container.setAttribute("data-testid", "help-button-container");

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
        aria-label="Help"
        aria-expanded={isOpen}
        title="Help"
        data-testid="help-button"
        className={`w-11 h-11 flex items-center justify-center rounded-xl border border-border-subtle bg-surface-panel text-text-secondary hover:bg-surface-pill-hover hover:text-text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 min-h-[44px] min-w-[44px] shrink-0 ${
          isOpen ? "bg-surface-pill text-blue-600 dark:text-accent-blue border-blue-500/30" : ""
        } ${className}`}
      >
        <CircleHelp className="w-4 h-4 text-text-secondary" />
      </button>
    );

    if (portalTarget) {
      return createPortal(button, portalTarget);
    }

    return button;
  }
);

HelpButton.displayName = "HelpButton";
