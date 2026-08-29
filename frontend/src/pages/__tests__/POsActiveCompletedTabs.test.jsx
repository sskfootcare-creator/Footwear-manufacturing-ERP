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

describe("POs Active vs Completed Tabs Filter", () => {
  const mockPOs = [
    {
      id: "po_active_1",
      po_number: "PO-ACTIVE-001",
      client_name: "Active Client",
      po_date: "2026-03-01",
      line_items: [{ style_code: "SSK_OXFORD", quantity: 50, unit_price: 500, amount: 25000 }],
      total_quantity: 50,
      grand_total: 25000,
      is_completed: false,
      status: "pending",
    },
    {
      id: "po_completed_1",
      po_number: "PO-COMPLETED-001",
      client_name: "Completed Client",
      po_date: "2026-02-15",
      line_items: [{ style_code: "SSK_BOOT", quantity: 100, unit_price: 800, amount: 80000 }],
      total_quantity: 100,
      grand_total: 80000,
      is_completed: true,
      status: "completed",
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url.startsWith("/pos")) return Promise.resolve({ data: mockPOs });
      if (url.startsWith("/styles")) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: [] });
    });
  });

  test("Defaults to Active tab showing only active POs, switching to Completed shows completed POs", async () => {
    render(
      <MemoryRouter>
        <POs />
      </MemoryRouter>
    );

    // Wait for POs data to load into the active tab
    await waitFor(() => {
      expect(screen.getByText("PO-ACTIVE-001")).toBeInTheDocument();
    });

    // Default tab is Active -> only PO-ACTIVE-001 should be visible
    expect(screen.queryByText("PO-COMPLETED-001")).not.toBeInTheDocument();

    // Click Completed tab
    fireEvent.click(screen.getByTestId("tab-completed-pos"));

    // Now PO-COMPLETED-001 is displayed and PO-ACTIVE-001 is hidden
    await waitFor(() => {
      expect(screen.getByText("PO-COMPLETED-001")).toBeInTheDocument();
    });
    expect(screen.queryByText("PO-ACTIVE-001")).not.toBeInTheDocument();

    // Click Active tab again
    fireEvent.click(screen.getByTestId("tab-active-pos"));
    await waitFor(() => {
      expect(screen.getByText("PO-ACTIVE-001")).toBeInTheDocument();
    });
    expect(screen.queryByText("PO-COMPLETED-001")).not.toBeInTheDocument();
  });
});
