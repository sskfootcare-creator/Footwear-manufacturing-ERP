import { useEffect, useState, useCallback, useMemo } from "react";
import { http, inr, num } from "../lib/api";
import { PageHeader, Card, Badge, StatTile } from "../components/ui-kit";
import {
  Building2,
  Package,
  Factory,
  FileText,
  Truck,
  Users,
  DollarSign,
  Download,
  RefreshCw,
  Search,
  Calendar,
  AlertTriangle,
  TrendingUp,
  CreditCard,
  Layers,
  Clock,
  CheckCircle2,
  ArrowDownRight,
  ArrowUpRight,
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const PALETTE = [
  "#C27842",
  "#2563EB",
  "#16A34A",
  "#7C3AED",
  "#F59E0B",
  "#DC2626",
  "#0EA5E9",
  "#A65D24",
];

const TABS = [
  { key: "business", label: "Total Business", icon: Building2, testId: "tab-business" },
  { key: "inventory", label: "Inventory & Materials", icon: Package, testId: "tab-inventory" },
  { key: "production", label: "Production Line", icon: Factory, testId: "tab-production" },
  { key: "sales", label: "Invoices & Sales", icon: FileText, testId: "tab-sales" },
  { key: "procurement", label: "Vendor Procurement", icon: Truck, testId: "tab-procurement" },
  { key: "receivables", label: "Client Receivables & AR", icon: Users, testId: "tab-receivables" },
  { key: "pnl", label: "Expenses & P&L", icon: DollarSign, testId: "tab-pnl" },
];

function downloadCsv(filename, headers, rows) {
  const content =
    "data:text/csv;charset=utf-8," +
    [
      headers.map((h) => `"${h}"`).join(","),
      ...rows.map((r) => r.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(",")),
    ].join("\n");
  const encodedUri = encodeURI(content);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export default function Reports() {
  const [activeTab, setActiveTab] = useState("business");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Tab datasets
  const [businessData, setBusinessData] = useState(null);
  const [inventoryData, setInventoryData] = useState(null);
  const [productionData, setProductionData] = useState(null);
  const [salesData, setSalesData] = useState(null);
  const [procurementData, setProcurementData] = useState(null);
  const [receivablesData, setReceivablesData] = useState(null);
  const [pnlData, setPnlData] = useState(null);

  // Filter query parameters
  const params = useMemo(() => {
    const p = {};
    if (fromDate) p.from_date = fromDate;
    if (toDate) p.to_date = toDate;
    return p;
  }, [fromDate, toDate]);

  // Fetch logic for active tab
  const loadActiveData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (activeTab === "business") {
        const res = await http.get("/reports/business-summary", { params });
        setBusinessData(res.data);
      } else if (activeTab === "inventory") {
        const res = await http.get("/reports/inventory-materials", { params });
        setInventoryData(res.data);
      } else if (activeTab === "production") {
        const res = await http.get("/reports/production-overview", { params });
        setProductionData(res.data);
      } else if (activeTab === "sales") {
        const res = await http.get("/reports/invoices-sales", { params });
        setSalesData(res.data);
      } else if (activeTab === "procurement") {
        const res = await http.get("/reports/vendor-procurement", { params });
        setProcurementData(res.data);
      } else if (activeTab === "receivables") {
        const res = await http.get("/reports/client-receivables", { params });
        setReceivablesData(res.data);
      } else if (activeTab === "pnl") {
        const res = await http.get("/reports/pnl-detailed", { params });
        setPnlData(res.data);
      }
    } catch (err) {
      console.error("Failed to load report data:", err);
      setError(err?.response?.data?.detail || "Failed to load report data. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [activeTab, params]);

  useEffect(() => {
    loadActiveData();
  }, [loadActiveData]);

  // Date Preset Handlers
  const handlePreset = (preset) => {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const fmt = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

    if (preset === "all") {
      setFromDate("");
      setToDate("");
    } else if (preset === "this_month") {
      const first = new Date(now.getFullYear(), now.getMonth(), 1);
      setFromDate(fmt(first));
      setToDate(fmt(now));
    } else if (preset === "last_30") {
      const past = new Date();
      past.setDate(past.getDate() - 30);
      setFromDate(fmt(past));
      setToDate(fmt(now));
    } else if (preset === "quarter") {
      const qMonth = Math.floor(now.getMonth() / 3) * 3;
      const qStart = new Date(now.getFullYear(), qMonth, 1);
      setFromDate(fmt(qStart));
      setToDate(fmt(now));
    } else if (preset === "fy") {
      // Indian Financial Year: April 1 to March 31
      const fyStartYear = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
      setFromDate(`${fyStartYear}-04-01`);
      setToDate(fmt(now));
    }
  };

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        title="Executive & Financial Reports"
        subtitle="Enterprise Management Reporting Suite"
        testId="reports-page-header"
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={loadActiveData}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold uppercase tracking-wider bg-white border-2 border-slate-300 hover:border-slate-900 transition-colors shadow-sm disabled:opacity-50"
              title="Refresh Report Data"
              data-testid="reports-refresh-btn"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>
        }
      />

      <div className="px-4 sm:px-8 space-y-6">
        {/* Date Filter Bar & Presets */}
        <div className="bg-white border-2 border-slate-200 p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mr-1 flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5" /> Quick Presets:
              </span>
              <button
                onClick={() => handlePreset("all")}
                data-testid="preset-all"
                className={`px-2.5 py-1 text-xs font-bold border transition-colors ${
                  !fromDate && !toDate
                    ? "bg-[#0F172A] text-white border-[#0F172A]"
                    : "bg-slate-50 text-slate-700 border-slate-300 hover:bg-slate-100"
                }`}
              >
                All Time
              </button>
              <button
                onClick={() => handlePreset("this_month")}
                data-testid="preset-month"
                className="px-2.5 py-1 text-xs font-bold border border-slate-300 bg-slate-50 text-slate-700 hover:bg-slate-100 transition-colors"
              >
                This Month
              </button>
              <button
                onClick={() => handlePreset("last_30")}
                data-testid="preset-last30"
                className="px-2.5 py-1 text-xs font-bold border border-slate-300 bg-slate-50 text-slate-700 hover:bg-slate-100 transition-colors"
              >
                Last 30 Days
              </button>
              <button
                onClick={() => handlePreset("quarter")}
                data-testid="preset-quarter"
                className="px-2.5 py-1 text-xs font-bold border border-slate-300 bg-slate-50 text-slate-700 hover:bg-slate-100 transition-colors"
              >
                This Quarter
              </button>
              <button
                onClick={() => handlePreset("fy")}
                data-testid="preset-fy"
                className="px-2.5 py-1 text-xs font-bold border border-slate-300 bg-slate-50 text-slate-700 hover:bg-slate-100 transition-colors"
              >
                FY to Date
              </button>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase font-bold tracking-widest text-slate-500">Period:</span>
              <input
                type="date"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
                className="border border-slate-300 px-2 py-1 text-xs font-mono focus:border-[#C27842] outline-none"
                data-testid="report-from-date"
              />
              <span className="text-slate-400 text-xs">to</span>
              <input
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                className="border border-slate-300 px-2 py-1 text-xs font-mono focus:border-[#C27842] outline-none"
                data-testid="report-to-date"
              />
              {(fromDate || toDate) && (
                <button
                  onClick={() => {
                    setFromDate("");
                    setToDate("");
                  }}
                  data-testid="report-clear-dates"
                  className="text-xs font-bold text-red-600 hover:text-red-800 ml-1 uppercase tracking-wider"
                >
                  Clear
                </button>
              )}
            </div>
          </div>
        </div>

        {/* 7 Enterprise Navigation Tabs */}
        <div className="flex border-b-2 border-slate-200 overflow-x-auto no-scrollbar gap-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = activeTab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                data-testid={t.testId}
                className={`px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-4 -mb-0.5 transition-colors flex items-center gap-2 whitespace-nowrap ${
                  active
                    ? "border-[#C27842] text-slate-900 bg-slate-50"
                    : "border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300"
                }`}
              >
                <Icon className={`w-4 h-4 ${active ? "text-[#C27842]" : "text-slate-400"}`} />
                <span>{t.label}</span>
              </button>
            );
          })}
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-4 bg-red-50 border-l-4 border-red-500 text-red-700 text-sm font-semibold flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-xs uppercase font-bold tracking-wider hover:underline">
              Dismiss
            </button>
          </div>
        )}

        {/* Active Tab View */}
        {loading && !businessData && !inventoryData && !salesData ? (
          <div className="p-12 text-center text-slate-400 font-mono text-sm">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-[#C27842]" />
            Loading enterprise metrics…
          </div>
        ) : (
          <div>
            {activeTab === "business" && <BusinessSummaryTab data={businessData} />}
            {activeTab === "inventory" && <InventoryValuationTab data={inventoryData} />}
            {activeTab === "production" && <ProductionOverviewTab data={productionData} />}
            {activeTab === "sales" && <InvoicesSalesTab data={salesData} />}
            {activeTab === "procurement" && <VendorProcurementTab data={procurementData} />}
            {activeTab === "receivables" && <ClientReceivablesTab data={receivablesData} />}
            {activeTab === "pnl" && <DetailedPnlTab data={pnlData} />}
          </div>
        )}
      </div>
    </div>
  );
}

