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

describe("Expenses Bank Account Selection", () => {
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
          data: [
            {
              id: "bank_acc_101",
              name: "HDFC Primary",
              bank_name: "HDFC Bank",
              account_number_last4: "5432",
              account_type: "online_channel",
              active: true,
            },
            {
              id: "bank_acc_102",
              name: "UCO Operations",
              bank_name: "UCO Bank",
              account_number_last4: "9876",
              account_type: "b2b_client",
              active: true,
            },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });
  });

  it("fetches active bank accounts and renders dropdown in expense creation modal", async () => {
    render(<Expenses />);

    await waitFor(() => {
      expect(http.get).toHaveBeenCalledWith("/banking/accounts", {
        params: { active: true },
      });
    });

    const addBtn = screen.getByTestId("add-expense-btn");
    fireEvent.click(addBtn);

    const bankDropdown = await screen.findByTestId("expense-form-bank-account");
    expect(bankDropdown).toBeInTheDocument();

    expect(screen.getByText(/HDFC Primary/)).toBeInTheDocument();
    expect(screen.getByText(/UCO Operations/)).toBeInTheDocument();

    // Select a bank account and submit
    fireEvent.change(screen.getByTestId("expense-form-amount"), {
      target: { value: "15000" },
    });
    fireEvent.change(screen.getByTestId("expense-form-payee"), {
      target: { value: "Landlord" },
    });
    fireEvent.change(bankDropdown, {
      target: { value: "bank_acc_101" },
    });

    http.post.mockResolvedValueOnce({ data: { id: "exp_1" } });

    const submitBtn = screen.getByTestId("save-expense-btn");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/expenses",
        expect.objectContaining({
          amount: 15000,
          payee: "Landlord",
          bank_account_id: "bank_acc_101",
        })
      );
    });
  });

  it("renders existing bank_account_id in expense edit modal", async () => {
    http.get.mockImplementation((url) => {
      if (url === "/expenses") {
        return Promise.resolve({
          data: [
            {
              id: "exp_22",
              category: "Raw Materials",
              amount: 50000,
              date: "2026-08-10",
              payee: "Rexine Trader",
              bank_account_id: "bank_acc_102",
              notes: "Sole raw material",
            },
          ],
        });
      }
      if (url === "/reports/pnl") {
        return Promise.resolve({ data: {} });
      }
      if (url === "/expenses/due-queue" || url === "/expenses/recurring") {
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
              account_type: "online_channel",
              active: true,
            },
            {
              id: "bank_acc_102",
              name: "UCO Operations",
              bank_name: "UCO Bank",
              account_number_last4: "9876",
              account_type: "b2b_client",
              active: true,
            },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });

    render(<Expenses />);

    await screen.findByText("Rexine Trader");

    const editBtn = screen.getByTestId("edit-expense-exp_22");
    fireEvent.click(editBtn);

    const bankDropdown = await screen.findByTestId("expense-form-bank-account");
    expect(bankDropdown).toBeInTheDocument();
    expect(bankDropdown.value).toBe("bank_acc_102");

    // Change to bank_acc_101 and update
    fireEvent.change(bankDropdown, {
      target: { value: "bank_acc_101" },
    });

    http.put.mockResolvedValueOnce({ data: { id: "exp_22" } });

    const submitBtn = screen.getByTestId("save-expense-btn");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.put).toHaveBeenCalledWith(
        "/expenses/exp_22",
        expect.objectContaining({
          amount: 50000,
          payee: "Rexine Trader",
          bank_account_id: "bank_acc_101",
        })
      );
    });
  });

  it("allows selecting 'Paid via Cash' and choosing a cash withdrawal entry", async () => {
    http.get.mockImplementation((url) => {
      if (url === "/expenses") return Promise.resolve({ data: [] });
      if (url === "/reports/pnl") return Promise.resolve({ data: {} });
      if (url === "/expenses/due-queue" || url === "/expenses/recurring") return Promise.resolve({ data: [] });
      if (url === "/banking/accounts") {
        return Promise.resolve({
          data: [{ id: "bank_acc_101", name: "HDFC Primary", active: true }],
        });
      }
      if (url === "/banking/cash-ledger") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "cash_leg_55",
                date: "2026-08-15",
                amount: 10000,
                remaining_balance: 6500,
                notes: "ATM Floor Cash",
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: [] });
    });

    render(<Expenses />);

    const addBtn = await screen.findByTestId("add-expense-btn");
    fireEvent.click(addBtn);

    // Switch to Paid via Cash
    const cashToggle = await screen.findByTestId("expense-pay-via-cash");
    fireEvent.click(cashToggle);

    // Cash ledger dropdown should appear
    const cashDropdown = await screen.findByTestId("expense-form-cash-ledger");
    expect(cashDropdown).toBeInTheDocument();
    expect(screen.getByText(/₹6,500/)).toBeInTheDocument();

    // Fill form and select cash ledger
    fireEvent.change(screen.getByTestId("expense-form-amount"), {
      target: { value: "3500" },
    });
    fireEvent.change(screen.getByTestId("expense-form-payee"), {
      target: { value: "Agra Packaging Store" },
    });
    fireEvent.change(cashDropdown, {
      target: { value: "cash_leg_55" },
    });

    http.post.mockResolvedValueOnce({ data: { id: "exp_cash_1" } });

    const submitBtn = screen.getByTestId("save-expense-btn");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/expenses",
        expect.objectContaining({
          amount: 3500,
          payee: "Agra Packaging Store",
          paid_via: "cash",
          cash_ledger_id: "cash_leg_55",
          bank_account_id: null,
        })
      );
    });
  });
});

