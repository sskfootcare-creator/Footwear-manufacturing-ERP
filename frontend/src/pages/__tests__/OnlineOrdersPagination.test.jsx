import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import OnlineOrders from "../OnlineOrders";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => {
  const original = jest.requireActual("../../lib/api");
  return {
    ...original,
    http: {
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      delete: jest.fn(),
      patch: jest.fn(),
    },
  };
});

describe("OnlineOrders Large File Import Preview Pagination", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.includes("/order-import-format-configs")) {
        return Promise.resolve({
          data: [
            {
              platform: "flipkart",
              role: "order",
              is_picklist: false,
              column_map: { leaf_sku: "FSN" },
            },
          ],
        });
      }
      if (url.includes("/online-orders/jobs")) return Promise.resolve({ data: [] });
      if (url.includes("/online-orders/stats")) return Promise.resolve({ data: {} });
      return Promise.resolve({ data: [] });
    });
  });

  test("Allows user to review all 550+ rows across pages before commit, including errors in rows 301+", async () => {
    // Generate 550 rows with an error in row #350
    const mockRows = Array.from({ length: 550 }, (_, i) => {
      const rowNum = i + 1;
      const isError = rowNum === 350;
      return {
        source_row_index: rowNum,
        order_id: `OD-${10000 + rowNum}`,
        leaf_sku_raw: isError ? "CORRUPTED_SKU_350" : `SKU_${rowNum}`,
        group_id: `GRP_${rowNum}`,
        derived_size: "8",
        style_code: isError ? "" : "SSK_OXFORD",
        qty: 1,
        matched: !isError,
        match_via: isError ? "" : "sku_map",
        exception_reason: isError ? "SKU not found in mapping" : "",
      };
    });

    http.post.mockImplementation((url) => {
      if (url.includes("/online-orders/import-configured")) {
        return Promise.resolve({
          data: {
            platform: "flipkart",
            filename: "large_batch_550.xlsx",
            header_row_1_based: 1,
            stats: {
              total_rows_read: 550,
              matched: 549,
              unmatched: 1,
              order_style_rows: 550,
              picklist_rows: 0,
              distinct_orders: 550,
            },
            rows: mockRows,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(
      <MemoryRouter>
        <OnlineOrders />
      </MemoryRouter>
    );

    // Open import drawer
    const importBtn = await screen.findByRole("button", { name: /Import orders/i });
    fireEvent.click(importBtn);

    // Drop file and trigger preview
    const file = new File(["dummy excel content"], "large_batch_550.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const fileInput = await screen.findByTestId("import-order-file-input");
    fireEvent.change(fileInput, { target: { files: [file] } });

    const previewBtn = await screen.findByRole("button", { name: /Preview import/i });
    fireEvent.click(previewBtn);


    // Wait for preview to render
    await waitFor(() => {
      expect(screen.getByText("1–100 of 550")).toBeInTheDocument();
    });

    // Check page navigation: go to page 4 (rows 301–400)
    const nextBtn = screen.getByTestId("preview-next-page");
    fireEvent.click(nextBtn); // page 2
    fireEvent.click(nextBtn); // page 3
    fireEvent.click(nextBtn); // page 4

    expect(screen.getByText("301–400 of 550")).toBeInTheDocument();

    // Verify row 350 error is visible and reviewable on page 4
    expect(screen.getByText("CORRUPTED_SKU_350")).toBeInTheDocument();
    expect(screen.getByText("SKU not found in mapping")).toBeInTheDocument();

    // Filter by Exceptions
    const exceptionsFilterBtn = screen.getByTestId("preview-filter-unmatched");
    fireEvent.click(exceptionsFilterBtn);

    // Confirm filter narrows to the exception row
    expect(screen.getByText("1–1 of 1")).toBeInTheDocument();
    expect(screen.getByText("CORRUPTED_SKU_350")).toBeInTheDocument();
  });
});
