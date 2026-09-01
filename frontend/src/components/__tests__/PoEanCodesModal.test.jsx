import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import PoEanCodesModal from "../PoEanCodesModal";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => ({
  http: {
    get: jest.fn(),
    post: jest.fn(),
    delete: jest.fn(),
  },
  inr: (val) => `₹${Number(val || 0).toLocaleString("en-IN")}`,
}));

describe("PoEanCodesModal Component", () => {
  const mockPo = {
    id: "po_123",
    po_number: "PO-2026-001",
    client_name: "Bata India",
    po_date: "2026-09-01",
    line_items: [
      { style_code: "SSK-101", color: "Black", size: "7", quantity: 100 },
      { style_code: "SSK-101", color: "Black", size: "8", quantity: 150 },
    ],
  };

  const mockFormats = [
    {
      id: "fmt_bata",
      name: "Bata Barcodes Format",
      client_name: "Bata",
      active: true,
    },
    {
      id: "fmt_generic",
      name: "Generic EAN Template",
      client_name: "",
      active: true,
    },
  ];

  const mockExistingEans = [
    {
      id: "ean_1",
      po_id: "po_123",
      po_number: "PO-2026-001",
      style_code: "SSK-101",
      color: "Black",
      size: "7",
      ean_code: "8901234500001",
      imported_at: "2026-09-01T10:00:00Z",
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url === "/po-ean-formats?active=true") {
        return Promise.resolve({ data: mockFormats });
      }
      if (url === "/pos/po_123/ean-codes") {
        return Promise.resolve({
          data: {
            ok: true,
            items: mockExistingEans,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
  });

  test("renders modal with header, summary metrics, and stored barcodes table", async () => {
    render(
      <PoEanCodesModal
        po={mockPo}
        isOpen={true}
        onClose={jest.fn()}
        onUpdated={jest.fn()}
      />
    );

    expect(
      await screen.findByText((content) => content.includes("PO Barcodes & EAN Import"))
    ).toBeInTheDocument();
    expect(screen.getByText("Bata India")).toBeInTheDocument();
    expect(screen.getByTestId("tab-current-eans")).toBeInTheDocument();
    expect(screen.getByTestId("tab-upload-eans")).toBeInTheDocument();

    expect(await screen.findByTestId("po-eans-table")).toBeInTheDocument();
    expect(screen.getByText("SSK-101")).toBeInTheDocument();
    expect(screen.getByText("8901234500001")).toBeInTheDocument();
  });

  test("switches to upload tab, previews file, and triggers import", async () => {
    const mockPreviewResponse = {
      ok: true,
      filename: "barcodes.xlsx",
      total_rows: 2,
      po_matched_count: 2,
      duplicate_keys: [],
      extracted_items: [
        {
          row_number: 1,
          style_code: "SSK-101",
          color: "Black",
          size: "7",
          ean_code: "8901234500001",
          is_po_match: true,
          exists_in_db: true,
        },
        {
          row_number: 2,
          style_code: "SSK-101",
          color: "Black",
          size: "8",
          ean_code: "8901234500002",
          is_po_match: true,
          exists_in_db: false,
        },
      ],
    };

    http.post.mockImplementation((url) => {
      if (url.includes("preview-upload")) {
        return Promise.resolve({ data: mockPreviewResponse });
      }
      if (url.includes("/import")) {
        return Promise.resolve({
          data: {
            ok: true,
            imported: 2,
            skipped_duplicates: 0,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    const onUpdated = jest.fn();

    render(
      <PoEanCodesModal
        po={mockPo}
        isOpen={true}
        onClose={jest.fn()}
        onUpdated={onUpdated}
      />
    );

    // Switch to upload tab
    fireEvent.click(await screen.findByTestId("tab-upload-eans"));

    expect(screen.getByTestId("select-po-ean-format")).toBeInTheDocument();
    expect(screen.getByTestId("po-ean-file-input")).toBeInTheDocument();

    // Upload mock file
    const file = new File(["dummy content"], "test_barcodes.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    fireEvent.change(screen.getByTestId("po-ean-file-input"), {
      target: { files: [file] },
    });

    // Check preview container renders
    expect(await screen.findByTestId("po-ean-preview-container")).toBeInTheDocument();
    expect(screen.getByTestId("metric-total-rows")).toHaveTextContent("2");
    expect(screen.getByTestId("metric-matched-rows")).toHaveTextContent("2");

    // Toggle overwrite checkbox
    const overwriteCheckbox = screen.getByTestId("checkbox-overwrite-ean");
    fireEvent.click(overwriteCheckbox);
    expect(overwriteCheckbox).toBeChecked();

    // Click Import
    const importBtn = screen.getByTestId("confirm-import-ean-btn");
    fireEvent.click(importBtn);

    // Check success banner
    const successBanner = await screen.findByTestId("ean-import-success-banner");
    expect(successBanner).toBeInTheDocument();
    expect(successBanner).toHaveTextContent(/Successfully imported 2 EAN barcode\(s\)/);
    expect(onUpdated).toHaveBeenCalled();
  });

  test("flags unmatched rows that do not match valid style/color/size for the PO", async () => {
    const mockPreviewResponse = {
      ok: true,
      filename: "client_barcodes.xlsx",
      total_rows: 3,
      po_matched_count: 1,
      duplicate_keys: [],
      extracted_items: [
        {
          row_number: 1,
          style_code: "SSK-101",
          color: "Black",
          size: "7",
          ean_code: "8901234500001",
          is_po_match: true,
        },
        {
          row_number: 2,
          style_code: "UNKNOWN_ARTICLE",
          color: "Red",
          size: "9",
          ean_code: "8909999999999",
          is_po_match: false,
        },
      ],
    };

    const mockImportResultWithUnmatched = {
      ok: true,
      po_id: "po_123",
      po_number: "PO-2026-001",
      total_rows: 2,
      imported: 1,
      skipped_duplicates: 0,
      unmatched_count: 1,
      unmatched_rows: [
        {
          row_number: 2,
          raw_style: "UNKNOWN_ARTICLE",
          raw_color: "Red",
          raw_size: "9",
          style_code: "UNKNOWN_ARTICLE",
          color: "Red",
          size: "9",
          ean_code: "8909999999999",
          reason: "Style/color/size 'UNKNOWN_ARTICLE / Red / 9' does not match any valid line item in PO #PO-2026-001",
        },
      ],
    };

    http.post.mockImplementation((url) => {
      if (url.includes("preview-upload")) {
        return Promise.resolve({ data: mockPreviewResponse });
      }
      if (url.includes("/import")) {
        return Promise.resolve({ data: mockImportResultWithUnmatched });
      }
      return Promise.resolve({ data: {} });
    });

    render(
      <PoEanCodesModal
        po={mockPo}
        isOpen={true}
        onClose={jest.fn()}
        onUpdated={jest.fn()}
      />
    );

    fireEvent.click(await screen.findByTestId("tab-upload-eans"));

    const file = new File(["dummy"], "client_barcodes.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    fireEvent.change(screen.getByTestId("po-ean-file-input"), {
      target: { files: [file] },
    });

    const importBtn = await screen.findByTestId("confirm-import-ean-btn");
    fireEvent.click(importBtn);

    // Summary banner shows imported count
    const successBanner = await screen.findByTestId("ean-import-success-banner");
    expect(successBanner).toHaveTextContent(/Successfully imported 1 EAN barcode\(s\)/);

    // Alert shows 1 unmatched row flagged with reason and details
    const alertBox = screen.getByTestId("unmatched-rows-alert");
    expect(alertBox).toBeInTheDocument();
    expect(alertBox).toHaveTextContent("1 row(s) failed to match a valid style/color/size for this PO");
    expect(alertBox).toHaveTextContent("UNKNOWN_ARTICLE");
    expect(alertBox).toHaveTextContent("8909999999999");
    expect(alertBox).toHaveTextContent("does not match any valid line item");
  });

  test("clears all PO EAN codes on user confirmation", async () => {
    http.delete.mockResolvedValue({ data: { ok: true, deleted_count: 1 } });
    const onUpdated = jest.fn();

    render(
      <PoEanCodesModal
        po={mockPo}
        isOpen={true}
        onClose={jest.fn()}
        onUpdated={onUpdated}
      />
    );

    const clearBtn = await screen.findByTestId("clear-po-eans-btn");
    fireEvent.click(clearBtn);

    // Confirmation dialog appears
    expect(screen.getByText(/Clear PO Barcodes/i)).toBeInTheDocument();
    const confirmBtn = screen.getByText("Confirm");
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(http.delete).toHaveBeenCalledWith("/pos/po_123/ean-codes");
      expect(onUpdated).toHaveBeenCalled();
    });
  });
});
