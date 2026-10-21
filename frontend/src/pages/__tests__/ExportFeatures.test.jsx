import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { downloadCsv, downloadBlob, triggerApiExport } from "../../lib/exportUtils";
import { http } from "../../lib/api";

// Mock http client
jest.mock("../../lib/api", () => ({
  ...jest.requireActual("../../lib/api"),
  http: {
    get: jest.fn(),
  },
}));

// Mock sonner toast
jest.mock("sonner", () => ({
  toast: {
    loading: jest.fn(() => "toast-1"),
    dismiss: jest.fn(),
    success: jest.fn(),
    error: jest.fn(),
  },
}));

describe("Export Utilities & UI Integration", () => {
  let originalCreateObjectURL;
  let originalRevokeObjectURL;
  let mockClick;

  beforeEach(() => {
    jest.clearAllMocks();

    originalCreateObjectURL = window.URL.createObjectURL;
    originalRevokeObjectURL = window.URL.revokeObjectURL;

    window.URL.createObjectURL = jest.fn(() => "blob:http://localhost/mock-blob-uuid");
    window.URL.revokeObjectURL = jest.fn();

    mockClick = jest.fn();
    const realCreateElement = document.createElement.bind(document);
    jest.spyOn(document, "createElement").mockImplementation((tag) => {
      const el = realCreateElement(tag);
      if (tag === "a") {
        el.click = mockClick;
      }
      return el;
    });
  });

  afterEach(() => {
    window.URL.createObjectURL = originalCreateObjectURL;
    window.URL.revokeObjectURL = originalRevokeObjectURL;
    jest.restoreAllMocks();
  });

  test("downloadCsv generates UTF-8 BOM CSV blob and triggers anchor download", () => {
    const headers = ["Invoice No", "Client", "Amount"];
    const rows = [
      ["INV-001", "Bata India", 15000],
      ["INV-002", "Relaxo", 22000],
    ];

    downloadCsv("test_invoices.csv", headers, rows);

    expect(window.URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(mockClick).toHaveBeenCalledTimes(1);
  });

  test("downloadBlob creates blob URL and clicks anchor", () => {
    const blob = new Blob(["dummy content"], { type: "text/plain" });
    downloadBlob(blob, "dummy.txt");

    expect(window.URL.createObjectURL).toHaveBeenCalledWith(blob);
    expect(mockClick).toHaveBeenCalledTimes(1);
  });

  test("triggerApiExport fetches binary blob and triggers download with server filename", async () => {
    const mockBlob = new Blob(["PK fake zip data"], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    http.get.mockResolvedValueOnce({
      data: mockBlob,
      headers: {
        "content-disposition": 'attachment; filename="SSK_Overdue_Invoices_2026-10-21.xlsx"',
        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      },
    });

    const res = await triggerApiExport(
      "/invoices/export",
      { status: "overdue", format: "xlsx" },
      "fallback.xlsx"
    );

    expect(res).toBe(true);
    expect(http.get).toHaveBeenCalledWith("/invoices/export", {
      params: { status: "overdue", format: "xlsx" },
      responseType: "blob",
    });
    expect(mockClick).toHaveBeenCalledTimes(1);
  });

  test("triggerApiExport handles errors gracefully", async () => {
    http.get.mockRejectedValueOnce(new Error("Network Error"));

    await expect(
      triggerApiExport("/invoices/export", { status: "overdue" }, "fallback.xlsx")
    ).rejects.toThrow("Network Error");
  });
});
