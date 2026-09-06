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

describe("BankReconciliation Record Deposit Flow", () => {
  const mockAccounts = [
    { id: "acc_hdfc", name: "HDFC Primary", bank_name: "HDFC", account_number_last4: "1234" },
    { id: "acc_icici", name: "ICICI Operational", bank_name: "ICICI", account_number_last4: "5678" },
  ];

  beforeEach(() => {
    jest.clearAllMocks();

    http.get.mockImplementation((url, config) => {
      if (url === "/banking/accounts") {
        return Promise.resolve({ data: mockAccounts });
      }
      if (url === "/banking/reconciliation/summary") {
        return Promise.resolve({
          data: {
            bank_account_name: "HDFC Primary",
            total_statement_lines: 3,
            unmatched_statement_lines: 1,
            matched_statement_lines: 2,
            statement_closing_balance: 152000,
            erp_calculated_balance: 152000,
            unreconciled_difference: 0,
            is_reconciled: true,
            summary: {
              matched_income: 60000,
              total_income: 60000,
              unmatched_income: 0,
              matched_expenses: 8000,
              total_expenses: 8000,
              unmatched_expenses: 0,
              net_operating_cashflow: 52000,
            },
            accounts: [
              {
                bank_account_id: "acc_hdfc",
                opening_balance: 100000,
                matched_income: 60000,
                total_reconciled_credits: 60000,
                matched_expenses: 8000,
                total_reconciled_debits: 8000,
                net_statement_flow: 52000,
              },
            ],
          },
        });
      }
      if (url === "/banking/statement-lines") {
        return Promise.resolve({
          data: [
            {
              id: "stmt_credit_1",
              date: "2026-09-02",
              narration: "NEFT REFUND FROM SOLE CORP",
              reference_no: "UTR987654321",
              debit_amount: 0,
              credit_amount: 15000,
              match_status: "unmatched",
              bank_account_id: "acc_hdfc",
            },
          ],
        });
      }
      if (url === "/banking/transfers/suggested") {
        return Promise.resolve({ data: { pairs: [] } });
      }
      if (url === "/banking/cash-withdrawals/suggested") {
        return Promise.resolve({ data: { total_suggestions: 0, candidates: [] } });
      }
      if (url === "/banking/erp-candidates/unmatched" || url === "/banking/unmatched-erp-candidates") {
        return Promise.resolve({
          data: {
            ok: true,
            total: 1,
            candidates: [
              {
                id: "dep_rec_1",
                type: "deposit",
                date: "2026-09-02",
                amount: 15000,
                description: "Vendor Refund - Sole Corp raw material credit",
                side: "credit",
                party: "Sole Corp",
                reference: "UTR987654321",
              },
            ],
          },
        });
      }
      if (url === "/banking/reconciliation-locks" || url === "/banking/periods/locks") {
        return Promise.resolve({ data: { locks: [] } });
      }
      return Promise.resolve({ data: [] });
    });
  });

  test("Allows recording a generic deposit via RecordDepositModal from header", async () => {
    http.post.mockResolvedValueOnce({
      data: {
        ok: true,
        id: "dep_rec_1",
        deposit: {
          id: "dep_rec_1",
          bank_account_id: "acc_hdfc",
          amount: 15000,
          date: "2026-09-02",
          category: "refund",
          description: "Sole Corp raw material refund",
          remarks: "NEFT REF 44210",
        },
      },
    });

    render(<BankReconciliation />);

    // Click + Record Deposit button in header
    const recordDepositBtn = await screen.findByTestId("record-deposit-btn");
    fireEvent.click(recordDepositBtn);

    // Modal opens
    const accountSelect = await screen.findByTestId("record-deposit-account-select");
    const amountInput = screen.getByTestId("record-deposit-amount-input");
    const dateInput = screen.getByTestId("record-deposit-date-input");
    const categorySelect = screen.getByTestId("record-deposit-category-select");
    const descInput = screen.getByTestId("record-deposit-description-input");
    const remarksInput = screen.getByTestId("record-deposit-remarks-input");

    fireEvent.change(accountSelect, { target: { value: "acc_hdfc" } });
    fireEvent.change(amountInput, { target: { value: "15000" } });
    fireEvent.change(dateInput, { target: { value: "2026-09-02" } });
    fireEvent.change(categorySelect, { target: { value: "refund" } });
    fireEvent.change(descInput, { target: { value: "Sole Corp raw material refund" } });
    fireEvent.change(remarksInput, { target: { value: "NEFT REF 44210" } });

    const submitBtn = screen.getByTestId("record-deposit-submit-btn");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith("/banking/deposits", {
        bank_account_id: "acc_hdfc",
        amount: 15000,
        date: "2026-09-02",
        category: "refund",
        description: "Sole Corp raw material refund",
        remarks: "NEFT REF 44210",
      });
    });
  });

  test("Renders deposit candidate in ERP expected tab with green badge", async () => {
    render(<BankReconciliation />);

    // Switch to ERP Expected Records tab
    const erpTab = await screen.findByTestId("tab-erp-expected");
    fireEvent.click(erpTab);

    // Verify deposit candidate is displayed
    expect(await screen.findByText("Vendor Refund - Sole Corp raw material credit")).toBeInTheDocument();
    expect(screen.getByText("Sole Corp")).toBeInTheDocument();
    expect(screen.getByText("+15,000.00")).toBeInTheDocument();

    // Verify tab contains + Record Deposit button
    const tabRecordBtn = screen.getByTestId("tab-record-deposit-btn");
    expect(tabRecordBtn).toBeInTheDocument();
  });

  test("Allows manual matching of an imported bank credit line to a recorded deposit", async () => {
    http.patch.mockResolvedValueOnce({
      data: {
        ok: true,
        id: "stmt_credit_1",
        match_status: "matched",
        matched_to: { type: "deposit", ref_id: "dep_rec_1" },
      },
    });

    render(<BankReconciliation />);

    // Select HDFC Account tab
    const accTab = await screen.findByTestId("tab-account-acc_hdfc");
    fireEvent.click(accTab);

    // Verify unmatched statement line appears
    await waitFor(() => {
      expect(screen.getByText("NEFT REFUND FROM SOLE CORP")).toBeInTheDocument();
    });

    // Find and click Match ERP button on the unmatched credit line
    const matchBtns = await screen.findAllByText("Match ERP");
    expect(matchBtns.length).toBeGreaterThan(0);
    fireEvent.click(matchBtns[0]);

    // Manual match modal opens, showing deposit candidate
    expect(await screen.findByText("Vendor Refund - Sole Corp raw material credit")).toBeInTheDocument();
    expect(screen.getByText("✓ Amount Match")).toBeInTheDocument();

    // Click "Link This"
    const linkBtn = screen.getByRole("button", { name: /link this/i });
    fireEvent.click(linkBtn);

    await waitFor(() => {
      expect(http.patch).toHaveBeenCalledWith("/banking/statement-lines/stmt_credit_1/match", {
        match_status: "matched",
        matched_to: { type: "deposit", ref_id: "dep_rec_1" },
      });
    });
  });

  test("Renders ERP Reconciled Balance card with both income and expense breakdown", async () => {
    render(<BankReconciliation />);

    // Check ERP balance value
    const erpVal = await screen.findByTestId("erp-balance-val");
    expect(erpVal).toBeInTheDocument();

    // Verify Reconciled Payouts & Expenses footer displays both credits and debits
    expect(screen.getByText(/Reconciled Payouts & Expenses/i)).toBeInTheDocument();
    expect(screen.getByTestId("erp-reconciled-credits")).toHaveTextContent("+60,000.00");
    expect(screen.getByTestId("erp-reconciled-debits")).toHaveTextContent("-8,000.00");
  });
});
