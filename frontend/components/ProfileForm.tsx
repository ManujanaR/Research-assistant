"use client";

import React, { useState } from "react";
import { ApiError } from "@/lib/api";

export interface ProfileFormProps {
  initialDisplayName?: string | null;
  onSave: (name: string | null) => Promise<void> | void;
  onCancel?: () => void;
}

export function ProfileForm({
  initialDisplayName,
  onSave,
  onCancel,
}: ProfileFormProps) {
  const [name, setName] = useState<string>(initialDisplayName ?? "");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmed = name.trim();

    if (trimmed.length > 60) {
      setError("Display name must be 60 characters or fewer.");
      return;
    }

    for (const ch of trimmed) {
      if (
        !(
          /[a-zA-Z0-9]/.test(ch) ||
          ch === " " ||
          ch === "." ||
          ch === "'" ||
          ch === "-"
        )
      ) {
        setError("Display name contains characters that are not allowed.");
        return;
      }
    }

    setIsSaving(true);
    try {
      await onSave(trimmed.length > 0 ? trimmed : null);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to update profile.");
      }
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form
      data-testid="profile-form"
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 text-left"
    >
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <label
            htmlFor="display-name-input"
            className="text-xs sm:text-sm font-medium text-text-primary"
          >
            Display name
          </label>
          <span
            data-testid="profile-char-counter"
            className="text-xs text-text-secondary"
          >
            {name.length}/60
          </span>
        </div>
        <input
          id="display-name-input"
          data-testid="profile-name-input"
          type="text"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            if (error) setError(null);
          }}
          placeholder="e.g. Ada Lovelace"
          aria-describedby={error ? "display-name-error" : undefined}
          className="w-full px-3 py-2 text-sm rounded-xl border border-border-subtle bg-bg-base text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors"
        />
        {error && (
          <div
            id="display-name-error"
            data-testid="profile-form-error"
            role="alert"
            className="text-xs text-red-600 dark:text-red-400 mt-1"
          >
            {error}
          </div>
        )}
      </div>

      <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-border-subtle">
        {onCancel && (
          <button
            type="button"
            data-testid="profile-cancel-btn"
            onClick={onCancel}
            disabled={isSaving}
            className="px-3.5 py-2 text-xs sm:text-sm font-medium rounded-xl border border-border-subtle hover:bg-surface-pill text-text-secondary hover:text-text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            Cancel
          </button>
        )}
        <button
          type="submit"
          data-testid="profile-save-btn"
          disabled={isSaving}
          className="px-4 py-2 text-xs sm:text-sm font-medium rounded-xl bg-blue-600 hover:bg-blue-700 text-white transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-50"
        >
          {isSaving ? "Saving..." : "Save"}
        </button>
      </div>
    </form>
  );
}
