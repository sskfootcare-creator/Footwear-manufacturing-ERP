import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import OnlineProfitability from "../OnlineProfitability";
import { http } from "../../lib/api";

// Mock http module
jest.mock("../../lib/api", () => ({
  http: {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
  },
  inr: (val) => `₹${Number(val || 0).toLocaleString("en-IN")}`,
  num: (val) => Number(val || 0).toLocaleString("en-IN"),
}));

// Mock recharts
jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  LineChart: ({ children }) => <div>{children}</div>,
  Line: () => <div />,
  BarChart: ({ children }) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  Tooltip: () => <div />,
  CartesianGrid: () => <div />,
  Legend: () => <div />,
}));

describe("OnlineProfitability Page & Tabs", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    http.get.mockImplementation((url) => {
      if (url === "/styles") {
        return Promise.resolve({ data: [] });
      }
      if (url.includes("/reports/online-profitability")) {
        return Promise.resolve({
          data: {
            revenue_source_used: "Orders Ledger",
            is_estimated: false,
            cost_is_estimated: false,
            total_net_sales: 50000,
            total_net_cogs: 30000,
            gross_profit: 20000,
            gross_margin_pct: 40.0,
            by_style: [],
            daily_trend: [],
          },
        });
      }
      if (url.includes("/online-orders/reconciliation-summary")) {
        return Promise.resolve({
          data: {
            total_rows: 10,
            packed: 10,
            returned_to_stock: 2,
            pending: 0,
            net_sold: 8,
            never_touched_inventory: 0,
            overview: {
              platform: "myntra",
              month: "2026-09",
              net_sold_revenue: 40000,
              platform_earnings: 32000,
              total_cost_of_production: 20000,
              allocated_operational_cost: 5000,
              actual_net_profit: 7000,
              actual_net_margin_pct: "17.50",
              return_analytics: {
                total_returned_units: 2,
                overall_return_rate_pct: 20.0,
                total_return_amount_lost: 10000,
                total_reverse_logistics_cost: 800,
                total_return_financial_damage: 10800,
                rto_vs_rvp: { rto_units: 1, rvp_units: 1, rto_pct: 50, rvp_pct: 50 },
                most_returned_styles: [],
              },
              platform_fee_breakdown: {
                commission: 4000,
                forward_shipping: 2000,
                reverse_shipping: 800,
                fixed_fee: 600,
                taxes_gst: 1332,
                total_fees: 8732,
              },
              styles: [
                {
                  style_code: "FL_AK_002",
                  myntra_style_id: "28933414",
                  erp_style_code: "SSK_00034",
                  image_url: "/company/laser_cut_flat.jpg",
                  style_name: "Anouk Embellished Open Toe Flats",
                  brand: "ANOUK",
                  gross_units: 10,
                  packed_qty: 10,
                  returned_qty: 2,
                  rto_qty: 0,
                  net_sold_qty: 8,
                  unit_production_cost: 210,
                  total_production_cost: 1680,
                  net_sold_seller_price: 5000,
                  gross_profit: 3320,
                  margin_pct: 66.4,
                  return_rate_pct: 20.0,
                  reverse_logistics_cost: 800,
                  return_amount_lost: 10000,
                  total_return_cost: 10800,
                },
              ],
              sku_bifurcation: [
                {
                  sku_code: "FL_AK_002-38",
                  style_root: "FL_AK_002",
                  myntra_style_id: "28933414",
                  erp_style_code: "SSK_00034",
                  brand: "ANOUK",
                  color: "Burgundy",
                  size: "38",
                  gross_units: 5,
                  returns_units: 1,
                  net_units: 4,
                  net_sales: 2500,
                  platform_expenses: 800,
                  platform_earnings: 1700,
                  unit_production_cost: 210,
                  total_production_cost: 840,
                  contribution_after_platform: 860,
                  margin_pct: 66.4,
                  is_mapped: true,
                },
              ],
            },
          },
        });
      }
      if (url.includes("/online-reconciliation/summary")) {
        return Promise.resolve({
          data: {
            total_non_order_deductions: 1250,
            return_charges_by_style: { "FL_AK_002": 800 },
            non_order_deductions_ledger: [
              {
                id: "ded-1",
                settlement_date: "2026-09-18",
                seller_id: "SELLER-1",
                settlement_type: "Storage Fee",
                utr: "UTR123456",
                settlement_description: "Monthly warehouse storage charge",
                settlement_amount: 1250,
              },
            ],
          },
        });
      }
      if (url.includes("/online-returns/analytics")) {
        return Promise.resolve({
          data: {
            month: "2026-08",
            total_returns: 10,
            customer_returns: 6,
            rto_returns: 4,
            category_breakdown: {
              SIZING_FIT: 5,
              COURIER_RTO: 4,
              QUALITY_DEFECT: 1,
            },
            styles: [
              {
                style_code: "SSK-TEST-01",
                brand: "SSK",
                total_returns: 5,
                customer_returns: 3,
                rto_returns: 2,
                estimated_reverse_freight: 425,
                sizes: { "8": { total: 5, too_small: 4, too_big: 1, other: 0 } },
              },
            ],
          },
        });
      }
      if (url.includes("/online-returns/prescriptions")) {
        return Promise.resolve({
          data: {
            prescriptions: [
              {
                style_code: "SSK-TEST-01",
                priority: "HIGH",
                total_returns: 5,
                actions: [
                  {
                    action_type: "LAST_ADJUSTMENT",
                    category: "SIZING_FIT",
                    title: "Pattern Widening",
                    recommendation: "Expand toe-box width by 3.5mm",
                    expected_impact: "Reduces returns by 40%",
                  },
                ],
              },
            ],
          },
        });
      }
      if (url.includes("/online-returns/actions")) {
        return Promise.resolve({ data: [] });
      }
      if (url.includes("/online-returns/impact-check")) {
        return Promise.resolve({ data: { results: [] } });
      }
      return Promise.resolve({ data: {} });
    });
  });

  test("renders Profitability Engine, Monthly PnL, and Return Reduction Engine top tabs", async () => {
    render(<OnlineProfitability />);

    expect(screen.getByTestId("tab-overview")).toBeInTheDocument();
    expect(screen.getByTestId("tab-monthly-pnl")).toBeInTheDocument();
    expect(screen.getByTestId("tab-returns-engine")).toBeInTheDocument();

    // Verify removed obsolete tabs are absent
    expect(screen.queryByText(/5-Report Reconciler/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/File Import Suite/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Unreconciled Orders/i)).not.toBeInTheDocument();
  });

  test("clicking Return Reduction Engine top tab displays returns intelligence directly", async () => {
    render(<OnlineProfitability />);

    fireEvent.click(screen.getByTestId("tab-returns-engine"));

    await waitFor(() => {
      expect(screen.getByTestId("returns-intelligence-tab")).toBeInTheDocument();
      expect(screen.getByText(/Footwear Return Root-Cause Taxonomy/i)).toBeInTheDocument();
    });
  });

  test("shows Return Charges & Deductions subtab inside Monthly PnL Reconciliation", async () => {
    render(<OnlineProfitability />);

    // Switch to Monthly PnL Reconciliation
    fireEvent.click(screen.getByTestId("tab-monthly-pnl"));

    // Verify sub-tabs
    await waitFor(() => {
      expect(screen.getByText(/Return Charges & Deductions/i)).toBeInTheDocument();
    });

    // Click Return Charges & Deductions subtab
    fireEvent.click(screen.getByText(/Return Charges & Deductions/i));

    // Verify contents
    await waitFor(() => {
      expect(screen.getByTestId("returns-deductions-tab")).toBeInTheDocument();
      expect(screen.getByText(/Marketplace Fee Deductions Breakdown/i)).toBeInTheDocument();
      expect(screen.getByText(/Return Charges & Reverse Freight by Style/i)).toBeInTheDocument();
      expect(screen.getByText(/Non-Order Deductions Ledger/i)).toBeInTheDocument();
      expect(screen.getByText(/FL_AK_002/i)).toBeInTheDocument();
      expect(screen.getByText(/Monthly warehouse storage charge/i)).toBeInTheDocument();
    });
  });

  test("verifies Returns Root-Causes & Prescriptions is removed from Monthly PnL and kept in dedicated top tab", async () => {
    render(<OnlineProfitability />);

    fireEvent.click(screen.getByTestId("tab-monthly-pnl"));

    await waitFor(() => {
      expect(screen.getByText(/Return Charges & Deductions/i)).toBeInTheDocument();
      expect(screen.queryByText(/Returns Root-Causes & Prescriptions/i)).not.toBeInTheDocument();
    });
  });

  test("renders style photo, Myntra Style ID, and ERP Style Code in Style Breakdown & COGS", async () => {
    render(<OnlineProfitability />);

    fireEvent.click(screen.getByTestId("tab-monthly-pnl"));

    // Click Style Breakdown & COGS subtab
    await waitFor(() => {
      expect(screen.getByText(/Style Breakdown & COGS/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Style Breakdown & COGS/i));

    // Verify photo, Myntra Style ID, ERP Style Code, and brand are rendered
    await waitFor(() => {
      expect(screen.getByText(/FL_AK_002/i)).toBeInTheDocument();
      expect(screen.getByText(/28933414/i)).toBeInTheDocument();
      expect(screen.getByText(/SSK_00034/i)).toBeInTheDocument();
      expect(screen.getByAltText("FL_AK_002")).toBeInTheDocument();
      expect(screen.getByAltText("FL_AK_002")).toHaveAttribute("src", "/company/laser_cut_flat.jpg");
    });
  });

  test("edits unit cost inline without triggering full page reload or unmounting table", async () => {
    http.put.mockResolvedValueOnce({
      data: {
        platform: "myntra",
        month: "2026-08",
        styles_count: 1,
        total_net_sold: 8,
        net_sold_revenue: 4000,
        total_cost_of_production: 1600,
        actual_net_profit: 2400,
        actual_net_margin_pct: 60.0,
        styles: [
          {
            style_code: "FL_AK_002",
            myntra_style_id: "28933414",
            erp_style_code: "SSK_00034",
            brand: "Anouk",
            style_name: "FL_AK_002 Women Laser Cut Flat",
            article_type: "Flats",
            colors: ["Burgundy"],
            sizes: { "4": 2, "5": 2, "6": 2, "7": 2 },
            total_orders: 10,
            packed_qty: 10,
            returned_qty: 2,
            rto_qty: 0,
            cancelled_qty: 0,
            net_sold_qty: 8,
            total_seller_price: 5000,
            net_sold_seller_price: 4000,
            unit_production_cost: 200,
            total_production_cost: 1600,
            gross_profit: 2400,
            margin_pct: 60.0,
          },
        ],
      },
    });

    render(<OnlineProfitability />);

    fireEvent.click(screen.getByTestId("tab-monthly-pnl"));

    await waitFor(() => {
      expect(screen.getByText(/Style Breakdown & COGS/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Style Breakdown & COGS/i));

    await waitFor(() => {
      expect(screen.getByTitle(/Edit unit production cost/i)).toBeInTheDocument();
    });

    // Click edit button
    fireEvent.click(screen.getByTitle(/Edit unit production cost/i));

    // Input field should now be present
    const costInput = screen.getByRole("spinbutton");
    expect(costInput).toBeInTheDocument();
    fireEvent.change(costInput, { target: { value: "200" } });

    // Save with checkmark button
    const saveBtn = screen.getByTitle(/Save \(Enter\)/i);
    fireEvent.click(saveBtn);

    // Verify PUT was called with correct payload
    await waitFor(() => {
      expect(http.put).toHaveBeenCalledWith(
        "/online-orders/monthly-reconciliation-overview/cost",
        expect.objectContaining({
          style_code: "FL_AK_002",
          unit_production_cost: 200,
        })
      );
    });

    // Ensure full-page loader was NOT triggered during the update
    expect(screen.queryByText(/Loading monthly PnL reconciliation data…/i)).not.toBeInTheDocument();
    
    // Debug what is rendered
    await waitFor(() => {
      expect(screen.getByText(/200/)).toBeInTheDocument();
    });
  });

  test("renders style photo, Myntra Style ID, and ERP Style Code in Return Charges & Reverse Freight table", async () => {
    render(<OnlineProfitability />);

    fireEvent.click(screen.getByTestId("tab-monthly-pnl"));

    // Navigate to Return Charges & Deductions subtab
    await waitFor(() => {
      expect(screen.getByText(/Return Charges & Deductions/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/Return Charges & Deductions/i));

    // Check table headers and style identifiers
    await waitFor(() => {
      expect(screen.getByText(/Return Charges & Reverse Freight by Style/i)).toBeInTheDocument();
      expect(screen.getByText(/Style & Codes \/ Article/i)).toBeInTheDocument();
      expect(screen.getByText(/28933414/i)).toBeInTheDocument();
      expect(screen.getByText(/SSK_00034/i)).toBeInTheDocument();
      expect(screen.getByAltText("FL_AK_002")).toBeInTheDocument();
      expect(screen.getByAltText("FL_AK_002")).toHaveAttribute("src", "/company/laser_cut_flat.jpg");
    });
  });

  test("renders style photo, style code, and ERP Style Code alongside SKU code in SKU Drill-down table", async () => {
    render(<OnlineProfitability />);

    fireEvent.click(screen.getByTestId("tab-monthly-pnl"));

    // Navigate to SKU Drill-down subtab
    await waitFor(() => {
      expect(screen.getByText(/SKU Drill-down/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/SKU Drill-down/i));

    // Check SKU table headers and style metadata
    await waitFor(() => {
      expect(screen.getByText(/SKU Code & Style Identifiers/i)).toBeInTheDocument();
      expect(screen.getByText(/FL_AK_002-38/i)).toBeInTheDocument();
      expect(screen.getByText(/Style: FL_AK_002/i)).toBeInTheDocument();
      expect(screen.getByText(/ERP: SSK_00034/i)).toBeInTheDocument();
      expect(screen.getByAltText("FL_AK_002")).toBeInTheDocument();
      expect(screen.getByAltText("FL_AK_002")).toHaveAttribute("src", "/company/laser_cut_flat.jpg");
    });
  });
});
