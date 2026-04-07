export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-card border border-dashed border-border bg-white px-4 py-8 text-center">
      <h3 className="text-base font-semibold">{title}</h3>
      <p className="mt-1 text-sm text-muted">{message}</p>
    </div>
  );
}
