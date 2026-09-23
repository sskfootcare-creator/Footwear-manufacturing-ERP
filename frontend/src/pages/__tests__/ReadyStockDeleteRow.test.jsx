import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ReadyStock, { isRowEmpty } from "../ReadyStock";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => {
  const actual = jest.requireActual("../../lib/api");
  return {
    ...actual,
    http: {
      get: jest.fn(),
      post: jest.fn(),
      patch: jest.fn(),
      delete: jest.fn(),
    },
  };
});

describe("ReadyStock Row Deletion Tests", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.confirm = jest.fn(() => true);
    window.alert = jest.fn();
  });

  test("isRowEmpty returns true only when available_qty and all stock fields are 0", () => {
    const emptyRow = {
      ready_stock_qty: 0,
      reserved_qty: 0,
      available_qty: 0,
      in_transit_qty: 0,
      return_qty: 0,
      damaged_qty: 0,
      liquidation_qty: 0,
    };
    expect(isRowEmpty(emptyRow)).toBe(true);

    expect(isRowEmpty({ ...emptyRow, ready_stock_qty: 5 })).toBe(false);
    expect(isRowEmpty({ ...emptyRow, reserved_qty: 1 })).toBe(false);
    expect(isRowEmpty({ ...emptyRow, in_transit_qty: 2 })).toBe(false);
    expect(isRowEmpty({ ...emptyRow, return_qty: 3 })).toBe(false);
    expect(isRowEmpty({ ...emptyRow, damaged_qty: 4 })).toBe(false);
    expect(isRowEmpty({ ...emptyRow, liquidation_qty: 1 })).toBe(false);
    expect(isRowEmpty({ ...emptyRow, available_qty: 10 })).toBe(false);
    expect(isRowEmpty(null)).toBe(false);
  });

  test("renders SKU rows and only enables delete button for empty rows in Style card", async () => {
    const mockStyles = [
      { id: "s1", code: "SSK-TEST-01", name: "Runner 1" },
    ];
    const mockRows = [
      {
        id: "fg_empty",
        style_id: "s1",
        style_code: "SSK-TEST-01",
        color: "Black",
        size: "40",
        ready_stock_qty: 0,
        reserved_qty: 0,
        available_qty: 0,
        in_transit_qty: 0,
        return_qty: 0,
        damaged_qty: 0,
        liquidation_qty: 0,
        min_stock_level: 25,
      },
      {
        id: "fg_has_stock",
        style_id: "s1",
        style_code: "SSK-TEST-01",
        color: "Black",
        size: "41",
        ready_stock_qty: 15,
        reserved_qty: 0,
        available_qty: 15,
        in_transit_qty: 0,
        return_qty: 0,
        damaged_qty: 0,
        liquidation_qty: 0,
        min_stock_level: 25,
      },
    ];

    http.get.mockImplementation((url) => {
      if (url.includes("/styles")) return Promise.resolve({ data: mockStyles });
      if (url.includes("/fg-inventory")) return Promise.resolve({ data: mockRows });
      return Promise.resolve({ data: [] });
    });
    http.delete.mockResolvedValue({ data: { message: "Inventory record deleted successfully", id: "fg_empty" } });

    render(<ReadyStock />);

    // Wait for data load
    await waitFor(() => {
      expect(screen.getByTestId("ready-stock-header")).toBeInTheDocument();
    });

    // Toggle rows view on the card
    const toggleRowsBtn = await screen.findByTestId("toggle-rows-SSK-TEST-01");
    fireEvent.click(toggleRowsBtn);

    // Empty row delete button should be enabled
    const emptyDelBtn = await screen.findByTestId("delete-fg-SSK-TEST-01-Black-40");
    expect(emptyDelBtn).toBeEnabled();

    // Row with stock delete button should be disabled
    const hasStockDelBtn = await screen.findByTestId("delete-fg-SSK-TEST-01-Black-41");
    expect(hasStockDelBtn).toBeDisabled();

    // Click delete on empty row
    await waitFor(() => {
      fireEvent.click(emptyDelBtn);
    });
    expect(window.confirm).toHaveBeenCalled();
    expect(http.delete).toHaveBeenCalledWith("/fg-inventory/fg_empty");
  });

  test("renders SKU rows in table view and allows row deletion", async () => {
    const mockStyles = [
      { id: "s1", code: "SSK-TEST-01", name: "Runner 1" },
    ];
    const mockRows = [
      {
        id: "fg_empty_2",
        style_id: "s1",
        style_code: "SSK-TEST-01",
        color: "White",
        size: "38",
        ready_stock_qty: 0,
        reserved_qty: 0,
        available_qty: 0,
        in_transit_qty: 0,
        return_qty: 0,
        damaged_qty: 0,
        liquidation_qty: 0,
        min_stock_level: 25,
      },
    ];

    http.get.mockImplementation((url) => {
      if (url.includes("/styles")) return Promise.resolve({ data: mockStyles });
      if (url.includes("/fg-inventory")) return Promise.resolve({ data: mockRows });
      return Promise.resolve({ data: [] });
    });
    http.delete.mockResolvedValue({ data: { message: "deleted" } });

    render(<ReadyStock />);

    await waitFor(() => {
      expect(screen.getByTestId("view-mode-table")).toBeInTheDocument();
    });

    // Switch to Table view
    fireEvent.click(screen.getByTestId("view-mode-table"));

    const tableDelBtns = await screen.findAllByTestId("table-delete-fg-fg_empty_2");
    expect(tableDelBtns[0]).toBeEnabled();

    await waitFor(() => {
      fireEvent.click(tableDelBtns[0]);
    });
    expect(window.confirm).toHaveBeenCalled();
    expect(http.delete).toHaveBeenCalledWith("/fg-inventory/fg_empty_2");
  });
});
