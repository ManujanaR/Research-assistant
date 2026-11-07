import type { Metadata } from "next";
import "./globals.css";
import { ThemeToggle } from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "Mitra Research Assistant",
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
                if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                  document.documentElement.classList.add('dark');
                } else {
                  document.documentElement.classList.remove('dark');
                }
              } catch (_) {}
            `,
          }}
        />
      </head>
      <body className="h-full bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 antialiased flex flex-col overflow-hidden transition-colors duration-150">
        <header className="h-16 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex-shrink-0 z-10 shadow-sm transition-colors duration-150">
          <div className="w-full px-4 sm:px-6 lg:px-8 h-full flex items-center justify-between">
            <div className="flex items-center gap-2 sm:gap-2.5">
              <span className="text-xl font-bold tracking-tight text-blue-600 dark:text-blue-400">
                Mitra
              </span>
              <span className="text-xl font-medium text-slate-700 dark:text-slate-200">
                Research Assistant
              </span>
            </div>
            <div className="flex items-center gap-2.5 sm:gap-3">
              <span className="hidden xs:inline-flex text-xs font-medium px-2.5 py-1 bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 rounded-full border border-blue-200 dark:border-blue-800/80">
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
