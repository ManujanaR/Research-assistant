"use client";

import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Lock, LogOut, User as UserIcon, X } from "lucide-react";
import { ProfileForm } from "./ProfileForm";
import { ChangePasswordForm } from "./ChangePasswordForm";
import { signOut, updateProfile, UserResponse } from "@/lib/api";

export interface ProfileMenuProps {
  user: UserResponse;
  onUserUpdate?: (user: UserResponse) => void;
  onSignOut?: () => void;
}

export function computeInitials(displayName?: string | null, email?: string): string {
  const name = displayName?.trim();
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return parts[0].slice(0, 2).toUpperCase();
  }
  if (!email) return "U";
  const localPart = email.split("@")[0].trim();
  const parts = localPart.split(/[._-]/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return localPart.slice(0, 2).toUpperCase() || "U";
}

export function ProfileMenu({ user, onUserUpdate, onSignOut }: ProfileMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [initials, setInitials] = useState<string>("");
  const [activeModal, setActiveModal] = useState<"profile" | "password" | null>(null);
  const [focusedIndex, setFocusedIndex] = useState(0);
  const [portalTarget, setPortalTarget] = useState<Element | null>(null);

  const avatarRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Initials are computed in an effect, not during render
  useEffect(() => {
    setInitials(computeInitials(user.display_name, user.email));
  }, [user.display_name, user.email]);

  // Top bar portal mounting
  useEffect(() => {
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

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;

    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(target) &&
        avatarRef.current &&
        !avatarRef.current.contains(target)
      ) {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Focus management when menu opens
  useEffect(() => {
    if (isOpen) {
      setFocusedIndex(0);
      itemRefs.current[0]?.focus();
    }
  }, [isOpen]);

  // Keyboard navigation for menu
  const handleMenuKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setIsOpen(false);
      avatarRef.current?.focus();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = (focusedIndex + 1) % 3;
      setFocusedIndex(next);
      itemRefs.current[next]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev = (focusedIndex - 1 + 3) % 3;
      setFocusedIndex(prev);
      itemRefs.current[prev]?.focus();
    }
  };

  const handleEditProfileClick = () => {
    setIsOpen(false);
    setActiveModal("profile");
  };

  const handleChangePasswordClick = () => {
    setIsOpen(false);
    setActiveModal("password");
  };

  const handleSignOutClick = async () => {
    setIsOpen(false);
    try {
      await signOut();
    } catch {
      // Regardless of error, proceed with local sign-out
    } finally {
      if (onSignOut) {
        onSignOut();
      }
    }
  };

  const handleProfileSave = async (newName: string | null) => {
    const updated = await updateProfile(newName);
    if (onUserUpdate) {
      onUserUpdate({
        id: updated.id,
        email: updated.email,
        display_name: updated.display_name,
      });
    }
    setActiveModal(null);
  };

  const content = (
    <div className="relative inline-block text-left flex-shrink-0" data-testid="profile-menu-container">
      {/* Avatar button */}
      <button
        ref={avatarRef}
        type="button"
        data-testid="profile-avatar"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="Open profile menu"
        onClick={() => setIsOpen((prev) => !prev)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
            if (!isOpen) {
              e.preventDefault();
              setIsOpen(true);
            }
          }
        }}
        className="w-8 h-8 rounded-full bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs flex items-center justify-center flex-shrink-0 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 shadow-sm"
      >
        {initials}
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div
          ref={menuRef}
          role="menu"
          data-testid="profile-menu-dropdown"
          aria-label="User profile options"
          onKeyDown={handleMenuKeyDown}
          className="absolute right-0 mt-2 w-64 rounded-2xl border border-border-subtle bg-surface-panel shadow-lg py-2 z-50 text-text-primary focus:outline-none transition-colors"
        >
          {/* Header showing name and email as plain text */}
          <div className="px-4 py-2 border-b border-border-subtle mb-1">
            <div
              data-testid="profile-menu-name"
              className="text-sm font-semibold text-text-primary truncate"
            >
              {user.display_name ? user.display_name : "No name set"}
            </div>
            <div
              data-testid="profile-menu-email"
              className="text-xs text-text-secondary truncate"
            >
              {user.email}
            </div>
          </div>

          {/* Menu items */}
          <button
            ref={(el) => {
              itemRefs.current[0] = el;
            }}
            type="button"
            role="menuitem"
            data-testid="menu-item-edit-profile"
            tabIndex={focusedIndex === 0 ? 0 : -1}
            onClick={handleEditProfileClick}
            className="w-full flex items-center gap-2.5 px-4 py-2 text-xs sm:text-sm font-medium hover:bg-surface-pill text-text-primary transition-colors text-left focus:outline-none focus-visible:bg-surface-pill"
          >
            <UserIcon className="w-4 h-4 text-text-secondary" />
            <span>Edit profile</span>
          </button>

          <button
            ref={(el) => {
              itemRefs.current[1] = el;
            }}
            type="button"
            role="menuitem"
            data-testid="menu-item-change-password"
            tabIndex={focusedIndex === 1 ? 0 : -1}
            onClick={handleChangePasswordClick}
            className="w-full flex items-center gap-2.5 px-4 py-2 text-xs sm:text-sm font-medium hover:bg-surface-pill text-text-primary transition-colors text-left focus:outline-none focus-visible:bg-surface-pill"
          >
            <Lock className="w-4 h-4 text-text-secondary" />
            <span>Change password</span>
          </button>

          <div className="my-1 border-t border-border-subtle" />

          <button
            ref={(el) => {
              itemRefs.current[2] = el;
            }}
            type="button"
            role="menuitem"
            data-testid="menu-item-sign-out"
            tabIndex={focusedIndex === 2 ? 0 : -1}
            onClick={handleSignOutClick}
            className="w-full flex items-center gap-2.5 px-4 py-2 text-xs sm:text-sm font-medium hover:bg-surface-pill text-red-600 dark:text-red-400 transition-colors text-left focus:outline-none focus-visible:bg-surface-pill"
          >
            <LogOut className="w-4 h-4" />
            <span>Sign out</span>
          </button>
        </div>
      )}

      {/* Edit Profile Modal Dialog */}
      {activeModal === "profile" && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-profile-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
        >
          <div className="w-full max-w-md rounded-2xl border border-border-subtle bg-surface-panel p-6 shadow-xl relative animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-4 border-b border-border-subtle mb-4">
              <h2
                id="edit-profile-title"
                className="text-base font-semibold text-text-primary"
              >
                Edit profile
              </h2>
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                aria-label="Close dialog"
                className="p-1 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface-pill transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <ProfileForm
              initialDisplayName={user.display_name}
              onSave={handleProfileSave}
              onCancel={() => setActiveModal(null)}
            />
          </div>
        </div>
      )}

      {/* Change Password Modal Dialog */}
      {activeModal === "password" && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="change-password-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
        >
          <div className="w-full max-w-md rounded-2xl border border-border-subtle bg-surface-panel p-6 shadow-xl relative animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-4 border-b border-border-subtle mb-4">
              <h2
                id="change-password-title"
                className="text-base font-semibold text-text-primary"
              >
                Change password
              </h2>
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                aria-label="Close dialog"
                className="p-1 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface-pill transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <ChangePasswordForm
              onCancel={() => setActiveModal(null)}
            />
          </div>
        </div>
      )}
    </div>
  );

  if (portalTarget) {
    return createPortal(content, portalTarget);
  }

  return content;
}
