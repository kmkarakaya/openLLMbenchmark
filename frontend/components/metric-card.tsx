export function MetricCard({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "accent" | "success" | "warning" }) {
  const toneClass =
    tone === "accent"
      ? "border-accent/35 bg-sky-50"
      : tone === "success"
        ? "border-success/35 bg-green-50"
        : tone === "warning"
          ? "border-warning/35 bg-amber-50"
          : "border-border bg-white";

  return (
    <article className={`rounded-ui border p-3 ${toneClass}`}>
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </article>
  );
}
