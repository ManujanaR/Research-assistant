import type { Metadata } from "next";
import "./globals.css";

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
    <html lang="en" className="h-full">
      <body className="h-full bg-slate-50 text-slate-900 antialiased flex flex-col overflow-hidden">
        <header className="h-16 border-b border-slate-200 bg-white flex-shrink-0 z-10 shadow-sm">
          <div className="w-full px-4 sm:px-6 lg:px-8 h-full flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold tracking-tight text-blue-600">
                Mitra
              </span>
              <span className="text-xl font-medium text-slate-700">
                Research Assistant
              </span>
            </div>
            <span className="text-xs font-medium px-2.5 py-1 bg-blue-50 text-blue-700 rounded-full border border-blue-200">
              Grounded AI
            </span>
          </div>
        </header>

        <main className="flex-1 min-h-0 w-full overflow-hidden flex flex-col">
          {children}
        </main>
      </body>
    </html>
  );
}
