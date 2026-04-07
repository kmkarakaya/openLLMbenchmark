export function ErrorState({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-card border border-danger/30 bg-red-50 px-4 py-4">
      <h3 className="text-base font-semibold text-danger">{title}</h3>
      <p className="mt-1 text-sm text-red-900">{message}</p>
    </div>
  );
}
