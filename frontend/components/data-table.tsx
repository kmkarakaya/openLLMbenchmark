import type { ReactNode } from "react";

export type DataTableColumn<T> = {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
};

export function DataTable<T>({
  rows,
  columns,
  emptyMessage
}: {
  rows: T[];
  columns: DataTableColumn<T>[];
  emptyMessage: string;
}) {
  if (!rows.length) {
    return <p className="text-sm text-muted">{emptyMessage}</p>;
  }
  return (
    <div className="overflow-auto rounded-ui border border-border">
      <table className="min-w-full border-collapse text-sm">
        <thead className="bg-slate-50">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="border-b border-border px-3 py-2 text-left text-xs font-semibold uppercase text-muted">
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="bg-white">
              {columns.map((column) => (
                <td key={column.key} className="border-b border-border px-3 py-2 align-top">
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
