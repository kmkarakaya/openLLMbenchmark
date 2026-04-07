import type { SelectHTMLAttributes } from "react";

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`focus-ring h-10 rounded-ui border border-border bg-white px-3 text-sm text-text ${
        props.className ?? ""
      }`}
    />
  );
}
