"use client";

import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { LogOut } from "lucide-react";
import { signOut } from "@/lib/api";

export interface SignOutButtonProps {
  email: string;
  onSignOut: () => void;
}

export function SignOutButton({ email, onSignOut }: SignOutButtonProps) {
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [portalTarget, setPortalTarget] = useState<Element | null>(null);

  useEffect(() => {
    // Locate the top bar actions area in layout.tsx (to the left of theme toggle)
    const headerActions =
      document.querySelector('[data-testid="top-bar-actions"]') ||
      document.querySelector("header.bg-surface-panel .flex.items-center.gap-2\\.5") ||
      document.querySelector("header .flex.items-center.gap-2\\.5");

    if (headerActions) {
      const themeToggle =
        headerActions.querySelector('button[aria-label*="theme" i]') ||
        headerActions.querySelector('button[data-testid="theme-toggle"]') ||
        headerActions.lastElementChild;

      const container = document.createElement("div");
      container.className = "flex items-center flex-shrink-0 min-w-0";
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

  const handleSignOut = async () => {
    setIsSigningOut(true);
    try {
      await signOut();
    } catch {
      // Regardless of network error, proceed with local sign-out to return to sign-in page
    } finally {
      setIsSigningOut(false);
      onSignOut();
    }
  };

  const content = (
    <div
      data-testid="user-session-controls"
      className="flex items-center gap-1.5 sm:gap-2.5 text-xs sm:text-sm mr-1.5 sm:mr-2 min-w-0 flex-shrink-0"
    >
      <span
        data-testid="user-email-display"
        title={email}
        className="hidden sm:inline max-w-[110px] md:max-w-[160px] lg:max-w-[220px] truncate text-text-secondary font-medium select-none"
      >
        {email}
      </span>
      <button
        type="button"
        data-testid="sign-out-btn"
        onClick={handleSignOut}
        disabled={isSigningOut}
        aria-label="Sign out"
        title="Sign out"
        className="flex items-center justify-center gap-1.5 px-2.5 sm:px-3 py-1.5 text-xs font-medium rounded-xl border border-border-subtle bg-surface-pill hover:bg-surface-pill-hover text-text-primary transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-50 min-h-[44px] min-w-[44px] sm:min-w-0 flex-shrink-0"
      >
        <LogOut className="w-4 h-4 flex-shrink-0" />
        <span className="hidden sm:inline">
          {isSigningOut ? "Signing out..." : "Sign out"}
        </span>
      </button>
    </div>
  );

  if (portalTarget) {
    return createPortal(content, portalTarget);
  }

  return content;
}
