import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import Payroll from "../Payroll";
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

const mockWorkers = [
  { id: "w1", name: "Ramesh Kumar", role: "cutting", phone: "9876543210" },
  { id: "w2", name: "Suresh Pal", role: "stitching", phone: "9876543211" },
];

const mockPayrollReport = {
  rows: [
    {
      worker_id: "w1",
      worker_name: "Ramesh Kumar",
      role: "cutting",
      pairs: 100,
      gross_amount: 15000,
      bonus: 500,
      deductions: 200,
      advances: 3000,
      net_payable: 12300,
      items: [],
    },
  ],
  totals: {
    pairs: 100,
    gross_amount: 15000,
    bonus: 500,
    deductions: 200,
    advances: 3000,
    net_payable: 12300,
  },
};

const mockBankAccounts = [
  {
    id: "bank-1",
    name: "HDFC Primary Current",
    bank_name: "HDFC Bank",
    account_number_last4: "4567",
    is_active: true,
  },
  {
    id: "bank-2",
    name: "ICICI Business Account",
    bank_name: "ICICI Bank",
    account_number_last4: "8899",
    is_active: true,
  },
];

const mockCashLedger = [
  {
    id: "cl-1",
    date: "2026-09-01",
    notes: "Office Petty Cash Withdrawal",
    withdrawal_amount: 50000,
    remaining_balance: 35000,
  },
];

const mockAdvances = [
  {
    id: "adv-1",
    worker_id: "w1",
    worker_name: "Ramesh Kumar",
    amount: 3000,
    date: "2026-09-02",
    txn_type: "advance",
    notes: "Mid-month advance",
    paid_via: "cash",
    cash_ledger_id: "cl-1",
    cash_ledger_notes: "Office Petty Cash Withdrawal",
    settled: false,
  },
];

describe("Payroll Payment Source & ERP Integration", () => {
  beforeEach(() => {
    jest.clearAllMocks();

    http.get.mockImplementation((url) => {
      if (url.startsWith("/reports/payroll")) {
        return Promise.resolve({ data: mockPayrollReport });
      }
      if (url === "/workers") {
        return Promise.resolve({ data: mockWorkers });
      }
      if (url === "/banking/accounts") {
        return Promise.resolve({ data: mockBankAccounts });
      }
      if (url === "/banking/cash-ledger") {
        return Promise.resolve({ data: mockCashLedger });
      }
      if (url === "/advances") {
        return Promise.resolve({ data: mockAdvances });
      }
      if (url.includes("/ledger")) {
        return Promise.resolve({
          data: {
            worker: mockWorkers[0],
            entries: [],
            total_earned: 15000,
            total_paid: 3000,
            net_balance: 12000,
          },
        });
      }
      return Promise.resolve({ data: [] });
    });

    http.post.mockImplementation((url) => {
      if (url === "/advances") {
        return Promise.resolve({ data: { id: "adv-new", ok: true } });
      }
      return Promise.resolve({ data: {} });
    });
  });

  test("loads payroll data and clicking Record Payment opens modal with Net Due prefilled", async () => {
    render(<Payroll />);

    await waitFor(() => {
      expect(screen.getByTestId("payroll-row-w1")).toBeInTheDocument();
    });

    const payBtn = screen.getByTestId("pay-w1");
    fireEvent.click(payBtn);

    await waitFor(() => {
      expect(screen.getByText("Record Wage Payment")).toBeInTheDocument();
    });

    // Check payment mode selector buttons are rendered
    expect(screen.getByTestId("mode-cash")).toBeInTheDocument();
    expect(screen.getByTestId("mode-bank")).toBeInTheDocument();
    expect(screen.getByTestId("mode-upi")).toBeInTheDocument();

    // Default cash ledger should be selected with remaining balance
    expect(screen.getByTestId("adv-cash-ledger")).toBeInTheDocument();
    expect(screen.getByText(/Office Petty Cash Withdrawal/i)).toBeInTheDocument();
    expect(screen.getAllByText(/35,000/).length).toBeGreaterThanOrEqual(1);
  });

  test("allows switching to Bank Transfer and selects a bank account", async () => {
    render(<Payroll />);

    await waitFor(() => {
      expect(screen.getByTestId("payroll-row-w1")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("pay-w1"));

    await waitFor(() => {
      expect(screen.getByTestId("mode-bank")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("mode-bank"));

    await waitFor(() => {
      expect(screen.getByTestId("adv-bank-account")).toBeInTheDocument();
    });

    expect(screen.getByText(/HDFC Primary Current/i)).toBeInTheDocument();

    // Submit payment via Bank Transfer
    const saveBtn = screen.getByTestId("adv-save");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/advances",
        expect.objectContaining({
          worker_id: "w1",
          amount: 12300,
          paid_via: "bank_transfer",
          bank_account_id: "bank-1",
          txn_type: "payment",
        })
      );
    });
  });

  test("allows switching to UPI, enters UPI ref, and submits", async () => {
    render(<Payroll />);

    await waitFor(() => {
      expect(screen.getByTestId("payroll-row-w1")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("pay-w1"));

    await waitFor(() => {
      expect(screen.getByTestId("mode-upi")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("mode-upi"));

    await waitFor(() => {
      expect(screen.getByTestId("adv-upi-ref")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId("adv-upi-ref"), {
      target: { value: "UPI/987654321098" },
    });

    fireEvent.click(screen.getByTestId("adv-save"));

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/advances",
        expect.objectContaining({
          worker_id: "w1",
          amount: 12300,
          paid_via: "upi",
          bank_account_id: "bank-1",
          upi_reference: "UPI/987654321098",
          txn_type: "payment",
        })
      );
    });
  });

  test("warns if cash amount exceeds cash pool remaining balance", async () => {
    render(<Payroll />);

    await waitFor(() => {
      expect(screen.getByTestId("payroll-row-w1")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("pay-w1"));

    await waitFor(() => {
      expect(screen.getByTestId("adv-cash-ledger")).toBeInTheDocument();
    });

    // Enter amount 50,000 which is greater than 35,000 pool balance
    const amountInput = screen.getByDisplayValue("12300");
    fireEvent.change(amountInput, { target: { value: "50000" } });

    await waitFor(() => {
      expect(screen.getByText(/Exceeds pool balance/i)).toBeInTheDocument();
    });
  });
});
