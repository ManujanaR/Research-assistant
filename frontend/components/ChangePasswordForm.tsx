"use client";

import React, { useRef, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { ApiError, changePassword } from "@/lib/api";

export interface ChangePasswordFormProps {
  onSuccess?: () => void;
  onCancel?: () => void;
}

export function ChangePasswordForm({
  onSuccess,
  onCancel,
}: ChangePasswordFormProps) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const [currentError, setCurrentError] = useState<string | null>(null);
  const [newError, setNewError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const currentPasswordRef = useRef<HTMLInputElement>(null);
  const newPasswordRef = useRef<HTMLInputElement>(null);
  const confirmPasswordRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentError(null);
    setNewError(null);
    setConfirmError(null);
    setGeneralError(null);
    setSuccessMessage(null);

    // 1. Validation checks with focus moved to first error
    if (!currentPassword) {
      setCurrentError("Current password is required.");
      currentPasswordRef.current?.focus();
      return;
    }

    if (newPassword.length < 8) {
      setNewError("Password must be at least 8 characters.");
      newPasswordRef.current?.focus();
      return;
    }

    if (currentPassword === newPassword) {
      setNewError("New password must be different from current password.");
      newPasswordRef.current?.focus();
      return;
    }

    if (newPassword !== confirmPassword) {
      setConfirmError("Passwords do not match.");
      confirmPasswordRef.current?.focus();
      return;
    }

    setIsSubmitting(true);
    try {
      await changePassword(currentPassword, newPassword);
      setSuccessMessage("Password changed. Other devices have been signed out.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      if (onSuccess) {
        onSuccess();
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setCurrentError("Current password is incorrect.");
          currentPasswordRef.current?.focus();
        } else if (err.status === 422) {
          setNewError(err.detail);
          newPasswordRef.current?.focus();
        } else {
          setGeneralError(err.detail);
        }
      } else if (err instanceof Error) {
        setGeneralError(err.message);
      } else {
        setGeneralError("An unexpected error occurred while changing password.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form
      data-testid="change-password-form"
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 text-left"
    >
      {/* Current password field */}
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="current-password"
          className="text-xs sm:text-sm font-medium text-text-primary"
        >
          Current password
        </label>
        <div className="relative flex items-center">
          <input
            ref={currentPasswordRef}
            id="current-password"
            data-testid="current-password-input"
            type={showCurrent ? "text" : "password"}
            value={currentPassword}
            onChange={(e) => {
              setCurrentPassword(e.target.value);
              if (currentError) setCurrentError(null);
            }}
            placeholder="••••••••"
            aria-describedby={currentError ? "current-password-error" : undefined}
            className="w-full px-3 py-2 pr-10 text-sm rounded-xl border border-border-subtle bg-bg-base text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors"
          />
          <button
            type="button"
            data-testid="toggle-current-password"
            onClick={() => setShowCurrent((prev) => !prev)}
            aria-label={showCurrent ? "Hide current password" : "Show current password"}
            className="absolute right-2.5 p-1 text-text-secondary hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
          >
            {showCurrent ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        {currentError && (
          <div
            id="current-password-error"
            data-testid="current-password-error"
            role="alert"
            className="text-xs text-red-600 dark:text-red-400 mt-1"
          >
            {currentError}
          </div>
        )}
      </div>

      {/* New password field */}
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="new-password"
          className="text-xs sm:text-sm font-medium text-text-primary"
        >
          New password
        </label>
        <div className="relative flex items-center">
          <input
            ref={newPasswordRef}
            id="new-password"
            data-testid="new-password-input"
            type={showNew ? "text" : "password"}
            value={newPassword}
            onChange={(e) => {
              setNewPassword(e.target.value);
              if (newError) setNewError(null);
            }}
            placeholder="••••••••"
            aria-describedby={newError ? "new-password-error" : undefined}
            className="w-full px-3 py-2 pr-10 text-sm rounded-xl border border-border-subtle bg-bg-base text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors"
          />
          <button
            type="button"
            data-testid="toggle-new-password"
            onClick={() => setShowNew((prev) => !prev)}
            aria-label={showNew ? "Hide new password" : "Show new password"}
            className="absolute right-2.5 p-1 text-text-secondary hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
          >
            {showNew ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        {newError && (
          <div
            id="new-password-error"
            data-testid="new-password-error"
            role="alert"
            className="text-xs text-red-600 dark:text-red-400 mt-1"
          >
            {newError}
          </div>
        )}
      </div>

      {/* Confirm password field */}
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="confirm-password"
          className="text-xs sm:text-sm font-medium text-text-primary"
        >
          Confirm new password
        </label>
        <div className="relative flex items-center">
          <input
            ref={confirmPasswordRef}
            id="confirm-password"
            data-testid="confirm-password-input"
            type={showConfirm ? "text" : "password"}
            value={confirmPassword}
            onChange={(e) => {
              setConfirmPassword(e.target.value);
              if (confirmError) setConfirmError(null);
            }}
            placeholder="••••••••"
            aria-describedby={confirmError ? "confirm-password-error" : undefined}
            className="w-full px-3 py-2 pr-10 text-sm rounded-xl border border-border-subtle bg-bg-base text-text-primary placeholder:text-text-secondary/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors"
          />
          <button
            type="button"
            data-testid="toggle-confirm-password"
            onClick={() => setShowConfirm((prev) => !prev)}
            aria-label={showConfirm ? "Hide confirm password" : "Show confirm password"}
            className="absolute right-2.5 p-1 text-text-secondary hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
          >
            {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        {confirmError && (
          <div
            id="confirm-password-error"
            data-testid="confirm-password-error"
            role="alert"
            className="text-xs text-red-600 dark:text-red-400 mt-1"
          >
            {confirmError}
          </div>
        )}
      </div>

      {generalError && (
        <div
          data-testid="change-password-general-error"
          role="alert"
          className="text-xs text-red-600 dark:text-red-400"
        >
          {generalError}
        </div>
      )}

      {successMessage && (
        <div
          data-testid="change-password-success"
          role="status"
          className="text-xs text-green-600 dark:text-green-400 font-medium"
        >
          {successMessage}
        </div>
      )}

      <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-border-subtle">
        {onCancel && (
          <button
            type="button"
            data-testid="change-password-cancel-btn"
            onClick={onCancel}
            disabled={isSubmitting}
            className="px-3.5 py-2 text-xs sm:text-sm font-medium rounded-xl border border-border-subtle hover:bg-surface-pill text-text-secondary hover:text-text-primary transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            Cancel
          </button>
        )}
        <button
          type="submit"
          data-testid="change-password-submit-btn"
          disabled={isSubmitting}
          className="px-4 py-2 text-xs sm:text-sm font-medium rounded-xl bg-blue-600 hover:bg-blue-700 text-white transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-50"
        >
          {isSubmitting ? "Changing..." : "Change password"}
        </button>
      </div>
    </form>
  );
}
