export function LoadingSkeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div className="grid gap-2">
      {Array.from({ length: lines }).map((_, idx) => (
        <div key={idx} className="h-9 animate-pulse rounded-ui bg-slate-200" />
      ))}
    </div>
  );
}
