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
          attach_pdf: false,
          include_bank_details: true,
        })
      );
      expect(alertMock).toHaveBeenCalledWith(
        "Payment reminder successfully sent to accounts@bata.com"
      );
    });
  });

  test("only renders payment reminder button on overdue invoices and not on paid or pending invoices", async () => {
    const mixedInvoices = [
      {
        id: "inv_overdue",
        invoice_no: "SSK-OVERDUE-01",
        client_name: "Bata India Ltd",
        net_amount: 100000,
        received_amount: 0,
        outstanding: 100000,
        status: "overdue",
        due_date: "2026-10-10",
        days_to_due: -12,
      },
      {
        id: "inv_paid",
        invoice_no: "SSK-PAID-02",
        client_name: "Relaxo Footwears",
        net_amount: 80000,
        received_amount: 80000,
        outstanding: 0,
        status: "paid",
        due_date: "2026-10-20",
        days_to_due: 0,
      },
      {
        id: "inv_pending",
        invoice_no: "SSK-PENDING-03",
        client_name: "Metro Brands",
        net_amount: 60000,
        received_amount: 0,
        outstanding: 60000,
        status: "pending",
        due_date: "2026-11-15",
        days_to_due: 24,
      },
    ];

    http.get.mockImplementation((url) => {
      if (url === "/invoices") return Promise.resolve({ data: mixedInvoices });
      return Promise.resolve({ data: [] });
    });

    render(<Invoices />);

    await waitFor(() => {
      expect(screen.getByText("SSK-OVERDUE-01")).toBeInTheDocument();
      expect(screen.getByText("SSK-PAID-02")).toBeInTheDocument();
      expect(screen.getByText("SSK-PENDING-03")).toBeInTheDocument();
    });

    // OVERDUE invoice MUST have the reminder button
    expect(screen.getByTestId("inv-reminder-SSK-OVERDUE-01")).toBeInTheDocument();

    // PAID and PENDING invoices MUST NOT have the reminder button
    expect(screen.queryByTestId("inv-reminder-SSK-PAID-02")).toBeNull();
    expect(screen.queryByTestId("inv-reminder-SSK-PENDING-03")).toBeNull();
  });

  test("handles multiple overdue invoices for client and allows consolidation", async () => {
    const multiOverduePreview = {
      ...mockPreview,
      client_overdue_count: 2,
      client_total_overdue: 175000,
      client_all_overdue: [
        {
          id: "inv_123",
          invoice_no: "SSK26-27-099",
          due_date: "2026-10-15",
          days_overdue: 7,
          outstanding: 100000,
        },
        {
          id: "inv_124",
          invoice_no: "SSK26-27-100",
          due_date: "2026-10-10",
          days_overdue: 12,
          outstanding: 75000,
        },
      ],
    };

    http.get.mockImplementation((url) => {
      if (url === "/invoices") return Promise.resolve({ data: [mockInvoice] });
      if (url === "/invoices/inv_123/payment-reminder-preview") {
        return Promise.resolve({ data: multiOverduePreview });
      }
      return Promise.resolve({ data: [] });
    });

    render(<Invoices />);

    await waitFor(() => {
      expect(screen.getByTestId("inv-reminder-SSK26-27-099")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("inv-reminder-SSK26-27-099"));

    // Modal opens and detects multiple overdue invoices banner
    await waitFor(() => {
      expect(screen.getByText(/Multiple Overdue Invoices/i)).toBeInTheDocument();
      expect(screen.getByText(/SSK26-27-100/i)).toBeInTheDocument();
    });

    // Send with multiple overdue invoices consolidated
    const sendSubmitBtn = screen.getByTestId("send-reminder-submit-btn");
    fireEvent.click(sendSubmitBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/invoices/inv_123/send-payment-reminder",
        expect.objectContaining({
          invoice_ids: ["inv_123", "inv_124"],
        })
      );
    });
  });

  test("opens batch overdue reminders modal and dispatches batch reminders", async () => {
    http.get.mockImplementation((url) => {
      if (url === "/invoices") return Promise.resolve({ data: [mockInvoice] });
      if (url === "/invoices/overdue-reminders-summary") {
        return Promise.resolve({
          data: {
            ok: true,
            total_overdue_invoices: 2,
            total_overdue_amount: 150000,
            clients: [
              {
                client_name: "Bata India Ltd",
                client_email: "accounts@bata.com",
                invoice_ids: ["inv_123", "inv_124"],
                invoices: [
                  { invoice_no: "SSK-001", outstanding: 100000 },
                  { invoice_no: "SSK-002", outstanding: 50000 },
                ],
                total_outstanding: 150000,
                max_days_overdue: 14,
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: [] });
    });

    http.post.mockImplementation((url) => {
      if (url === "/invoices/send-batch-overdue-reminders") {
        return Promise.resolve({
          data: { ok: true, sent_count: 1, failed_count: 0 },
        });
      }
      return Promise.resolve({ data: { ok: true } });
    });

    render(<Invoices />);

    // Click Remind Overdue button in top banner
    await waitFor(() => {
      expect(screen.getByTestId("batch-remind-overdue-banner-btn")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("batch-remind-overdue-banner-btn"));

    // Modal appears with client details
    await waitFor(() => {
      expect(screen.getByTestId("batch-overdue-reminder-modal")).toBeInTheDocument();
      expect(screen.getByText("Batch Collection Automation")).toBeInTheDocument();
      expect(screen.getByText("Total Overdue Invoices")).toBeInTheDocument();
      expect(screen.getByText("Send to 1 Client")).toBeInTheDocument();
    });

    // Submit batch reminders
    const submitBtn = screen.getByTestId("send-batch-reminders-submit-btn");
    expect(submitBtn).not.toBeDisabled();
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/invoices/send-batch-overdue-reminders",
        expect.objectContaining({
          batches: expect.arrayContaining([
            expect.objectContaining({
              client_name: "Bata India Ltd",
              to_email: "accounts@bata.com",
              invoice_ids: ["inv_123", "inv_124"],
            }),
          ]),
        })
      );
      expect(alertMock).toHaveBeenCalledWith(
        "Successfully sent overdue payment reminders to 1 client(s)."
      );
    });
  });
});
