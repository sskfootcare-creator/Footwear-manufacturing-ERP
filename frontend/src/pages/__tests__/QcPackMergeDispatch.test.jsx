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

describe("QC & Pack Merged Dispatch Functionality", () => {
  const mockJobCard1 = {
    id: "job_wine_1",
    po_id: "po_100",
    po_number: "PO-100",
    client_name: "Client Alpha",
    style_id: "style_1",
    style_code: "SSK_00017",
    color: "WINE",
    size: "7",
    quantity: 120,
    completed_qty: 120,
    stage: "qc_pack",
    components: { upper_done: true, bottom_done: true, sole_done: true },
  };

  const mockJobCard2 = {
    id: "job_cream_1",
    po_id: "po_100",
    po_number: "PO-100",
    client_name: "Client Alpha",
    style_id: "style_1",
    style_code: "SSK_00017",
    color: "CREAM",
    size: "7",
    quantity: 120,
    completed_qty: 120,
    stage: "qc_pack",
    components: { upper_done: true, bottom_done: true, sole_done: true },
  };

  const mockJobCardOtherPo = {
    id: "job_diff_1",
    po_id: "po_200",
    po_number: "PO-200",
    client_name: "Client Beta",
    style_id: "style_2",
    style_code: "SSK_00007",
    color: "TAN",
    size: "8",
    quantity: 100,
    completed_qty: 100,
    stage: "qc_pack",
    components: { upper_done: true, bottom_done: true, sole_done: true },
  };

  const mockCartons = [
    { id: "c1", job_id: "job_wine_1", po_id: "po_100", style_code: "SSK_00017", color: "WINE", size: "7", qty: 20, status: "packed" },
    { id: "c2", job_id: "job_cream_1", po_id: "po_100", style_code: "SSK_00017", color: "CREAM", size: "7", qty: 20, status: "packed" },
  ];

  beforeAll(() => {
    window.URL.createObjectURL = jest.fn(() => "blob:mock-url");
    window.URL.revokeObjectURL = jest.fn();
  });

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.startsWith("/production/jobs")) {
        return Promise.resolve({ data: [mockJobCard1, mockJobCard2, mockJobCardOtherPo] });
      }
      if (url.startsWith("/workers")) return Promise.resolve({ data: [] });
      if (url.startsWith("/styles")) return Promise.resolve({ data: [] });
      if (url.startsWith("/production/archive")) return Promise.resolve({ data: [] });
      if (url.startsWith("/packing-lists")) return Promise.resolve({ data: [] });
      if (url.startsWith("/dispatch-records")) return Promise.resolve({ data: [] });
      if (url.startsWith("/invoices")) return Promise.resolve({ data: [] });
      if (url.startsWith("/packing/cartons")) return Promise.resolve({ data: mockCartons });
      return Promise.resolve({ data: [] });
    });
  });

  test("QC & Pack cards show Merge checkbox, restricts cross-PO merging, and dispatches single invoice for same PO cards", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    // Wait for jobs to load
    await waitFor(() => {
      expect(screen.getByTestId("group-PO-100::SSK_00017::WINE")).toBeInTheDocument();
      expect(screen.getByTestId("group-PO-100::SSK_00017::CREAM")).toBeInTheDocument();
      expect(screen.getByTestId("group-PO-200::SSK_00007::TAN")).toBeInTheDocument();
    });

    // Both cards in PO-100 and the card in PO-200 should have QC Pack Merge checkboxes
    const wineCheckbox = screen.getByTestId("qc-pack-select-PO-100::SSK_00017::WINE");
    const creamCheckbox = screen.getByTestId("qc-pack-select-PO-100::SSK_00017::CREAM");
    const tanCheckbox = screen.getByTestId("qc-pack-select-PO-200::SSK_00007::TAN");

    expect(wineCheckbox).not.toBeChecked();
    expect(creamCheckbox).not.toBeChecked();
    expect(tanCheckbox).not.toBeChecked();
    expect(tanCheckbox).not.toBeDisabled();

    // 1. Check first card (WINE, PO-100)
    fireEvent.click(wineCheckbox);
    expect(wineCheckbox).toBeChecked();

    // 2. Card with different PO (PO-200) should now be disabled from selection
    expect(tanCheckbox).toBeDisabled();

    // 3. Check second card (CREAM, PO-100)
    fireEvent.click(creamCheckbox);
    expect(creamCheckbox).toBeChecked();

    // 4. Header action button and column header button should now be visible with count 2
    const headerMergeBtn = screen.getByTestId("qc-pack-merge-dispatch-btn");
    expect(headerMergeBtn).toHaveTextContent("Merge Dispatch Docs (2)");

    const columnMergeBtn = screen.getByTestId("column-merge-dispatch-btn");
    expect(columnMergeBtn).toBeInTheDocument();

    // 5. Click Merge Dispatch Docs to open the merged DispatchDialog
    fireEvent.click(headerMergeBtn);

    // Dialog should show merged dispatch details
    await waitFor(() => {
      expect(screen.getByTestId("dispatch-dialog")).toBeInTheDocument();
      expect(screen.getByTestId("dispatch-dialog-title")).toHaveTextContent("PO: PO-100 · Merged Dispatch (2 Cards)");
      expect(screen.getByTestId("dispatch-total-pairs")).toHaveTextContent("240");
    });

    // Verify both style cards are rendered inside the dialog breakdown section
    const dialog = screen.getByTestId("dispatch-dialog");
    const quantitiesSection = within(dialog).getByTestId("dispatch-quantities-section");
    expect(within(quantitiesSection).getByText("WINE")).toBeInTheDocument();
    expect(within(quantitiesSection).getByText("CREAM")).toBeInTheDocument();

    // Mock successful dispatch response
    http.post.mockResolvedValueOnce({
      data: new Uint8Array([80, 75, 3, 4]), // ZIP magic bytes
      headers: {
        "content-type": "application/zip",
        "x-invoice-no": "SSK26-27-088",
        "x-dispatch-record-id": "dr_merged_100",
      },
    });

    // 6. Click Generate & Download ZIP
    const generateBtn = screen.getByTestId("dispatch-confirm-btn");
    fireEvent.click(generateBtn);

    // 7. Verify http.post was called with merged job_ids and shared po_id
    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/dispatch",
        expect.objectContaining({
          po_id: "po_100",
          job_ids: expect.arrayContaining(["job_wine_1", "job_cream_1"]),
          dispatch_quantities: expect.objectContaining({
            job_wine_1: 120,
            job_cream_1: 120,
          }),
        }),
        expect.anything()
      );
    });

    // 8. Verify completion view shows single invoice SSK26-27-088 for both cards
    await waitFor(() => {
      expect(screen.getByTestId("dispatch-success-msg")).toBeInTheDocument();
      expect(screen.getByTestId("dispatch-success-msg")).toHaveTextContent("Dispatched — Invoice SSK26-27-088");
      expect(screen.getByTestId("dispatch-success-msg")).toHaveTextContent("Single invoice generated for 2 production cards");
    });
  });
});
