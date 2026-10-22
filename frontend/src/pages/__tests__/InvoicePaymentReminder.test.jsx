import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import Invoices from "../Invoices";
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

const mockInvoice = {
  id: "inv_123",
  invoice_no: "SSK26-27-099",
  client_name: "Bata India Ltd",
  client_email: "accounts@bata.com",
  net_amount: 150000,
  received_amount: 50000,
  outstanding: 100000,
  status: "overdue",
  due_date: "2026-10-15",
  days_to_due: -7,
  po_number: "PO-BATA-55",
};

const mockPreview = {
  ok: true,
  invoice_id: "inv_123",
  invoice_no: "SSK26-27-099",
  client_name: "Bata India Ltd",
  client_email: "accounts@bata.com",
  contact_person: "Mr. Sharma",
  net_amount: 150000,
  received_amount: 50000,
  outstanding: 100000,
  due_date: "2026-10-15",
  is_overdue: true,
  days_to_due: -7,
  status: "overdue",
  po_number: "PO-BATA-55",
  has_pdf: true,
  pdf_filename: "SSK26-27-099.pdf",
  email_configured: true,
  from_email: "billing@sskfootcare.com",
  from_name: "SSK Footcare Manufacturing",
  default_cc: "audit@sskfootcare.com",
  default_subject: "OVERDUE PAYMENT REMINDER: Invoice #SSK26-27-099 (Bata India Ltd) - ₹1,00,000.00",
  default_message_text: "Please arrange payment.",
  preview_html: "<div>Invoice Reminder</div>",
  reminder_history: [],
  reminder_count: 0,
};

describe("Invoices Tab Payment Reminder Flow", () => {
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
      if (url.includes("/banking/accounts")) {
        return Promise.resolve({ data: [] });
      }
      if (url.includes("/banking/cash-accounts")) {
        return Promise.resolve({ data: [] });
      }
      if (url === "/styles") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/invoices/inv_123/payment-reminder-preview") {
        return Promise.resolve({ data: mockPreview });
      }
      return Promise.resolve({ data: [] });
    });

    http.post.mockImplementation((url) => {
      if (url === "/invoices/inv_123/send-payment-reminder") {
        return Promise.resolve({
          data: {
            ok: true,
            message: "Payment reminder successfully sent to accounts@bata.com",
            reminder: {
              sent_at: "2026-10-22T12:00:00Z",
              sent_to: "accounts@bata.com",
            },
          },
        });
      }
      return Promise.resolve({ data: { ok: true } });
    });
  });

  afterEach(() => {
    alertMock.mockRestore();
  });

  test("renders Payment Reminder button and opens reminder modal", async () => {
    render(<Invoices />);

    // Wait for invoice row to appear
    await waitFor(() => {
      expect(screen.getByText("SSK26-27-099")).toBeInTheDocument();
    });

    // Check reminder action button exists
    const reminderBtn = screen.getByTestId("inv-reminder-SSK26-27-099");
    expect(reminderBtn).toBeInTheDocument();

    // Click reminder button
    fireEvent.click(reminderBtn);

    // Modal should appear
    await waitFor(() => {
      const modal = screen.getByTestId("payment-reminder-modal");
      expect(modal).toBeInTheDocument();
      expect(screen.getByText(/Direct Email Advisory/i)).toBeInTheDocument();
    });

    // Verify Gmail connection badge is displayed
    await waitFor(() => {
      expect(screen.getByText("Connected")).toBeInTheDocument();
      expect(screen.getByText(/billing@sskfootcare.com/i)).toBeInTheDocument();
    });

    // Verify recipient input is pre-filled
    const toInput = screen.getByTestId("reminder-to-email-input");
    expect(toInput.value).toBe("accounts@bata.com");

    // Click Send Reminder
    const sendSubmitBtn = screen.getByTestId("send-reminder-submit-btn");
    fireEvent.click(sendSubmitBtn);

    // Verify API called
    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/invoices/inv_123/send-payment-reminder",
        expect.objectContaining({
          to_email: "accounts@bata.com",
          attach_pdf: true,
          include_bank_details: true,
        })
      );
      expect(alertMock).toHaveBeenCalledWith(
        "Payment reminder successfully sent to accounts@bata.com"
      );
    });
  });
});
