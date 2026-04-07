"use client";

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) {
    return null;
  }
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/45 px-4">
      <div className="w-full max-w-md rounded-card border border-border bg-surface p-5 shadow-soft">
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="mt-2 text-sm text-muted">{message}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button className="focus-ring rounded-ui border border-border bg-white px-3 py-2 text-sm font-medium" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button className="focus-ring rounded-ui bg-danger px-3 py-2 text-sm font-semibold text-white" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
