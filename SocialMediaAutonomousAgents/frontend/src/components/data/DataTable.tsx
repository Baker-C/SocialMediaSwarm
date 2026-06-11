import { Fragment, useMemo, useState } from 'react';

export type DataTableColumn<T> = {
  id: string;
  header: string;
  accessor: (row: T) => React.ReactNode;
  sortValue?: (row: T) => string | number | null | undefined;
  align?: 'left' | 'right';
};

type DataTableProps<T> = {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  emptyMessage?: string;
  ariaLabel: string;
  onRowClick?: (row: T) => void;
  /** When provided, rows toggle open on click and render this content below. */
  renderExpanded?: (row: T) => React.ReactNode;
};

type SortState = {
  columnId: string;
  direction: 'asc' | 'desc';
};

function compareValues(a: unknown, b: unknown): number {
  if (a == null && b == null) {
    return 0;
  }
  if (a == null) {
    return 1;
  }
  if (b == null) {
    return -1;
  }
  if (typeof a === 'number' && typeof b === 'number') {
    return a - b;
  }
  return String(a).localeCompare(String(b));
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  emptyMessage = 'No data.',
  ariaLabel,
  onRowClick,
  renderExpanded,
}: DataTableProps<T>) {
  const [sort, setSort] = useState<SortState | null>(null);
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());

  const expandable = Boolean(renderExpanded);

  const toggleExpanded = (key: string) => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const sortedRows = useMemo(() => {
    if (!sort) {
      return rows;
    }
    const column = columns.find((c) => c.id === sort.columnId);
    if (!column?.sortValue) {
      return rows;
    }
    const sorted = [...rows].sort((a, b) =>
      compareValues(column.sortValue!(a), column.sortValue!(b))
    );
    return sort.direction === 'desc' ? sorted.reverse() : sorted;
  }, [columns, rows, sort]);

  const handleSort = (columnId: string) => {
    const column = columns.find((c) => c.id === columnId);
    if (!column?.sortValue) {
      return;
    }
    setSort((prev) => {
      if (prev?.columnId === columnId) {
        return { columnId, direction: prev.direction === 'asc' ? 'desc' : 'asc' };
      }
      return { columnId, direction: 'asc' };
    });
  };

  if (rows.length === 0) {
    return <p className="data-table__empty">{emptyMessage}</p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table" aria-label={ariaLabel}>
        <thead>
          <tr>
            {expandable ? <th className="data-table__th data-table__th--caret" scope="col" /> : null}
            {columns.map((col) => {
              const sortable = Boolean(col.sortValue);
              const active = sort?.columnId === col.id;
              return (
                <th
                  key={col.id}
                  className={`data-table__th${col.align === 'right' ? ' data-table__th--right' : ''}`}
                  scope="col"
                >
                  {sortable ? (
                    <button
                      type="button"
                      className={`data-table__sort${active ? ' data-table__sort--active' : ''}`}
                      onClick={() => handleSort(col.id)}
                    >
                      {col.header}
                      {active ? (sort?.direction === 'asc' ? ' ↑' : ' ↓') : null}
                    </button>
                  ) : (
                    col.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => {
            const key = rowKey(row);
            const isOpen = expandable && expandedKeys.has(key);
            const activate = expandable
              ? () => toggleExpanded(key)
              : onRowClick
                ? () => onRowClick(row)
                : undefined;
            return (
              <Fragment key={key}>
                <tr
                  className={activate ? 'data-table__row--clickable' : undefined}
                  onClick={activate}
                  onKeyDown={
                    activate
                      ? (e) => {
                          if (e.key === 'Enter') {
                            activate();
                          }
                        }
                      : undefined
                  }
                  tabIndex={activate ? 0 : undefined}
                  role={activate ? 'button' : undefined}
                  aria-expanded={expandable ? isOpen : undefined}
                >
                  {expandable ? (
                    <td className="data-table__td--caret" aria-hidden="true">
                      <span
                        className={`data-table__caret${isOpen ? ' data-table__caret--open' : ''}`}
                      >
                        ▶
                      </span>
                    </td>
                  ) : null}
                  {columns.map((col) => (
                    <td
                      key={col.id}
                      className={col.align === 'right' ? 'data-table__td--right' : undefined}
                    >
                      {col.accessor(row) ?? '—'}
                    </td>
                  ))}
                </tr>
                {isOpen ? (
                  <tr className="data-table__expanded-row">
                    <td colSpan={columns.length + 1}>{renderExpanded!(row)}</td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
