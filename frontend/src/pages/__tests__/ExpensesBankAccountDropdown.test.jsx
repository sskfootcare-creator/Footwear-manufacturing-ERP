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

  it("allows selecting 'Paid via Cash' and choosing a Per-Source Cash Account without individual withdrawals", async () => {
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
      if (url === "/banking/cash-accounts") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "ca_hdfc_01",
                name: "Cash (HDFC Primary)",
                current_balance: 6500,
                source_bank_account_id: "bank_acc_101",
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
    expect(screen.getByText(/Cash \(HDFC Primary\) • Available: ₹6,500/)).toBeInTheDocument();

    // Verify Specific Cash Withdrawals is NOT present in document
    expect(screen.queryByText(/Specific Cash Withdrawals/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ATM Floor Cash/i)).not.toBeInTheDocument();

    // Fill form and select cash account
    fireEvent.change(screen.getByTestId("expense-form-amount"), {
      target: { value: "3500" },
    });
    fireEvent.change(screen.getByTestId("expense-form-payee"), {
      target: { value: "Agra Packaging Store" },
    });
    fireEvent.change(cashDropdown, {
      target: { value: "ca_hdfc_01" },
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
          cash_account_id: "ca_hdfc_01",
          bank_account_id: null,
        })
      );
    });
  });

  it("allows recording a direct cash withdrawal and immediately using it for cash expense via cash account", async () => {
    let cashAccounts = [];
    http.get.mockImplementation((url) => {
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
          ],
        });
      }
      if (url === "/banking/cash-ledger") {
        return Promise.resolve({ data: { items: [] } });
      }
      if (url === "/banking/cash-accounts") {
        return Promise.resolve({ data: { items: cashAccounts } });
      }
      if (url === "/expenses") return Promise.resolve({ data: [] });
      if (url === "/reports/pnl") return Promise.resolve({ data: { revenue: 0, expenses: 0, gross_profit: 0, net_profit: 0 } });
      if (url === "/expenses/due-queue") return Promise.resolve({ data: [] });
      if (url === "/expenses/recurring") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });

    render(<Expenses />);

    // Click Record Cash Withdrawal in Expenses action bar
    const recordCashBtn = await screen.findByTestId("record-cash-withdrawal-btn");
    fireEvent.click(recordCashBtn);

    // Modal appears
    const accountSelect = await screen.findByTestId("record-cash-account-select");
    const amountInput = screen.getByTestId("record-cash-amount-input");
    const notesInput = screen.getByTestId("record-cash-notes-input");

    fireEvent.change(accountSelect, { target: { value: "bank_acc_101" } });
    fireEvent.change(amountInput, { target: { value: "50000" } });
    fireEvent.change(notesInput, { target: { value: "for worker wages this week" } });

    // Mock direct cash-ledger creation response and cash account addition
    http.post.mockImplementation((url, payload) => {
      if (url === "/banking/cash-ledger") {
        const newDoc = {
          id: "cash_leg_new_999",
          bank_account_id: payload.bank_account_id,
          amount: payload.amount,
          remaining_balance: payload.amount,
          date: payload.date,
          notes: payload.notes,
        };
        cashAccounts = [
          {
            id: "ca_hdfc_01",
            name: "Cash (HDFC Primary)",
            current_balance: 50000,
            source_bank_account_id: "bank_acc_101",
          },
        ];
        return Promise.resolve({
          data: {
            ok: true,
            cash_ledger: newDoc,
            cash_account_id: "ca_hdfc_01",
          },
        });
      }
      if (url === "/expenses") {
        return Promise.resolve({ data: { id: "exp_1" } });
      }
      return Promise.resolve({ data: {} });
    });

    const submitCashBtn = screen.getByTestId("record-cash-submit-btn");
    fireEvent.click(submitCashBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith("/banking/cash-ledger", {
        bank_account_id: "bank_acc_101",
        amount: 50000,
        date: expect.any(String),
        notes: "for worker wages this week",
      });
    });

    // Now open Add Expense modal
    const addExpenseBtn = screen.getByTestId("add-expense-btn");
    fireEvent.click(addExpenseBtn);

    const cashToggle = await screen.findByTestId("expense-pay-via-cash");
    fireEvent.click(cashToggle);

    // Newly funded cash account is available in dropdown and specific withdrawals are omitted
    const cashDropdown = await screen.findByTestId("expense-form-cash-ledger");
    expect(cashDropdown).toBeInTheDocument();
    expect(await screen.findByText(/Cash \(HDFC Primary\) • Available: ₹50,000/i)).toBeInTheDocument();
    expect(screen.queryByText(/Specific Cash Withdrawals/i)).not.toBeInTheDocument();
  });

  test("renders bank-paid wage expense with Wage Payout badge and bank attribution", async () => {
    const mockWageExpense = {
      id: "exp_wage_1",
      category: "wages",
      amount: 4500,
      date: "2026-08-16",
      payee: "Ramesh Kumar",
      notes: "Wage payment to Ramesh Kumar for 2026-08-01-2026-08-15 (UPI Ref: UPI/987654/PAY)",
      paid_via: "bank",
      bank_account_id: "bank_acc_101",
      linked_wage_payment_id: "wp_12345",
      status: "confirmed",
    };

    http.get.mockImplementation((url) => {
      if (url === "/expenses") {
        return Promise.resolve({ data: [mockWageExpense] });
      }
      if (url === "/expenses/due-queue") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/expenses/recurring-templates") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/expenses/pnl-summary") {
        return Promise.resolve({
          data: { revenue: 0, cogs: 0, total_expenses: 4500, net_profit: -4500, category_totals: { wages: 4500 } },
        });
      }
      if (url === "/banking/accounts") {
        return Promise.resolve({
          data: [
            { id: "bank_acc_101", name: "HDFC Primary Current A/C", bank_name: "HDFC", is_active: true },
          ],
        });
      }
      if (url === "/banking/cash-ledger") {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve({ data: [] });
    });

    render(<Expenses />);

    await waitFor(() => {
      expect(screen.getByTestId("expense-row-exp_wage_1")).toBeInTheDocument();
    });

    const row = screen.getByTestId("expense-row-exp_wage_1");
    expect(row).toHaveTextContent("wages");

    // Check Wage Payout badge is rendered and links to payroll
    const badge = screen.getByTestId("linked-wage-badge-exp_wage_1");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent("Wage Payout");
    expect(badge).toHaveAttribute("href", "/payroll");

    // Check payee has Karigar Wage indicator
    expect(screen.getByText("Ramesh Kumar")).toBeInTheDocument();
    expect(screen.getByText("Karigar Wage")).toBeInTheDocument();

    // Check Bank Account attribution
    const bankAttr = screen.getByTestId("expense-bank-attr-exp_wage_1");
    expect(bankAttr).toBeInTheDocument();
    expect(bankAttr).toHaveTextContent("HDFC Primary Current A/C");
  });

  it("allows selecting a Per-Source Cash Account, shows balance pill, and submits cash_account_id", async () => {
    http.get.mockImplementation((url) => {
      if (url === "/expenses") return Promise.resolve({ data: [] });
      if (url === "/reports/pnl") return Promise.resolve({ data: {} });
      if (url === "/expenses/due-queue" || url === "/expenses/recurring") return Promise.resolve({ data: [] });
      if (url === "/banking/accounts") return Promise.resolve({ data: [] });
      if (url === "/banking/cash-ledger") return Promise.resolve({ data: { items: [] } });
      if (url === "/banking/cash-accounts") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "ca_hdfc_01",
                name: "Cash (HDFC Primary)",
                current_balance: 25000,
                source_bank_account_id: "bank_acc_101",
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

    // Cash account option should appear in dropdown
    const cashDropdown = await screen.findByTestId("expense-form-cash-ledger");
    expect(cashDropdown).toBeInTheDocument();
    expect(screen.getByText(/Cash \(HDFC Primary\) • Available: ₹25,000/)).toBeInTheDocument();

    // Select the cash account
    fireEvent.change(cashDropdown, { target: { value: "ca_hdfc_01" } });

    // Fill amount that is within balance
    fireEvent.change(screen.getByTestId("expense-form-amount"), { target: { value: "12000" } });
    fireEvent.change(screen.getByTestId("expense-form-payee"), { target: { value: "Office Supplies Depot" } });

    // Balance status pill should show sufficient balance
    const pill = await screen.findByTestId("expense-cash-balance-pill");
    expect(pill).toBeInTheDocument();
    expect(pill).toHaveTextContent(/Sufficient cash balance/);
    expect(pill).toHaveTextContent(/25,000/);

    // If amount exceeds balance
    fireEvent.change(screen.getByTestId("expense-form-amount"), { target: { value: "30000" } });
    expect(screen.getByTestId("expense-cash-balance-pill")).toHaveTextContent(/Exceeds balance by/);

    // Reset amount back to valid 12000
    fireEvent.change(screen.getByTestId("expense-form-amount"), { target: { value: "12000" } });

    http.post.mockResolvedValueOnce({ data: { id: "exp_ca_99" } });

    const submitBtn = screen.getByTestId("save-expense-btn");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/expenses",
        expect.objectContaining({
          amount: 12000,
          payee: "Office Supplies Depot",
          paid_via: "cash",
          cash_account_id: "ca_hdfc_01",
          cash_ledger_id: null,
          bank_account_id: null,
        })
      );
    });
  });

  it("renders cash expense with cash account attribution badge in table", async () => {
    const mockCashExpense = {
      id: "exp_cash_99",
      category: "Transport & Logistics",
      amount: 1500,
      date: "2026-08-20",
      payee: "Local Tempo Driver",
      notes: "Material transport",
      paid_via: "cash",
      cash_account_id: "ca_hdfc_01",
      status: "confirmed",
    };

    http.get.mockImplementation((url) => {
      if (url === "/expenses") return Promise.resolve({ data: [mockCashExpense] });
      if (url === "/reports/pnl") return Promise.resolve({ data: {} });
      if (url === "/expenses/due-queue" || url === "/expenses/recurring") return Promise.resolve({ data: [] });
      if (url === "/banking/accounts") return Promise.resolve({ data: [] });
      if (url === "/banking/cash-ledger") return Promise.resolve({ data: { items: [] } });
      if (url === "/banking/cash-accounts") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "ca_hdfc_01",
                name: "Cash (HDFC Primary)",
                current_balance: 20000,
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: [] });
    });

    render(<Expenses />);

    await waitFor(() => {
      expect(screen.getByTestId("expense-cash-attr-exp_cash_99")).toBeInTheDocument();
    });

    const cashBadge = screen.getByTestId("expense-cash-attr-exp_cash_99");
    expect(cashBadge).toHaveTextContent("Cash (HDFC Primary)");
  });
});


