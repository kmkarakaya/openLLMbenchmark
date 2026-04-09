import { useMemo, useState } from "react";
import type { ReactNode } from "react";

type SortDirection = "asc" | "desc";

export type DataTableColumn<T> = {
  key: string;
  header: string;
  headerHelp?: string;
  render: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number | null;
  defaultSortDirection?: SortDirection;
};

function normalizeSortValue(value: string | number | null | undefined): string | number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string") {
    return value;
  }
  return null;
}

export function DataTable<T>({
  rows,
  columns,
  emptyMessage
}: {
  rows: T[];
  columns: DataTableColumn<T>[];
  emptyMessage: string;
}) {
  const [sortState, setSortState] = useState<{ key: string; direction: SortDirection } | null>(null);
  const collator = useMemo(() => new Intl.Collator(undefined, { numeric: true, sensitivity: "base" }), []);

  const sortedRows = useMemo(() => {
    if (!sortState) {
      return rows;
    }

    const activeColumn = columns.find((column) => column.key === sortState.key);
    if (!activeColumn?.sortValue) {
      return rows;
    }

    return [...rows].sort((leftRow, rightRow) => {
      const leftValue = normalizeSortValue(activeColumn.sortValue?.(leftRow));
      const rightValue = normalizeSortValue(activeColumn.sortValue?.(rightRow));

      if (leftValue === null && rightValue === null) {
        return 0;
      }
      if (leftValue === null) {
        return 1;
      }
      if (rightValue === null) {
        return -1;
      }

      let comparison = 0;
      if (typeof leftValue === "number" && typeof rightValue === "number") {
        comparison = leftValue - rightValue;
      } else {
        comparison = collator.compare(String(leftValue), String(rightValue));
      }

      return sortState.direction === "desc" ? comparison * -1 : comparison;
    });
  }, [collator, columns, rows, sortState]);

  const onSort = (column: DataTableColumn<T>) => {
    if (!column.sortValue) {
      return;
    }
    setSortState((current) => {
      if (current?.key === column.key) {
        return {
          key: column.key,
          direction: current.direction === "desc" ? "asc" : "desc"
        };
      }
      return {
        key: column.key,
        direction: column.defaultSortDirection ?? "desc"
      };
    });
  };

  if (!rows.length) {
    return <p className="text-sm text-muted">{emptyMessage}</p>;
  }
  return (
    <div className="overflow-auto rounded-ui border border-border">
      <table className="min-w-full border-collapse text-sm">
        <thead className="bg-slate-50">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className="border-b border-border px-3 py-2 text-left text-xs font-semibold uppercase text-muted"
                aria-sort={
                  sortState?.key === column.key
                    ? sortState.direction === "asc"
                      ? "ascending"
                      : "descending"
                    : undefined
                }
              >
                <span className="inline-flex items-center gap-1">
                  {column.sortValue ? (
                    <button
                      type="button"
                      className={`focus-ring inline-flex items-center gap-1 rounded-ui px-1 py-0.5 text-left ${
                        sortState?.key === column.key ? "text-text" : "text-muted hover:text-text"
                      }`}
                      onClick={() => onSort(column)}
                      aria-label={`Sort by ${column.header}`}
                    >
                      <span>{column.header}</span>
                      {sortState?.key === column.key ? (
                        <span aria-hidden="true" className="text-[10px] normal-case">
                          {sortState.direction === "desc" ? "v" : "^"}
                        </span>
                      ) : null}
                    </button>
                  ) : (
                    <span>{column.header}</span>
                  )}
                  {column.headerHelp ? (
                    <span
                      title={column.headerHelp}
                      aria-label={`${column.header} help: ${column.headerHelp}`}
                      className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-border bg-white text-[10px] font-bold text-muted"
                    >
                      i
                    </span>
                  ) : null}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, rowIndex) => (
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
