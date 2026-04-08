import type { ReactNode } from "react";

export function Card({
  title,
  children,
  actions,
  className
}: {
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-card border border-border bg-surface p-4 shadow-soft md:p-5 ${className ?? ""}`}>
      {(title || actions) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">{title}</h2>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
