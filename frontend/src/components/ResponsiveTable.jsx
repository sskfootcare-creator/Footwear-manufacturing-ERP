/**
 * ResponsiveTable — single source of truth for tabular data across the ERP.
 *
 * Desktop (md+):  standard <table> with thead/tbody, full row styling.
 * Mobile (<md):   stacked card-per-row layout:
 *   • columns with `primary: true`   → large card header (title + subtitle)
 *   • all other columns              → label : value grid
 *   • columns with `action: true`    → full-width tappable button footer
 *
 * Props
 * ─────
 * columns      {Array}    Column config (see below).
 * rows         {Array}    Data rows.
 * rowKey       {Function} (row, i) → unique key. Default: (_, i) => i
 * rowClassName {Function} (row) → extra className string on <tr> / card wrapper.
 * rowStyle     {Function} (row) → inline style object for <tr> / card wrapper.
 * onRowClick   {Function} (row, e) → makes the whole card/row clickable.
 * emptyMessage {string}   Message shown when rows.length === 0.
 * loading      {bool}     Show skeleton shimmer instead of rows.
 * stickyHeader {bool}     Adds sticky top-0 to thead (desktop only). Default false.
 * className    {string}   Extra class on the root wrapper.
 * testId       {string}   data-testid on the root wrapper.
 *
 * Column shape
 * ────────────
 * key          {string}   Unique key (used for React key).
 * header       {string}   Column header label.
 * render       {Function} (row) → React node.  If omitted, renders row[key].
 * primary      {bool}     Pin to card header on mobile (title / subtitle).
 * action       {bool}     Render in card footer as tappable button row.
 * hidden       {bool}     Never render this column (useful for conditional cols).
 * className    {string}   Extra class on <td> (desktop) / value wrapper (mobile).
 * headerClass  {string}   Extra class on <th>.
 * mobileLabel  {string}   Override label in mobile label:value grid (defaults to header).
 * noMobile     {bool}     Skip this column in the mobile card body (e.g. very dense data).
 * colSpan      {number}   td colSpan on desktop.
 */
