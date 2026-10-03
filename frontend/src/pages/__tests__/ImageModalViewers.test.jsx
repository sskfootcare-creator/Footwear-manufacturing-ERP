import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Production from "../Production";
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
      patch: jest.fn(),
    },
  };
});

describe("Clickable Image Modals in Production Card & Invoice View Modal", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("1. Production Card Image is clickable and opens image preview modal", async () => {
    const mockJob = {
      id: "job_img_1",
      po_id: "po_img_123",
      po_number: "PO-IMG-001",
      client_name: "RELAXO FOOTWEARS",
      style_id: "style_img_1",
      style_code: "SSK_SNEAKER_01",
      created_at: "2026-09-15T08:30:00.000000+00:00",
      color: "BLACK/RED",
      size: "9",
      quantity: 100,
      completed_qty: 0,
      stage: "cutting",
      archived: false,
    };

    const mockStyle = {
      code: "SSK_SNEAKER_01",
      name: "Sneaker Pro",
      image_url: "https://example.com/images/sneaker_full.jpg",
      image_thumbnail_url: "https://example.com/images/sneaker_thumb.jpg",
    };

    http.get.mockImplementation((url) => {
      if (url.startsWith("/production/jobs")) {
        return Promise.resolve({ data: [mockJob] });
      }
      if (url.startsWith("/workers")) return Promise.resolve({ data: [] });
      if (url.startsWith("/styles")) return Promise.resolve({ data: [mockStyle] });
      if (url.startsWith("/production/archive")) return Promise.resolve({ data: [] });
      if (url.startsWith("/packing-lists")) return Promise.resolve({ data: [] });
      if (url.startsWith("/dispatch-records")) return Promise.resolve({ data: [] });
      if (url.startsWith("/invoices")) return Promise.resolve({ data: [] });
      if (url.startsWith("/vendors")) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });

    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    const key = "PO-IMG-001::SSK_SNEAKER_01::BLACK/RED";
    // Find the image container
    const imgContainer = await screen.findByTestId(`card-img-container-${key}`);
    expect(imgContainer).toBeInTheDocument();
    expect(imgContainer).toHaveAttribute("title", "Click to view full image in modal");

    // Click the image container
    fireEvent.click(imgContainer);

    // Verify modal opened
    const modal = await screen.findByTestId("image-view-modal");
    expect(modal).toBeInTheDocument();
    expect(screen.getByText(/Sneaker Pro \(SSK_SNEAKER_01\) · BLACK\/RED/i)).toBeInTheDocument();

    // Verify modal close button works
    const closeBtn = screen.getByTestId("image-modal-close");
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByTestId("image-view-modal")).not.toBeInTheDocument();
    });
  });

  test("2. Invoice View Modal displays line item thumbnail and clicking it opens image preview modal", async () => {
    const mockInvoice = {
      id: "inv_123",
      invoice_no: "INV-2026-0042",
      client_name: "METRO BRANDS LTD",
      invoice_date: "2026-09-18",
      status: "pending",
      subtotal: 50000,
      grand_total: 59000,
      outstanding: 59000,
      line_items_snapshot: [
        {
          style_code: "SSK_FORMAL_02",
          color: "TAN",
          size: "8",
          quantity: 50,
          unit_price: 1000,
          amount: 50000,
        },
      ],
    };

    const mockStyle = {
      code: "SSK_FORMAL_02",
      name: "Oxford Classic",
      image_url: "https://example.com/images/oxford_full.jpg",
      image_thumbnail_url: "https://example.com/images/oxford_thumb.jpg",
    };

    http.get.mockImplementation((url) => {
      if (url.startsWith("/invoices/cash-forecast")) return Promise.resolve({ data: null });
      if (url.startsWith("/banking/accounts")) return Promise.resolve({ data: [] });
      if (url.startsWith("/banking/cash-accounts")) return Promise.resolve({ data: [] });
      if (url.startsWith("/styles")) return Promise.resolve({ data: [mockStyle] });
      if (url === "/invoices/inv_123") return Promise.resolve({ data: mockInvoice });
      if (url.startsWith("/invoices")) return Promise.resolve({ data: [mockInvoice] });
      return Promise.resolve({ data: [] });
    });

    render(
      <MemoryRouter>
        <Invoices />
      </MemoryRouter>
    );

    // Click the view button on the invoice row
    const viewBtn = await screen.findByTestId("inv-view-INV-2026-0042");
    fireEvent.click(viewBtn);

    // Verify invoice detail modal is opened
    const invModal = await screen.findByTestId("invoice-modal");
    expect(invModal).toBeInTheDocument();

    // Verify thumbnail is displayed in line items
    const thumb = await screen.findByTestId("inv-line-item-thumb-0");
    expect(thumb).toBeInTheDocument();

    // Click the thumbnail
    fireEvent.click(thumb);

    // Verify image preview modal opened
    const imgModal = await screen.findByTestId("image-view-modal");
    expect(imgModal).toBeInTheDocument();
    expect(screen.getByText(/Oxford Classic \(SSK_FORMAL_02\) · TAN/i)).toBeInTheDocument();

    // Close preview modal
    const closeBtn = screen.getByTestId("image-modal-close");
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByTestId("image-view-modal")).not.toBeInTheDocument();
    });
  });
});
