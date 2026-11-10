import type { Metadata, Viewport } from "next";
import "./globals.css";
import "katex/dist/katex.min.css";
import { ThemeToggle } from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "Research Assistant",
  description:
    "AI-powered structured summarization and grounded Q&A for research papers.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                if (localStorage.theme === 'dark') {
                  document.documentElement.classList.add('dark');
                } else {
                  document.documentElement.classList.remove('dark');
                }
              } catch (_) {}
            `,
          }}
        />
      </head>
      <body className="min-h-screen h-dvh bg-bg-base text-text-primary antialiased flex flex-col overflow-hidden transition-colors duration-150">
        <header className="h-14 sm:h-16 border-b border-border-subtle bg-surface-panel flex-shrink-0 z-10 shadow-sm transition-colors duration-150">
          <div className="w-full px-3 sm:px-6 lg:px-8 h-full flex items-center justify-between gap-2 min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <span className="truncate text-lg sm:text-xl font-bold tracking-tight text-blue-600 dark:text-accent-blue">
                Research{" "}
                <span className="hidden sm:inline font-medium text-slate-700 dark:text-text-primary">
                  Assistant
                </span>
              </span>
            </div>
            <div data-testid="top-bar-actions" className="flex shrink-0 items-center gap-1.5">
              <span className="hidden lg:inline-flex text-xs font-medium px-2.5 py-1 bg-surface-pill text-blue-700 dark:text-accent-blue rounded-full border border-border-subtle">
                Grounded AI
              </span>
              <ThemeToggle />
            </div>
          </div>
        </header>

        <main className="flex-1 min-h-0 w-full overflow-hidden flex flex-col">
          {children}
        </main>
      </body>
    </html>
  );
}
