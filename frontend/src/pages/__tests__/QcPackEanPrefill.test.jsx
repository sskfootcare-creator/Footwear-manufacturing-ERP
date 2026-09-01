import { render, screen, waitFor, fireEvent } from "@testing-library/react";
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

describe("QC-Pack Confirmation EAN Pre-fill and Visual Indicators", () => {
  const mockJobs = [
    {
      id: "job_1",
      po_id: "po_123",
      po_number: "PO-BATA-001",
      client_name: "Bata India",
      style_id: "style_1",
      style_code: "ART-BATA",
      color: "Black",
      size: "7",
      quantity: 50,
      completed_qty: 50,
      stage: "qc_pack",
      status: "in_progress",
    },
    {
      id: "job_2",
      po_id: "po_123",
      po_number: "PO-BATA-001",
      client_name: "Bata India",
      style_id: "style_1",
      style_code: "ART-BATA",
      color: "Black",
      size: "8",
      quantity: 50,
      completed_qty: 50,
      stage: "qc_pack",
      status: "in_progress",
    },
    {
      id: "job_3",
      po_id: "po_123",
      po_number: "PO-BATA-001",
      client_name: "Bata India",
      style_id: "style_1",
      style_code: "ART-BATA",
      color: "Black",
      size: "9",
      quantity: 30,
      completed_qty: 30,
      stage: "qc_pack",
      status: "in_progress",
    },
  ];

  const mockStyles = [
    {
      id: "style_1",
      code: "ART-BATA",
      name: "Bata Formal",
      colors: [{ name: "Black" }],
      default_pairs_per_carton: { default: 50 },
    },
  ];

  const mockPoEanCodes = [
    {
      id: "ean_1",
      po_id: "po_123",
      po_number: "PO-BATA-001",
      style_code: "ART-BATA",
      color: "Black",
      size: "7",
      ean_code: "8901234500007",
    },
    {
      id: "ean_2",
      po_id: "po_123",
      po_number: "PO-BATA-001",
      style_code: "ART-BATA",
      color: "Black",
      size: "8",
      ean_code: "8901234500008",
    },
    // Note: Size 9 is deliberately missing from PO's imported barcode file
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.startsWith("/production/jobs")) {
        return Promise.resolve({ data: mockJobs });
      }
      if (url.startsWith("/styles")) {
        return Promise.resolve({ data: mockStyles });
      }
      if (url.startsWith("/workers")) {
        return Promise.resolve({ data: [] });
      }
      if (url.startsWith("/pos/")) {
        if (url.includes("/ean-codes")) {
          return Promise.resolve({
            data: {
              ok: true,
              po_id: "po_123",
              items: mockPoEanCodes,
            },
          });
        }
        return Promise.resolve({ data: { id: "po_123", po_number: "PO-BATA-001" } });
      }
      if (url.startsWith("/packing/cartons")) {
        return Promise.resolve({ data: [] });
      }
      if (url.startsWith("/packing/ean-codes")) {
        return Promise.resolve({ data: [] });
      }
      if (url.startsWith("/invoices")) {
        return Promise.resolve({ data: [] });
      }
      if (url.startsWith("/dispatch-records")) {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve({ data: [] });
    });
  });

  test("pre-fills EAN codes from PO file and visually distinguishes auto-filled vs manual entries", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    // Click "Pack Carton" on the job group card in QC & Pack column
    const packBtn = await screen.findByTestId(/^pack-carton-btn-/);
    fireEvent.click(packBtn);

    // Dialog opens
    expect(await screen.findByTestId("carton-pack-dialog")).toBeInTheDocument();

    // Verify Size 7 is pre-filled from client file and shows green badge
    const eanInput7 = await screen.findByTestId("ean-input-7");
    expect(eanInput7).toHaveValue("8901234500007");
    expect(screen.getByTestId("ean-source-client-7")).toBeInTheDocument();
    expect(screen.getByTestId("ean-source-client-7")).toHaveTextContent("Auto-filled from client file");

    // Verify Size 8 is pre-filled from client file and shows green badge
    const eanInput8 = screen.getByTestId("ean-input-8");
    expect(eanInput8).toHaveValue("8901234500008");
    expect(screen.getByTestId("ean-source-client-8")).toBeInTheDocument();
    expect(screen.getByTestId("ean-source-client-8")).toHaveTextContent("Auto-filled from client file");

    // Verify Size 9 has no match, shows empty input and amber "Needs manual entry" badge
    const eanInput9 = screen.getByTestId("ean-input-9");
    expect(eanInput9).toHaveValue("");
    expect(screen.getByTestId("ean-source-manual-9")).toBeInTheDocument();
    expect(screen.getByTestId("ean-source-manual-9")).toHaveTextContent("Needs manual entry");

    // Test editing: override Size 7 with manual edit
    fireEvent.change(eanInput7, { target: { value: "OVERRIDE-EAN-7" } });
    expect(eanInput7).toHaveValue("OVERRIDE-EAN-7");
    expect(await screen.findByTestId("ean-source-modified-7")).toBeInTheDocument();
    expect(screen.getByTestId("ean-source-modified-7")).toHaveTextContent("Manual override (edited)");

    // Fill manual entry for Size 9
    fireEvent.change(eanInput9, { target: { value: "MANUAL-EAN-9" } });
    expect(eanInput9).toHaveValue("MANUAL-EAN-9");

    // Fill carton quantities:
    // Size 7 (completed 50) -> 1 box of 50
    // Size 8 (completed 50) -> 1 box of 50
    // Size 9 (completed 30) -> 1 box of 30
    const cartonInputs = screen.getAllByRole("spinbutton");
    fireEvent.change(cartonInputs[0], { target: { value: "50" } });
    fireEvent.change(cartonInputs[1], { target: { value: "50" } });
    fireEvent.change(cartonInputs[2], { target: { value: "30" } });

    http.post.mockResolvedValueOnce({ data: { ok: true } });

    // Submit confirmation
    const confirmBtn = screen.getByTestId("confirm-carton-packing-btn");
    fireEvent.click(confirmBtn);

    // Verify that the edited and manual EANs are submitted and not reverted
    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith("/packing/confirm-qc-pack", {
        job_ids: ["job_1", "job_2", "job_3"],
        eans: [
          { size: "7", ean_code: "OVERRIDE-EAN-7" },
          { size: "8", ean_code: "8901234500008" },
          { size: "9", ean_code: "MANUAL-EAN-9" },
        ],
        cartons: [
          { size: "7", qty: 50 },
          { size: "8", qty: 50 },
          { size: "9", qty: 30 },
        ],
      });
    });
  });
});
