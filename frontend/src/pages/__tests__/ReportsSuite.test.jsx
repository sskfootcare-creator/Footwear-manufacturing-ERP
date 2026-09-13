import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Reports from "../Reports";
import { http } from "../../lib/api";

jest.mock("../../lib/api", () => {
  const original = jest.requireActual("../../lib/api");
  return {
    ...original,
    http: {
      get: jest.fn(),
      post: jest.fn(),
    },
    inr: (val) => `₹${Number(val || 0).toLocaleString("en-IN")}`,
    num: (val) => Number(val || 0).toLocaleString("en-IN"),
  };
});

jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => <div data-testid="mock-responsive-container">{children}</div>,
  BarChart: ({ children }) => <div>{children}</div>,
  LineChart: ({ children }) => <div>{children}</div>,
  PieChart: ({ children }) => <div>{children}</div>,
  Bar: () => null,
  Line: () => null,
  Pie: () => null,
  Cell: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  CartesianGrid: () => null,
}));

describe("Enterprise ERP Reports Suite Integration", () => {
  const mockBusinessSummary = {
    gross_revenue: 150000.0,
    total_b2b_invoiced: 100000.0,
    total_online_revenue: 50000.0,
    total_procurement: 60000.0,
    labor_cost: 20000.0,
    cogs: 80000.0,
    gross_profit: 70000.0,
    gross_margin_pct: 46.67,
    operating_expenses: 15000.0,
    net_profit: 55000.0,
    net_margin_pct: 36.67,
    total_ar_receivables: 35000.0,
    total_ap_payables: 25000.0,
    total_liquid_funds: 120000.0,
    total_bank_balance: 100000.0,
    total_cash_balance: 20000.0,
    pipeline_jobs_count: 8,
    pipeline_pairs_count: 1200,
    dispatched_pairs_count: 450,
    inventory_valuation: 85000.0,
    monthly_trend: [
      { month: "2026-08", revenue: 120000, procurement: 50000, expenses: 10000, profit: 60000 },
      { month: "2026-09", revenue: 150000, procurement: 60000, expenses: 15000, profit: 75000 },
    ],
  };

  const mockInventory = {
    total_items: 2,
    total_valuation: 45000.0,
    low_stock_count: 1,
    out_of_stock_count: 0,
    inward_movement_qty: 600,
    inward_movement_val: 30000,
    outward_movement_qty: 400,
    outward_movement_val: 20000,
    categories: [
      { category: "Leather", items_count: 1, total_stock: 300, total_valuation: 36000 },
      { category: "Soles", items_count: 1, total_stock: 100, total_valuation: 9000 },
    ],
    materials: [
      {
        id: "mat_1",
        code: "LEA-BUFF",
        name: "Buff Calf Leather",
        category: "Leather",
        unit: "sqft",
        current_stock: 300,
        weighted_avg_rate: 120,
        last_purchase_rate: 125,
        total_valuation: 36000,
        reorder_level: 50,
        status: "Adequate",
      },
      {
        id: "mat_2",
        code: "SOLE-PU",
        name: "PU Sneaker Sole",
        category: "Soles",
        unit: "pairs",
        current_stock: 20,
        weighted_avg_rate: 90,
        last_purchase_rate: 95,
        total_valuation: 1800,
        reorder_level: 50,
        status: "Low Stock",
      },
    ],
  };

  const mockProduction = {
    total_jobs: 5,
    active_jobs: 4,
    total_pairs_started: 1500,
    total_pairs_dispatched: 450,
    total_defects: 3,
    total_rejected_pairs: 12,
    stage_breakdown: [
      { stage: "cutting", job_count: 1, total_pairs: 300 },
      { stage: "stitching", job_count: 2, total_pairs: 450 },
      { stage: "lasting", job_count: 1, total_pairs: 300 },
      { stage: "dispatched", job_count: 1, total_pairs: 450 },
    ],
  };

  const mockSales = {
    total_invoices: 2,
    total_invoiced: 100000.0,
    total_paid: 65000.0,
    total_balance: 35000.0,
    collection_rate_pct: 65.0,
    top_clients: [
      { client_name: "Apex Footwear Corp", total_billed: 60000, total_paid: 40000, total_balance: 20000 },
      { client_name: "Bata Stores", total_billed: 40000, total_paid: 25000, total_balance: 15000 },
    ],
    invoices: [
      {
        id: "inv_1",
        invoice_number: "INV-2026-001",
        invoice_date: "2026-09-01",
        client_name: "Apex Footwear Corp",
        total_pairs: 300,
        grand_total: 60000,
        paid_amount: 40000,
        balance_due: 20000,
        status: "partially_paid",
      },
    ],
  };

  const mockProcurement = {
    total_pos: 2,
    total_po_value: 60000.0,
    total_paid: 35000.0,
    total_balance_due: 25000.0,
    total_ordered_qty: 800,
    total_received_qty: 600,
    fulfillment_rate_pct: 75.0,
    ap_aging: { "0_30": 15000, "31_60": 10000, "61_90": 0, "90_plus": 0 },
    vendors: [
      {
        vendor_name: "Prime Leather Tannery",
        pos_count: 1,
        total_amount: 40000,
        paid_amount: 25000,
        balance_due: 15000,
        ordered_qty: 500,
        received_qty: 400,
      },
    ],
    purchase_orders: [
      {
        id: "po_1",
        po_number: "PO-VEN-01",
        vendor_name: "Prime Leather Tannery",
        created_at: "2026-09-02",
        ordered_quantity: 500,
        received_quantity: 400,
        total_amount: 40000,
        paid_amount: 25000,
        balance_due: 15000,
        status: "partially_received",
      },
    ],
  };

  const mockReceivables = {
    total_clients: 1,
    total_invoiced: 60000.0,
    total_paid: 40000.0,
    total_outstanding: 20000.0,
    ar_aging: { "0_30": 20000, "31_60": 0, "61_90": 0, "90_plus": 0 },
    clients: [
      {
        client_id: "c_1",
        name: "Apex Footwear Corp",
        contact_person: "John Doe",
        phone: "9876543210",
        payment_terms_days: 30,
        invoiced_total: 60000,
        paid_total: 40000,
        balance_due: 20000,
        aging_bucket: "0-30",
      },
    ],
  };

  const mockPnl = {
    gross_revenue: 150000.0,
    b2b_revenue: 100000.0,
    online_revenue: 50000.0,
    material_cogs: 60000.0,
    labor_cogs: 20000.0,
    total_cogs: 80000.0,
    gross_profit: 70000.0,
    gross_margin_pct: 46.67,
    total_opex: 15000.0,
    net_profit: 55000.0,
    net_margin_pct: 36.67,
    expense_categories: [
      { category: "Utilities", amount: 5000 },
      { category: "Rent", amount: 10000 },
    ],
    monthly_pnl: [
      {
        month: "2026-09",
        revenue: 150000,
        cogs: 80000,
        gross_profit: 70000,
        opex: 15000,
        net_profit: 55000,
        net_margin_pct: 36.67,
      },
    ],
  };

  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url === "/reports/business-summary") return Promise.resolve({ data: mockBusinessSummary });
      if (url === "/reports/inventory-materials") return Promise.resolve({ data: mockInventory });
      if (url === "/reports/production-overview") return Promise.resolve({ data: mockProduction });
      if (url === "/reports/invoices-sales") return Promise.resolve({ data: mockSales });
      if (url === "/reports/vendor-procurement") return Promise.resolve({ data: mockProcurement });
      if (url === "/reports/client-receivables") return Promise.resolve({ data: mockReceivables });
      if (url === "/reports/pnl-detailed") return Promise.resolve({ data: mockPnl });
      return Promise.reject(new Error(`Unhandled URL: ${url}`));
    });
  });

  test("Renders Executive Business Summary with KPI cards and monthly trajectory", async () => {
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("business-summary-tab")).toBeInTheDocument();
    });

    expect(screen.getByText("360° Executive Business Performance")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-gross-revenue")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-total-procurement")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-liquid-funds")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-net-profit")).toBeInTheDocument();
    expect(http.get).toHaveBeenCalledWith("/reports/business-summary", expect.any(Object));
  });

  test("Switches to Inventory & Materials tab and filters materials by search", async () => {
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("tab-inventory")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("tab-inventory"));

    await waitFor(() => {
      expect(screen.getByTestId("inventory-materials-tab")).toBeInTheDocument();
      expect(screen.getByText("Buff Calf Leather")).toBeInTheDocument();
    });

    // Test Search input
    const searchInput = screen.getByTestId("search-inventory-input");
    fireEvent.change(searchInput, { target: { value: "PU" } });

    expect(screen.queryByText("Buff Calf Leather")).not.toBeInTheDocument();
    expect(screen.getByText("PU Sneaker Sole")).toBeInTheDocument();
  });

  test("Switches to Production Line tab and verifies stage-wise throughput", async () => {
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("tab-production")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("tab-production"));

    await waitFor(() => {
      expect(screen.getByTestId("production-overview-tab")).toBeInTheDocument();
      expect(screen.getByText("Production Line & Manufacturing WIP")).toBeInTheDocument();
      expect(screen.getByTestId("prod-pairs-started")).toBeInTheDocument();
    });

    expect(http.get).toHaveBeenCalledWith("/reports/production-overview", expect.any(Object));
  });

  test("Switches to Invoices & Sales tab and renders invoice register", async () => {
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("tab-sales")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("tab-sales"));

    await waitFor(() => {
      expect(screen.getByTestId("invoices-sales-tab")).toBeInTheDocument();
      expect(screen.getByText("INV-2026-001")).toBeInTheDocument();
      expect(screen.getByText("B2B Invoices & Sales Performance")).toBeInTheDocument();
    });

    expect(http.get).toHaveBeenCalledWith("/reports/invoices-sales", expect.any(Object));
  });

  test("Switches to Vendor Procurement tab and renders AP aging schedule", async () => {
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("tab-procurement")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("tab-procurement"));

    await waitFor(() => {
      expect(screen.getByTestId("vendor-procurement-tab")).toBeInTheDocument();
      expect(screen.getByText("Accounts Payable (AP) Aging Schedule")).toBeInTheDocument();
      expect(screen.getByText("Prime Leather Tannery")).toBeInTheDocument();
    });

    expect(http.get).toHaveBeenCalledWith("/reports/vendor-procurement", expect.any(Object));
  });

  test("Switches to Client Receivables & AR tab and displays customer balances", async () => {
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("tab-receivables")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("tab-receivables"));

    await waitFor(() => {
      expect(screen.getByTestId("client-receivables-tab")).toBeInTheDocument();
      expect(screen.getByText("Accounts Receivable (AR) Aging Schedule")).toBeInTheDocument();
      expect(screen.getByText("John Doe")).toBeInTheDocument();
    });

    expect(http.get).toHaveBeenCalledWith("/reports/client-receivables", expect.any(Object));
  });

  test("Switches to Detailed P&L tab and shows margin schedule", async () => {
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("tab-pnl")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("tab-pnl"));

    await waitFor(() => {
      expect(screen.getByTestId("pnl-detailed-tab")).toBeInTheDocument();
      expect(screen.getByText("Comprehensive Profit & Loss (P&L) Statement")).toBeInTheDocument();
      expect(screen.getByText("1. Operating Revenue")).toBeInTheDocument();
      expect(screen.getByText("5. Net Operating Profit")).toBeInTheDocument();
    });

    expect(http.get).toHaveBeenCalledWith("/reports/pnl-detailed", expect.any(Object));
  });

  test("Applies quick preset date filter and triggers data reload with date params", async () => {
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("preset-month")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("preset-month"));

    await waitFor(() => {
      expect(http.get).toHaveBeenCalledWith(
        "/reports/business-summary",
        expect.objectContaining({
          params: expect.objectContaining({
            from_date: expect.any(String),
            to_date: expect.any(String),
          }),
        })
      );
    });
  });

  test("Invokes CSV Export without errors", async () => {
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("export-business-csv")).toBeInTheDocument();
    });

    // Mock document.createElement
    const clickSpy = jest.fn();
    const originalCreateElement = document.createElement.bind(document);
    jest.spyOn(document, "createElement").mockImplementation((tag) => {
      const el = originalCreateElement(tag);
      if (tag === "a") {
        el.click = clickSpy;
      }
      return el;
    });

    fireEvent.click(screen.getByTestId("export-business-csv"));
    expect(clickSpy).toHaveBeenCalled();

    document.createElement.mockRestore();
  });
});
