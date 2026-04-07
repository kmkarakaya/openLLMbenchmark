import "./globals.css";
import type { Metadata } from "next";
import { IBM_Plex_Mono, Inter, Space_Grotesk } from "next/font/google";
import type { ReactNode } from "react";

import { AppShell } from "../components/app-shell";
import { ToastProvider } from "../components/toast-host";
import { AppStateProvider } from "../lib/app-state";

export const metadata: Metadata = {
  title: "Open LLM Benchmark UI",
  description: "API-first benchmark UI for model runs, datasets, and results."
};

const headingFont = Space_Grotesk({ subsets: ["latin"], variable: "--font-heading" });
const bodyFont = Inter({ subsets: ["latin"], variable: "--font-body" });
const monoFont = IBM_Plex_Mono({ subsets: ["latin"], variable: "--font-mono", weight: ["400", "500"] });

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={`${headingFont.variable} ${bodyFont.variable} ${monoFont.variable}`}>
        <AppStateProvider>
          <ToastProvider>
            <AppShell>{children}</AppShell>
          </ToastProvider>
        </AppStateProvider>
      </body>
    </html>
  );
}
