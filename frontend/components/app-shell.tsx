"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { ApiError, getHealth, getSloStatus, resetSloStatus } from "../lib/api";
import { StatusBanner } from "./status-banner";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/configure", label: "Configure" },
  { href: "/run", label: "Benchmark Run" },
  { href: "/results", label: "Results" },
  { href: "/datasets", label: "Dataset Management" }
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState(true);
  const [healthLabel, setHealthLabel] = useState("checking");
  const [sloLabel, setSloLabel] = useState("checking");
  const [resettingSlo, setResettingSlo] = useState(false);
  const [banner, setBanner] = useState<{ tone: "info" | "warning" | "danger" | "success"; title: string; message: string } | null>(null);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    let active = true;

    const run = async () => {
      try {
        const [health, slo] = await Promise.all([getHealth(), getSloStatus()]);
        if (!active) {
          return;
        }
        setHealthLabel(`${health.status} (${health.version})`);
        setSloLabel(slo.breached ? "breached" : "ok");
        if (slo.breached) {
          setBanner({
            tone: "warning",
            title: "SLO breach:",
            message: "Run operations may be throttled or disabled until the system stabilizes."
          });
        } else {
          setBanner(null);
        }
      } catch (error) {
        if (!active) {
          return;
        }
        const message = error instanceof ApiError ? error.message : "API status check failed";
        setBanner({
          tone: "danger",
          title: "API degraded:",
          message
        });
        setHealthLabel("unavailable");
        setSloLabel("unknown");
      }
    };

    void run();
    const interval = window.setInterval(() => void run(), 15000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const refreshSystemStatus = async () => {
    const [health, slo] = await Promise.all([getHealth(), getSloStatus()]);
    setHealthLabel(`${health.status} (${health.version})`);
    setSloLabel(slo.breached ? "breached" : "ok");
    if (slo.breached) {
      setBanner({
        tone: "warning",
        title: "SLO breach:",
        message: "Run operations may be throttled or disabled until the system stabilizes."
      });
    } else {
      setBanner(null);
    }
  };

  const handleResetSlo = async () => {
    setResettingSlo(true);
    try {
      await resetSloStatus();
      await refreshSystemStatus();
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "SLO reset failed";
      setBanner({
        tone: "danger",
        title: "SLO reset failed:",
        message
      });
    } finally {
      setResettingSlo(false);
    }
  };

  return (
    <div className="min-h-screen">
      <div className="flex min-h-screen">
        <aside
          className={`fixed inset-y-0 left-0 z-30 w-64 border-r border-border bg-primary px-4 py-4 text-white transition-transform lg:static lg:translate-x-0 ${
            menuOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
          } ${desktopSidebarOpen ? "lg:block" : "lg:hidden"}`}
        >
          <div className="mb-6 flex items-start justify-between gap-2">
            <div>
              <h1 className="text-xl font-semibold text-white">Open LLM Benchmark</h1>
              <p className="mt-1 text-xs text-slate-200">Enterprise Operator UI</p>
            </div>
            <button
              className="focus-ring rounded-ui border border-white/30 px-2 py-1 text-xs font-medium text-white hover:bg-white/10 lg:hidden"
              onClick={() => setMenuOpen(false)}
              aria-label="Close sidebar menu"
            >
              Close
            </button>
            <button
              className="focus-ring hidden rounded-ui border border-white/30 px-2 py-1 text-xs font-medium text-white hover:bg-white/10 lg:inline-flex"
              onClick={() => setDesktopSidebarOpen(false)}
              aria-label="Collapse sidebar"
              data-testid="sidebar-collapse"
            >
              Hide
            </button>
          </div>
          <nav className="grid gap-1">
            {NAV_ITEMS.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`focus-ring rounded-ui px-3 py-2 text-sm font-medium ${
                    active ? "bg-white text-primary" : "text-slate-100 hover:bg-white/10"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-20 border-b border-border bg-surface/95 backdrop-blur">
            <div className="flex items-center justify-between gap-3 px-4 py-3 md:px-6">
              <div className="flex items-center gap-2">
                <button
                  className="focus-ring rounded-ui border border-border px-3 py-2 text-sm font-medium lg:hidden"
                  onClick={() => setMenuOpen((prev) => !prev)}
                >
                  Menu
                </button>
                <button
                  className="focus-ring hidden rounded-ui border border-border px-3 py-2 text-sm font-medium lg:inline-flex"
                  onClick={() => setDesktopSidebarOpen((prev) => !prev)}
                  aria-pressed={!desktopSidebarOpen}
                  data-testid="sidebar-toggle"
                >
                  {desktopSidebarOpen ? "Hide Sidebar" : "Show Sidebar"}
                </button>
                <div>
                  <p className="text-xs uppercase tracking-wide text-muted">System Status</p>
                  <p className="text-sm font-medium">Health: {healthLabel} | SLO: {sloLabel}</p>
                </div>
              </div>
              <div className="text-right text-xs text-muted">
                <p>API-first architecture</p>
                <p className="font-log">NEXT_PUBLIC_API_BASE_URL</p>
              </div>
            </div>
            {sloLabel === "breached" ? (
              <div className="px-4 pb-3 md:px-6">
                <button
                  type="button"
                  className="focus-ring rounded-ui border border-border bg-white px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => void handleResetSlo()}
                  disabled={resettingSlo}
                >
                  {resettingSlo ? "Resetting SLO..." : "Reset SLO"}
                </button>
              </div>
            ) : null}
            {banner ? (
              <div className="px-4 pb-3 md:px-6">
                <StatusBanner tone={banner.tone} title={banner.title} message={banner.message} />
              </div>
            ) : null}
          </header>

          <main className="px-4 py-5 md:px-6 md:py-6">{children}</main>
        </div>
      </div>
      {menuOpen ? (
        <button
          aria-label="Close menu overlay"
          onClick={() => setMenuOpen(false)}
          className="fixed inset-0 z-20 bg-slate-900/40 lg:hidden"
        />
      ) : null}
    </div>
  );
}
