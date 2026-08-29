import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Production from "../Production";
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

describe("Production View Dispatch Details Modal", () => {
  const mockArchivedJob = {
    id: "job_arch_1",
    po_id: "po_123",
    po_number: "PO-DISP-001",
    client_name: "Relaxo Footwear",
    style_id: "style_1",
    style_code: "OXFORD-BLK",
    color: "Black",
    size: "8",
    quantity: 60,
    completed_qty: 60,
    stage: "dispatched",
    archived: true,
    invoice_generated_at: "2026-03-01T10:00:00Z",
  };

  const mockDispatchRecord = {
    id: "dr_123",
    invoice_id: "inv_123",
    invoice_no: "INV-2026-0088",
    dispatched_at: "2026-03-01T10:30:00Z",
    dispatched_by: "dispatch@ssk.com",
    client_name: "Relaxo Footwear",
    po_ids: ["po_123"],
    po_numbers: ["PO-DISP-001"],
    job_ids: ["job_arch_1"],
    total_cartons: 3,
    total_qty: 60,
    vehicle_no: "MH-04-AB-9999",
    transporter: "VRL Logistics",
    transport_mode: "Road Express",
    driver_name: "Suresh Kumar",
    driver_phone: "+91 9876543210",
    packing_cartons_snapshot: [
      { box_number: 1, style_code: "OXFORD-BLK", color: "Black", size: "8", qty: 20, ean_code: "8901234567890" },
      { box_number: 2, style_code: "OXFORD-BLK", color: "Black", size: "8", qty: 20, ean_code: "8901234567890" },
      { box_number: 3, style_code: "OXFORD-BLK", color: "Black", size: "8", qty: 20, ean_code: "8901234567890" },
    ],
  };

  const mockInvoice = {
    id: "inv_123",
    invoice_no: "INV-2026-0088",
    invoice_date: "2026-03-01",
    client_name: "Relaxo Footwear",
    vehicle_no: "MH-04-AB-9999",
    transport_mode: "Road Express",
    transporter: "VRL Logistics",
    driver_name: "Suresh Kumar",
    driver_phone: "+91 9876543210",
  };

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.startsWith("/production/jobs")) return Promise.resolve({ data: [] });
      if (url.startsWith("/workers")) return Promise.resolve({ data: [] });
      if (url.startsWith("/styles")) return Promise.resolve({ data: [{ code: "OXFORD-BLK", name: "Oxford Classic Black" }] });
      if (url.startsWith("/production/archive")) return Promise.resolve({ data: [mockArchivedJob] });
      if (url.startsWith("/packing-lists")) return Promise.resolve({ data: [] });
      if (url.startsWith("/dispatch-records?limit=1000")) return Promise.resolve({ data: [mockDispatchRecord] });
      if (url.startsWith("/dispatch-records/dr_123")) return Promise.resolve({ data: mockDispatchRecord });
      if (url.startsWith("/invoices")) return Promise.resolve({ data: [mockInvoice] });
      if (url.startsWith("/packing/cartons")) return Promise.resolve({ data: mockDispatchRecord.packing_cartons_snapshot });
      return Promise.resolve({ data: [] });
    });
  });

  test("Opens View Dispatch Details and displays full size-wise breakdown, carton assignments, vehicle info and document links", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    // Switch to Archive View via toggle-archive
    await waitFor(() => {
      expect(screen.getByTestId("toggle-archive")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("toggle-archive"));

    // Verify Archive view is rendered
    await waitFor(() => {
      expect(screen.getByTestId("archive-list")).toBeInTheDocument();
    });

    // Find the View Dispatch Details button on the archived tile
    const groupKey = `PO-DISP-001::OXFORD-BLK::Black`;
    const dispatchDetailsBtn = await screen.findByTestId(`archive-dispatch-details-${groupKey}`);
    expect(dispatchDetailsBtn).toBeInTheDocument();
    fireEvent.click(dispatchDetailsBtn);

    // Verify Dispatch Details Modal opens and finishes loading
    const modal = await screen.findByTestId("dispatch-details-modal");
    expect(modal).toBeInTheDocument();

    await waitFor(() => {
      expect(within(modal).getByText("VRL Logistics")).toBeInTheDocument();
    });

    const modalScope = within(modal);

    // 1. Verify Header & Metadata inside modal
    expect(modalScope.getByText("Relaxo Footwear")).toBeInTheDocument();
    expect(modalScope.getByText("VRL Logistics")).toBeInTheDocument();
    expect(modalScope.getByText("MH-04-AB-9999")).toBeInTheDocument();
    expect(modalScope.getByText("Road Express")).toBeInTheDocument();
    expect(modalScope.getByText("Suresh Kumar (+91 9876543210)")).toBeInTheDocument();
    expect(modalScope.getByText("60 pairs")).toBeInTheDocument();
    expect(modalScope.getByText("3 cartons")).toBeInTheDocument();

    // 2. Verify Consolidated Generated Document download buttons
    expect(modalScope.getByTestId("dispatch-modal-download-invoice")).toBeInTheDocument();
    expect(modalScope.getByTestId("dispatch-modal-download-packing")).toBeInTheDocument();
    expect(modalScope.getByTestId("dispatch-modal-download-labels")).toBeInTheDocument();
    expect(modalScope.getByTestId("dispatch-modal-download-cartonlist")).toBeInTheDocument();

    // 3. Verify Size-wise Quantity Breakdown table
    const sizeTable = modalScope.getByTestId("dispatch-size-breakdown-table");
    expect(sizeTable).toBeInTheDocument();
    expect(sizeTable).toHaveTextContent("OXFORD-BLK");
    expect(sizeTable).toHaveTextContent("Black");
    expect(sizeTable).toHaveTextContent("8");
    expect(sizeTable).toHaveTextContent("60 prs");

    // 4. Verify Carton Assignments table (which items in which carton)
    const cartonTable = modalScope.getByTestId("dispatch-cartons-table");
    expect(cartonTable).toBeInTheDocument();
    expect(cartonTable).toHaveTextContent("Carton #1");
    expect(cartonTable).toHaveTextContent("Carton #2");
    expect(cartonTable).toHaveTextContent("Carton #3");
    expect(cartonTable).toHaveTextContent("8901234567890");

    // 5. Close modal
    fireEvent.click(modalScope.getByTestId("dispatch-details-close"));
    await waitFor(() => {
      expect(screen.queryByTestId("dispatch-details-modal")).not.toBeInTheDocument();
    });
  });
});
