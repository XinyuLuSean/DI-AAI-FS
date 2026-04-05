import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DI-AAI-FS — Document Intelligence Platform",
  description:
    "Upload documents, extract structured data, and get AI-powered evidence-backed summaries.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased" suppressHydrationWarning>
        <header className="border-b border-gray-200 bg-white px-6 py-4">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <div className="flex items-center gap-6">
              <h1 className="text-lg font-semibold tracking-tight">
                DI-AAI-FS
                <span className="ml-2 text-sm font-normal text-gray-500">
                  Document Intelligence Platform
                </span>
              </h1>
              <nav className="flex items-center gap-1">
                <a
                  href="/"
                  className="rounded-md px-3 py-1.5 text-sm font-medium text-gray-600 transition hover:bg-gray-100 hover:text-gray-900"
                >
                  Upload
                </a>
                <a
                  href="/review"
                  className="rounded-md px-3 py-1.5 text-sm font-medium text-gray-600 transition hover:bg-gray-100 hover:text-gray-900"
                >
                  Review Queue
                </a>
              </nav>
            </div>
            <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700">
              MVP v0.1
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
