import type { ReactNode } from "react";

export function Field({
  label,
  children,
  helper,
  error
}: {
  label: string;
  children: ReactNode;
  helper?: string;
  error?: string | null;
}) {
  return (
    <label className="grid gap-1">
      <span className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</span>
      {children}
      {error ? <span className="text-xs text-danger">{error}</span> : null}
      {!error && helper ? <span className="text-xs text-muted">{helper}</span> : null}
    </label>
  );
}
