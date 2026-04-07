export function StatusBanner({
  tone,
  title,
  message
}: {
  tone: "info" | "success" | "warning" | "danger";
  title: string;
  message: string;
}) {
  const classes =
    tone === "success"
      ? "border-success/35 bg-green-50 text-green-800"
      : tone === "warning"
        ? "border-warning/35 bg-amber-50 text-amber-800"
        : tone === "danger"
          ? "border-danger/35 bg-red-50 text-red-800"
          : "border-accent/35 bg-sky-50 text-sky-800";

  return (
    <div className={`rounded-ui border px-3 py-2 text-sm ${classes}`} role="status" aria-live="polite">
      <span className="font-semibold">{title}</span> <span>{message}</span>
    </div>
  );
}
