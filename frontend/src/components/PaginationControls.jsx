import React from "react";

/**
 * PaginationControls — Standardized ERP-wide pagination component.
 *
 * Provides a unified, professional toolbar matching SSK brand guidelines:
 * - Informative record counts ("Showing 1 to 25 of 142 records" or compact "1–25 of 142")
 * - Configurable page size dropdown (10, 25, 50, 100, optional All)
 * - First («), Previous (‹), sliding numeric page pills, Next (›), and Last (») buttons
 * - Brand navy highlighting (#1E3A8A / white) for the active page
 * - Full test-id prefixing for automated testing
 *
 * Props:
 * @param {number}   currentPage       Current 1-based page index (default 1)
 * @param {number}   totalItems        Total number of records across all pages
 * @param {number}   pageSize          Number of items per page (default 25)
 * @param {function} onPageChange      Callback (newPage: number) => void
 * @param {function} onPageSizeChange  Callback (newSize: number) => void
 * @param {string}   testIdPrefix      Prefix for test IDs (default "pagination")
 * @param {number[]} pageSizeOptions   Array of selectable page sizes (default [10, 25, 50, 100])
 * @param {string|function} rangeTextFormat "verbose" | "compact" | ((start, end, total) => string)
 * @param {boolean}  showSizeSelector  Whether to show the page size select (default true)
 * @param {boolean}  showRecordCount   Whether to show the record range counter (default true)
 * @param {boolean}  showFirstLast     Whether to show First («) and Last (») buttons (default true)
 * @param {boolean}  allowAll          Whether to include an "All (N)" option in the size selector
 * @param {string}   className         Extra Tailwind / CSS classes for container
 * @param {string}   prevTestId        Custom data-testid override for Previous button
 * @param {string}   nextTestId        Custom data-testid override for Next button
 * @param {string}   pageSizeTestId    Custom data-testid override for Page Size selector
 */
export default function PaginationControls({
  currentPage = 1,
  totalItems = 0,
  pageSize = 25,
  onPageChange,
  onPageSizeChange,
  testIdPrefix = "pagination",
  pageSizeOptions = [10, 25, 50, 100],
  rangeTextFormat = "verbose",
  showSizeSelector = true,
  showRecordCount = true,
  showFirstLast = true,
  allowAll = false,
  className = "",
  prevTestId,
  nextTestId,
  pageSizeTestId,
}) {
  const effectivePageSize = pageSize === 0 ? totalItems || 1 : pageSize;
  const totalPages = Math.max(1, Math.ceil(totalItems / effectivePageSize));

  if (totalItems === 0) return null;

  const validPage = Math.min(Math.max(1, currentPage), totalPages);
  const startItem = pageSize === 0 ? 1 : Math.min((validPage - 1) * effectivePageSize + 1, totalItems);
  const endItem = pageSize === 0 ? totalItems : Math.min(validPage * effectivePageSize, totalItems);

  // Sliding window of 5 page numbers
  const getPageNumbers = () => {
    if (pageSize === 0) return [1];
    const pages = [];
    const maxVisible = 5;
    if (totalPages <= maxVisible) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      let start = Math.max(1, validPage - 2);
      let end = Math.min(totalPages, start + maxVisible - 1);
      if (end - start < maxVisible - 1) {
        start = Math.max(1, end - maxVisible + 1);
      }
      for (let i = start; i <= end; i++) pages.push(i);
    }
    return pages;
  };

  const pageNumbers = getPageNumbers();

  const handlePageChange = (newPage) => {
    if (newPage < 1 || newPage > totalPages || newPage === validPage) return;
    if (onPageChange) onPageChange(newPage);
  };

  const handleSizeChange = (newSize) => {
    if (onPageSizeChange) onPageSizeChange(Number(newSize));
    if (onPageChange) onPageChange(1);
  };

  const renderRecordText = () => {
    if (typeof rangeTextFormat === "function") {
      return rangeTextFormat(startItem, endItem, totalItems);
    }
    if (rangeTextFormat === "compact") {
      return `${startItem}–${endItem} of ${totalItems}`;
    }
    return (
      <>
        Showing <span className="font-mono font-bold text-slate-900">{startItem}</span> to{" "}
        <span className="font-mono font-bold text-slate-900">{endItem}</span> of{" "}
        <span className="font-mono font-bold text-slate-900">{totalItems}</span> records
      </>
    );
  };

  return (
    <div
      className={`flex items-center justify-between gap-4 flex-wrap pt-3 border-t border-slate-200 text-xs ${className}`}
      data-testid={`${testIdPrefix}-bar`}
    >
      <div className="flex items-center gap-3 text-slate-600">
        {showRecordCount && (
          <span className="font-medium" data-testid={`${testIdPrefix}-count-info`}>
            {renderRecordText()}
          </span>
        )}

        {showSizeSelector && onPageSizeChange && (
          <div className="flex items-center gap-1.5 border-l border-slate-300 pl-3">
            <span className="text-[10px] uppercase font-bold text-slate-500">Per page:</span>
            <select
              value={pageSize}
              onChange={(e) => handleSizeChange(e.target.value)}
              className="border border-slate-300 rounded bg-white px-2 py-1 text-xs font-bold text-slate-800 focus:outline-none focus:border-[#2563EB]"
              data-testid={pageSizeTestId || `${testIdPrefix}-size-select`}
            >
              {pageSizeOptions.map((sz) => (
                <option key={sz} value={sz}>
                  {sz}
                </option>
              ))}
              {allowAll && <option value={0}>{`All (${totalItems})`}</option>}
            </select>
          </div>
        )}
      </div>

      <div className="flex items-center gap-1">
        {showFirstLast && (
          <button
            type="button"
            onClick={() => handlePageChange(1)}
            disabled={validPage <= 1}
            className="px-2 py-1 border border-slate-300 rounded text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            data-testid={`${testIdPrefix}-first`}
            title="First page"
          >
            «
          </button>
        )}

        <button
          type="button"
          onClick={() => handlePageChange(validPage - 1)}
          disabled={validPage <= 1}
          className="px-2 py-1 border border-slate-300 rounded text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          data-testid={prevTestId || `${testIdPrefix}-prev`}
          title="Previous page"
        >
          ‹
        </button>

        {pageNumbers.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => handlePageChange(p)}
            className={`px-2.5 py-1 rounded text-xs font-mono font-bold transition-colors ${
              validPage === p
                ? "bg-[#1E3A8A] text-white border border-[#1E3A8A] shadow-sm"
                : "bg-white text-slate-700 border border-slate-300 hover:bg-slate-100"
            }`}
            data-testid={`${testIdPrefix}-page-${p}`}
          >
            {p}
          </button>
        ))}

        <button
          type="button"
          onClick={() => handlePageChange(validPage + 1)}
          disabled={validPage >= totalPages}
          className="px-2 py-1 border border-slate-300 rounded text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          data-testid={nextTestId || `${testIdPrefix}-next`}
          title="Next page"
        >
          ›
        </button>

        {showFirstLast && (
          <button
            type="button"
            onClick={() => handlePageChange(totalPages)}
            disabled={validPage >= totalPages}
            className="px-2 py-1 border border-slate-300 rounded text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            data-testid={`${testIdPrefix}-last`}
            title="Last page"
          >
            »
          </button>
        )}
      </div>
    </div>
  );
}
