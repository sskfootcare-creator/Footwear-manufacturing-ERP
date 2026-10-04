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
      put: jest.fn(),
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

describe("Expenses Mobile UI and Karigar Wage Selection", () => {
  const mockWorkers = [
    { id: "wk_1", name: "Ramesh Karigar", department: "Upper Stitching", phone: "9876543210" },
    { id: "wk_2", name: "Suresh Sole Worker", department: "Sole Pasting", phone: "9876543211" },
  ];

  beforeEach(() => {
    jest.clearAllMocks();

    http.get.mockImplementation((url) => {
      if (url === "/expenses") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/reports/pnl") {
        return Promise.resolve({
          data: {
            revenue: 0,
            expenses: 0,
            gross_profit: 0,
            net_profit: 0,
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
          data: [{ id: "acc_1", name: "HDFC Current", bank_name: "HDFC", account_number_last4: "9988" }],
        });
      }
      if (url === "/banking/cash-accounts") {
        return Promise.resolve({
          data: { items: [{ id: "cash_1", name: "Factory Floor Petty Cash", balance: 50000 }] },
        });
      }
      if (url === "/banking/cash-ledger") {
        return Promise.resolve({ data: { items: [] } });
      }
      if (url === "/workers") {
        return Promise.resolve({ data: mockWorkers });
      }
      return Promise.resolve({ data: [] });
    });

    http.post.mockResolvedValue({
      data: {
        id: "exp_101",
        category: "wages",
        amount: 3500,
        payee: "Ramesh Karigar",
        worker_id: "wk_1",
        worker_name: "Ramesh Karigar",
      },
    });
  });

  test("Add expense modal contains consolidated Wages category and Karigar selector", async () => {
    render(<Expenses />);

    await waitFor(() => {
      expect(screen.getByTestId("add-expense-btn")).toBeInTheDocument();
    });

    // Open Add Expense modal
    fireEvent.click(screen.getByTestId("add-expense-btn"));

    // Verify modal is open
    expect(screen.getByText("Add New Expense Record")).toBeInTheDocument();

    // Check category dropdown options
    const categorySelect = screen.getByTestId("expense-form-category");
    const options = Array.from(categorySelect.querySelectorAll("option")).map((o) => o.textContent.trim());

    // Single consolidated wages category
    expect(options).toContain("Wages & Labour (Karigar)");
    // Should NOT contain duplicate categories
    expect(options).not.toContain("Labor & Wages");
    expect(options).not.toContain("Contract Labour");

    // Since default category is "wages", Karigar picker should be visible
    expect(screen.getByTestId("expense-karigar-picker-container")).toBeInTheDocument();
    const workerSelect = screen.getByTestId("expense-form-worker-select");
    expect(workerSelect).toBeInTheDocument();

    // Select Ramesh Karigar
    fireEvent.change(workerSelect, { target: { value: "wk_1" } });

    // Payee field should be automatically filled with Ramesh Karigar
    const payeeInput = screen.getByTestId("expense-form-payee");
    expect(payeeInput.value).toBe("Ramesh Karigar");

    // Enter Amount
    const amountInput = screen.getByTestId("expense-form-amount");
    fireEvent.change(amountInput, { target: { value: "3500" } });

    // Submit the form
    const saveBtn = screen.getByTestId("save-expense-btn");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/expenses",
        expect.objectContaining({
          category: "wages",
          amount: 3500,
          payee: "Ramesh Karigar",
          worker_id: "wk_1",
          worker_name: "Ramesh Karigar",
        })
      );
    });
  });

  test("Karigar picker hides when switching to non-wage category", async () => {
    render(<Expenses />);

    await waitFor(() => {
      expect(screen.getByTestId("add-expense-btn")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("add-expense-btn"));

    const categorySelect = screen.getByTestId("expense-form-category");
    // Switch to Electricity
    fireEvent.change(categorySelect, { target: { value: "Electricity" } });

    // Karigar picker should not be shown
    expect(screen.queryByTestId("expense-karigar-picker-container")).not.toBeInTheDocument();
  });
});
