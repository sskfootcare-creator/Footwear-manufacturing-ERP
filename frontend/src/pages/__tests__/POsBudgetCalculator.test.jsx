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

describe("POs Budget Calculator (Multi-PO) Drawer", () => {
  const mockPOs = [
    {
      id: "po_1",
      po_number: "PO-2220012750",
      client_name: "SIYARAM SILK MILLS LTD.",
      po_date: "2026-10-21",
      line_items: [
        {
          style_code: "S-ZEC-001",
          description: "T-Strap Flat Sandal",
          color: "Black",
          size: "7",
          quantity: 200,
          unit_price: 600,
          amount: 120000,
          profitability: {
            bom_cost: 200,
            labor_cost: 50,
            packing_cost: 20,
            outside_cost: 0,
            total_cost: 270,
            profit: 330,
            is_estimated: false,
          },
        },
      ],
      total_quantity: 200,
      grand_total: 120000,
      is_completed: false,
      status: "pending",
    },
    {
      id: "po_2",
      po_number: "PO-2220012753",
      client_name: "SIYARAM SILK MILLS LTD.",
      po_date: "2026-10-21",
      line_items: [
        {
          style_code: "S-ZEC-002",
          description: "Wedge Sandal",
          color: "Tan",
          size: "8",
          quantity: 100,
          unit_price: 700,
          amount: 70000,
          profitability: {
            bom_cost: 220,
            labor_cost: 60,
            packing_cost: 20,
            outside_cost: 0,
            total_cost: 300,
            profit: 400,
            is_estimated: true,
          },
        },
      ],
      total_quantity: 100,
      grand_total: 70000,
      is_completed: false,
      status: "pending",
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

  test("Clicking Budget Calculator (Multi-PO) button opens drawer and renders production budget without crashing", async () => {
    render(
      <MemoryRouter>
        <POs />
      </MemoryRouter>
    );

    // Wait for POs data to load
    await waitFor(() => {
      expect(screen.getByText("PO-2220012750")).toBeInTheDocument();
    });

    // Locate and click the Budget Calculator button in the header
    const budgetBtn = screen.getByTestId("header-multi-po-budget-btn");
    expect(budgetBtn).toBeInTheDocument();
    fireEvent.click(budgetBtn);

    // Verify Drawer opens and contains Production Budget Alignment title
    await waitFor(() => {
      expect(screen.getByText(/Production Budget Alignment/i)).toBeInTheDocument();
    });

    // Verify KPI card is rendered
    expect(screen.getByTestId("multi-po-budget-kpi-card")).toBeInTheDocument();
    expect(screen.getByText(/Total BOM Cost/i)).toBeInTheDocument();
    expect(screen.getByText(/Total Labour Cost/i)).toBeInTheDocument();
    expect(screen.getByText(/Total Production Budget/i)).toBeInTheDocument();

    // Verify action buttons
    expect(screen.getByTestId("confirm-align-budget-btn")).toBeInTheDocument();
  });
});

