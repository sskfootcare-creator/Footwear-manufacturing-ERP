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

describe("BankReconciliation Credit Matching & Scoping", () => {
  const mockAccounts = [
    {
      id: "acc_a",
      name: "Account A - UCO Bank",
      bank_name: "UCO Bank",
      account_number_last4: "1111",
      account_type: "b2b_client",
      opening_balance: 100000,
    },
    {
      id: "acc_b",
      name: "Account B - ICICI Bank",
      bank_name: "ICICI Bank",
      account_number_last4: "2222",
      account_type: "b2b_client",
      opening_balance: 200000,
    },
  ];

  const mockSummary = {
    accounts: [
      {
        bank_account_id: "acc_a",
        account_name: "Account A - UCO Bank",
        opening_balance: 100000,
        total_reconciled_credits: 0,
        total_reconciled_debits: 0,
        net_statement_flow: 0,
      },
      {
        bank_account_id: "acc_b",
        account_name: "Account B - ICICI Bank",
        opening_balance: 200000,
        total_reconciled_credits: 0,
        total_reconciled_debits: 0,
        net_statement_flow: 0,
      },
    ],
    summary: {
      net_operating_cashflow: 0,
      total_income: 0,
      total_expenses: 0,
    },
  };

  const mockStatementLinesAccountA = [
    {
      id: "line_a_1",
      bank_account_id: "acc_a",
      date: "2026-09-02",
      narration: "NEFT CR - APEX DISTRIBUTORS",
      reference_no: "NEFT889900",
      debit_amount: 0,
      credit_amount: 64500,
      running_balance: 164500,
      match_status: "unmatched",
    },
  ];

  const mockPaymentCandidatesAccountA = [
    {
      type: "payment",
      id: "pay_a_1",
      date: "2026-09-02",
      amount: 64500,
      description: "Client Payment PAY-001 - Apex Distributors",
      side: "credit",
      party: "Apex Distributors",
      reference: "NEFT889900",
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();

    http.get.mockImplementation((url, config) => {
      if (url === "/banking/accounts") {
        return Promise.resolve({ data: mockAccounts });
      }
      if (url === "/banking/reconciliation/summary") {
        return Promise.resolve({ data: mockSummary });
      }
      if (url === "/banking/statement-lines") {
        const accId = config?.params?.bank_account_id;
        if (!accId || accId === "all" || accId === "acc_a") {
          return Promise.resolve({ data: { items: mockStatementLinesAccountA } });
        }
        return Promise.resolve({ data: { items: [] } });
      }
      if (url === "/banking/transfers/suggested") {
        return Promise.resolve({ data: { pairs: [] } });
      }
      if (url === "/banking/unmatched-erp-candidates") {
        const accId = config?.params?.bank_account_id;
        if (accId === "acc_a" || !accId || accId === "all") {
          return Promise.resolve({ data: { candidates: mockPaymentCandidatesAccountA } });
        }
        // Account B must return no candidates
        return Promise.resolve({ data: { candidates: [] } });
      }
      if (url === "/banking/periods/locks") {
        return Promise.resolve({ data: { locks: [] } });
      }
      return Promise.resolve({ data: {} });
    });

    http.post.mockImplementation((url) => {
      if (url.includes("/banking/accounts/acc_a/reconcile")) {
        return Promise.resolve({
          data: {
            ok: true,
            dry_run: false,
            bank_account_id: "acc_a",
            bank_account_name: "Account A - UCO Bank",
            total_unmatched_evaluated: 1,
            auto_matched_count: 1,
            pending_review_count: 0,
            no_match_count: 0,
            min_confidence_percent: 95,
            matched_details: [
              {
                statement_line_id: "line_a_1",
                amount: 64500,
                side: "credit",
                matched_type: "payment",
                ref_id: "pay_a_1",
                candidate_title: "Apex Distributors",
                confidence_percent: 100,
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: { ok: true } });
    });
  });

  test("suggests matched credit in manual match modal scoped to Account A", async () => {
    render(<BankReconciliation />);

    // Select Account A tab
    const accATab = await screen.findByTestId("tab-account-acc_a");
    fireEvent.click(accATab);

    // Verify unmatched statement line appears
    await waitFor(() => {
      expect(screen.getByText("NEFT CR - APEX DISTRIBUTORS")).toBeInTheDocument();
    });

    // Click "Match ERP" button
    const matchBtns = await screen.findAllByText("Match ERP");
    expect(matchBtns.length).toBeGreaterThan(0);
    fireEvent.click(matchBtns[0]);

    // Verify modal appears and fetches candidates with bank_account_id="acc_a"
    await waitFor(() => {
      expect(screen.getByText("Manual Link & Reconcile")).toBeInTheDocument();
    });

    // Check Candidate was suggested with amount match indicator
    await waitFor(() => {
      expect(screen.getByText("Apex Distributors")).toBeInTheDocument();
      expect(screen.getByText("✓ Amount Match")).toBeInTheDocument();
    });

    // Verify http.get called with bank_account_id = "acc_a"
    const candidateCalls = http.get.mock.calls.filter(
      (c) => c[0] === "/banking/unmatched-erp-candidates" && c[1]?.params?.bank_account_id === "acc_a"
    );
    expect(candidateCalls.length).toBeGreaterThan(0);
  });

  test("runs bulk auto-reconcile on Account A and renders auto-reconcile results banner", async () => {
    render(<BankReconciliation />);

    // Select Account A tab
    const accATab = await screen.findByTestId("tab-account-acc_a");
    fireEvent.click(accATab);

    // Auto-reconcile button should be enabled for Account A
    const autoReconcileBtn = await screen.findByTestId("auto-reconcile-btn");
    expect(autoReconcileBtn).not.toBeDisabled();
    fireEvent.click(autoReconcileBtn);

    // Verify reconcile endpoint was invoked for acc_a
    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        expect.stringContaining("/banking/accounts/acc_a/reconcile")
      );
    });

    // Verify Auto-Reconcile summary banner is rendered in the UI
    const banner = await screen.findByTestId("auto-reconcile-result-banner");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent("1 auto-matched");
    expect(banner).toHaveTextContent("Account A - UCO Bank");

    // Dismiss banner
    const dismissBtn = screen.getByTestId("dismiss-reconcile-result-btn");
    fireEvent.click(dismissBtn);
    await waitFor(() => {
      expect(screen.queryByTestId("auto-reconcile-result-banner")).not.toBeInTheDocument();
    });
  });

  test("strictly scopes ERP candidates to selected bank account, isolating Account B", async () => {
    render(<BankReconciliation />);

    // Switch to Account B
    const accBTab = await screen.findByTestId("tab-account-acc_b");
    fireEvent.click(accBTab);

    // Check ERP candidates called for Account B
    await waitFor(() => {
      const bCalls = http.get.mock.calls.filter(
        (c) => c[0] === "/banking/unmatched-erp-candidates" && c[1]?.params?.bank_account_id === "acc_b"
      );
      expect(bCalls.length).toBeGreaterThan(0);
    });

    // Switch to Unmatched ERP Records tab
    const erpTab = screen.getByTestId("tab-erp-expected");
    fireEvent.click(erpTab);

    // Verify Account B has no ERP records
    await waitFor(() => {
      expect(screen.getByText("No unreconciled ERP records found.")).toBeInTheDocument();
    });
    expect(screen.queryByText("Apex Distributors")).not.toBeInTheDocument();
  });
});
