import { useEffect, useMemo, useState, useCallback } from "react";
import { http, inr, num } from "../lib/api";
import {
  PageHeader,
  Card,
  StatTile,
  BtnPrimary,
  BtnSecondary,
  Badge,
} from "../components/ui-kit";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  TrendingUp,
  RefreshCw,
  Download,
  Filter,
  DollarSign,
  Briefcase,
  Layers,
  Calendar,
  CheckCircle,
  Clock,
  ChevronRight,
  X,
  Search,
  ArrowUpDown,
  PieChart as PieIcon,
  HelpCircle,
} from "lucide-react";

const isoToday = () => new Date().toISOString().slice(0, 10);
const isoDaysAgo = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

export default function B2BProfitability() {
  const [activeTab, setActiveTab] = useState("by_client");

  // Filters
  const [dateFrom, setDateFrom] = useState(isoDaysAgo(30));
  const [dateTo, setDateTo] = useState(isoToday());
  const [clientId, setClientId] = useState("");
  const [styleId, setStyleId] = useState("");

  // Lists for Dropdowns
  const [clientsList, setClientsList] = useState([]);
  const [stylesList, setStylesList] = useState([]);

  // Data & Loading States
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [profitData, setProfitData] = useState(null);

  // Sorting State for Tables
  const [sortField, setSortField] = useState("total_profit");
  const [sortOrder, setSortOrder] = useState("desc");
  const [searchQuery, setSearchQuery] = useState("");

  // Drill-down Modal State
  const [drilldownItem, setDrilldownItem] = useState(null); // { type: 'client'|'style', title: string, lines: [] }

  // Load Dropdown Options
  useEffect(() => {
    http.get("/clients")
      .then((r) => setClientsList(r.data || []))
      .catch(() => setClientsList([]));

    http.get("/styles")
      .then((r) => setStylesList(r.data || []))
      .catch(() => setStylesList([]));
  }, []);

  // Fetch B2B Profitability Data
  const loadProfitability = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = {
        date_from: dateFrom,
        date_to: dateTo,
      };
      if (clientId) params.client_id = clientId;
      if (styleId) params.style_id = styleId;

      const { data } = await http.get("/b2b-profitability", { params });
      setProfitData(data);
    } catch (err) {
      console.error("Failed to load B2B profitability data:", err);
      setError(err?.response?.data?.detail || "Failed to load B2B profitability report.");
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, clientId, styleId]);

  useEffect(() => {
    loadProfitability();
  }, [loadProfitability]);

  // Handle Sort Toggle
  const handleSort = (field) => {
    if (sortField === field) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  const summary = profitData?.summary || {};
  const byClient = profitData?.by_client || [];
  const byStyle = profitData?.by_style || [];
  const byMonth = profitData?.by_month || [];
  const allLines = profitData?.lines || [];

  // Filtered & Sorted Clients
  const sortedClients = useMemo(() => {
    let list = [...byClient];
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      list = list.filter((c) => (c.client_name || "").toLowerCase().includes(q));
    }
    list.sort((a, b) => {
      let va = a[sortField] ?? 0;
      let vb = b[sortField] ?? 0;
      if (typeof va === "string") {
        return sortOrder === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      return sortOrder === "asc" ? va - vb : vb - va;
    });
    return list;
  }, [byClient, searchQuery, sortField, sortOrder]);

  // Filtered & Sorted Styles
  const sortedStyles = useMemo(() => {
    let list = [...byStyle];
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (s) =>
          (s.style_code || "").toLowerCase().includes(q) ||
          (s.style_name || "").toLowerCase().includes(q)
      );
    }
    list.sort((a, b) => {
      let va = a[sortField] ?? 0;
      let vb = b[sortField] ?? 0;
      if (typeof va === "string") {
        return sortOrder === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      return sortOrder === "asc" ? va - vb : vb - va;
    });
    return list;
  }, [byStyle, searchQuery, sortField, sortOrder]);

  // Export CSV Handler
  const exportCSV = () => {
    if (!allLines.length) return;
    const headers = [
      "PO Number",
      "Invoice Number",
      "Invoice Date",
      "Client Name",
      "Style Code",
      "Style Name",
      "Quantity (Pairs)",
      "Unit Price (₹)",
      "BOM Cost (₹)",
      "Labor Cost (₹)",
      "Labor Source",
      "Packing Cost (₹)",
      "Overhead Cost (₹)",
      "Total Unit Cost (₹)",
      "Line Revenue (₹)",
      "Line Cost (₹)",
      "Line Profit (₹)",
      "Margin %",
    ];

    const rows = allLines.map((l) => [
      l.po_number || "",
      l.invoice_no || "",
      l.invoice_date || "",
      `"${l.client_name || ""}"`,
      `"${l.style_code || ""}"`,
      `"${l.style_name || ""}"`,
      l.quantity || 0,
      l.unit_price || 0,
      l.bom_cost || 0,
      l.labor_cost || 0,
      l.labor_source || "estimated",
      l.packing_cost || 0,
      l.overhead_cost || 0,
      l.unit_total_cost || 0,
      l.line_revenue || 0,
      l.line_cost || 0,
      l.line_profit || 0,
      l.profit_pct || 0,
    ]);

    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `b2b_profitability_${dateFrom}_to_${dateTo}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        title="B2B Profitability Analytics"
        subtitle="Realized PO & Invoice Margin Analysis"
        action={
          <div className="flex items-center gap-2">
            <BtnSecondary onClick={exportCSV} disabled={!allLines.length}>
              <Download className="w-4 h-4 mr-1.5 inline-block" />
              Export CSV
            </BtnSecondary>
            <BtnPrimary onClick={loadProfitability} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 inline-block ${loading ? "animate-spin" : ""}`} />
              Refresh
            </BtnPrimary>
          </div>
        }
      />

      {/* Top Filter Bar */}
      <Card className="p-4 sm:p-6 bg-white shadow-sm border-slate-200">
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 flex-1">
            <div>
              <label className="text-[11px] font-bold uppercase tracking-wider text-slate-600 block mb-1">
                From Date
              </label>
              <input
                type="date"
                className="w-full border-2 border-slate-300 bg-slate-50 px-3 py-2 text-sm font-mono focus:border-[#2563EB] focus:outline-none"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>
            <div>
              <label className="text-[11px] font-bold uppercase tracking-wider text-slate-600 block mb-1">
                To Date
              </label>
              <input
                type="date"
                className="w-full border-2 border-slate-300 bg-slate-50 px-3 py-2 text-sm font-mono focus:border-[#2563EB] focus:outline-none"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>
            <div>
              <label className="text-[11px] font-bold uppercase tracking-wider text-slate-600 block mb-1">
                Client Filter
              </label>
              <select
                className="w-full border-2 border-slate-300 bg-slate-50 px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
              >
                <option value="">All Clients</option>
                {clientsList.map((c) => (
                  <option key={c._id || c.id || c.name} value={c._id || c.id || c.name}>
                    {c.name || c.client_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[11px] font-bold uppercase tracking-wider text-slate-600 block mb-1">
                Style Filter
              </label>
              <select
                className="w-full border-2 border-slate-300 bg-slate-50 px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none font-mono"
                value={styleId}
                onChange={(e) => setStyleId(e.target.value)}
              >
                <option value="">All Styles</option>
                {stylesList.map((s) => (
                  <option key={s._id || s.id || s.code} value={s.code || s._id}>
                    {s.code} - {s.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-2 lg:pt-0">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Preset:</span>
            <button
              onClick={() => {
                setDateFrom(isoDaysAgo(30));
                setDateTo(isoToday());
              }}
              className="px-2.5 py-1 text-xs font-bold border border-slate-300 bg-slate-100 hover:bg-slate-200"
            >
              30 Days
            </button>
            <button
              onClick={() => {
                setDateFrom(isoDaysAgo(90));
                setDateTo(isoToday());
              }}
              className="px-2.5 py-1 text-xs font-bold border border-slate-300 bg-slate-100 hover:bg-slate-200"
            >
              90 Days
            </button>
            <button
              onClick={() => {
                setDateFrom(`${new Date().getFullYear()}-01-01`);
                setDateTo(isoToday());
              }}
              className="px-2.5 py-1 text-xs font-bold border border-slate-300 bg-slate-100 hover:bg-slate-200"
            >
              YTD
            </button>
          </div>
        </div>
      </Card>

      {error && (
        <Card className="p-4 bg-red-50 border-red-300 text-red-700 text-sm font-medium">
          ⚠️ {error}
        </Card>
      )}

      {/* Summary KPI Tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatTile
          label="Total Realized Revenue"
          value={inr(summary.total_revenue || 0)}
          sub={`${num(summary.total_pairs || 0)} pairs across ${summary.total_lines_count || 0} lines`}
          accent="#2563EB"
        />
        <StatTile
          label="Total Production Cost"
          value={inr(summary.total_cost || 0)}
          sub="BOM + Labor + Packing + Overhead"
          accent="#64748B"
        />
        <StatTile
          label="Total Net Profit"
          value={inr(summary.total_profit || 0)}
          sub={`${summary.profit_pct || 0}% Realized Margin`}
          accent={summary.total_profit >= 0 ? "#10B981" : "#EF4444"}
        />
        <StatTile
          label="Dispatched Lines"
          value={num(summary.total_lines_count || 0)}
          sub={`${summary.confirmed_lines_count || 0} Confirmed | ${summary.estimated_lines_count || 0} Est.`}
          accent="#8B5CF6"
        />
      </div>

      {/* Labor Cost Source Distinction Banner */}
      <Card className="p-5 border-l-4 border-l-emerald-600 bg-gradient-to-r from-slate-900 to-slate-800 text-white shadow-md">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-emerald-400" />
              <h3 className="font-extrabold text-base tracking-wide uppercase">
                Labor Costing Breakdown (Confirmed vs Estimated)
              </h3>
            </div>
            <p className="text-xs text-slate-300 max-w-3xl">
              Realized profit distinguishes actual worker rates assigned on the factory floor from pre-production estimate rates.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-4 bg-slate-900/80 p-3 rounded border border-slate-700">
            <div className="text-left border-r border-slate-700 pr-4">
              <div className="text-[10px] uppercase font-bold text-emerald-400 flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
                Profit (Confirmed Actual Labor)
              </div>
              <div className="text-lg font-bold font-mono text-white mt-0.5">
                {inr(summary.confirmed_profit || 0)}
              </div>
              <div className="text-[11px] text-slate-400">
                {summary.confirmed_lines_count || 0} invoice lines
              </div>
            </div>

            <div className="text-left">
              <div className="text-[10px] uppercase font-bold text-amber-400 flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
                Profit (Est., Pending Production Data)
              </div>
              <div className="text-lg font-bold font-mono text-white mt-0.5">
                {inr(summary.estimated_profit || 0)}
              </div>
              <div className="text-[11px] text-slate-400">
                {summary.estimated_lines_count || 0} invoice lines
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Tabs Bar */}
      <div className="border-b-2 border-slate-200 flex items-center gap-2 overflow-x-auto bg-white px-2">
        <button
          onClick={() => {
            setActiveTab("by_client");
            setSortField("total_profit");
          }}
          className={`px-5 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-colors flex items-center gap-2 whitespace-nowrap ${
            activeTab === "by_client"
              ? "border-[#0F172A] text-[#0F172A] bg-slate-50"
              : "border-transparent text-slate-500 hover:text-slate-900"
          }`}
        >
          <Briefcase className="w-4 h-4" />
          By Client ({byClient.length})
        </button>

        <button
          onClick={() => {
            setActiveTab("by_style");
            setSortField("total_profit");
          }}
          className={`px-5 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-colors flex items-center gap-2 whitespace-nowrap ${
            activeTab === "by_style"
              ? "border-[#0F172A] text-[#0F172A] bg-slate-50"
              : "border-transparent text-slate-500 hover:text-slate-900"
          }`}
        >
          <Layers className="w-4 h-4" />
          By Style ({byStyle.length})
        </button>

        <button
          onClick={() => setActiveTab("by_month")}
          className={`px-5 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-colors flex items-center gap-2 whitespace-nowrap ${
            activeTab === "by_month"
              ? "border-[#0F172A] text-[#0F172A] bg-slate-50"
              : "border-transparent text-slate-500 hover:text-slate-900"
          }`}
        >
          <TrendingUp className="w-4 h-4" />
          Monthly Trends
        </button>

        <button
          onClick={() => setActiveTab("all_lines")}
          className={`px-5 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-colors flex items-center gap-2 whitespace-nowrap ${
            activeTab === "all_lines"
              ? "border-[#0F172A] text-[#0F172A] bg-slate-50"
              : "border-transparent text-slate-500 hover:text-slate-900"
          }`}
        >
          <Calendar className="w-4 h-4" />
          All Line Items ({allLines.length})
        </button>
      </div>

      {/* Tab 1: By Client */}
      {activeTab === "by_client" && (
        <Card className="p-4 sm:p-6 bg-white space-y-4">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <h3 className="font-extrabold text-lg text-slate-900 uppercase tracking-tight">
              B2B Client Profitability Ranking
            </h3>
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search client name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full border-2 border-slate-300 pl-9 pr-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
              />
            </div>
          </div>

          <div className="overflow-x-auto border border-slate-200">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 uppercase tracking-wider text-slate-600 font-bold border-b border-slate-200">
                <tr>
                  <th className="py-3 px-4">Client Name</th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:bg-slate-200" onClick={() => handleSort("total_pairs")}>
                    Pairs <ArrowUpDown className="w-3 h-3 inline ml-0.5" />
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:bg-slate-200" onClick={() => handleSort("total_revenue")}>
                    Revenue <ArrowUpDown className="w-3 h-3 inline ml-0.5" />
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:bg-slate-200" onClick={() => handleSort("total_cost")}>
                    Production Cost <ArrowUpDown className="w-3 h-3 inline ml-0.5" />
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:bg-slate-200" onClick={() => handleSort("total_profit")}>
                    Net Profit <ArrowUpDown className="w-3 h-3 inline ml-0.5" />
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:bg-slate-200" onClick={() => handleSort("profit_pct")}>
                    Margin % <ArrowUpDown className="w-3 h-3 inline ml-0.5" />
                  </th>
                  <th className="py-3 px-4 text-center">Labor Status</th>
                  <th className="py-3 px-4 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 font-mono">
                {sortedClients.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-slate-400 font-sans">
                      No client profitability data found for selected period.
                    </td>
                  </tr>
                ) : (
                  sortedClients.map((c, i) => (
                    <tr key={c.client_name || i} className="hover:bg-slate-50 transition-colors">
                      <td className="py-3 px-4 font-sans font-bold text-slate-900">{c.client_name}</td>
                      <td className="py-3 px-4 text-right text-slate-700">{num(c.total_pairs)}</td>
                      <td className="py-3 px-4 text-right font-bold text-slate-900">{inr(c.total_revenue)}</td>
                      <td className="py-3 px-4 text-right text-slate-600">{inr(c.total_cost)}</td>
                      <td className={`py-3 px-4 text-right font-bold ${c.total_profit >= 0 ? "text-emerald-700" : "text-red-600"}`}>
                        {inr(c.total_profit)}
                      </td>
                      <td className="py-3 px-4 text-right font-bold">
                        <span
                          className={`px-2 py-0.5 rounded text-[11px] ${
                            c.profit_pct >= 20
                              ? "bg-emerald-100 text-emerald-800"
                              : c.profit_pct >= 10
                              ? "bg-blue-100 text-blue-800"
                              : c.profit_pct >= 0
                              ? "bg-amber-100 text-amber-800"
                              : "bg-red-100 text-red-800"
                          }`}
                        >
                          {c.profit_pct}%
                        </span>
                      </td>
                      <td className="py-3 px-4 text-center font-sans">
                        <div className="flex items-center justify-center gap-1">
                          {c.confirmed_lines_count > 0 && (
                            <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-800 text-[10px] font-bold rounded">
                              ✓ {c.confirmed_lines_count} Confirmed
                            </span>
                          )}
                          {c.estimated_lines_count > 0 && (
                            <span className="px-1.5 py-0.5 bg-amber-100 text-amber-800 text-[10px] font-bold rounded">
                              ⚡ {c.estimated_lines_count} Est.
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-center">
                        <BtnSecondary
                          className="!py-1 !px-2.5 text-[10px]"
                          onClick={() =>
                            setDrilldownItem({
                              type: "client",
                              title: `Client Breakdown: ${c.client_name}`,
                              lines: c.lines || [],
                            })
                          }
                        >
                          Drill-down →
                        </BtnSecondary>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Tab 2: By Style */}
      {activeTab === "by_style" && (
        <Card className="p-4 sm:p-6 bg-white space-y-4">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              <h3 className="font-extrabold text-lg text-slate-900 uppercase tracking-tight">
                Style Profitability Ranking
              </h3>
              <p className="text-xs text-slate-500">
                Surfaces which footwear styles generate the highest profit margins vs high revenue only.
              </p>
            </div>
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search style code or name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full border-2 border-slate-300 pl-9 pr-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
              />
            </div>
          </div>

          <div className="overflow-x-auto border border-slate-200">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 uppercase tracking-wider text-slate-600 font-bold border-b border-slate-200">
                <tr>
                  <th className="py-3 px-4">Style Code</th>
                  <th className="py-3 px-4">Style Description</th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:bg-slate-200" onClick={() => handleSort("total_pairs")}>
                    Pairs <ArrowUpDown className="w-3 h-3 inline ml-0.5" />
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:bg-slate-200" onClick={() => handleSort("total_revenue")}>
                    Revenue <ArrowUpDown className="w-3 h-3 inline ml-0.5" />
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:bg-slate-200" onClick={() => handleSort("total_cost")}>
                    Unit Cost (Avg) <ArrowUpDown className="w-3 h-3 inline ml-0.5" />
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:bg-slate-200" onClick={() => handleSort("total_profit")}>
                    Net Profit <ArrowUpDown className="w-3 h-3 inline ml-0.5" />
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:bg-slate-200" onClick={() => handleSort("profit_pct")}>
                    Margin % <ArrowUpDown className="w-3 h-3 inline ml-0.5" />
                  </th>
                  <th className="py-3 px-4 text-center">Labor Status</th>
                  <th className="py-3 px-4 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 font-mono">
                {sortedStyles.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-8 text-center text-slate-400 font-sans">
                      No style profitability data found for selected period.
                    </td>
                  </tr>
                ) : (
                  sortedStyles.map((s, i) => {
                    const avgUnitCost = s.total_pairs > 0 ? s.total_cost / s.total_pairs : 0;
                    return (
                      <tr key={s.style_code || i} className="hover:bg-slate-50 transition-colors">
                        <td className="py-3 px-4 font-bold text-[#0F172A]">{s.style_code}</td>
                        <td className="py-3 px-4 font-sans font-medium text-slate-700">{s.style_name}</td>
                        <td className="py-3 px-4 text-right text-slate-700">{num(s.total_pairs)}</td>
                        <td className="py-3 px-4 text-right font-bold text-slate-900">{inr(s.total_revenue)}</td>
                        <td className="py-3 px-4 text-right text-slate-600">{inr(avgUnitCost)}</td>
                        <td className={`py-3 px-4 text-right font-bold ${s.total_profit >= 0 ? "text-emerald-700" : "text-red-600"}`}>
                          {inr(s.total_profit)}
                        </td>
                        <td className="py-3 px-4 text-right font-bold">
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] ${
                              s.profit_pct >= 25
                                ? "bg-emerald-100 text-emerald-800"
                                : s.profit_pct >= 15
                                ? "bg-blue-100 text-blue-800"
                                : s.profit_pct >= 0
                                ? "bg-amber-100 text-amber-800"
                                : "bg-red-100 text-red-800"
                            }`}
                          >
                            {s.profit_pct}%
                          </span>
                        </td>
                        <td className="py-3 px-4 text-center font-sans">
                          <div className="flex items-center justify-center gap-1">
                            {s.confirmed_lines_count > 0 && (
                              <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-800 text-[10px] font-bold rounded">
                                ✓ {s.confirmed_lines_count} Confirmed
                              </span>
                            )}
                            {s.estimated_lines_count > 0 && (
                              <span className="px-1.5 py-0.5 bg-amber-100 text-amber-800 text-[10px] font-bold rounded">
                                ⚡ {s.estimated_lines_count} Est.
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-center">
                          <BtnSecondary
                            className="!py-1 !px-2.5 text-[10px]"
                            onClick={() =>
                              setDrilldownItem({
                                type: "style",
                                title: `Style Lines: ${s.style_code} (${s.style_name})`,
                                lines: s.lines || [],
                              })
                            }
                          >
                            Drill-down →
                          </BtnSecondary>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Tab 3: Monthly Trends */}
      {activeTab === "by_month" && (
        <div className="space-y-6">
          <Card className="p-4 sm:p-6 bg-white space-y-4">
            <h3 className="font-extrabold text-lg text-slate-900 uppercase tracking-tight">
              Monthly Revenue vs Cost & Profit Trend
            </h3>

            {byMonth.length === 0 ? (
              <div className="py-12 text-center text-slate-400 font-sans">
                No monthly trend data available.
              </div>
            ) : (
              <div className="h-80 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={byMonth} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="month font-mono" stroke="#64748b" />
                    <YAxis stroke="#64748b" />
                    <Tooltip
                      formatter={(val) => inr(val)}
                      contentStyle={{ backgroundColor: "#0f172a", borderRadius: "4px", color: "#fff" }}
                    />
                    <Legend />
                    <Bar dataKey="total_revenue" name="Total Revenue" fill="#2563EB" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="total_cost" name="Production Cost" fill="#64748B" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="total_profit" name="Net Profit" fill="#10B981" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>

          <Card className="p-4 sm:p-6 bg-white space-y-4">
            <h4 className="font-bold text-sm text-slate-700 uppercase">Monthly Performance Breakdown</h4>
            <div className="overflow-x-auto border border-slate-200">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-100 uppercase tracking-wider text-slate-600 font-bold border-b border-slate-200">
                  <tr>
                    <th className="py-3 px-4">Month</th>
                    <th className="py-3 px-4 text-right">Pairs</th>
                    <th className="py-3 px-4 text-right">Total Revenue</th>
                    <th className="py-3 px-4 text-right">Total Cost</th>
                    <th className="py-3 px-4 text-right">Confirmed Profit</th>
                    <th className="py-3 px-4 text-right">Estimated Profit</th>
                    <th className="py-3 px-4 text-right">Total Profit</th>
                    <th className="py-3 px-4 text-right">Margin %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {byMonth.map((m) => (
                    <tr key={m.month} className="hover:bg-slate-50">
                      <td className="py-3 px-4 font-bold text-slate-900">{m.month}</td>
                      <td className="py-3 px-4 text-right text-slate-700">{num(m.total_pairs)}</td>
                      <td className="py-3 px-4 text-right font-bold text-slate-900">{inr(m.total_revenue)}</td>
                      <td className="py-3 px-4 text-right text-slate-600">{inr(m.total_cost)}</td>
                      <td className="py-3 px-4 text-right text-emerald-700 font-bold">{inr(m.confirmed_profit)}</td>
                      <td className="py-3 px-4 text-right text-amber-700 font-bold">{inr(m.estimated_profit)}</td>
                      <td className={`py-3 px-4 text-right font-bold ${m.total_profit >= 0 ? "text-emerald-700" : "text-red-600"}`}>
                        {inr(m.total_profit)}
                      </td>
                      <td className="py-3 px-4 text-right font-bold">{m.profit_pct}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* Tab 4: All Lines / Detailed Table */}
      {activeTab === "all_lines" && (
        <Card className="p-4 sm:p-6 bg-white space-y-4">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <h3 className="font-extrabold text-lg text-slate-900 uppercase tracking-tight">
              Individual Line Item Profitability Log
            </h3>
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search PO, style, or client..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full border-2 border-slate-300 pl-9 pr-3 py-1.5 text-xs focus:border-[#2563EB] focus:outline-none"
              />
            </div>
          </div>

          <LineItemsTable lines={allLines.filter((l) => {
            if (!searchQuery) return true;
            const q = searchQuery.toLowerCase();
            return (
              (l.po_number || "").toLowerCase().includes(q) ||
              (l.invoice_no || "").toLowerCase().includes(q) ||
              (l.client_name || "").toLowerCase().includes(q) ||
              (l.style_code || "").toLowerCase().includes(q)
            );
          })} />
        </Card>
      )}

      {/* Drill-down Modal / Drawer */}
      {drilldownItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs">
          <div className="bg-white border-2 border-slate-900 max-w-5xl w-full max-h-[90vh] flex flex-col shadow-2xl">
            <div className="p-4 sm:p-6 border-b-2 border-slate-200 flex items-center justify-between bg-slate-900 text-white">
              <div>
                <span className="text-[10px] uppercase font-bold tracking-wider text-emerald-400 block mb-1">
                  B2B Line Item Drill-down
                </span>
                <h2 className="text-lg sm:text-xl font-black">{drilldownItem.title}</h2>
              </div>
              <button
                onClick={() => setDrilldownItem(null)}
                className="p-1 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            <div className="p-4 sm:p-6 overflow-y-auto space-y-4">
              <LineItemsTable lines={drilldownItem.lines} />
            </div>

            <div className="p-4 border-t-2 border-slate-200 bg-slate-50 flex justify-end">
              <BtnSecondary onClick={() => setDrilldownItem(null)}>
                Close Window
              </BtnSecondary>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Reusable Detailed Line Items Table
function LineItemsTable({ lines }) {
  if (!lines || lines.length === 0) {
    return (
      <div className="py-12 text-center text-slate-400 font-sans border border-slate-200">
        No line items match criteria.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto border border-slate-200">
      <table className="w-full text-left text-xs font-mono">
        <thead className="bg-slate-100 uppercase tracking-wider text-slate-600 font-bold border-b border-slate-200">
          <tr>
            <th className="py-3 px-3">Date</th>
            <th className="py-3 px-3">PO / Invoice #</th>
            <th className="py-3 px-3">Client</th>
            <th className="py-3 px-3">Style Code</th>
            <th className="py-3 px-3 text-right">Pairs</th>
            <th className="py-3 px-3 text-right">Unit Price</th>
            <th className="py-3 px-3 text-right">BOM Cost</th>
            <th className="py-3 px-3 text-right">Labor Cost</th>
            <th className="py-3 px-3 text-right">Packing</th>
            <th className="py-3 px-3 text-right">Total Unit Cost</th>
            <th className="py-3 px-3 text-right">Line Revenue</th>
            <th className="py-3 px-3 text-right">Line Profit</th>
            <th className="py-3 px-3 text-right">Margin %</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200">
          {lines.map((l, idx) => (
            <tr key={l.id || idx} className="hover:bg-slate-50 transition-colors">
              <td className="py-3 px-3 text-slate-600 whitespace-nowrap">{l.invoice_date}</td>
              <td className="py-3 px-3 font-bold text-slate-900 whitespace-nowrap">
                {l.po_number}
                {l.invoice_no && <span className="text-[10px] text-slate-500 block font-normal">{l.invoice_no}</span>}
              </td>
              <td className="py-3 px-3 font-sans font-medium text-slate-800">{l.client_name}</td>
              <td className="py-3 px-3 font-bold text-slate-900">{l.style_code}</td>
              <td className="py-3 px-3 text-right text-slate-700 font-bold">{num(l.quantity)}</td>
              <td className="py-3 px-3 text-right font-bold text-slate-900">{inr(l.unit_price)}</td>
              <td className="py-3 px-3 text-right text-slate-600">{inr(l.bom_cost)}</td>
              <td className="py-3 px-3 text-right whitespace-nowrap">
                <span className="font-bold text-slate-800">{inr(l.labor_cost)}</span>
                <span
                  className={`block text-[9px] font-sans font-bold uppercase tracking-wider ${
                    l.is_estimated ? "text-amber-600" : "text-emerald-600"
                  }`}
                >
                  {l.is_estimated ? "⚡ Estimated" : "✓ Actual"}
                </span>
              </td>
              <td className="py-3 px-3 text-right text-slate-600">{inr(l.packing_cost)}</td>
              <td className="py-3 px-3 text-right font-bold text-slate-800">{inr(l.unit_total_cost)}</td>
              <td className="py-3 px-3 text-right font-bold text-slate-900">{inr(l.line_revenue)}</td>
              <td className={`py-3 px-3 text-right font-bold ${l.line_profit >= 0 ? "text-emerald-700" : "text-red-600"}`}>
                {inr(l.line_profit)}
              </td>
              <td className="py-3 px-3 text-right font-bold">
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] ${
                    l.profit_pct >= 20
                      ? "bg-emerald-100 text-emerald-800"
                      : l.profit_pct >= 0
                      ? "bg-amber-100 text-amber-800"
                      : "bg-red-100 text-red-800"
                  }`}
                >
                  {l.profit_pct}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
