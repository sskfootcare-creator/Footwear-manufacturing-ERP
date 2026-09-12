import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import VendorPOs from "../VendorPOs";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => {
  const original = jest.requireActual("../../lib/api");
  return {
    ...original,
    http: {
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      delete: jest.fn(),
      patch: jest.fn(),
    },
    inr: (val) => `₹${Number(val || 0).toLocaleString("en-IN")}`,
  };
});

jest.mock("../../lib/auth", () => ({
  useAuth: () => ({
    user: { id: "user_1", role: "admin", name: "Admin Test", email: "admin@ssk.com" },
  }),
}));

describe("VendorPOs Payment Tracking & Vendor Ledger Integration", () => {
  const mockPOs = [
    {
      id: "vpo_1",
      po_number: "PO-VEN-2026-0010",
      vendor_id: "ven_1",
      vendor_name: "Apex Leather Supplies",
      status: "sent",
      total_amount: 15000,
      paid_amount: 5000,
      balance_due: 10000,
      payment_status: "partially_paid",
      expected_delivery_date: "2026-09-20",
      line_items: [
        { material_id: "mat_1", quantity: 50, rate: 300, amount: 15000, received_quantity: 0 },
      ],
    },
  ];

  const mockVendors = [
    {
      id: "ven_1",
      name: "Apex Leather Supplies",
      payment_terms_days: 30,
    },
  ];

  const mockAgeing = {
    summary: {
      total_vendors: 1,
      total_outstanding: 10000,
      total_current: 10000,
      total_days_1_30: 0,
      total_days_31_60: 0,
      total_days_60_plus: 0,
    },
    vendors: [
      {
        vendor_id: "ven_1",
        vendor_name: "Apex Leather Supplies",
        payment_terms_days: 30,
        outstanding_balance: 10000,
        current: 10000,
        days_1_30: 0,
        days_31_60: 0,
        days_60_plus: 0,
      },
    ],
  };

  const mockLedger = {
    vendor_id: "ven_1",
    vendor_name: "Apex Leather Supplies",
    payment_terms_days: 30,
    total_received: 15000,
    total_paid: 5000,
    current_balance: 10000,
    transactions: [
      {
        type: "receive",
        date: "2026-09-01",
        reference: "GRN-001",
        po_number: "PO-VEN-2026-0010",
        description: "Material Receipt (PO: PO-VEN-2026-0010)",
        debit: 0,
        credit: 15000,
        running_balance: 15000,
      },
      {
        type: "payment",
        date: "2026-09-05",
        reference: "UTR987654",
        po_number: "PO-VEN-2026-0010",
        description: "Payment via NEFT (UTR987654) [PO: PO-VEN-2026-0010]",
        debit: 5000,
        credit: 0,
        running_balance: 10000,
      },
    ],
  };

  const mockBankAccounts = [
    {
      id: "acc_hdfc",
      name: "Primary HDFC Current",
      bank_name: "HDFC Bank",
      account_number_last4: "4765",
      current_balance: 500000,
      active: true,
    },
    {
      id: "acc_uco",
      name: "Secondary UCO Current",
      bank_name: "UCO Bank",
      account_number_last4: "0946",
      current_balance: 250000,
      active: true,
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.startsWith("/vendor-pos")) return Promise.resolve({ data: mockPOs });
      if (url.startsWith("/vendors/ageing")) return Promise.resolve({ data: mockAgeing });
      if (url.includes("/ledger")) return Promise.resolve({ data: mockLedger });
      if (url.startsWith("/vendors")) return Promise.resolve({ data: mockVendors });
      if (url.startsWith("/materials")) return Promise.resolve({ data: [] });
      if (url.includes("/banking/accounts")) return Promise.resolve({ data: mockBankAccounts });
      return Promise.resolve({ data: [] });
    });
    http.post.mockResolvedValue({ data: { ok: true } });
  });

  test("Renders PO with financial tracking (Total, Paid, Balance, Status) and opens payment modal with ERP bank accounts", async () => {
    render(
      <MemoryRouter>
        <VendorPOs />
      </MemoryRouter>
    );

    // Wait for PO table to load
    await waitFor(() => {
      expect(screen.getByText("PO-VEN-2026-0010")).toBeInTheDocument();
    });

    // Check financial amounts (may appear in KPI tiles and table)
    expect(screen.getAllByText("₹15,000").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("₹5,000").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("₹10,000").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("partially paid")).toBeInTheDocument();

    // Click "Pay" button
    const payBtn = screen.getByTestId("pay-po-btn-vpo_1");
    expect(payBtn).toBeInTheDocument();
    fireEvent.click(payBtn);

    // Verify Payment Modal opened
    await waitFor(() => {
      expect(screen.getByTestId("vendor-payment-modal")).toBeInTheDocument();
    });
    expect(screen.getByText("Payment for PO: PO-VEN-2026-0010")).toBeInTheDocument();

    // Verify Paying Bank select lists ERP accounts
    const bankSelect = screen.getByTestId("pay-bank-account-select");
    expect(bankSelect).toBeInTheDocument();
    expect(screen.getByText(/Primary HDFC Current/)).toBeInTheDocument();
    expect(screen.getByText(/Secondary UCO Current/)).toBeInTheDocument();

    // Select the UCO bank account
    fireEvent.change(bankSelect, { target: { value: "acc_uco" } });

    // Click "Confirm Payment"
    const confirmBtn = screen.getByRole("button", { name: /confirm payment/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/vendor-pos/vpo_1/payments",
        expect.objectContaining({
          amount: 10000,
          mode: "NEFT",
          bank_account_id: "acc_uco",
        })
      );
    });
  });

  test("Opens Vendor Ledger Drawer with chronological transactions and running balance", async () => {
    render(
      <MemoryRouter>
        <VendorPOs />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Apex Leather Supplies")).toBeInTheDocument();
    });

    // Click "View Ledger"
    const ledgerLink = screen.getByRole("button", { name: /view ledger/i });
    fireEvent.click(ledgerLink);

    // Verify Ledger Drawer opens and loads data
    await waitFor(() => {
      expect(screen.getByTestId("vendor-ledger-drawer")).toBeInTheDocument();
    });
    expect(screen.getByText("Vendor Financial Ledger")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("GRN-001")).toBeInTheDocument();
      expect(screen.getByText("UTR987654")).toBeInTheDocument();
    });
  });

  test("Switches to Vendor Ledgers & Ageing tab and renders AP ageing buckets", async () => {
    render(
      <MemoryRouter>
        <VendorPOs />
      </MemoryRouter>
    );

    // Switch tab
    const ledgersTab = screen.getByTestId("tab-vendor-ledgers");
    fireEvent.click(ledgersTab);

    await waitFor(() => {
      expect(screen.getByTestId("vendor-ageing-view")).toBeInTheDocument();
    });

    expect(screen.getByText("Accounts Payable & Vendor Ageing Analysis")).toBeInTheDocument();
    expect(http.get).toHaveBeenCalledWith("/vendors/ageing");
  });
});
