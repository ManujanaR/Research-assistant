import type { Metadata } from "next";
import "./globals.css";
import { ThemeToggle } from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "Research Assistant",
  description:
    "AI-powered structured summarization and grounded Q&A for research papers.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
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
      <body className="h-full bg-bg-base text-text-primary antialiased flex flex-col overflow-hidden transition-colors duration-150">
        <header className="h-16 border-b border-border-subtle bg-surface-panel flex-shrink-0 z-10 shadow-sm transition-colors duration-150">
          <div className="w-full px-4 sm:px-6 lg:px-8 h-full flex items-center justify-between">
            <div className="flex items-center gap-2 sm:gap-2.5">
              <span className="text-xl font-bold tracking-tight text-blue-600 dark:text-accent-blue">
                Research
              </span>
              <span className="text-xl font-medium text-slate-700 dark:text-text-primary">
                Assistant
              </span>
            </div>
            <div className="flex items-center gap-2.5 sm:gap-3">
              <span className="hidden xs:inline-flex text-xs font-medium px-2.5 py-1 bg-surface-pill text-blue-700 dark:text-accent-blue rounded-full border border-border-subtle">
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
