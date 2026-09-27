import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { ServerWakeBanner } from "@/components/ServerWakeBanner";

import "./globals.css";
import { Providers } from "./providers";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Data to Deck",
  description: "Upload a dataset, get tested findings, clear answers and a slide deck.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <Providers>
          <header className="sticky top-0 z-40 border-b border-border/70 bg-background/75 backdrop-blur-md">
            <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
              <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight">
                <LogoMark />
                Data to Deck
              </Link>
              <nav className="flex items-center gap-1 text-sm">
                <Link
                  href="/"
                  className="rounded-lg px-3 py-1.5 font-medium text-muted transition hover:bg-surface-muted hover:text-foreground"
                >
                  New analysis
                </Link>
              </nav>
            </div>
            <ServerWakeBanner />
          </header>
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 sm:py-12">
            {children}
          </main>
          <footer className="border-t border-border/70">
            <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-6 text-xs text-muted sm:px-6">
              <span>Statistics by pandas &amp; SciPy · narrative by Claude · decks by python-pptx</span>
              <span>Your rows never leave the server.</span>
            </div>
          </footer>
        </Providers>
      </body>
    </html>
  );
}

function LogoMark() {
  return (
    <span aria-hidden className="grid size-7 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 shadow-sm">
      <svg viewBox="0 0 16 16" className="size-4 text-white" fill="none">
        <rect x="2" y="9" width="2.5" height="5" rx="1" fill="currentColor" />
        <rect x="6.75" y="5.5" width="2.5" height="8.5" rx="1" fill="currentColor" />
        <rect x="11.5" y="2" width="2.5" height="12" rx="1" fill="currentColor" />
      </svg>
    </span>
  );
}
