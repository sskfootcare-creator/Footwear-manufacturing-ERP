import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import POs from "../POs";
import { http } from "../../lib/api";

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

describe("POs SKU Resolver Warning on Failure", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.startsWith("/pos")) return Promise.resolve({ data: [] });
      if (url.startsWith("/styles")) return Promise.resolve({ data: [{ code: "SSK_OXFORD", name: "Oxford Classic" }] });
      if (url.startsWith("/sku-map/resolve")) {
        // Simulate resolver endpoint failure / down
        return Promise.reject(new Error("Resolver network timeout / 500 error"));
      }
      return Promise.resolve({ data: [] });
    });
  });

  test("Shows visible warning when SKU resolver fails during PO extraction", async () => {
    http.post.mockImplementation((url) => {
      if (url === "/pos/extract") {
        return Promise.resolve({
          data: {
            po_number: "PO-TEST-123",
            client_name: "B2B Client Corp",
            line_items: [
              {
                style_code: "UNKNOWN_EXT_SKU_99",
                description: "Sample shoe",
                quantity: 10,
                unit_price: 500,
              },
            ],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(
      <MemoryRouter>
        <POs />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("pos-header")).toBeInTheDocument();
    });

    const fileInput = screen.getByTestId("upload-po-input");
    const testFile = new File(["dummy pdf content"], "order.pdf", { type: "application/pdf" });


    fireEvent.change(fileInput, { target: { files: [testFile] } });

    await waitFor(() => {
      // Confirm drawer opened with extracted PO
      expect(screen.getByTestId("form-po-number")).toHaveValue("PO-TEST-123");
    });

    // Check that the inline warning is visible to the user
    const warningEl = await screen.findByTestId("po-line-0-resolution-warning");
    expect(warningEl).toHaveTextContent("Could not auto-resolve SKU mapping — check manually");
  });
});
