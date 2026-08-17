export function Table({ columns, children }) {
  const normalized = columns.map((column) => (typeof column === "string" ? { label: column } : column));
  const hasWidthHints = normalized.some((column) => column.width || column.minWidth);
  return (
    <div className="table-wrap">
      <table className={hasWidthHints ? "table-fixed" : undefined}>
        {hasWidthHints ? (
          <colgroup>
            {normalized.map((column, index) => (
              <col key={index} style={column.width ? { width: column.width } : undefined} />
            ))}
          </colgroup>
        ) : null}
        <thead>
          <tr>
            {normalized.map((column, index) => (
              <th key={index} style={column.minWidth ? { minWidth: column.minWidth } : undefined}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
