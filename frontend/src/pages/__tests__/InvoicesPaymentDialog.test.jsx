import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import Invoices, { PaymentDialog } from "../Invoices";
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

const mockBankAccounts = [
  {
    id: "bank_acc_101",
    name: "HDFC Primary Current",
    bank_name: "HDFC Bank",
    account_number_last4: "5432",
    active: true,
  },
  {
    id: "bank_acc_102",
    name: "UCO Operations",
    bank_name: "UCO Bank",
    account_number_last4: "9876",
    active: true,
  },
];

const mockInvoice = {
  id: "inv_001",
  invoice_no: "INV-2026-001",
  client_name: "Metro Shoes",
  net_amount: 50000,
  outstanding: 30000,
  status: "partial",
};

describe("Invoices PaymentDialog Bank Account Dropdown", () => {
  let alertMock;

  beforeEach(() => {
    jest.clearAllMocks();
    alertMock = jest.spyOn(window, "alert").mockImplementation(() => {});

    http.get.mockImplementation((url) => {
      if (url === "/invoices") {
        return Promise.resolve({ data: [mockInvoice] });
      }
      if (url === "/invoices/cash-forecast") {
        return Promise.resolve({ data: null });
      }
      if (url === "/banking/accounts") {
        return Promise.resolve({ data: mockBankAccounts });
      }
      return Promise.resolve({ data: [] });
    });

    http.post.mockResolvedValue({ data: { ok: true } });
  });

  afterEach(() => {
    alertMock.mockRestore();
  });

  it("fetches active bank accounts and renders them in PaymentDialog dropdown", async () => {
    render(
      <PaymentDialog
        invoiceMeta={mockInvoice}
        onClose={jest.fn()}
        onSaved={jest.fn()}
      />
    );

    await waitFor(() => {
      expect(http.get).toHaveBeenCalledWith("/banking/accounts", {
        params: { active: true },
      });
    });

    const select = await screen.findByTestId("pay-bank-account");
    expect(select).toBeInTheDocument();
    expect(select).toHaveAttribute("required");

    expect(screen.getByText(/-- Select Bank Account --/i)).toBeInTheDocument();
    expect(screen.getByText(/HDFC Primary Current/i)).toBeInTheDocument();
    expect(screen.getByText(/UCO Operations/i)).toBeInTheDocument();
  });

  it("requires a bank account to be selected before submitting", async () => {
    const onSaved = jest.fn();
    render(
      <PaymentDialog
        invoiceMeta={mockInvoice}
        onClose={jest.fn()}
        onSaved={onSaved}
        bankAccounts={mockBankAccounts}
      />
    );

    const submitBtn = screen.getByTestId("pay-submit");
    fireEvent.click(submitBtn);

    expect(alertMock).toHaveBeenCalledWith("Please select a bank account");
    expect(http.post).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("submits bank_account_id along with payment fields to /payments", async () => {
    const onSaved = jest.fn();
    render(
      <PaymentDialog
        invoiceMeta={mockInvoice}
        onClose={jest.fn()}
        onSaved={onSaved}
        bankAccounts={mockBankAccounts}
      />
    );

    const select = screen.getByTestId("pay-bank-account");
    fireEvent.change(select, { target: { value: "bank_acc_101" } });

    fireEvent.change(screen.getByTestId("pay-amount"), {
      target: { value: "15000" },
    });
    fireEvent.change(screen.getByTestId("pay-ref"), {
      target: { value: "UTR-TEST-12345" },
    });

    const submitBtn = screen.getByTestId("pay-submit");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith("/payments", {
        invoice_ids: ["inv_001"],
        amount: 15000,
        payment_date: expect.any(String),
        mode: "NEFT",
        reference: "UTR-TEST-12345",
        bank: "HDFC Bank",
        bank_account_id: "bank_acc_101",
        notes: "",
      });
    });

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalled();
    });
  });

  it("integrates seamlessly into Invoices list payment recording flow", async () => {
    render(<Invoices />);

    await waitFor(() => {
      expect(screen.getByText("INV-2026-001")).toBeInTheDocument();
    });

    // Click Record Payment button on invoice
    const payBtn = screen.getByTestId("inv-payment-INV-2026-001");
    fireEvent.click(payBtn);

    const dialog = await screen.findByTestId("payment-dialog");
    expect(dialog).toBeInTheDocument();

    const select = await screen.findByTestId("pay-bank-account");
    expect(select).toBeInTheDocument();
    expect(screen.getByText(/HDFC Primary Current/i)).toBeInTheDocument();

    // Select UCO account
    fireEvent.change(select, { target: { value: "bank_acc_102" } });

    const submitBtn = screen.getByTestId("pay-submit");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/payments",
        expect.objectContaining({
          invoice_ids: ["inv_001"],
          amount: 30000,
          bank_account_id: "bank_acc_102",
        })
      );
    });
  });

  it("supports recording cash receipts linked to a cash account", async () => {
    const mockCashAccounts = [
      {
        id: "cash_acc_201",
        name: "Cash (HDFC)",
        source_bank_account_id: "bank_acc_101",
        current_balance: 15000,
      },
    ];

    const onSaved = jest.fn();
    render(
      <PaymentDialog
        invoiceMeta={mockInvoice}
        onClose={jest.fn()}
        onSaved={onSaved}
        bankAccounts={mockBankAccounts}
        cashAccounts={mockCashAccounts}
      />
    );

    const select = screen.getByTestId("pay-bank-account");
    expect(screen.getByText(/Cash \(HDFC\)/i)).toBeInTheDocument();

    // Select cash account
    fireEvent.change(select, { target: { value: "cash_cash_acc_201" } });

    // Mode is automatically switched to Cash
    expect(screen.getByTestId("pay-mode").value).toBe("Cash");
    expect(screen.getByText(/Physical Cash Account selected/i)).toBeInTheDocument();

    const submitBtn = screen.getByTestId("pay-submit");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/payments",
        expect.objectContaining({
          invoice_ids: ["inv_001"],
          amount: 30000,
          account_type: "cash",
          cash_account_id: "cash_acc_201",
          bank_account_id: "bank_acc_101",
          mode: "Cash",
        })
      );
    });
    expect(onSaved).toHaveBeenCalled();
  });
});
