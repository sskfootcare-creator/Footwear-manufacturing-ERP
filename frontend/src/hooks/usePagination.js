import { useState, useMemo, useEffect } from "react";

/**
 * usePagination — Standard React hook for managing ERP table pagination state.
 *
 * Supports both client-side item array slicing and server-side total counting.
 *
 * @param {Array|number} itemsOrTotal Array of items (client-side) OR total item count (server-side)
 * @param {Object} options Configuration options
 * @param {number} options.initialPage Initial 1-based page index (default: 1)
 * @param {number} options.initialPageSize Initial items per page (default: 25)
 * @param {number[]} options.pageSizeOptions Selectable page sizes (default: [10, 25, 50, 100])
 * @param {string} options.testIdPrefix Test ID prefix for rendered controls (default: "pagination")
 * @param {boolean} options.allowAll Whether "All" option is allowed (default: false)
 * @param {string|function} options.rangeTextFormat Range text format ("verbose" | "compact")
 *
 * @returns {Object} Pagination state and helpers
 */
export function usePagination(itemsOrTotal, options = {}) {
  const {
    initialPage = 1,
    initialPageSize = 25,
    pageSizeOptions = [10, 25, 50, 100],
    testIdPrefix = "pagination",
    allowAll = false,
    rangeTextFormat = "verbose",
  } = options;

  const isArray = Array.isArray(itemsOrTotal);
  const items = isArray ? itemsOrTotal : null;
  const totalItems = isArray ? itemsOrTotal.length : Number(itemsOrTotal) || 0;

  const [page, setPage] = useState(initialPage);
  const [pageSize, setPageSize] = useState(initialPageSize);

  const effectivePageSize = pageSize === 0 ? totalItems || 1 : pageSize;
  const totalPages = Math.max(1, Math.ceil(totalItems / effectivePageSize));

  // Auto-clamp active page if dataset size shrinks (e.g. searching/filtering)
  useEffect(() => {
    if (page > totalPages && totalPages > 0) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const validPage = Math.min(Math.max(1, page), totalPages);

  const startIdx = pageSize === 0 ? 0 : (validPage - 1) * effectivePageSize;
  const endIdx = pageSize === 0 ? totalItems : Math.min(startIdx + effectivePageSize, totalItems);

  const startItem = totalItems === 0 ? 0 : startIdx + 1;
  const endItem = endIdx;

  const paginatedItems = useMemo(() => {
    if (!isArray) return [];
    if (pageSize === 0) return items;
    return items.slice(startIdx, endIdx);
  }, [isArray, items, pageSize, startIdx, endIdx]);

  const resetPage = () => setPage(1);

  const paginationProps = {
    currentPage: validPage,
    totalItems,
    pageSize,
    onPageChange: setPage,
    onPageSizeChange: setPageSize,
    pageSizeOptions,
    testIdPrefix,
    allowAll,
    rangeTextFormat,
  };

  return {
    page: validPage,
    currentPage: validPage,
    setPage,
    setCurrentPage: setPage,
    pageSize,
    setPageSize,
    totalPages,
    totalItems,
    startItem,
    endItem,
    paginatedItems,
    resetPage,
    paginationProps,
  };
}

export default usePagination;
