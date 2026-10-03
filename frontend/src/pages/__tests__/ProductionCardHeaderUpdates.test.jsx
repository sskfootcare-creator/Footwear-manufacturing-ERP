import { render, screen } from "@testing-library/react";
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

describe("Production Card Header Layout Updates", () => {
  const mockProcJob = {
    id: "job_proc_1",
    po_id: "po_123",
    po_number: "PO-PROC-999",
    client_name: "BATA INDIA LTD",
    style_id: "style_001",
    style_code: "SSK_BATA_01",
    po_style_code: null,
    created_at: "2026-09-10T08:30:00.000000+00:00",
    color: "BROWN",
    size: "8",
    quantity: 240,
    completed_qty: 0,
    stage: "procurement",
    archived: false,
    delivery_date: "2026-09-30",
  };

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.startsWith("/production/jobs")) {
        return Promise.resolve({ data: [mockProcJob] });
      }
      if (url.startsWith("/workers")) return Promise.resolve({ data: [] });
      if (url.startsWith("/styles")) return Promise.resolve({ data: [{ code: "SSK_BATA_01", name: "Bata Loafer" }] });
      if (url.startsWith("/production/archive")) return Promise.resolve({ data: [] });
      if (url.startsWith("/packing-lists")) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });
  });

  test("1. Shows date of creation on top left corner", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    const key = "PO-PROC-999::SSK_BATA_01::BROWN";
    const createdEl = await screen.findByTestId(`created-date-${key}`);
    expect(createdEl).toBeInTheDocument();
    expect(createdEl).toHaveTextContent("Created: 10 Sep 2026");
  });

  test("2. Shows combine checkbox on top right", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    const key = "PO-PROC-999::SSK_BATA_01::BROWN";
    const combineLabel = await screen.findByTestId(`proc-combine-label-${key}`);
    expect(combineLabel).toBeInTheDocument();
    expect(combineLabel).toHaveTextContent("Combine");
    const checkbox = screen.getByTestId(`proc-select-${key}`);
    expect(checkbox).toBeInTheDocument();
  });

  test("3. Shows client name inline with quantity", async () => {
    render(
      <MemoryRouter>
        <Production />
      </MemoryRouter>
    );

    const key = "PO-PROC-999::SSK_BATA_01::BROWN";
    const clientEl = await screen.findByTestId(`client-name-${key}`);
    expect(clientEl).toBeInTheDocument();
    expect(clientEl).toHaveTextContent("BATA INDIA LTD");

    // Verify client name is in the same container as totalQty
    const parentContainer = clientEl.parentElement;
    expect(parentContainer).toHaveTextContent("240 pairs");
    expect(parentContainer).toHaveTextContent("BATA INDIA LTD");
  });
});
