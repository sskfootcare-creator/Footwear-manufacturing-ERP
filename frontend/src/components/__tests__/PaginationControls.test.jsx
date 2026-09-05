import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import PaginationControls from "../PaginationControls";
import { usePagination } from "../../hooks/usePagination";

describe("PaginationControls Component", () => {
  test("renders record counter and pagination buttons correctly", () => {
    const onPageChange = jest.fn();
    const onPageSizeChange = jest.fn();

    render(
      <PaginationControls
        currentPage={1}
        totalItems={142}
        pageSize={25}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
        testIdPrefix="test-pagination"
      />
    );

    expect(screen.getByTestId("test-pagination-bar")).toBeInTheDocument();
    expect(screen.getByText(/Showing/i)).toBeInTheDocument();
    expect(screen.getByText("142")).toBeInTheDocument();

    // First and Prev should be disabled on page 1
    const firstBtn = screen.getByTestId("test-pagination-first");
    const prevBtn = screen.getByTestId("test-pagination-prev");
    expect(firstBtn).toBeDisabled();
    expect(prevBtn).toBeDisabled();

    // Next and Last should be enabled
    const nextBtn = screen.getByTestId("test-pagination-next");
    const lastBtn = screen.getByTestId("test-pagination-last");
    expect(nextBtn).toBeEnabled();
    expect(lastBtn).toBeEnabled();

    // Clicking Next triggers onPageChange(2)
    fireEvent.click(nextBtn);
    expect(onPageChange).toHaveBeenCalledWith(2);

    // Clicking Last triggers onPageChange(6) because 142/25 = 6 pages
    fireEvent.click(lastBtn);
    expect(onPageChange).toHaveBeenCalledWith(6);
  });

  test("handles page size selection and changes", () => {
    const onPageChange = jest.fn();
    const onPageSizeChange = jest.fn();

    render(
      <PaginationControls
        currentPage={3}
        totalItems={100}
        pageSize={25}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
        testIdPrefix="test-size"
      />
    );

    const select = screen.getByTestId("test-size-size-select");
    fireEvent.change(select, { target: { value: "50" } });

    expect(onPageSizeChange).toHaveBeenCalledWith(50);
    expect(onPageChange).toHaveBeenCalledWith(1);
  });

  test("renders compact range text when rangeTextFormat is 'compact'", () => {
    render(
      <PaginationControls
        currentPage={2}
        totalItems={100}
        pageSize={25}
        onPageChange={() => {}}
        testIdPrefix="compact-pag"
        rangeTextFormat="compact"
      />
    );

    expect(screen.getByText("26–50 of 100")).toBeInTheDocument();
  });

  test("returns null if totalItems is 0", () => {
    const { container } = render(
      <PaginationControls
        currentPage={1}
        totalItems={0}
        pageSize={25}
        onPageChange={() => {}}
      />
    );
    expect(container.firstChild).toBeNull();
  });
});

describe("usePagination Hook", () => {
  function TestConsumer({ items, options }) {
    const {
      page,
      pageSize,
      totalPages,
      paginatedItems,
      setPage,
      setPageSize,
      paginationProps,
    } = usePagination(items, options);

    return (
      <div>
        <div data-testid="hook-page">{page}</div>
        <div data-testid="hook-size">{pageSize}</div>
        <div data-testid="hook-total-pages">{totalPages}</div>
        <div data-testid="hook-rendered-count">{paginatedItems.length}</div>
        <button data-testid="btn-next" onClick={() => setPage(page + 1)}>
          Next
        </button>
        <button data-testid="btn-size-50" onClick={() => setPageSize(50)}>
          Set 50
        </button>
        <PaginationControls {...paginationProps} />
      </div>
    );
  }

  test("correctly slices items and updates on page navigation", () => {
    const dataset = Array.from({ length: 65 }, (_, i) => ({ id: i, label: `Item ${i}` }));

    render(<TestConsumer items={dataset} options={{ initialPageSize: 25 }} />);

    expect(screen.getByTestId("hook-page")).toHaveTextContent("1");
    expect(screen.getByTestId("hook-total-pages")).toHaveTextContent("3");
    expect(screen.getByTestId("hook-rendered-count")).toHaveTextContent("25");

    fireEvent.click(screen.getByTestId("btn-next"));
    expect(screen.getByTestId("hook-page")).toHaveTextContent("2");
    expect(screen.getByTestId("hook-rendered-count")).toHaveTextContent("25");

    fireEvent.click(screen.getByTestId("btn-next"));
    expect(screen.getByTestId("hook-page")).toHaveTextContent("3");
    // 65 - 50 = 15 items on page 3
    expect(screen.getByTestId("hook-rendered-count")).toHaveTextContent("15");
  });
});