/* =========================================================================
   TAB 1: EXECUTIVE / TOTAL BUSINESS SUMMARY
   ========================================================================= */
function BusinessSummaryTab({ data }) {
  if (!data) return <div className="p-8 text-center text-slate-400 font-mono">No financial data available.</div>;

  const handleExport = () => {
    const headers = ["Metric", "Value (INR / Count)"];
    const rows = [
      ["Gross Operating Revenue", data.gross_revenue],
      ["B2B Invoiced Revenue", data.total_b2b_invoiced],
      ["Online Marketplace Revenue", data.total_online_revenue],
      ["Raw Material Procurement Spend", data.total_procurement],
      ["Direct Karigar Wages", data.labor_cost],
      ["Cost of Goods Sold (COGS)", data.cogs],
      ["Gross Operating Profit", data.gross_profit],
      ["Gross Margin %", `${data.gross_margin_pct}%`],
      ["Operating Expenses (OPEX)", data.operating_expenses],
      ["Net Operating Profit", data.net_profit],
      ["Net Profit Margin %", `${data.net_margin_pct}%`],
      ["Total Liquid Funds (Bank & Cash)", data.total_liquid_funds],
      ["Bank Balances", data.total_bank_balance],
      ["Cash Balances", data.total_cash_balance],
      ["Total Accounts Receivable (AR)", data.total_ar_receivables],
      ["Total Accounts Payable (AP)", data.total_ap_payables],
      ["Active WIP Pairs in Pipeline", data.pipeline_pairs_count],
      ["Total Dispatched Pairs", data.dispatched_pairs_count],
      ["Raw Material Inventory Valuation", data.inventory_valuation],
    ];
    downloadCsv("SSK_ERP_Executive_Business_Summary.csv", headers, rows);
  };

  return (
    <div className="space-y-6" data-testid="business-summary-tab">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">
            360° Executive Business Performance
          </h2>
          <p className="text-xs text-slate-500">Unifying sales, manufacturing, procurement, and treasury balance</p>
        </div>
        <button
          onClick={handleExport}
          data-testid="export-business-csv"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-700 shadow-sm transition-colors"
        >
          <Download className="w-3.5 h-3.5" /> Export Summary CSV
        </button>
      </div>

      {/* 8 Primary Executive KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile
          label="Gross Revenue"
          value={inr(data.gross_revenue)}
          sub={`B2B: ${inr(data.total_b2b_invoiced)} | Online: ${inr(data.total_online_revenue)}`}
          accent="#16A34A"
          testId="kpi-gross-revenue"
        />
        <StatTile
          label="Total Procurement Spend"
          value={inr(data.total_procurement)}
          sub="Raw Materials & Components"
          accent="#2563EB"
          testId="kpi-total-procurement"
        />
        <StatTile
          label="Direct Labor Wages"
          value={inr(data.labor_cost)}
          sub="Karigar piece-rate earnings"
          accent="#C27842"
          testId="kpi-labor-cost"
        />
        <StatTile
          label="Operating Expenses"
          value={inr(data.operating_expenses)}
          sub="Factory overhead, utilities, admin"
          accent="#DC2626"
          testId="kpi-operating-expenses"
        />
        <StatTile
          label="Net Operating Profit"
          value={inr(data.net_profit)}
          sub={`Net Margin: ${data.net_margin_pct}%`}
          accent={data.net_profit >= 0 ? "#16A34A" : "#DC2626"}
          testId="kpi-net-profit"
        />
        <StatTile
          label="Total Liquid Funds"
          value={inr(data.total_liquid_funds)}
          sub={`Bank: ${inr(data.total_bank_balance)} | Cash: ${inr(data.total_cash_balance)}`}
          accent="#0EA5E9"
          testId="kpi-liquid-funds"
        />
        <StatTile
          label="Accounts Receivable (AR)"
          value={inr(data.total_ar_receivables)}
          sub="Pending collections from clients"
          accent="#F59E0B"
          testId="kpi-ar-receivables"
        />
        <StatTile
          label="Accounts Payable (AP)"
          value={inr(data.total_ap_payables)}
          sub="Pending payments to vendors"
          accent="#7C3AED"
          testId="kpi-ap-payables"
        />
      </div>

      {/* Monthly Financial Trend Chart */}
      <Card className="p-6">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800">
              Monthly Financial Trajectory (Revenue vs Spend vs Profit)
            </h3>
            <span className="text-xs text-slate-500">Historical performance across active operating months</span>
          </div>
        </div>
        <div className="w-full h-80" data-testid="business-trend-chart">
          {data.monthly_trend && data.monthly_trend.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.monthly_trend} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`} />
                <Tooltip
                  formatter={(value) => [inr(value), ""]}
                  contentStyle={{ fontSize: 12, border: "2px solid #0F172A" }}
                />
                <Legend wrapperStyle={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase" }} />
                <Line type="monotone" dataKey="revenue" name="Gross Revenue" stroke="#16A34A" strokeWidth={2.5} />
                <Line type="monotone" dataKey="procurement" name="Procurement" stroke="#2563EB" strokeWidth={2} />
                <Line type="monotone" dataKey="expenses" name="Expenses" stroke="#DC2626" strokeWidth={2} />
                <Line type="monotone" dataKey="profit" name="Net Profit" stroke="#C27842" strokeWidth={2.5} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-400 font-mono text-xs">
              No historical trend data available for selected filter period.
            </div>
          )}
        </div>
      </Card>

      {/* Operational Highlights Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-5">
          <div className="text-[10px] uppercase tracking-widest font-bold text-slate-500 mb-2">
            Factory WIP & Throughput
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-3xl font-bold text-slate-900">{num(data.pipeline_pairs_count)}</span>
            <span className="text-xs text-slate-500 font-bold uppercase">Pairs in Pipeline</span>
          </div>
          <div className="mt-4 pt-4 border-t border-slate-100 flex justify-between text-xs text-slate-600">
            <span>Dispatched Pairs:</span>
            <span className="font-mono font-bold text-[#16A34A]">{num(data.dispatched_pairs_count)} pairs</span>
          </div>
          <div className="mt-1 flex justify-between text-xs text-slate-600">
            <span>Active Production Jobs:</span>
            <span className="font-mono font-bold">{data.pipeline_jobs_count} jobs</span>
          </div>
        </Card>

        <Card className="p-5">
          <div className="text-[10px] uppercase tracking-widest font-bold text-slate-500 mb-2">
            Inventory Asset Valuation
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-3xl font-bold text-[#2563EB]">{inr(data.inventory_valuation)}</span>
          </div>
          <div className="mt-4 pt-4 border-t border-slate-100 text-xs text-slate-600">
            Current balance of leather, soles, adhesives, and hardware calculated at weighted average rate.
          </div>
        </Card>

        <Card className="p-5">
          <div className="text-[10px] uppercase tracking-widest font-bold text-slate-500 mb-2">
            Working Capital Health
          </div>
          <div className="flex items-baseline gap-2">
            <span
              className={`font-mono text-3xl font-bold ${
                data.total_ar_receivables >= data.total_ap_payables ? "text-[#16A34A]" : "text-amber-600"
              }`}
            >
              {inr(data.total_ar_receivables - data.total_ap_payables)}
            </span>
          </div>
          <div className="mt-4 pt-4 border-t border-slate-100 text-xs text-slate-600 flex justify-between">
            <span>AR vs AP Net Ratio:</span>
            <span className="font-mono font-bold">
              {data.total_ap_payables > 0
                ? `${(data.total_ar_receivables / data.total_ap_payables).toFixed(2)}x`
                : "∞"}
            </span>
          </div>
        </Card>
      </div>
    </div>
  );
}

/* =========================================================================
   TAB 2: RAW MATERIALS & INVENTORY VALUATION
   ========================================================================= */
function InventoryValuationTab({ data }) {
  const [searchTerm, setSearchTerm] = useState("");
  const [filterCategory, setFilterCategory] = useState("all");

  const categories = data?.categories || [];
  const materials = data?.materials || [];

  const filteredMaterials = useMemo(() => {
    return materials.filter((m) => {
      const matchSearch =
        (m.name || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
        (m.code || "").toLowerCase().includes(searchTerm.toLowerCase());
      const matchCat = filterCategory === "all" || m.category === filterCategory;
      return matchSearch && matchCat;
    });
  }, [materials, searchTerm, filterCategory]);

  if (!data) return <div className="p-8 text-center text-slate-400 font-mono">No inventory data available.</div>;

  const handleExport = () => {
    const headers = [
      "Material Code",
      "Material Name",
      "Category",
      "Current Stock",
      "Unit",
      "Weighted Avg Rate (INR)",
      "Last Purchase Rate (INR)",
      "Valuation (INR)",
      "Reorder Level",
      "Status",
    ];
    const rows = filteredMaterials.map((m) => [
      m.code,
      m.name,
      m.category,
      m.current_stock,
      m.unit,
      m.weighted_avg_rate,
      m.last_purchase_rate,
      m.total_valuation,
      m.reorder_level,
      m.status,
    ]);
    downloadCsv("SSK_ERP_Material_Inventory_Valuation.csv", headers, rows);
  };

  return (
    <div className="space-y-6" data-testid="inventory-materials-tab">
      <div className="flex flex-wrap justify-between items-center gap-4">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">
            Raw Materials & Inventory Valuation
          </h2>
          <p className="text-xs text-slate-500">Live valuation, weighted average costs, and stock shortage alerts</p>
        </div>
        <button
          onClick={handleExport}
          data-testid="export-inventory-csv"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-700 shadow-sm transition-colors"
        >
          <Download className="w-3.5 h-3.5" /> Export Inventory CSV
        </button>
      </div>

      {/* KPI Tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile
          label="Total Inventory Value"
          value={inr(data.total_valuation)}
          sub="Weighted Average Valuation"
          accent="#16A34A"
          testId="inv-total-valuation"
        />
        <StatTile
          label="Total Material SKUs"
          value={data.total_items}
          sub="Catalogued materials"
          accent="#2563EB"
          testId="inv-total-items"
        />
        <StatTile
          label="Low Stock Alert"
          value={data.low_stock_count}
          sub="Below reorder threshold"
          accent="#F59E0B"
          testId="inv-low-stock"
        />
        <StatTile
          label="Out of Stock"
          value={data.out_of_stock_count}
          sub="Zero balance items"
          accent="#DC2626"
          testId="inv-out-of-stock"
        />
      </div>

      {/* Inward vs Outward Movement Snapshot */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="p-4 bg-emerald-50/40 border-emerald-200">
          <div className="flex items-center gap-2 text-emerald-800 text-xs font-bold uppercase tracking-wider mb-1">
            <ArrowDownRight className="w-4 h-4 text-emerald-600" /> Inward Receipts / GRN
          </div>
          <div className="flex items-baseline justify-between mt-2">
            <span className="font-mono text-2xl font-bold text-emerald-900">{inr(data.inward_movement_val)}</span>
            <span className="text-xs font-mono text-emerald-700 font-semibold">{num(data.inward_movement_qty)} units</span>
          </div>
        </Card>
        <Card className="p-4 bg-amber-50/40 border-amber-200">
          <div className="flex items-center gap-2 text-amber-800 text-xs font-bold uppercase tracking-wider mb-1">
            <ArrowUpRight className="w-4 h-4 text-amber-600" /> Outward Consumption / Issues
          </div>
          <div className="flex items-baseline justify-between mt-2">
            <span className="font-mono text-2xl font-bold text-amber-900">{inr(data.outward_movement_val)}</span>
            <span className="text-xs font-mono text-amber-700 font-semibold">{num(data.outward_movement_qty)} units</span>
          </div>
        </Card>
      </div>

      {/* Category Distribution Chart */}
      <Card className="p-6">
        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 mb-4">
          Category-wise Inventory Valuation Distribution
        </h3>
        <div className="w-full h-64" data-testid="inventory-category-chart">
          {categories.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={categories} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="category" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(value) => [inr(value), "Valuation"]} />
                <Bar dataKey="total_valuation" fill="#C27842" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-400 font-mono text-xs">
              No category data available.
            </div>
          )}
        </div>
      </Card>

      {/* Search & Material Valuation Table */}
      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2 flex-1 max-w-sm">
            <div className="relative w-full">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search material code or name…"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full border border-slate-300 pl-9 pr-3 py-1.5 text-xs font-mono focus:border-[#C27842] outline-none"
                data-testid="search-inventory-input"
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase font-bold tracking-wider text-slate-500">Category:</span>
            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              className="border border-slate-300 px-2 py-1.5 text-xs bg-white focus:border-[#C27842] outline-none font-bold"
              data-testid="filter-inventory-category"
            >
              <option value="all">{`All Categories (${materials.length})`}</option>
              {categories.map((c) => (
                <option key={c.category} value={c.category}>
                  {`${c.category} (${c.items_count})`}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                <th className="py-2.5 px-3">Code</th>
                <th className="py-2.5 px-3">Material Name</th>
                <th className="py-2.5 px-3">Category</th>
                <th className="py-2.5 px-3 text-right">Stock</th>
                <th className="py-2.5 px-3">Unit</th>
                <th className="py-2.5 px-3 text-right">Weighted Rate</th>
                <th className="py-2.5 px-3 text-right">Last Purchase</th>
                <th className="py-2.5 px-3 text-right">Valuation</th>
                <th className="py-2.5 px-3 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 font-mono">
              {filteredMaterials.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-6 text-center text-slate-400">
                    No materials matched your filter criteria.
                  </td>
                </tr>
              ) : (
                filteredMaterials.map((m) => (
                  <tr key={m.id} className="hover:bg-slate-50/80 transition-colors" data-testid={`material-row-${m.id}`}>
                    <td className="py-2 px-3 font-bold text-slate-900">{m.code}</td>
                    <td className="py-2 px-3 font-sans font-medium text-slate-800">{m.name}</td>
                    <td className="py-2 px-3 font-sans text-slate-600">{m.category}</td>
                    <td className="py-2 px-3 text-right font-bold">{num(m.current_stock)}</td>
                    <td className="py-2 px-3 text-slate-500 font-sans">{m.unit}</td>
                    <td className="py-2 px-3 text-right text-slate-600">{inr(m.weighted_avg_rate)}</td>
                    <td className="py-2 px-3 text-right text-slate-600">{inr(m.last_purchase_rate)}</td>
                    <td className="py-2 px-3 text-right font-bold text-slate-900">{inr(m.total_valuation)}</td>
                    <td className="py-2 px-3 text-center font-sans">
                      {m.status === "Out of Stock" ? (
                        <Badge color="red">Out of Stock</Badge>
                      ) : m.status === "Low Stock" ? (
                        <Badge color="yellow">Low Stock</Badge>
                      ) : (
                        <Badge color="green">Adequate</Badge>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/* =========================================================================
   TAB 3: PRODUCTION LINE OVERVIEW & STAGE WIP
   ========================================================================= */
function ProductionOverviewTab({ data }) {
  if (!data) return <div className="p-8 text-center text-slate-400 font-mono">No production data available.</div>;

  const stageBreakdown = data.stage_breakdown || [];

  const handleExport = () => {
    const headers = ["Manufacturing Stage", "Job Cards Count", "Pairs in Stage"];
    const rows = stageBreakdown.map((s) => [s.stage, s.job_count, s.total_pairs]);
    downloadCsv("SSK_ERP_Production_Stage_Throughput.csv", headers, rows);
  };

  return (
    <div className="space-y-6" data-testid="production-overview-tab">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">
            Production Line & Manufacturing WIP
          </h2>
          <p className="text-xs text-slate-500">Shop floor throughput, stage queue balances, and defect analytics</p>
        </div>
        <button
          onClick={handleExport}
          data-testid="export-production-csv"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-700 shadow-sm transition-colors"
        >
          <Download className="w-3.5 h-3.5" /> Export Production CSV
        </button>
      </div>

      {/* KPI Tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile
          label="Total Job Cards"
          value={data.total_jobs}
          sub={`Active: ${data.active_jobs} jobs`}
          accent="#C27842"
          testId="prod-total-jobs"
        />
        <StatTile
          label="Total Pairs Started"
          value={num(data.total_pairs_started)}
          sub="Cumulative production volume"
          accent="#2563EB"
          testId="prod-pairs-started"
        />
        <StatTile
          label="Pairs Dispatched"
          value={num(data.total_pairs_dispatched)}
          sub="Fulfilled & shipped"
          accent="#16A34A"
          testId="prod-pairs-dispatched"
        />
        <StatTile
          label="Total Defects Logged"
          value={data.total_defects}
          sub={`Rejected: ${data.total_rejected_pairs} pairs`}
          accent="#DC2626"
          testId="prod-total-defects"
        />
      </div>

      {/* Stage-wise Active WIP Bar Chart */}
      <Card className="p-6">
        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 mb-4">
          Pairs by Production Stage Pipeline
        </h3>
        <div className="w-full h-72" data-testid="production-stage-chart">
          {stageBreakdown.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stageBreakdown} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis
                  dataKey="stage"
                  tick={{ fontSize: 11 }}
                  angle={-20}
                  textAnchor="end"
                  tickFormatter={(val) => val.replace(/_/g, " ").toUpperCase()}
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(value) => [`${num(value)} pairs`, "Volume"]}
                  labelFormatter={(lbl) => String(lbl).replace(/_/g, " ").toUpperCase()}
                />
                <Bar dataKey="total_pairs" fill="#2563EB" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-400 font-mono text-xs">
              No stage WIP data available.
            </div>
          )}
        </div>
      </Card>

      {/* Stage WIP Table */}
      <Card className="p-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">
          Stage-wise Work-In-Progress Queue
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                <th className="py-2.5 px-3">Stage</th>
                <th className="py-2.5 px-3 text-right">Job Cards</th>
                <th className="py-2.5 px-3 text-right">Total Pairs</th>
                <th className="py-2.5 px-3 text-right">% of Total Volume</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 font-mono">
              {stageBreakdown.map((s) => {
                const pct =
                  data.total_pairs_started > 0
                    ? ((s.total_pairs / data.total_pairs_started) * 100).toFixed(1)
                    : "0.0";
                return (
                  <tr key={s.stage} className="hover:bg-slate-50 transition-colors">
                    <td className="py-2 px-3 font-sans font-bold capitalize text-slate-900">
                      {s.stage.replace(/_/g, " ")}
                    </td>
                    <td className="py-2 px-3 text-right font-medium">{s.job_count}</td>
                    <td className="py-2 px-3 text-right font-bold text-slate-900">{num(s.total_pairs)}</td>
                    <td className="py-2 px-3 text-right text-slate-500">{pct}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/* =========================================================================
   TAB 4: INVOICES & SALES PERFORMANCE
   ========================================================================= */
function InvoicesSalesTab({ data }) {
  const [searchInvoice, setSearchInvoice] = useState("");

  const invoices = data?.invoices || [];
  const topClients = data?.top_clients || [];

  const filteredInvoices = useMemo(() => {
    return invoices.filter((i) => {
      return (
        (i.invoice_number || "").toLowerCase().includes(searchInvoice.toLowerCase()) ||
        (i.client_name || "").toLowerCase().includes(searchInvoice.toLowerCase())
      );
    });
  }, [invoices, searchInvoice]);

  if (!data) return <div className="p-8 text-center text-slate-400 font-mono">No sales data available.</div>;

  const handleExport = () => {
    const headers = [
      "Invoice Number",
      "Invoice Date",
      "Client Name",
      "Total Pairs",
      "Grand Total (INR)",
      "Paid Amount (INR)",
      "Balance Due (INR)",
      "Status",
    ];
    const rows = filteredInvoices.map((i) => [
      i.invoice_number,
      i.invoice_date,
      i.client_name,
      i.total_pairs,
      i.grand_total,
      i.paid_amount,
      i.balance_due,
      i.status,
    ]);
    downloadCsv("SSK_ERP_Sales_Invoices_Register.csv", headers, rows);
  };

  return (
    <div className="space-y-6" data-testid="invoices-sales-tab">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">
            B2B Invoices & Sales Performance
          </h2>
          <p className="text-xs text-slate-500">Tax invoices, cash collection rates, and client revenue contributions</p>
        </div>
        <button
          onClick={handleExport}
          data-testid="export-sales-csv"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-700 shadow-sm transition-colors"
        >
          <Download className="w-3.5 h-3.5" /> Export Invoices CSV
        </button>
      </div>

      {/* KPI Tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile
          label="Total Invoiced Value"
          value={inr(data.total_invoiced)}
          sub={`${data.total_invoices} tax invoices issued`}
          accent="#16A34A"
          testId="sales-total-invoiced"
        />
        <StatTile
          label="Total Collections Received"
          value={inr(data.total_paid)}
          sub={`Realization Rate: ${data.collection_rate_pct}%`}
          accent="#2563EB"
          testId="sales-total-paid"
        />
        <StatTile
          label="Outstanding Balance Due"
          value={inr(data.total_balance)}
          sub="Uncollected receivables"
          accent="#DC2626"
          testId="sales-total-balance"
        />
        <StatTile
          label="Collection Rate"
          value={`${data.collection_rate_pct}%`}
          sub="Paid / Invoiced ratio"
          accent="#F59E0B"
          testId="sales-collection-rate"
        />
      </div>

      {/* Top Clients Breakdown */}
      {topClients.length > 0 && (
        <Card className="p-6">
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 mb-4">
            Top Clients by Revenue Contribution
          </h3>
          <div className="w-full h-64" data-testid="sales-top-clients-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={topClients} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="client_name" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`} />
                <Tooltip formatter={(value) => [inr(value), "Billed"]} />
                <Bar dataKey="total_billed" fill="#16A34A" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* Invoices Register Table */}
      <Card className="p-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">Invoices Register</h3>
          <div className="relative w-64">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search invoice or client…"
              value={searchInvoice}
              onChange={(e) => setSearchInvoice(e.target.value)}
              className="w-full border border-slate-300 pl-9 pr-3 py-1.5 text-xs font-mono focus:border-[#C27842] outline-none"
              data-testid="search-invoices-input"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                <th className="py-2.5 px-3">Invoice #</th>
                <th className="py-2.5 px-3">Date</th>
                <th className="py-2.5 px-3">Client</th>
                <th className="py-2.5 px-3 text-right">Pairs</th>
                <th className="py-2.5 px-3 text-right">Grand Total</th>
                <th className="py-2.5 px-3 text-right">Paid</th>
                <th className="py-2.5 px-3 text-right">Balance Due</th>
                <th className="py-2.5 px-3 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 font-mono">
              {filteredInvoices.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-slate-400">
                    No invoices found.
                  </td>
                </tr>
              ) : (
                filteredInvoices.map((i) => (
                  <tr key={i.id} className="hover:bg-slate-50 transition-colors">
                    <td className="py-2 px-3 font-bold text-slate-900">{i.invoice_number}</td>
                    <td className="py-2 px-3 text-slate-600">{i.invoice_date}</td>
                    <td className="py-2 px-3 font-sans font-medium text-slate-800">{i.client_name}</td>
                    <td className="py-2 px-3 text-right">{num(i.total_pairs)}</td>
                    <td className="py-2 px-3 text-right font-bold text-slate-900">{inr(i.grand_total)}</td>
                    <td className="py-2 px-3 text-right text-emerald-600">{inr(i.paid_amount)}</td>
                    <td className="py-2 px-3 text-right font-bold text-red-600">{inr(i.balance_due)}</td>
                    <td className="py-2 px-3 text-center font-sans">
                      {i.status === "paid" ? (
                        <Badge color="green">Paid</Badge>
                      ) : i.status === "partially_paid" ? (
                        <Badge color="yellow">Partial</Badge>
                      ) : (
                        <Badge color="red">Unpaid</Badge>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/* =========================================================================
   TAB 5: VENDOR PROCUREMENT & AP REPORT
   ========================================================================= */
function VendorProcurementTab({ data }) {
  if (!data) return <div className="p-8 text-center text-slate-400 font-mono">No procurement data available.</div>;

  const vendors = data.vendors || [];
  const purchaseOrders = data.purchase_orders || [];
  const apAging = data.ap_aging || {};

  const handleExport = () => {
    const headers = [
      "PO Number",
      "Vendor Name",
      "Created Date",
      "Ordered Qty",
      "Received Qty",
      "Total Amount (INR)",
      "Paid Amount (INR)",
      "Balance Due (INR)",
      "Status",
    ];
    const rows = purchaseOrders.map((p) => [
      p.po_number,
      p.vendor_name,
      p.created_at,
      p.ordered_quantity,
      p.received_quantity,
      p.total_amount,
      p.paid_amount,
      p.balance_due,
      p.status,
    ]);
    downloadCsv("SSK_ERP_Vendor_Procurement_AP.csv", headers, rows);
  };

  return (
    <div className="space-y-6" data-testid="vendor-procurement-tab">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">
            Vendor Procurement & Accounts Payable (AP)
          </h2>
          <p className="text-xs text-slate-500">Purchase orders, delivery fulfillment rates, and supplier payables aging</p>
        </div>
        <button
          onClick={handleExport}
          data-testid="export-procurement-csv"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-700 shadow-sm transition-colors"
        >
          <Download className="w-3.5 h-3.5" /> Export Procurement CSV
        </button>
      </div>

      {/* KPI Tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile
          label="Total Procurement Spend"
          value={inr(data.total_po_value)}
          sub={`${data.total_pos} vendor POs issued`}
          accent="#2563EB"
          testId="proc-total-value"
        />
        <StatTile
          label="Total Paid to Vendors"
          value={inr(data.total_paid)}
          sub="Disbursed supplier payments"
          accent="#16A34A"
          testId="proc-total-paid"
        />
        <StatTile
          label="Outstanding AP Balance"
          value={inr(data.total_balance_due)}
          sub="Accounts payable liabilities"
          accent="#DC2626"
          testId="proc-total-balance"
        />
        <StatTile
          label="Delivery Fulfillment"
          value={`${data.fulfillment_rate_pct}%`}
          sub={`${num(data.total_received_qty)} / ${num(data.total_ordered_qty)} units received`}
          accent="#F59E0B"
          testId="proc-fulfillment-rate"
        />
      </div>

      {/* Accounts Payable (AP) Aging Schedule */}
      <Card className="p-5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">
          Accounts Payable (AP) Aging Schedule
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 bg-emerald-50 border border-emerald-200">
            <div className="text-[10px] uppercase font-bold text-emerald-800 tracking-wider">0–30 Days</div>
            <div className="text-xl font-bold font-mono text-emerald-950 mt-1">{inr(apAging["0_30"] || 0)}</div>
            <div className="text-[11px] text-emerald-700 mt-1">Current dues</div>
          </div>
          <div className="p-4 bg-blue-50 border border-blue-200">
            <div className="text-[10px] uppercase font-bold text-blue-800 tracking-wider">31–60 Days</div>
            <div className="text-xl font-bold font-mono text-blue-950 mt-1">{inr(apAging["31_60"] || 0)}</div>
            <div className="text-[11px] text-blue-700 mt-1">Moderate aging</div>
          </div>
          <div className="p-4 bg-amber-50 border border-amber-200">
            <div className="text-[10px] uppercase font-bold text-amber-800 tracking-wider">61–90 Days</div>
            <div className="text-xl font-bold font-mono text-amber-950 mt-1">{inr(apAging["61_90"] || 0)}</div>
            <div className="text-[11px] text-amber-700 mt-1">Overdue alert</div>
          </div>
          <div className="p-4 bg-red-50 border border-red-200">
            <div className="text-[10px] uppercase font-bold text-red-800 tracking-wider">90+ Days</div>
            <div className="text-xl font-bold font-mono text-red-950 mt-1">{inr(apAging["90_plus"] || 0)}</div>
            <div className="text-[11px] text-red-700 mt-1">Critical aged payables</div>
          </div>
        </div>
      </Card>

      {/* Vendor Breakdown Table */}
      <Card className="p-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">
          Vendor-wise Procurement & Payables
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                <th className="py-2.5 px-3">Vendor Name</th>
                <th className="py-2.5 px-3 text-right">POs</th>
                <th className="py-2.5 px-3 text-right">Ordered Units</th>
                <th className="py-2.5 px-3 text-right">Received Units</th>
                <th className="py-2.5 px-3 text-right">Total Billed</th>
                <th className="py-2.5 px-3 text-right">Paid</th>
                <th className="py-2.5 px-3 text-right">Balance Due</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 font-mono">
              {vendors.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-400">
                    No vendor procurement records found.
                  </td>
                </tr>
              ) : (
                vendors.map((v) => (
                  <tr key={v.vendor_name} className="hover:bg-slate-50 transition-colors">
                    <td className="py-2 px-3 font-sans font-bold text-slate-900">{v.vendor_name}</td>
                    <td className="py-2 px-3 text-right">{v.pos_count}</td>
                    <td className="py-2 px-3 text-right">{num(v.ordered_qty)}</td>
                    <td className="py-2 px-3 text-right">{num(v.received_qty)}</td>
                    <td className="py-2 px-3 text-right font-bold text-slate-900">{inr(v.total_amount)}</td>
                    <td className="py-2 px-3 text-right text-emerald-600">{inr(v.paid_amount)}</td>
                    <td className="py-2 px-3 text-right font-bold text-red-600">{inr(v.balance_due)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/* =========================================================================
   TAB 6: CLIENT RECEIVABLES & AR REPORT
   ========================================================================= */
function ClientReceivablesTab({ data }) {
  const [searchClient, setSearchClient] = useState("");

  const clients = data?.clients || [];
  const arAging = data?.ar_aging || {};

  const filteredClients = useMemo(() => {
    return clients.filter((c) => (c.name || "").toLowerCase().includes(searchClient.toLowerCase()));
  }, [clients, searchClient]);

  if (!data) return <div className="p-8 text-center text-slate-400 font-mono">No receivables data available.</div>;

  const handleExport = () => {
    const headers = [
      "Client Name",
      "Contact Person",
      "Phone",
      "Invoiced Total (INR)",
      "Paid Total (INR)",
      "Outstanding Balance (INR)",
      "Aging Bucket",
      "Payment Terms (Days)",
    ];
    const rows = filteredClients.map((c) => [
      c.name,
      c.contact_person,
      c.phone,
      c.invoiced_total,
      c.paid_total,
      c.balance_due,
      c.aging_bucket,
      c.payment_terms_days,
    ]);
    downloadCsv("SSK_ERP_Client_Receivables_AR.csv", headers, rows);
  };

  return (
    <div className="space-y-6" data-testid="client-receivables-tab">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">
            Client Receivables & Accounts Receivable (AR)
          </h2>
          <p className="text-xs text-slate-500">Aging schedule, client ledgers, and outstanding debt balances</p>
        </div>
        <button
          onClick={handleExport}
          data-testid="export-receivables-csv"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-700 shadow-sm transition-colors"
        >
          <Download className="w-3.5 h-3.5" /> Export AR CSV
        </button>
      </div>

      {/* KPI Tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile
          label="Active B2B Clients"
          value={data.total_clients}
          sub="Customer ledger accounts"
          accent="#2563EB"
          testId="ar-total-clients"
        />
        <StatTile
          label="Total B2B Invoiced"
          value={inr(data.total_invoiced)}
          sub="Lifetime client billings"
          accent="#16A34A"
          testId="ar-total-invoiced"
        />
        <StatTile
          label="Total Collections Received"
          value={inr(data.total_paid)}
          sub="Realized bank receipts"
          accent="#0EA5E9"
          testId="ar-total-paid"
        />
        <StatTile
          label="Outstanding AR Balance"
          value={inr(data.total_outstanding)}
          sub="Pending client payments"
          accent="#DC2626"
          testId="ar-total-outstanding"
        />
      </div>

      {/* Accounts Receivable Aging Schedule */}
      <Card className="p-5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">
          Accounts Receivable (AR) Aging Schedule
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 bg-emerald-50 border border-emerald-200">
            <div className="text-[10px] uppercase font-bold text-emerald-800 tracking-wider">0–30 Days</div>
            <div className="text-xl font-bold font-mono text-emerald-950 mt-1">{inr(arAging["0_30"] || 0)}</div>
            <div className="text-[11px] text-emerald-700 mt-1">Current billings</div>
          </div>
          <div className="p-4 bg-blue-50 border border-blue-200">
            <div className="text-[10px] uppercase font-bold text-blue-800 tracking-wider">31–60 Days</div>
            <div className="text-xl font-bold font-mono text-blue-950 mt-1">{inr(arAging["31_60"] || 0)}</div>
            <div className="text-[11px] text-blue-700 mt-1">Moderate aging</div>
          </div>
          <div className="p-4 bg-amber-50 border border-amber-200">
            <div className="text-[10px] uppercase font-bold text-amber-800 tracking-wider">61–90 Days</div>
            <div className="text-xl font-bold font-mono text-amber-950 mt-1">{inr(arAging["61_90"] || 0)}</div>
            <div className="text-[11px] text-amber-700 mt-1">Collection overdue</div>
          </div>
          <div className="p-4 bg-red-50 border border-red-200">
            <div className="text-[10px] uppercase font-bold text-red-800 tracking-wider">90+ Days</div>
            <div className="text-xl font-bold font-mono text-red-950 mt-1">{inr(arAging["90_plus"] || 0)}</div>
            <div className="text-[11px] text-red-700 mt-1">Critical debt risk</div>
          </div>
        </div>
      </Card>

      {/* Client AR Ledger Table */}
      <Card className="p-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">Client Balances Register</h3>
          <div className="relative w-64">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search client name…"
              value={searchClient}
              onChange={(e) => setSearchClient(e.target.value)}
              className="w-full border border-slate-300 pl-9 pr-3 py-1.5 text-xs font-mono focus:border-[#C27842] outline-none"
              data-testid="search-client-input"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                <th className="py-2.5 px-3">Client Name</th>
                <th className="py-2.5 px-3">Contact</th>
                <th className="py-2.5 px-3">Phone</th>
                <th className="py-2.5 px-3 text-right">Invoiced Total</th>
                <th className="py-2.5 px-3 text-right">Paid Total</th>
                <th className="py-2.5 px-3 text-right">Outstanding Balance</th>
                <th className="py-2.5 px-3 text-center">Terms</th>
                <th className="py-2.5 px-3 text-center">Aging Bucket</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 font-mono">
              {filteredClients.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-slate-400">
                    No client records found.
                  </td>
                </tr>
              ) : (
                filteredClients.map((c) => (
                  <tr key={c.name} className="hover:bg-slate-50 transition-colors">
                    <td className="py-2 px-3 font-sans font-bold text-slate-900">{c.name}</td>
                    <td className="py-2 px-3 font-sans text-slate-600">{c.contact_person}</td>
                    <td className="py-2 px-3 text-slate-500">{c.phone}</td>
                    <td className="py-2 px-3 text-right text-slate-900">{inr(c.invoiced_total)}</td>
                    <td className="py-2 px-3 text-right text-emerald-600">{inr(c.paid_total)}</td>
                    <td className="py-2 px-3 text-right font-bold text-red-600">{inr(c.balance_due)}</td>
                    <td className="py-2 px-3 text-center font-sans text-slate-500">{c.payment_terms_days}d</td>
                    <td className="py-2 px-3 text-center font-sans">
                      {c.aging_bucket === "90+" ? (
                        <Badge color="red">90+ Days</Badge>
                      ) : c.aging_bucket === "61-90" ? (
                        <Badge color="orange">61–90 Days</Badge>
                      ) : c.aging_bucket === "31-60" ? (
                        <Badge color="yellow">31–60 Days</Badge>
                      ) : (
                        <Badge color="green">0–30 Days</Badge>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/* =========================================================================
   TAB 7: DETAILED P&L STATEMENT
   ========================================================================= */
function DetailedPnlTab({ data }) {
  if (!data) return <div className="p-8 text-center text-slate-400 font-mono">No P&L data available.</div>;

  const expenseCategories = data.expense_categories || [];
  const monthlyPnl = data.monthly_pnl || [];

  const handleExport = () => {
    const headers = ["Month", "Revenue (INR)", "COGS (INR)", "Gross Profit (INR)", "OPEX (INR)", "Net Profit (INR)", "Net Margin %"];
    const rows = monthlyPnl.map((m) => [
      m.month,
      m.revenue,
      m.cogs,
      m.gross_profit,
      m.opex,
      m.net_profit,
      `${m.net_margin_pct}%`,
    ]);
    downloadCsv("SSK_ERP_Detailed_PnL_Schedule.csv", headers, rows);
  };

  return (
    <div className="space-y-6" data-testid="pnl-detailed-tab">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">
            Comprehensive Profit & Loss (P&L) Statement
          </h2>
          <p className="text-xs text-slate-500">Revenue, direct COGS, gross margin, operating overheads, and net profit</p>
        </div>
        <button
          onClick={handleExport}
          data-testid="export-pnl-csv"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-300 hover:border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-700 shadow-sm transition-colors"
        >
          <Download className="w-3.5 h-3.5" /> Export P&L CSV
        </button>
      </div>

      {/* Top P&L Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile
          label="Gross Revenue"
          value={inr(data.gross_revenue)}
          sub={`B2B: ${inr(data.b2b_revenue)} | Online: ${inr(data.online_revenue)}`}
          accent="#16A34A"
          testId="pnl-gross-revenue"
        />
        <StatTile
          label="Cost of Goods Sold (COGS)"
          value={inr(data.total_cogs)}
          sub={`Materials: ${inr(data.material_cogs)} | Labor: ${inr(data.labor_cogs)}`}
          accent="#2563EB"
          testId="pnl-total-cogs"
        />
        <StatTile
          label="Gross Profit"
          value={inr(data.gross_profit)}
          sub={`Gross Margin: ${data.gross_margin_pct}%`}
          accent={data.gross_profit >= 0 ? "#16A34A" : "#DC2626"}
          testId="pnl-gross-profit"
        />
        <StatTile
          label="Net Operating Profit"
          value={inr(data.net_profit)}
          sub={`Net Margin: ${data.net_margin_pct}% (after ${inr(data.total_opex)} OPEX)`}
          accent={data.net_profit >= 0 ? "#16A34A" : "#DC2626"}
          testId="pnl-net-profit"
        />
      </div>

      {/* P&L Breakdown Schedule Table */}
      <Card className="p-6">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-4">
          Financial P&L Schedule Schedule
        </h3>
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
              <th className="py-2.5 px-3">Schedule Item</th>
              <th className="py-2.5 px-3">Classification</th>
              <th className="py-2.5 px-3 text-right">Amount (INR)</th>
              <th className="py-2.5 px-3 text-right">% of Revenue</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 font-mono">
            <tr className="bg-emerald-50/40 font-bold text-emerald-950">
              <td className="py-2.5 px-3 font-sans">1. Operating Revenue</td>
              <td className="py-2.5 px-3 font-sans text-emerald-700">Gross Sales Inflow</td>
              <td className="py-2.5 px-3 text-right">{inr(data.gross_revenue)}</td>
              <td className="py-2.5 px-3 text-right">100.0%</td>
            </tr>
            <tr className="text-slate-600">
              <td className="py-2 px-3 pl-6 font-sans">↳ B2B Invoiced Revenue</td>
              <td className="py-2 px-3 font-sans text-slate-500">Corporate & Wholesaler Invoices</td>
              <td className="py-2 px-3 text-right">{inr(data.b2b_revenue)}</td>
              <td className="py-2 px-3 text-right">
                {data.gross_revenue > 0 ? ((data.b2b_revenue / data.gross_revenue) * 100).toFixed(1) : "0.0"}%
              </td>
            </tr>
            <tr className="text-slate-600">
              <td className="py-2 px-3 pl-6 font-sans">↳ Online Marketplace Revenue</td>
              <td className="py-2 px-3 font-sans text-slate-500">Net settlements payout</td>
              <td className="py-2 px-3 text-right">{inr(data.online_revenue)}</td>
              <td className="py-2 px-3 text-right">
                {data.gross_revenue > 0 ? ((data.online_revenue / data.gross_revenue) * 100).toFixed(1) : "0.0"}%
              </td>
            </tr>

            <tr className="bg-blue-50/40 font-bold text-blue-950">
              <td className="py-2.5 px-3 font-sans">2. Cost of Goods Sold (COGS)</td>
              <td className="py-2.5 px-3 font-sans text-blue-700">Direct Manufacturing Cost</td>
              <td className="py-2.5 px-3 text-right">{inr(data.total_cogs)}</td>
              <td className="py-2.5 px-3 text-right">
                {data.gross_revenue > 0 ? ((data.total_cogs / data.gross_revenue) * 100).toFixed(1) : "0.0"}%
              </td>
            </tr>
            <tr className="text-slate-600">
              <td className="py-2 px-3 pl-6 font-sans">↳ Raw Materials & Procurement</td>
              <td className="py-2 px-3 font-sans text-slate-500">Leather, soles, hardware, adhesives</td>
              <td className="py-2 px-3 text-right">{inr(data.material_cogs)}</td>
              <td className="py-2 px-3 text-right">
                {data.gross_revenue > 0 ? ((data.material_cogs / data.gross_revenue) * 100).toFixed(1) : "0.0"}%
              </td>
            </tr>
            <tr className="text-slate-600">
              <td className="py-2 px-3 pl-6 font-sans">↳ Direct Karigar Wages</td>
              <td className="py-2 px-3 font-sans text-slate-500">Piece-rate worker payments</td>
              <td className="py-2 px-3 text-right">{inr(data.labor_cogs)}</td>
              <td className="py-2 px-3 text-right">
                {data.gross_revenue > 0 ? ((data.labor_cogs / data.gross_revenue) * 100).toFixed(1) : "0.0"}%
              </td>
            </tr>

            <tr className="bg-amber-50/50 font-bold text-amber-950">
              <td className="py-2.5 px-3 font-sans">3. Gross Operating Profit</td>
              <td className="py-2.5 px-3 font-sans text-amber-700">Revenue minus Direct COGS</td>
              <td className="py-2.5 px-3 text-right">{inr(data.gross_profit)}</td>
              <td className="py-2.5 px-3 text-right">{data.gross_margin_pct}%</td>
            </tr>

            <tr className="bg-rose-50/40 font-bold text-rose-950">
              <td className="py-2.5 px-3 font-sans">4. Total Operating Expenses (OPEX)</td>
              <td className="py-2.5 px-3 font-sans text-rose-700">General Overhead & Administrative</td>
              <td className="py-2.5 px-3 text-right">{inr(data.total_opex)}</td>
              <td className="py-2.5 px-3 text-right">
                {data.gross_revenue > 0 ? ((data.total_opex / data.gross_revenue) * 100).toFixed(1) : "0.0"}%
              </td>
            </tr>

            <tr className="bg-slate-900 text-white font-bold text-sm">
              <td className="py-3 px-3 font-sans">5. Net Operating Profit</td>
              <td className="py-3 px-3 font-sans text-slate-300">Final Operating Margin</td>
              <td className="py-3 px-3 text-right text-[#16A34A]">{inr(data.net_profit)}</td>
              <td className="py-3 px-3 text-right text-[#16A34A]">{data.net_margin_pct}%</td>
            </tr>
          </tbody>
        </table>
      </Card>

      {/* Expense Categories Breakdown */}
      {expenseCategories.length > 0 && (
        <Card className="p-6">
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800 mb-4">
            Operating Expenses Breakdown by Category
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
            <div className="w-full h-64" data-testid="pnl-expense-categories-chart">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={expenseCategories}
                    dataKey="amount"
                    nameKey="category"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={({ category }) => category}
                  >
                    {expenseCategories.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={PALETTE[index % PALETTE.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => inr(value)} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-2">
              {expenseCategories.map((c, i) => (
                <div key={c.category} className="flex justify-between items-center text-xs p-2 rounded bg-slate-50">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: PALETTE[i % PALETTE.length] }}
                    />
                    <span className="font-bold text-slate-800">{c.category}</span>
                  </div>
                  <span className="font-mono font-bold text-slate-900">{inr(c.amount)}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      {/* Monthly Comparative P&L Table */}
      {monthlyPnl.length > 0 && (
        <Card className="p-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-3">
            Monthly Comparative Performance Schedule
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                  <th className="py-2.5 px-3">Month</th>
                  <th className="py-2.5 px-3 text-right">Revenue</th>
                  <th className="py-2.5 px-3 text-right">COGS</th>
                  <th className="py-2.5 px-3 text-right">Gross Profit</th>
                  <th className="py-2.5 px-3 text-right">OPEX</th>
                  <th className="py-2.5 px-3 text-right">Net Profit</th>
                  <th className="py-2.5 px-3 text-right">Net Margin</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 font-mono">
                {monthlyPnl.map((m) => (
                  <tr key={m.month} className="hover:bg-slate-50 transition-colors">
                    <td className="py-2 px-3 font-bold text-slate-900">{m.month}</td>
                    <td className="py-2 px-3 text-right text-emerald-700">{inr(m.revenue)}</td>
                    <td className="py-2 px-3 text-right text-slate-600">{inr(m.cogs)}</td>
                    <td className="py-2 px-3 text-right text-slate-900 font-bold">{inr(m.gross_profit)}</td>
                    <td className="py-2 px-3 text-right text-rose-700">{inr(m.opex)}</td>
                    <td className="py-2 px-3 text-right font-bold text-emerald-800">{inr(m.net_profit)}</td>
                    <td className="py-2 px-3 text-right text-slate-500">{m.net_margin_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
