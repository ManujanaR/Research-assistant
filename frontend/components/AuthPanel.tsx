"use client";

import React, { useRef, useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { ApiError, UserResponse, signIn, signUp } from "@/lib/api";

export type AuthMode = "signin" | "signup";

export interface AuthPanelProps {
  onSuccess: (user: UserResponse) => void;
  initialMode?: AuthMode;
}

export function AuthPanel({ onSuccess, initialMode = "signin" }: AuthPanelProps) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const errorRef = useRef<HTMLDivElement | null>(null);
  const emailInputRef = useRef<HTMLInputElement | null>(null);
  const passwordInputRef = useRef<HTMLInputElement | null>(null);
  const confirmPasswordInputRef = useRef<HTMLInputElement | null>(null);

  const tabSignInRef = useRef<HTMLButtonElement | null>(null);
  const tabSignUpRef = useRef<HTMLButtonElement | null>(null);

  const switchMode = (newMode: AuthMode) => {
    setMode(newMode);
    setError(null);
    setPassword("");
    setConfirmPassword("");
  };

  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const targetMode: AuthMode = mode === "signin" ? "signup" : "signin";
      switchMode(targetMode);
      if (targetMode === "signin") {
        tabSignInRef.current?.focus();
      } else {
        tabSignUpRef.current?.focus();
      }
    }
  };

  const setAndFocusError = (errorMessage: string) => {
    setError(errorMessage);
    // Request animation frame ensures DOM update has rendered before focusing
    requestAnimationFrame(() => {
      errorRef.current?.focus();
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Client-side validations
    if (mode === "signup") {
      if (password !== confirmPassword) {
        setAndFocusError("Passwords do not match.");
        return;
      }
      if (password.length < 8) {
        setAndFocusError("Password must be at least 8 characters.");
        return;
      }
    }

    setIsLoading(true);

    try {
      if (mode === "signin") {
        const user = await signIn(email, password);
        onSuccess(user);
      } else {
        const user = await signUp(email, password);
        onSuccess(user);
      }
    } catch (err) {
      let message = "An unexpected error occurred.";
      if (err instanceof ApiError) {
        if (err.status === 401) {
          message = "Email or password is incorrect.";
        } else if (err.status === 409) {
          message = "An account with this email already exists.";
        } else if (err.status === 422) {
          message = "Password must be at least 8 characters.";
        } else if (err.status === 429) {
          message = "Too many attempts. Try again in a few minutes.";
        } else {
          message = err.detail || message;
        }
      } else if (err instanceof Error) {
        message = err.message;
      }
      setAndFocusError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      data-testid="auth-page"
      className="min-h-full w-full flex flex-col items-center justify-center p-4 sm:p-6 bg-bg-base text-text-primary transition-colors"
    >
      {/* Brand logo header above card */}
      <div className="flex items-center justify-center gap-2 mb-6 select-none">
        <span className="text-2xl sm:text-3xl font-bold tracking-tight text-blue-600 dark:text-accent-blue">
          Research
        </span>
        <span className="text-2xl sm:text-3xl font-medium text-slate-700 dark:text-text-primary">
          Assistant
        </span>
      </div>

      {/* Centred Card container */}
      <div
        data-testid="auth-card"
        className="w-full max-w-md rounded-2xl bg-surface-panel border border-border-subtle shadow-xl p-6 sm:p-8 transition-colors"
      >
        {/* ARIA TabList */}
        <div
          role="tablist"
          aria-label="Authentication tabs"
          className="flex border-b border-border-subtle mb-6 gap-2"
        >
          <button
            ref={tabSignInRef}
            role="tab"
            id="tab-signin"
            data-testid="tab-signin"
            aria-selected={mode === "signin"}
            aria-controls="panel-auth"
            tabIndex={mode === "signin" ? 0 : -1}
            onClick={() => switchMode("signin")}
            onKeyDown={handleTabKeyDown}
            className={`flex-1 pb-3 text-sm font-semibold border-b-2 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded-t ${
              mode === "signin"
                ? "border-blue-600 dark:border-accent-blue text-blue-600 dark:text-accent-blue"
                : "border-transparent text-text-muted hover:text-text-primary"
            }`}
          >
            Sign in
          </button>
          <button
            ref={tabSignUpRef}
            role="tab"
            id="tab-signup"
            data-testid="tab-signup"
            aria-selected={mode === "signup"}
            aria-controls="panel-auth"
            tabIndex={mode === "signup" ? 0 : -1}
            onClick={() => switchMode("signup")}
            onKeyDown={handleTabKeyDown}
            className={`flex-1 pb-3 text-sm font-semibold border-b-2 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded-t ${
              mode === "signup"
                ? "border-blue-600 dark:border-accent-blue text-blue-600 dark:text-accent-blue"
                : "border-transparent text-text-muted hover:text-text-primary"
            }`}
          >
            Sign up
          </button>
        </div>

        {/* Tab Panel Form */}
        <form
          id="panel-auth"
          role="tabpanel"
          aria-labelledby={mode === "signin" ? "tab-signin" : "tab-signup"}
          onSubmit={handleSubmit}
          noValidate
          className="flex flex-col gap-4"
        >
          {/* Email field */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="auth-email"
              className="text-xs sm:text-sm font-medium text-text-primary"
            >
              Email
            </label>
            <input
              ref={emailInputRef}
              id="auth-email"
              data-testid="auth-email-input"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-describedby={error ? "auth-error" : undefined}
              placeholder="name@example.com"
              className="w-full px-3.5 py-2.5 rounded-xl border border-border-subtle bg-bg-base text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm transition-colors"
            />
          </div>

          {/* Password field */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="auth-password"
              className="text-xs sm:text-sm font-medium text-text-primary"
            >
              Password
            </label>
            <input
              ref={passwordInputRef}
              id="auth-password"
              data-testid="auth-password-input"
              type="password"
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby={error ? "auth-error" : undefined}
              placeholder="••••••••"
              className="w-full px-3.5 py-2.5 rounded-xl border border-border-subtle bg-bg-base text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm transition-colors"
            />
          </div>

          {/* Confirm password field (Sign up only) */}
          {mode === "signup" && (
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="auth-confirm-password"
                className="text-xs sm:text-sm font-medium text-text-primary"
              >
                Confirm password
              </label>
              <input
                ref={confirmPasswordInputRef}
                id="auth-confirm-password"
                data-testid="auth-confirm-password-input"
                type="password"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                aria-describedby={error ? "auth-error" : undefined}
                placeholder="••••••••"
                className="w-full px-3.5 py-2.5 rounded-xl border border-border-subtle bg-bg-base text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm transition-colors"
              />
            </div>
          )}

          {/* Inline Error (above button with icon and text, colour not only signal) */}
          {error && (
            <div
              id="auth-error"
              ref={errorRef}
              tabIndex={-1}
              role="alert"
              data-testid="auth-error"
              className="flex items-start gap-2 text-xs sm:text-sm text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/20 px-3.5 py-2.5 rounded-xl outline-none focus:ring-2 focus:ring-red-500 transition-colors"
            >
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span className="flex-1">{error}</span>
            </div>
          )}

          {/* Primary Submit Button */}
          <button
            type="submit"
            data-testid="auth-submit-btn"
            disabled={isLoading}
            className="w-full mt-2 py-2.5 px-4 rounded-xl font-medium text-sm text-white bg-blue-600 hover:bg-blue-700 dark:bg-accent-blue dark:text-gray-900 dark:hover:bg-blue-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>{mode === "signin" ? "Signing in..." : "Creating account..."}</span>
              </>
            ) : (
              <span>{mode === "signin" ? "Sign in" : "Create account"}</span>
            )}
          </button>
        </form>
      </div>

      {/* Link below card switching between tabs */}
      <div className="mt-5 text-center text-xs sm:text-sm text-text-secondary">
        {mode === "signin" ? (
          <span>
            Don&apos;t have an account?{" "}
            <button
              type="button"
              data-testid="switch-to-signup-btn"
              onClick={() => switchMode("signup")}
              className="font-semibold text-blue-600 dark:text-accent-blue hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded px-1"
            >
              Sign up
            </button>
          </span>
        ) : (
          <span>
            Already have an account?{" "}
            <button
              type="button"
              data-testid="switch-to-signin-btn"
              onClick={() => switchMode("signin")}
              className="font-semibold text-blue-600 dark:text-accent-blue hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded px-1"
            >
              Sign in
            </button>
          </span>
        )}
      </div>
    </div>
  );
}
