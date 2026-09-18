import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Invoices from "../Invoices";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => {
  const original = jest.requireActual("../../lib/api");
  return {
    ...original,
    http: {
      get: jest.fn(),
      post: jest.fn(),
      delete: jest.fn(),
    },
  };
});

describe("Direct Invoice (No PO) Flow in Invoices.jsx", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url === "/invoices") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/invoices/cash-forecast") {
        return Promise.resolve({ data: null });
      }
      if (url === "/banking/accounts") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/banking/cash-accounts") {
        return Promise.resolve({ data: [] });
      }
      if (url === "/clients/master") {
        return Promise.resolve({
          data: [
            {
              id: "client-123",
              company_name: "Apex Footwear Stores",
              contact_person: "Suresh Gupta",
              phone: "9876543210",
              gstin: "09APEXF1234A1Z5",
              billing_address: "Mall Road, Kanpur",
              state_code: "09",
              payment_terms_days: 30,
            },
          ],
        });
      }
      return Promise.resolve({ data: {} });
    });
  });

  test("renders 'Create Direct Invoice' button and opens modal on click", async () => {
    render(<Invoices />);

    await waitFor(() => {
      expect(screen.getByTestId("btn-create-direct-invoice")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("btn-create-direct-invoice"));

    await waitFor(() => {
      expect(screen.getByText("Create Direct Tax Invoice")).toBeInTheDocument();
      expect(screen.getByText(/NO PO REQUIRED/i)).toBeInTheDocument();
    });
  });

  test("defaults to 5% GST and splits 2.5% CGST + 2.5% SGST for UP intra-state", async () => {
    render(<Invoices />);

    await waitFor(() => {
      expect(screen.getByTestId("btn-create-direct-invoice")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("btn-create-direct-invoice"));

    // Verify default 5% preset is selected and intra-state badge is shown
    await waitFor(() => {
      expect(
        screen.getByText(/Intra-State \(Within UP\): 2\.5% CGST \+ 2\.5% SGST/i)
      ).toBeInTheDocument();
    });

    // Default line item: 10 pairs @ 500 = 5000.
    // 2.5% CGST = 125, 2.5% SGST = 125. Grand total = 5250.
    expect(screen.getByText(/Grand Total:/i)).toBeInTheDocument();
    expect(screen.getByText("₹5,250")).toBeInTheDocument();
  });

  test("switches to 5% IGST when place of supply is out-of-state", async () => {
    render(<Invoices />);

    await waitFor(() => {
      expect(screen.getByTestId("btn-create-direct-invoice")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("btn-create-direct-invoice"));

    // Change place of supply dropdown to Delhi (07)
    await waitFor(() => {
      expect(screen.getByDisplayValue("09-Uttar Pradesh (Factory Home State)")).toBeInTheDocument();
    });
    const stateSelect = screen.getByDisplayValue("09-Uttar Pradesh (Factory Home State)");
    fireEvent.change(stateSelect, { target: { value: "07" } });

    // Verify badge updates to Inter-state IGST 5%
    await waitFor(() => {
      expect(screen.getByText(/Inter-State: 5% IGST/i)).toBeInTheDocument();
    });

    // 10 pairs @ 500 = 5000. IGST 5% = 250. Grand total = 5250.
    expect(screen.getByText("₹5,250")).toBeInTheDocument();
  });

  test("submits direct invoice to POST /api/invoices/direct", async () => {
    http.post.mockResolvedValueOnce({
      data: {
        ok: true,
        invoice_id: "inv-999",
        invoice_no: "SSK26-27-099",
      },
    });

    render(<Invoices />);

    await waitFor(() => {
      expect(screen.getByTestId("btn-create-direct-invoice")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("btn-create-direct-invoice"));

    // Fill Client Name
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/e\.g\. Apex Footwear Stores/i)).toBeInTheDocument();
    });
    const clientInput = screen.getByPlaceholderText(/e\.g\. Apex Footwear Stores/i);
    fireEvent.change(clientInput, { target: { value: "Metro Shoes Mumbai" } });

    // Fill Style code on first row
    const styleInput = screen.getByPlaceholderText(/e\.g\. DERBY-501/i);
    fireEvent.change(styleInput, { target: { value: "LOAFER-01" } });

    // Submit form
    const submitBtn = screen.getByText("Generate & Issue Direct Invoice");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/invoices/direct",
        expect.objectContaining({
          client_name: "Metro Shoes Mumbai",
          gst_rate: 5,
          cgst_rate: 2.5,
          sgst_rate: 2.5,
          igst_rate: 0,
          payment_terms_days: 30,
          line_items: [
            expect.objectContaining({
              style_code: "LOAFER-01",
              qty: 10,
              unit_price: 500,
            }),
          ],
        })
      );
    });
  });
});
