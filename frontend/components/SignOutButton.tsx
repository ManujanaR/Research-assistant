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
    const headerActions = document.querySelector("header .flex.items-center.gap-2\\.5");

    if (headerActions) {
      const themeToggle =
        headerActions.querySelector('button[aria-label*="theme" i]') ||
        headerActions.querySelector('button[data-testid="theme-toggle"]') ||
        headerActions.lastElementChild;

      const container = document.createElement("div");
      container.className = "flex items-center";
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
      className="flex items-center gap-2 sm:gap-3 text-xs sm:text-sm mr-2"
    >
      <span
        data-testid="user-email-display"
        title={email}
        className="max-w-[110px] xs:max-w-[150px] sm:max-w-[200px] truncate text-text-secondary font-medium select-none"
      >
        {email}
      </span>
      <button
        type="button"
        data-testid="sign-out-btn"
        onClick={handleSignOut}
        disabled={isSigningOut}
        aria-label="Sign out"
        className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg border border-border-subtle bg-surface-pill hover:bg-surface-pill-hover text-text-primary transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-50"
      >
        <LogOut className="w-3.5 h-3.5" />
        <span>{isSigningOut ? "Signing out..." : "Sign out"}</span>
      </button>
    </div>
  );

  if (portalTarget) {
    return createPortal(content, portalTarget);
  }

  return content;
}
