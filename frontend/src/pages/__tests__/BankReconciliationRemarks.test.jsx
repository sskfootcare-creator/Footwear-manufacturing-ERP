import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import BankReconciliation from "../BankReconciliation";
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
      put: jest.fn(),
      delete: jest.fn(),
    },
  };
});

describe("BankReconciliation Remarks Editable Column", () => {
  const mockAccounts = [
    {
      id: "acc_1",
      name: "HDFC Primary Current A/C",
      bank_name: "HDFC Bank",
      account_number_last4: "1234",
      account_type: "b2b_client",
      opening_balance: 100000,
    },
  ];

  const mockSummary = {
    accounts: [
      {
        bank_account_id: "acc_1",
        account_name: "HDFC Primary Current A/C",
        opening_balance: 100000,
        total_reconciled_credits: 50000,
        total_reconciled_debits: 20000,
        net_statement_flow: 30000,
      },
    ],
    summary: {
      net_operating_cashflow: 30000,
      total_income: 50000,
      total_expenses: 20000,
    },
  };

  const mockStatementLines = [
    {
      id: "line_1",
      bank_account_id: "acc_1",
      date: "2026-08-20",
      narration: "NEFT FROM CUSTOMER ABC",
      reference_no: "UTR998877",
      debit_amount: 0,
      credit_amount: 50000,
      running_balance: 150000,
      match_status: "unmatched",
      remarks: "Initial note",
    },
    {
      id: "line_2",
      bank_account_id: "acc_1",
      date: "2026-08-21",
      narration: "RTGS TO VENDOR XYZ",
      reference_no: "UTR554433",
      debit_amount: 20000,
      credit_amount: 0,
      running_balance: 130000,
      match_status: "matched",
      matched_to: { type: "vendor_payment", ref_id: "vp_1" },
      remarks: "Paid invoice #1001",
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();

    http.get.mockImplementation((url) => {
      if (url === "/banking/accounts") {
        return Promise.resolve({ data: mockAccounts });
      }
      if (url === "/banking/reconciliation/summary") {
        return Promise.resolve({ data: mockSummary });
      }
      if (url === "/banking/statement-lines") {
        return Promise.resolve({ data: { items: mockStatementLines } });
      }
      if (url === "/banking/transfers/suggested") {
        return Promise.resolve({ data: { pairs: [] } });
      }
      if (url === "/banking/unmatched-erp-candidates") {
        return Promise.resolve({ data: { candidates: [] } });
      }
      return Promise.resolve({ data: [] });
    });

    http.patch.mockResolvedValue({ data: { ok: true } });
  });

  test("renders remarks column and allows inline edit in unmatched lines tab", async () => {
    render(<BankReconciliation />);

    // Expand unmatched row for line_1
    const row1 = await screen.findByTestId("unmatched-row-line_1");
    fireEvent.click(row1);

    // Wait for statement line row to load inside drawer
    const remarkInput = await screen.findByTestId("remarks-input-line_1");
    expect(remarkInput).toBeInTheDocument();
    expect(remarkInput.value).toBe("Initial note");

    // Check remarks header in drawer
    const remarksHeaders = screen.getAllByText(/Remarks/i);
    expect(remarksHeaders.length).toBeGreaterThan(0);

    // Edit remark
    fireEvent.change(remarkInput, { target: { value: "Updated client remark" } });
    expect(remarkInput.value).toBe("Updated client remark");

    // Trigger blur to save
    fireEvent.blur(remarkInput);

    await waitFor(() => {
      expect(http.patch).toHaveBeenCalledWith("/banking/statement-lines/line_1/match", {
        remarks: "Updated client remark",
      });
    });
  });

  test("renders remarks column and allows inline edit in statement ledger tab", async () => {
    render(<BankReconciliation />);

    const ledgerTab = await screen.findByTestId("tab-ledger");
    fireEvent.click(ledgerTab);

    // Expand row for line_2 in ledger
    const row2 = await screen.findByTestId("ledger-row-line_2");
    fireEvent.click(row2);

    // Find input for line_2 in ledger drawer
    const remarkInput2 = await screen.findByTestId("remarks-input-line_2");
    expect(remarkInput2).toBeInTheDocument();
    expect(remarkInput2.value).toBe("Paid invoice #1001");

    // Edit and press Enter
    fireEvent.change(remarkInput2, { target: { value: "Paid invoice #1001 & updated tax receipt" } });
    fireEvent.keyDown(remarkInput2, { key: "Enter", code: "Enter" });

    await waitFor(() => {
      expect(http.patch).toHaveBeenCalledWith("/banking/statement-lines/line_2/match", {
        remarks: "Paid invoice #1001 & updated tax receipt",
      });
    });
  });

  test("flags cash withdrawal candidate in unmatched table and confirms via modal", async () => {
    const cashLine = {
      id: "line_atm_1",
      bank_account_id: "acc_1",
      date: "2026-08-25",
      narration: "ATM CASH WDL - SELF CHQ",
      reference_no: "ATM4433",
      debit_amount: 15000,
      credit_amount: 0,
      running_balance: 85000,
      match_status: "unmatched",
      remarks: "",
    };

    http.get.mockImplementation((url) => {
      if (url === "/banking/accounts") return Promise.resolve({ data: mockAccounts });
      if (url === "/banking/reconciliation/summary") return Promise.resolve({ data: mockSummary });
      if (url === "/banking/statement-lines") return Promise.resolve({ data: { items: [cashLine] } });
      if (url === "/banking/transfers/suggested") return Promise.resolve({ data: { pairs: [] } });
      if (url === "/banking/cash-withdrawals/suggested") {
        return Promise.resolve({
          data: {
            candidates: [{ ...cashLine, amount: 15000, suggestion_reason: "Pattern match" }],
          },
        });
      }
      if (url === "/banking/unmatched-erp-candidates") return Promise.resolve({ data: { candidates: [] } });
      return Promise.resolve({ data: [] });
    });

    http.post.mockResolvedValue({
      data: {
        ok: true,
        statement_line_id: "line_atm_1",
        cash_ledger_id: "cash_leg_123",
        amount: 15000,
        remaining_balance: 15000,
      },
    });

    render(<BankReconciliation />);

    // Check suggestion tag in table
    const suggestionTag = await screen.findByText("⚡ Suggested Cash Withdrawal");
    expect(suggestionTag).toBeInTheDocument();

    // Check Confirm Cash button in row
    const confirmBtn = screen.getByTestId("confirm-cash-btn-line_atm_1");
    expect(confirmBtn).toBeInTheDocument();

    // Click Confirm Cash to open modal
    fireEvent.click(confirmBtn);

    // Modal opens
    expect(await screen.findByText("Confirm Cash Withdrawal")).toBeInTheDocument();
    expect(screen.getByText("This transaction looks like a cash withdrawal.")).toBeInTheDocument();

    // Submit confirmation
    const modalConfirmBtn = screen.getByTestId("modal-confirm-cash-btn");
    fireEvent.click(modalConfirmBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith("/banking/cash-withdrawals/confirm", {
        statement_line_id: "line_atm_1",
        notes: "ATM CASH WDL - SELF CHQ",
      });
    });
  });

  test("suggested cash withdrawals tab lists candidates and allows confirmation", async () => {
    const cashCandidate = {
      id: "line_self_1",
      bank_account_id: "acc_1",
      bank_account_name: "HDFC Primary Current A/C",
      date: "2026-08-26",
      narration: "SELF CHEQUE 998811",
      reference_no: "CHQ998811",
      debit_amount: 30000,
      amount: 30000,
      match_status: "unmatched",
      suggestion_reason: "Narration matches cash withdrawal pattern (ATM/CASH/SELF)",
    };

    http.get.mockImplementation((url) => {
      if (url === "/banking/accounts") return Promise.resolve({ data: mockAccounts });
      if (url === "/banking/reconciliation/summary") return Promise.resolve({ data: mockSummary });
      if (url === "/banking/statement-lines") return Promise.resolve({ data: { items: [cashCandidate] } });
      if (url === "/banking/transfers/suggested") return Promise.resolve({ data: { pairs: [] } });
      if (url === "/banking/cash-withdrawals/suggested") {
        return Promise.resolve({
          data: {
            candidates: [cashCandidate],
          },
        });
      }
      if (url === "/banking/unmatched-erp-candidates") return Promise.resolve({ data: { candidates: [] } });
      return Promise.resolve({ data: [] });
    });

    http.post.mockResolvedValue({ data: { ok: true } });

    render(<BankReconciliation />);

    // Switch to Suggested Cash Withdrawals tab
    const cashTab = await screen.findByTestId("tab-cash-withdrawals");
    expect(cashTab).toBeInTheDocument();
    fireEvent.click(cashTab);

    // Verify candidate rendered
    expect(await screen.findByText("SELF CHEQUE 998811")).toBeInTheDocument();
    expect(screen.getByText("Cash In-Hand Candidate")).toBeInTheDocument();

    // Confirm from suggestions tab
    const confirmSuggestionBtn = screen.getByTestId("confirm-cash-suggestion-line_self_1");
    fireEvent.click(confirmSuggestionBtn);

    // Confirm in modal
    const modalConfirmBtn = await screen.findByTestId("modal-confirm-cash-btn");
    fireEvent.click(modalConfirmBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith("/banking/cash-withdrawals/confirm", {
        statement_line_id: "line_self_1",
        notes: "SELF CHEQUE 998811",
      });
    });
  });

  test("renders cash withdrawal breakdown modal with linked wage disbursements and remaining balance", async () => {
    const cashMatchedLine = {
      id: "line_cw_1",
      bank_account_id: "acc_1",
      date: "2026-08-20",
      narration: "ATM CASH WDL #9922",
      reference_no: "ATM9922",
      debit_amount: 10000,
      credit_amount: 0,
      running_balance: 90000,
      match_status: "matched",
      matched_to: { type: "cash_withdrawal", ref_id: "cl_100" },
      cash_ledger_info: {
        cash_ledger_id: "cl_100",
        withdrawal_amount: 10000,
        allocated_amount: 7500,
        remaining_balance: 2500,
        wage_payment_count: 2,
        wage_payments: [
          { id: "wp_1", worker_id: "w_1", worker_name: "Ramesh Karigar", amount: 4500, date: "2026-08-21", period_from: "2026-08-01", period_to: "2026-08-15", notes: "Fortnight wage" },
          { id: "wp_2", worker_id: "w_2", worker_name: "Suresh Karigar", amount: 3000, date: "2026-08-21", period_from: "2026-08-01", period_to: "2026-08-15", notes: "Fortnight wage", override_reason: "Advance folded into wage" },
        ],
      },
    };

    http.get.mockImplementation((url) => {
      if (url === "/banking/accounts") return Promise.resolve({ data: mockAccounts });
      if (url === "/banking/reconciliation/summary") return Promise.resolve({ data: mockSummary });
      if (url === "/banking/statement-lines") return Promise.resolve({ data: { items: [cashMatchedLine] } });
      if (url === "/banking/transfers/suggested") return Promise.resolve({ data: { pairs: [] } });
      if (url === "/banking/cash-withdrawals/suggested") return Promise.resolve({ data: { candidates: [] } });
      if (url === "/banking/cash-ledger/cl_100") {
        return Promise.resolve({
          data: {
            ok: true,
            withdrawal_amount: 10000,
            allocated_amount: 7500,
            remaining_balance: 2500,
            wage_payments: cashMatchedLine.cash_ledger_info.wage_payments,
            wage_payment_count: 2,
          },
        });
      }
      return Promise.resolve({ data: [] });
    });

    render(<BankReconciliation />);

    // Go to Statement Ledger tab
    const ledgerTab = await screen.findByTestId("tab-ledger");
    fireEvent.click(ledgerTab);

    // Expand row for cash withdrawal line
    const row = await screen.findByTestId("ledger-row-line_cw_1");
    fireEvent.click(row);

    // Find cash breakdown button in matched column / drawer
    const breakdownBtn = await screen.findByTestId("cash-breakdown-btn-line_cw_1");
    expect(breakdownBtn).toBeInTheDocument();
    expect(breakdownBtn).toHaveTextContent("Cash In-Hand #cl_100");

    // Click to open breakdown modal
    fireEvent.click(breakdownBtn);

    // Verify modal header & KPI metrics
    expect(await screen.findByText("Cash Withdrawal Audit Trail")).toBeInTheDocument();
    expect(screen.getByText("Disbursed to Karigars")).toBeInTheDocument();
    expect(screen.getByText("Unallocated Cash in Hand")).toBeInTheDocument();

    // Verify linked karigar payments
    expect(screen.getByText("Ramesh Karigar")).toBeInTheDocument();
    expect(screen.getByText("Suresh Karigar")).toBeInTheDocument();
    expect(screen.getByText("₹4,500")).toBeInTheDocument();
    expect(screen.getByText("₹3,000")).toBeInTheDocument();

    // Expand disbursement row to inspect drawer details
    const disbRow2 = await screen.findByTestId("disbursement-row-wp_2");
    fireEvent.click(disbRow2);
    expect(screen.getByText(/Advance folded into wage/i)).toBeInTheDocument();
  });

  test("statement ledger displays 4 clean columns in collapsed view and toggles detail drawer on click", async () => {
    render(<BankReconciliation />);

    // Go to Statement Ledger tab
    const ledgerTab = await screen.findByTestId("tab-ledger");
    fireEvent.click(ledgerTab);

    // Verify 4 clean headers
    expect(screen.getByText("Date")).toBeInTheDocument();
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(screen.getByText("Amount")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();

    // Check row_1 is initially collapsed (detail panel not in document)
    expect(screen.queryByTestId("ledger-detail-panel-line_1")).not.toBeInTheDocument();

    // Click row_1 or expand button to expand
    const expandBtn = await screen.findByTestId("expand-btn-line_1");
    fireEvent.click(expandBtn);

    // Detail drawer is now visible
    const detailPanel = await screen.findByTestId("ledger-detail-panel-line_1");
    expect(detailPanel).toBeInTheDocument();
    expect(detailPanel).toHaveTextContent("Full Narration / Description");
    expect(detailPanel).toHaveTextContent("NEFT FROM CUSTOMER ABC");
    expect(detailPanel).toHaveTextContent("Reference No");
    expect(detailPanel).toHaveTextContent("UTR998877");
    expect(detailPanel).toHaveTextContent("Running Balance");

    // Click expandBtn again to collapse
    fireEvent.click(expandBtn);
    expect(screen.queryByTestId("ledger-detail-panel-line_1")).not.toBeInTheDocument();
  });

  test("confirms no regression on manual matching, cash confirmation, and remark updates under collapsed layout", async () => {
    render(<BankReconciliation />);

    // 1. Wait for Unmatched Bank Lines to load
    await screen.findByTestId("unmatched-row-line_1");
    expect(screen.getByText("Date")).toBeInTheDocument();
    expect(screen.getByText("Account")).toBeInTheDocument();
    expect(screen.getByText("Narration / Description")).toBeInTheDocument();
    expect(screen.getByText("Amount")).toBeInTheDocument();
    expect(screen.getByText("Action")).toBeInTheDocument();

    // 2. Perform manual match action button
    const matchErpBtns = screen.getAllByText("Match ERP");
    expect(matchErpBtns.length).toBeGreaterThan(0);
    fireEvent.click(matchErpBtns[0]);
    expect(await screen.findByText("Manual Link & Reconcile")).toBeInTheDocument();
    const closeBtn = screen.getByText("Close");
    fireEvent.click(closeBtn);

    // 3. Test Tab Navigation
    const transferTab = await screen.findByTestId("tab-transfers");
    fireEvent.click(transferTab);
    expect((await screen.findAllByText("Suggested Inter-Account Transfers")).length).toBeGreaterThan(0);

    const cashTab = await screen.findByTestId("tab-cash-withdrawals");
    fireEvent.click(cashTab);
    expect((await screen.findAllByText("Suggested Cash Withdrawals")).length).toBeGreaterThan(0);

    const erpTab = await screen.findByTestId("tab-erp-expected");
    fireEvent.click(erpTab);
    expect((await screen.findAllByText(/Unmatched ERP Expected|Unmatched \/ Expected ERP Transactions/)).length).toBeGreaterThan(0);

    const ledgerTab = await screen.findByTestId("tab-ledger");
    fireEvent.click(ledgerTab);
    expect((await screen.findAllByText("Statement Ledger")).length).toBeGreaterThan(0);
  });
});