export default function ResponsiveTable({
  columns = [],
  rows = [],
  rowKey = (_, i) => i,
  rowClassName = () => "",
  rowStyle = () => ({}),
  onRowClick,
  emptyMessage = "No data.",
  loading = false,
  stickyHeader = false,
  className = "",
  testId,
}) {
  const visibleCols    = columns.filter((c) => !c.hidden);
  const primaryCols    = visibleCols.filter((c) => c.primary && !c.action);
  const bodyCols       = visibleCols.filter((c) => !c.primary && !c.action);
  const actionCols     = visibleCols.filter((c) => c.action);
  const mobileBodyCols = bodyCols.filter((c) => !c.noMobile);

  const getCellValue = (col, row) =>
    col.render ? col.render(row) : (row[col.key] ?? "—");

  // ── Skeleton rows ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className={`${className}`} data-testid={testId}>
        {/* Desktop skeleton */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b-2 border-slate-200 bg-slate-50">
                {visibleCols.map((c) => (
                  <th key={c.key} className={`px-4 py-3 text-left text-[10px] uppercase tracking-wider font-bold text-slate-500 ${c.headerClass || ""}`}>
                    {c.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-slate-100">
                  {visibleCols.map((c) => (
                    <td key={c.key} className="px-4 py-3">
                      <div className="h-3 bg-slate-200 rounded animate-pulse w-3/4" />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Mobile skeleton */}
        <div className="md:hidden space-y-3 p-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="bg-white border-2 border-slate-200 p-4 space-y-3">
              <div className="h-4 bg-slate-200 rounded animate-pulse w-2/3" />
              <div className="h-3 bg-slate-100 rounded animate-pulse w-1/2" />
              <div className="grid grid-cols-2 gap-2">
                {Array.from({ length: 4 }).map((_, j) => (
                  <div key={j} className="h-3 bg-slate-100 rounded animate-pulse" />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Empty state ────────────────────────────────────────────────────────────
  if (rows.length === 0) {
    return (
      <div className={`${className}`} data-testid={testId}>
        <div className="py-16 text-center text-sm text-slate-400 italic">
          {emptyMessage}
        </div>
      </div>
    );
  }

  return (
    <div className={`${className}`} data-testid={testId}>

      {/* ── DESKTOP TABLE ──────────────────────────────────────────────────── */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead className={`bg-slate-50 border-b-2 border-slate-200 text-left ${stickyHeader ? "sticky top-0 z-10" : ""}`}>
            <tr>
              {visibleCols.map((c) => (
                <th
                  key={c.key}
                  className={`px-4 py-3 text-[10px] uppercase tracking-wider font-bold text-slate-500 whitespace-nowrap ${c.headerClass || ""}`}
                >
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row, i) => {
              const key = rowKey(row, i);
              const extraClass = rowClassName(row);
              const extraStyle = rowStyle(row);
              const clickable  = !!onRowClick;
              return (
                <tr
                  key={key}
                  className={`transition-colors hover:bg-slate-50 ${extraClass} ${clickable ? "cursor-pointer" : ""}`}
                  style={extraStyle}
                  onClick={clickable ? (e) => onRowClick(row, e) : undefined}
                  data-testid={`row-${key}`}
                >
                  {visibleCols.map((c) => (
                    <td
                      key={c.key}
                      className={`px-4 py-3 ${c.className || ""}`}
                      colSpan={c.colSpan}
                    >
                      {getCellValue(c, row)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ── MOBILE CARDS ───────────────────────────────────────────────────── */}
      <div className="md:hidden divide-y divide-slate-100">
        {rows.map((row, i) => {
          const key        = rowKey(row, i);
          const extraClass = rowClassName(row);
          const extraStyle = rowStyle(row);
          const clickable  = !!onRowClick;

          // Primary columns split: [0] = title, [1] = subtitle, rest = ignored (stay in body)
          const [titleCol, subtitleCol, ...restPrimary] = primaryCols;

          return (
            <div
              key={key}
              className={`bg-white ${extraClass} ${clickable ? "cursor-pointer active:bg-slate-50" : ""}`}
              style={extraStyle}
              onClick={clickable ? (e) => onRowClick(row, e) : undefined}
              data-testid={`card-${key}`}
            >
              {/* Card header — primary fields */}
              {(titleCol || subtitleCol) && (
                <div className="px-4 pt-4 pb-2">
                  {titleCol && (
                    <div className={`font-bold text-sm text-slate-900 leading-tight ${titleCol.className || ""}`}>
                      {getCellValue(titleCol, row)}
                    </div>
                  )}
                  {subtitleCol && (
                    <div className={`text-xs text-slate-500 mt-0.5 ${subtitleCol.className || ""}`}>
                      {getCellValue(subtitleCol, row)}
                    </div>
                  )}
                  {/* any additional primary cols also go here as sub-labels */}
                  {restPrimary.map((c) => (
                    <div key={c.key} className={`text-xs text-slate-400 mt-0.5 ${c.className || ""}`}>
                      {getCellValue(c, row)}
                    </div>
                  ))}
                </div>
              )}

              {/* Card body — label:value grid */}
              {mobileBodyCols.length > 0 && (
                <div className="px-4 py-2 grid grid-cols-2 gap-x-4 gap-y-2">
                  {mobileBodyCols.map((c) => (
                    <div key={c.key} className="min-w-0">
                      <div className="text-[9px] uppercase tracking-wider font-bold text-slate-400 mb-0.5 truncate">
                        {c.mobileLabel || c.header}
                      </div>
                      <div className={`text-xs text-slate-800 leading-snug ${c.className || ""}`}>
                        {getCellValue(c, row)}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Card footer — action buttons */}
              {actionCols.length > 0 && (
                <div
                  className="px-4 pb-4 pt-2 flex flex-wrap gap-2"
                  onClick={(e) => e.stopPropagation()} // don't trigger row click from action area
                >
                  {actionCols.map((c) => (
                    <div key={c.key} className={c.className || ""}>
                      {getCellValue(c, row)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
