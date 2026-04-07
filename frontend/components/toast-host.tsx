"use client";

import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

type ToastTone = "success" | "warning" | "danger" | "info";

type ToastEntry = {
  id: number;
  tone: ToastTone;
  message: string;
};

type ToastContextValue = {
  pushToast: (tone: ToastTone, message: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);

  const pushToast = (tone: ToastTone, message: string) => {
    const next: ToastEntry = { id: Date.now() + Math.floor(Math.random() * 9999), tone, message };
    setToasts((prev) => [next, ...prev].slice(0, 4));
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== next.id));
    }, 4200);
  };

  const value = useMemo(() => ({ pushToast }), []);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastHost toasts={toasts} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used inside ToastProvider");
  }
  return ctx;
}

function ToastHost({ toasts }: { toasts: ToastEntry[] }) {
  return (
    <div className="pointer-events-none fixed right-4 top-4 z-50 grid w-full max-w-sm gap-2">
      {toasts.map((toast) => {
        const classes =
          toast.tone === "success"
            ? "border-success/35 bg-green-50 text-green-900"
            : toast.tone === "warning"
              ? "border-warning/35 bg-amber-50 text-amber-900"
              : toast.tone === "danger"
                ? "border-danger/35 bg-red-50 text-red-900"
                : "border-accent/35 bg-sky-50 text-sky-900";
        return (
          <div key={toast.id} className={`rounded-ui border px-3 py-2 text-sm shadow-soft ${classes}`}>
            {toast.message}
          </div>
        );
      })}
    </div>
  );
}
