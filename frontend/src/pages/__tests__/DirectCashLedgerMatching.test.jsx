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

describe("Direct Cash Ledger Creation and Statement Matching Flow", () => {
  const mockAccounts = [
    { id: "acc_1", name: "HDFC Primary", bank_name: "HDFC", account_number_last4: "1234" },
    { id: "acc_2", name: "ICICI Operational", bank_name: "ICICI", account_number_last4: "5678" },
  ];

  beforeEach(() => {
    jest.clearAllMocks();

    http.get.mockImplementation((url) => {
      if (url === "/banking/accounts") {
        return Promise.resolve({ data: mockAccounts });
      }
      if (url === "/banking/reconciliation/summary") {
        return Promise.resolve({
          data: {
            bank_account_name: "All Accounts",
            total_statement_lines: 5,
            unmatched_statement_lines: 2,
            matched_statement_lines: 3,
            statement_closing_balance: 100000,
            erp_calculated_balance: 100000,
            unreconciled_difference: 0,
            is_reconciled: true,
          },
        });
      }
      if (url === "/banking/statement-lines") {
        return Promise.resolve({
          data: [
            {
              id: "stmt_line_101",
              date: "2026-09-01",
              narration: "ATM WDL / 9876 / KOTAK",
              debit_amount: 25000,
              credit_amount: 0,
              match_status: "unmatched",
              bank_account_id: "acc_1",
            },
          ],
        });
      }
      if (url === "/banking/transfers/suggested") {
        return Promise.resolve({ data: { pairs: [] } });
      }
      if (url === "/banking/cash-withdrawals/suggested") {
        return Promise.resolve({
          data: {
            total_suggestions: 1,
            candidates: [
              {
                id: "stmt_line_101",
                date: "2026-09-01",
                narration: "ATM WDL / 9876 / KOTAK",
                amount: 25000,
                debit_amount: 25000,
                match_status: "unmatched",
                bank_account_id: "acc_1",
                bank_account_name: "HDFC Primary",
                is_existing_manual_entry: true,
                existing_cash_ledger_id: "cl_manual_777",
                existing_cash_ledger_date: "2026-09-01",
                existing_cash_ledger_amount: 25000,
                existing_cash_ledger_remaining: 15000,
                suggestion_reason: "Matches existing manual cash withdrawal (₹25000.00 on 2026-09-01)",
              },
            ],
          },
        });
      }
      if (url === "/banking/erp-candidates/unmatched") {
        return Promise.resolve({ data: { candidates: [] } });
      }
      if (url === "/banking/reconciliation-locks") {
        return Promise.resolve({ data: { locks: [] } });
      }
      return Promise.resolve({ data: [] });
    });
  });

  test("Allows recording a direct cash withdrawal entry via RecordCashWithdrawalModal", async () => {
    http.post.mockResolvedValueOnce({
      data: {
        ok: true,
        id: "cl_manual_777",
        cash_ledger: {
          id: "cl_manual_777",
          bank_account_id: "acc_1",
          amount: 25000,
          remaining_balance: 25000,
          date: "2026-09-01",
        },
      },
    });

    render(<BankReconciliation />);

    // Click + Record Cash Withdrawal button in header
    const recordBtn = await screen.findByTestId("record-cash-withdrawal-btn");
    fireEvent.click(recordBtn);

    // Modal opens
    const accountSelect = await screen.findByTestId("record-cash-account-select");
    const amountInput = screen.getByTestId("record-cash-amount-input");
    const dateInput = screen.getByTestId("record-cash-date-input");
    const notesInput = screen.getByTestId("record-cash-notes-input");

    fireEvent.change(accountSelect, { target: { value: "acc_1" } });
    fireEvent.change(amountInput, { target: { value: "25000" } });
    fireEvent.change(dateInput, { target: { value: "2026-09-01" } });
    fireEvent.change(notesInput, { target: { value: "Karigar weekly wage disbursement" } });

    const submitBtn = screen.getByTestId("record-cash-submit-btn");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith("/banking/cash-ledger", {
        bank_account_id: "acc_1",
        amount: 25000,
        date: "2026-09-01",
        notes: "Karigar weekly wage disbursement",
      });
    });
  });

  test("Renders suggested cash withdrawals matching existing manual entry and links directly", async () => {
    http.post.mockResolvedValueOnce({
      data: {
        ok: true,
        statement_line_id: "stmt_line_101",
        cash_ledger_id: "cl_manual_777",
        is_linked_to_existing: true,
      },
    });

    render(<BankReconciliation />);

    // Switch to Suggested Cash Withdrawals tab
    const cashTab = await screen.findByTestId("tab-cash-withdrawals");
    fireEvent.click(cashTab);

    // Verify candidate matches manual entry badge and 1-click Link button
    expect(await screen.findByText(/Matches Manual Entry/i)).toBeInTheDocument();
    expect(screen.getByText(/No duplicate will be created/i)).toBeInTheDocument();

    const linkBtn = screen.getByTestId("link-cash-manual-stmt_line_101");
    fireEvent.click(linkBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith("/banking/cash-withdrawals/confirm", {
        statement_line_id: "stmt_line_101",
        existing_cash_ledger_id: "cl_manual_777",
        notes: "ATM WDL / 9876 / KOTAK",
      });
    });
  });

  test("Review & Link modal displays existing entry match info and sends existing_cash_ledger_id", async () => {
    http.post.mockResolvedValueOnce({
      data: {
        ok: true,
        statement_line_id: "stmt_line_101",
        cash_ledger_id: "cl_manual_777",
        is_linked_to_existing: true,
      },
    });

    render(<BankReconciliation />);

    const cashTab = await screen.findByTestId("tab-cash-withdrawals");
    fireEvent.click(cashTab);

    const reviewBtn = await screen.findByTestId("confirm-cash-suggestion-stmt_line_101");
    fireEvent.click(reviewBtn);

    // Modal shows "Link Statement to Cash Entry" and match info
    expect(await screen.findByRole("heading", { name: /Link Statement to Cash Entry/i })).toBeInTheDocument();
    expect(screen.getByText(/Found unlinked manual entry of/i)).toBeInTheDocument();

    const modalConfirmBtn = screen.getByTestId("modal-confirm-cash-btn");
    fireEvent.click(modalConfirmBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith("/banking/cash-withdrawals/confirm", {
        statement_line_id: "stmt_line_101",
        existing_cash_ledger_id: "cl_manual_777",
        notes: "ATM WDL / 9876 / KOTAK",
      });
    });
  });

  test("Falls back to standard new cash withdrawal creation when no manual entry matches", async () => {
    http.get.mockImplementation((url) => {
      if (url === "/banking/accounts") return Promise.resolve({ data: mockAccounts });
      if (url === "/banking/reconciliation/summary") {
        return Promise.resolve({
          data: {
            bank_account_name: "All Accounts",
            total_statement_lines: 1,
            unmatched_statement_lines: 1,
            matched_statement_lines: 0,
            statement_closing_balance: 50000,
            erp_calculated_balance: 50000,
            unreconciled_difference: 0,
            is_reconciled: true,
          },
        });
      }
      if (url === "/banking/statement-lines") return Promise.resolve({ data: [] });
      if (url === "/banking/transfers/suggested") return Promise.resolve({ data: { pairs: [] } });
      if (url === "/banking/cash-withdrawals/suggested") {
        return Promise.resolve({
          data: {
            total_suggestions: 1,
            candidates: [
              {
                id: "stmt_line_fresh_999",
                date: "2026-09-01",
                narration: "ATM CASH WDL / HDFC",
                amount: 15000,
                debit_amount: 15000,
                match_status: "unmatched",
                bank_account_id: "acc_1",
                bank_account_name: "HDFC Primary",
                is_existing_manual_entry: false,
                existing_cash_ledger_id: null,
                suggestion_reason: "Narration matches cash withdrawal pattern (ATM/CASH/SELF)",
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: [] });
    });

    http.post.mockResolvedValueOnce({
      data: {
        ok: true,
        statement_line_id: "stmt_line_fresh_999",
        cash_ledger_id: "cl_fresh_123",
        amount: 15000,
        remaining_balance: 15000,
      },
    });

    render(<BankReconciliation />);

    const cashTab = await screen.findByTestId("tab-cash-withdrawals");
    fireEvent.click(cashTab);

    // Shows candidate badge and Confirm Cash In-Hand button
    expect(await screen.findByText(/Cash In-Hand Candidate/i)).toBeInTheDocument();

    const confirmBtn = screen.getByTestId("confirm-cash-suggestion-stmt_line_fresh_999");
    fireEvent.click(confirmBtn);

    // Opens confirmation modal without existing link banner
    expect(await screen.findByRole("heading", { name: /Confirm Cash Withdrawal/i })).toBeInTheDocument();
    expect(screen.queryByText(/Matches Existing Manual Cash Withdrawal/i)).not.toBeInTheDocument();

    const modalConfirmBtn = screen.getByTestId("modal-confirm-cash-btn");
    fireEvent.click(modalConfirmBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith("/banking/cash-withdrawals/confirm", {
        statement_line_id: "stmt_line_fresh_999",
        notes: "ATM CASH WDL / HDFC",
      });
    });
  });
});

