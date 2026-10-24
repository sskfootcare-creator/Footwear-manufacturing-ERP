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

describe("PO Production Budget and Planning Karigar Allocation", () => {
  const mockPO = {
    id: "po_test_123",
    po_number: "2220012752",
    client_name: "Test Footwear Corp",
    po_date: "2026-03-01",
    total_quantity: 520,
    subtotal: 67680,
    grand_total: 70980,
    is_completed: false,
    status: "active",
    line_items: [
      {
        style_code: "SSK_00212",
        description: "Denim Blue Sz 4",
        quantity: 65,
        unit_price: 130,
        amount: 8450,
        profitability: {
          bom_cost: 52.22,
          packing_cost: 12.0,
          labor_cost: 20.0,
          outside_cost: 0,
          total_cost: 84.22,
          profit: 45.78,
          profit_pct: 35.2,
          is_estimated: false,
        },
      },
      {
        style_code: "SSK_00212",
        description: "Denim Blue Sz 5",
        quantity: 455,
        unit_price: 130,
        amount: 59150,
        profitability: {
          bom_cost: 52.22,
          packing_cost: 12.0,
          labor_cost: 20.0,
          outside_cost: 0,
          total_cost: 84.22,
          profit: 45.78,
          profit_pct: 35.2,
          is_estimated: false,
        },
      },
    ],
    production_budget: {
      total_bom_cost: 27154.4,
      total_labor_cost: 10400.0,
      total_packing_cost: 6240.0,
      total_outside_cost: 0.0,
      total_budget: 43794.4,
      total_cost: 43794.4,
      total_revenue: 67680.0,
      total_profit: 23885.6,
      profit_pct: 35.3,
      total_quantity: 520,
      labor_source: "actual",
      is_estimated: false,
      is_fully_allocated: true,
    },
  };

  const mockPlanningJobs = {
    po_id: "po_test_123",
    po_number: "2220012752",
    jobs_count: 2,
    allocated_count: 6,
    total_roles: 6,
    is_fully_allocated: true,
    roles: [
      {
        key: "upper",
        label: "Upper Track",
        category: "component",
        is_allocated: true,
        worker_id: "w1",
        worker_name: "Ramesh Kumar",
        rate_per_pair: 8.0,
      },
      {
        key: "lasting",
        label: "Lasting",
        category: "assembly",
        is_allocated: true,
        worker_id: "w2",
        worker_name: "Suresh Patil",
        rate_per_pair: 12.0,
      },
    ],
    workers: [
      { id: "w1", name: "Ramesh Kumar", skill: "cutting", rate_per_pair: 8.0 },
      { id: "w2", name: "Suresh Patil", skill: "lasting", rate_per_pair: 12.0 },
    ],
  };

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url === "/pos") return Promise.resolve({ data: [mockPO] });
      if (url === "/styles") return Promise.resolve({ data: [] });
      if (url === "/pos/po_test_123") return Promise.resolve({ data: mockPO });
      if (url.includes("/planning-jobs")) return Promise.resolve({ data: mockPlanningJobs });
      if (url.includes("/documents")) return Promise.resolve({ data: { invoices: [], dispatch_records: [] } });
      return Promise.resolve({ data: [] });
    });
    http.post.mockImplementation((url) => {
      if (url.includes("/allocate-karigar")) return Promise.resolve({ data: mockPO });
      return Promise.resolve({ data: {} });
    });
  });

  test("Renders Production Budget card with Total BOM, Labour, Packing, and Total Budget", async () => {
    render(
      <MemoryRouter>
        <POs />
      </MemoryRouter>
    );

    // Wait for PO list
    await waitFor(() => {
      expect(screen.getByText("2220012752")).toBeInTheDocument();
    });

    // Click to open PO drawer
    fireEvent.click(screen.getByTestId("view-po-2220012752"));

    // Verify Planning Stage Karigar Allocation section renders
    await waitFor(() => {
      expect(screen.getByTestId("po-planning-stage-section")).toBeInTheDocument();
    });
    expect(screen.getByText(/Planning Stage · Karigar Allocation/i)).toBeInTheDocument();

    // Verify Production Budget Card renders below PO
    await waitFor(() => {
      expect(screen.getByTestId("po-production-budget-card")).toBeInTheDocument();
    });

    // Verify BOM, Labour, Packing, and Total Budget
    expect(screen.getByTestId("budget-total-bom")).toHaveTextContent("Total BOM Cost");
    expect(screen.getByTestId("budget-total-labor")).toHaveTextContent("Total Labour Cost");
    expect(screen.getByTestId("budget-total-packing")).toHaveTextContent("Total Packing Cost");
    expect(screen.getByTestId("budget-total-production")).toHaveTextContent("Production Budget");
    expect(screen.getByText(/Actual Allocated Karigar Rates/i)).toBeInTheDocument();
  });

  test("Allows changing/allocating karigar and sends allocate-karigar request", async () => {
    render(
      <MemoryRouter>
        <POs />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("view-po-2220012752")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("view-po-2220012752"));

    await waitFor(() => {
      expect(screen.getByTestId("edit-role-upper")).toBeInTheDocument();
    });

    // Click Change on upper role
    fireEvent.click(screen.getByTestId("edit-role-upper"));

    // Verify modal is open
    expect(screen.getByTestId("po-assign-karigar-modal")).toBeInTheDocument();

    // Select worker
    fireEvent.change(screen.getByTestId("select-karigar-dropdown"), {
      target: { value: "w2" },
    });

    // Change rate
    fireEvent.change(screen.getByTestId("input-karigar-rate"), {
      target: { value: "15.0" },
    });

    // Submit allocation
    fireEvent.click(screen.getByTestId("save-allocated-karigar-btn"));

    await waitFor(() => {
      expect(http.post).toHaveBeenCalledWith(
        "/pos/po_test_123/allocate-karigar",
        expect.objectContaining({
          role: "upper",
          worker_id: "w2",
          rate_per_pair: 15.0,
        })
      );
    });
  });
});
