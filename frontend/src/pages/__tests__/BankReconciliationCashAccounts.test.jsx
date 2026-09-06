import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import BankReconciliation from "../BankReconciliation";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => ({
  http: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
  inr: (val) => Number(val || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
  formatApiError: (err) => err?.message || "Error",
}));

describe("Bank Reconciliation - Per-Source Cash Accounts Flow", () => {
  const mockBankAccounts = [
    { id: "bank_hdfc", name: "HDFC Primary", bank_name: "HDFC", account_number_last4: "1234", account_type: "online_channel" },
    { id: "bank_uco", name: "UCO Bank Offline", bank_name: "UCO Bank", account_number_last4: "5678", account_type: "b2b_client" },
  ];

  const mockCashAccounts = [
    {
      id: "ca_hdfc",
      name: "Cash (HDFC)",
      source_bank_account_id: "bank_hdfc",
      bank_name: "HDFC Primary",
      current_balance: 35000,
      total_withdrawn: 50000,
      total_spent: 15000,
      account_type: "cash",
      is_cash_account: true,
    },
    {
      id: "ca_uco",
      name: "Cash (UCO Bank)",
      source_bank_account_id: "bank_uco",
      bank_name: "UCO Bank Offline",
      current_balance: 25000,
      total_withdrawn: 30000,
      total_spent: 5000,
      account_type: "cash",
      is_cash_account: true,
    },
  ];

  const mockHdfcTransactions = [
    {
      id: "in_cl_1",
      direction: "in",
      type: "cash_withdrawal",
      type_label: "Cash Withdrawal",
      date: "2026-04-01",
      title: "Cash from HDFC",
      payee: "HDFC Primary",
      description: "ATM Cash Withdrawal",
      amount: 50000,
      running_balance: 50000,
      ref_text: "Stmt Line 001",
      notes: "Weekly withdrawal for Karigar wages",
    },
    {
      id: "out_wp_1",
      direction: "out",
      type: "wage_payment",
      type_label: "Karigar Wage",
      date: "2026-04-02",
      title: "Ramesh Karigar",
      payee: "Ramesh Karigar",
      description: "Wage payment (2026-03-25 to 2026-04-01)",
      amount: 10000,
      running_balance: 40000,
      ref_text: "Wage #001",
      notes: "Piece-rate cutting wages",
    },
    {
      id: "out_exp_1",
      direction: "out",
      type: "expense",
      type_label: "Cash Expense",
      date: "2026-04-03",
      title: "City Hardware",
      payee: "City Hardware",
      description: "Machine oil and belts",
      amount: 5000,
      running_balance: 35000,
      ref_text: "Expense #001",
      notes: "Workshop emergency expense",
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();

    http.get.mockImplementation((url) => {
      if (url === "/banking/accounts") {
        return Promise.resolve({ data: mockBankAccounts });
      }
      if (url === "/banking/cash-accounts") {
        return Promise.resolve({
          data: {
            cash_accounts: mockCashAccounts,
            total_cash_in_hand: 60000,
            total_cash_withdrawn: 80000,
          },
        });
      }
      if (url === "/banking/cash-accounts/ca_hdfc/transactions") {
        return Promise.resolve({
          data: {
            ok: true,
            cash_account: mockCashAccounts[0],
            current_balance: 35000,
            total_withdrawn: 50000,
            total_spent: 15000,
            transactions: mockHdfcTransactions,
            items: mockHdfcTransactions,
          },
        });
      }
      if (url === "/banking/cash-accounts/ca_uco/transactions") {
        return Promise.resolve({
          data: {
            ok: true,
            cash_account: mockCashAccounts[1],
            current_balance: 25000,
            total_withdrawn: 30000,
            total_spent: 5000,
            transactions: [],
            items: [],
          },
        });
      }
      if (url === "/banking/reconciliation/summary") {
        return Promise.resolve({
          data: {
            summary: {
              total_income: 200000,
              total_expenses: 120000,
              total_cash_in_hand: 60000,
              total_cash_withdrawn: 80000,
            },
            accounts: [],
            available_months: ["2026-04"],
          },
        });
      }
      if (url === "/banking/statement-lines") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/banking/transfers/suggested") {
        return Promise.resolve({ data: { pairs: [] } });
      }
      if (url === "/banking/cash-withdrawals/suggested") {
        return Promise.resolve({ data: { candidates: [] } });
      }
      if (url === "/banking/unmatched-erp-candidates") {
        return Promise.resolve({ data: { candidates: [] } });
      }
      if (url === "/banking/periods/locks") {
        return Promise.resolve({ data: { locks: [] } });
      }
      return Promise.resolve({ data: {} });
    });

    http.post.mockResolvedValue({ data: { ok: true } });
  });

  test("Renders cash accounts tabs alongside bank accounts with distinct Cash Pool badges", async () => {
    render(<BankReconciliation />);

    // Check bank account tabs
    expect(await screen.findByText("HDFC Primary")).toBeInTheDocument();
    expect(await screen.findByText("UCO Bank Offline")).toBeInTheDocument();

    // Check cash account tabs with Cash Pool badges
    expect(await screen.findByTestId("tab-cash-account-ca_hdfc")).toBeInTheDocument();
    expect(await screen.findByTestId("tab-cash-account-ca_uco")).toBeInTheDocument();

    const cashPoolBadges = screen.getAllByText("Cash Pool");
    expect(cashPoolBadges.length).toBeGreaterThanOrEqual(2);
  });

  test("Switching to Cash (HDFC) displays dedicated Cash Pool rollup metrics and transactions ledger", async () => {
    render(<BankReconciliation />);

    const hdfcCashTab = await screen.findByTestId("tab-cash-account-ca_hdfc");
    fireEvent.click(hdfcCashTab);

    // Verify Cash Pool view rendered
    expect(await screen.findByTestId("cash-pool-view")).toBeInTheDocument();
    expect(screen.getByTestId("cash-account-title")).toHaveTextContent("Cash (HDFC)");

    // Check rollup metrics
    expect(screen.getByTestId("cash-pool-current-balance")).toBeInTheDocument();
    expect(screen.getByTestId("cash-pool-total-withdrawn")).toBeInTheDocument();
    expect(screen.getByTestId("cash-pool-total-spent")).toBeInTheDocument();

    // Check transactions ledger table rows
    expect(await screen.findByTestId("cash-txn-row-in_cl_1")).toBeInTheDocument();
    expect(await screen.findByTestId("cash-txn-row-out_wp_1")).toBeInTheDocument();
    expect(await screen.findByTestId("cash-txn-row-out_exp_1")).toBeInTheDocument();

    // Verify transaction details
    expect(screen.getByText("Ramesh Karigar")).toBeInTheDocument();
    expect(screen.getByText("City Hardware")).toBeInTheDocument();
  });

  test("Switching to empty Cash (UCO Bank) shows empty state with record withdrawal prompt", async () => {
    render(<BankReconciliation />);

    const ucoCashTab = await screen.findByTestId("tab-cash-account-ca_uco");
    fireEvent.click(ucoCashTab);

    expect(await screen.findByTestId("cash-pool-view")).toBeInTheDocument();
    expect(screen.getByTestId("cash-account-title")).toHaveTextContent("Cash (UCO Bank)");
    expect(await screen.findByTestId("cash-empty-state")).toBeInTheDocument();
  });

  test("Clicking Record Cash Withdrawal opens pre-selected modal", async () => {
    render(<BankReconciliation />);

    const hdfcCashTab = await screen.findByTestId("tab-cash-account-ca_hdfc");
    fireEvent.click(hdfcCashTab);

    const recordBtn = await screen.findByTestId("cash-pool-record-withdrawal-btn");
    fireEvent.click(recordBtn);

    // Verify modal is open
    expect(await screen.findByTestId("record-cash-amount-input")).toBeInTheDocument();
    expect(screen.getByTestId("record-cash-submit-btn")).toBeInTheDocument();
  });
});
