import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import Expenses from "../Expenses";
import { http } from "../../lib/api";

jest.mock("../../lib/auth", () => ({
  useAuth: () => ({
    user: { email: "admin@sskfootwear.com", role: "admin", name: "Admin" },
  }),
}));

jest.mock("../../lib/api", () => {
  const original = jest.requireActual("../../lib/api");
  return {
    ...original,
    http: {
      get: jest.fn(),
      post: jest.fn(),
      patch: jest.fn(),
      delete: jest.fn(),
    },
  };
});

jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  BarChart: ({ children }) => <div>{children}</div>,
  Bar: () => null,
  Cell: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  CartesianGrid: () => null,
}));

describe("Expenses Financial Outflow Export Feature", () => {
  const mockExportResponse = {
    from_date: "",
    to_date: "",
    export_type: "all",
    expenses: [
      {
        id: "exp_1",
        date: "2026-03-01",
        category: "Rent & Utilities",
        payee: "Agra Power Corp",
        amount: 15000,
        paid_via: "bank",
        bank_account_name: "HDFC Primary (••5432)",
        cash_account_name: "—",
        status: "paid",
        notes: "Electricity factory bill",
        is_recurring: false,
      },
    ],
    purchases: [
      {
        id: "po_1",
        po_number: "PO-2026-0088",
        date: "2026-03-02",
        vendor_name: "Apex Synthetic Leather",
        items_description: "PU Leather Roll",
        total_quantity: 200,
        received_quantity: 200,
        total_amount: 50000,
        paid_amount: 30000,
        balance_due: 20000,
        status: "received",
        expected_delivery_date: "2026-03-05",
      },
    ],
    summary: {
      expenses_count: 1,
      expenses_amount: 15000,
      purchases_count: 1,
      purchases_amount: 50000,
      total_outflow_amount: 65000,
    },
  };

  beforeEach(() => {
    jest.clearAllMocks();

    http.get.mockImplementation((url) => {
      if (url === "/expenses") {
        return Promise.resolve({
          data: [
            {
              id: "exp_1",
              date: "2026-03-01",
              category: "Rent & Utilities",
              payee: "Agra Power Corp",
              amount: 15000,
              paid_via: "bank",
              notes: "Electricity factory bill",
            },
          ],
        });
      }
      if (url === "/reports/pnl") {
        return Promise.resolve({
          data: {
            revenue: 200000,
            invoices_revenue: 150000,
            settlements_revenue: 50000,
            material_cost: 50000,
            labor_cost: 20000,
            expenses: 15000,
            recurring_expenses: 5000,
            variable_expenses: 10000,
            gross_profit: 130000,
            net_profit: 115000,
            category_totals: {},
            monthly_breakdown: [],
          },
        });
      }
      if (url === "/expenses/due-queue") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/expenses/recurring") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/banking/accounts") {
        return Promise.resolve({
          data: [
            {
              id: "bank_acc_101",
              name: "HDFC Primary",
              bank_name: "HDFC Bank",
              account_number_last4: "5432",
            },
          ],
        });
      }
      if (url === "/banking/cash-ledger") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/banking/cash-accounts") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/expenses/export-data") {
        return Promise.resolve({ data: mockExportResponse });
      }
      return Promise.resolve({ data: [] });
    });
  });

  test("renders Export Outflow buttons on page", async () => {
    render(<Expenses />);

    await waitFor(() => {
      expect(screen.getByTestId("export-outflows-btn")).toBeInTheDocument();
      expect(screen.getByTestId("filter-bar-export-btn")).toBeInTheDocument();
    });
  });

  test("clicking Export Outflows opens modal and fetches preview data", async () => {
    render(<Expenses />);

    await waitFor(() => {
      expect(screen.getByTestId("export-outflows-btn")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("export-outflows-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("export-outflows-modal")).toBeInTheDocument();
      expect(screen.getByText("Export Financial Outflow Data")).toBeInTheDocument();
    });

    expect(http.get).toHaveBeenCalledWith(
      "/expenses/export-data",
      expect.objectContaining({
        params: expect.objectContaining({ export_type: "all" }),
      })
    );

    // Verify summary KPI preview
    await waitFor(() => {
      expect(screen.getByTestId("export-total-outflow-kpi")).toHaveTextContent("65,000");
      expect(screen.getByTestId("export-expenses-kpi")).toHaveTextContent("15,000");
      expect(screen.getByTestId("export-purchases-kpi")).toHaveTextContent("50,000");
    });
  });

  test("allows switching export scope between All, Expenses Only, and Purchases Only", async () => {
    render(<Expenses />);

    await waitFor(() => {
      expect(screen.getByTestId("export-outflows-btn")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("export-outflows-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("export-outflows-modal")).toBeInTheDocument();
    });

    // Switch to expenses only
    fireEvent.click(screen.getByTestId("export-scope-expenses"));

    await waitFor(() => {
      expect(http.get).toHaveBeenCalledWith(
        "/expenses/export-data",
        expect.objectContaining({
          params: expect.objectContaining({ export_type: "expenses" }),
        })
      );
    });

    // Switch to purchases only
    fireEvent.click(screen.getByTestId("export-scope-purchases"));

    await waitFor(() => {
      expect(http.get).toHaveBeenCalledWith(
        "/expenses/export-data",
        expect.objectContaining({
          params: expect.objectContaining({ export_type: "purchases" }),
        })
      );
    });
  });

  test("allows selecting date presets and triggers export preview update", async () => {
    render(<Expenses />);

    await waitFor(() => {
      expect(screen.getByTestId("export-outflows-btn")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("export-outflows-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("export-outflows-modal")).toBeInTheDocument();
    });

    // Click 'This Month' preset
    fireEvent.click(screen.getByTestId("export-preset-this-month"));

    const fromDateInput = screen.getByTestId("export-from-date");
    await waitFor(() => {
      expect(fromDateInput.value).not.toBe("");
    });

    // Click 'All' preset
    fireEvent.click(screen.getByTestId("export-preset-all"));
    await waitFor(() => {
      expect(fromDateInput.value).toBe("");
    });

    await waitFor(() => {
      expect(screen.getByTestId("export-total-outflow-kpi")).toBeInTheDocument();
    });
  });

  test("triggers CSV download for consolidated, expenses, and purchases formats", async () => {
    // Mock URL and DOM link clicking
    const mockClick = jest.fn();
    const origCreateElement = document.createElement.bind(document);
    jest.spyOn(document, "createElement").mockImplementation((tag) => {
      const el = origCreateElement(tag);
      if (tag === "a") {
        el.click = mockClick;
      }
      return el;
    });

    render(<Expenses />);

    await waitFor(() => {
      expect(screen.getByTestId("export-outflows-btn")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("export-outflows-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("download-consolidated-csv")).toBeInTheDocument();
    });

    // Test consolidated download
    fireEvent.click(screen.getByTestId("download-consolidated-csv"));
    expect(mockClick).toHaveBeenCalled();

    // Test expenses CSV download
    fireEvent.click(screen.getByTestId("download-expenses-csv"));
    expect(mockClick).toHaveBeenCalled();

    // Test purchases CSV download
    fireEvent.click(screen.getByTestId("download-purchases-csv"));
    expect(mockClick).toHaveBeenCalled();

    document.createElement.mockRestore();
  });

  test("closes the modal when cancel or close X button is clicked", async () => {
    render(<Expenses />);

    await waitFor(() => {
      expect(screen.getByTestId("export-outflows-btn")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("export-outflows-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("export-outflows-modal")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("close-export-modal-btn"));

    await waitFor(() => {
      expect(screen.queryByTestId("export-outflows-modal")).not.toBeInTheDocument();
    });
  });
});
