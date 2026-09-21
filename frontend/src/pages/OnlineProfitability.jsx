import { useEffect, useState, useCallback } from "react";
import { http, inr, num } from "../lib/api";
import {
  PageHeader,
  Card,
  StatTile,
  BtnPrimary,
  BtnSecondary,
} from "../components/ui-kit";
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
} from "recharts";
import {
  Download,
  RefreshCw,
  TrendingUp,
  ShoppingBag,
  Info,
  Plus,
  X,
  Check,
  ScrollText,
  AlertTriangle,
  CheckCircle,
  Clock,
  ShieldAlert,
} from "lucide-react";
import MonthlyPnLReconciliation from "../components/MonthlyPnLReconciliation";
import ReturnsIntelligenceTab from "../components/ReturnsIntelligenceTab";

const isoToday = () => new Date().toISOString().slice(0, 10);
const isoDaysAgo = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

export default function OnlineProfitability() {
  // Navigation tabs: 'overview' (Profitability Engine) | 'monthly_pnl' (Monthly PnL Reconciliation)
  const [activeTab, setActiveTab] = useState("overview");

  // Filters & State
  const [platform, setPlatform] = useState("myntra");
  const [dateFrom, setDateFrom] = useState(isoDaysAgo(30));
  const [dateTo, setDateTo] = useState(isoToday());
  const [styleId, setStyleId] = useState("");
  const [styles, setStyles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Profitability report state
  const [profitData, setProfitData] = useState(null);

  // Cost Snapshot Modal State
  const [snapshotModalOpen, setSnapshotModalOpen] = useState(false);
  const [snapshotForm, setSnapshotForm] = useState({
    style_code: "",
    effective_date: isoToday(),
    total_cost: "",
    material_cost: "",
    labor_cost: "",
    notes: "",
  });

  // Load styles dropdown
  useEffect(() => {
    http.get("/styles")
      .then((r) => setStyles(r.data || []))
      .catch(() => setStyles([]));
  }, []);

  // Load Phase 4 Online Profitability Report Data
  const loadProfitability = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await http.get("/reports/online-profitability", {
        params: {
          platform: platform || undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          style_id: styleId || undefined,
        },
      });
      setProfitData(data);
    } catch (err) {
      console.error("Failed to load online profitability:", err);
      setError("Failed to load online profitability report.");
    } finally {
      setLoading(false);
    }
  }, [platform, dateFrom, dateTo, styleId]);

  useEffect(() => {
    loadProfitability();
  }, [loadProfitability]);

  // Excel Export Handler
  const handleExportExcel = async () => {
    try {
      const res = await http.get("/reports/online-profitability/export", {
        params: {
          platform: platform || undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          style_id: styleId || undefined,
        },
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `Online_Profitability_${platform || "all"}_${dateFrom}_to_${dateTo}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      alert("Failed to export Excel report: " + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleCreateSnapshot = async (e) => {
    e.preventDefault();
    if (!snapshotForm.style_code || !snapshotForm.total_cost) {
      alert("Please enter style code and total unit cost.");
      return;
    }
    try {
      await http.post("/online-reconciliation/cost-snapshots", {
        style_code: snapshotForm.style_code.trim(),
        effective_date: snapshotForm.effective_date,
        total_cost: parseFloat(snapshotForm.total_cost),
        material_cost: parseFloat(snapshotForm.material_cost || 0),
        labor_cost: parseFloat(snapshotForm.labor_cost || 0),
        notes: snapshotForm.notes,
      });
      setSnapshotModalOpen(false);
      loadProfitability();
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to create cost snapshot");
    }
  };

  return (
    <div>
      <PageHeader
        title="Online Commerce Profitability & Reconciliation"
        subtitle="Multi-Report Reconciliation Engine, Actual COGS Snapshot Matching & Settlement Ledger"
        testId="online-profitability-header"
      />

      <div className="p-2 sm:p-4 lg:p-8 space-y-6">
        {/* ── TOP NAV TAB BAR ────────────────────────────────────────────────── */}
        <div className="bg-white p-2 border border-slate-200 shadow-sm flex flex-wrap gap-2 items-center justify-between">
          <div className="flex flex-wrap gap-1">
            <button
              onClick={() => setActiveTab("overview")}
              className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors flex items-center gap-2 ${activeTab === "overview"
                  ? "bg-[#0F172A] text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              data-testid="tab-overview"
            >
              <TrendingUp className="w-3.5 h-3.5 text-[#C27842]" /> Profitability Engine
            </button>
            <button
              onClick={() => setActiveTab("monthly_pnl")}
              className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors flex items-center gap-2 ${activeTab === "monthly_pnl"
                  ? "bg-[#0F172A] text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              data-testid="tab-monthly-pnl"
            >
              <ScrollText className="w-3.5 h-3.5 text-indigo-400" /> Monthly PnL Reconciliation
            </button>
            <button
              onClick={() => setActiveTab("returns_engine")}
              className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors flex items-center gap-2 ${activeTab === "returns_engine"
                  ? "bg-[#0F172A] text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              data-testid="tab-returns-engine"
            >
              <ShieldAlert className="w-3.5 h-3.5 text-rose-500" /> Return Reduction Engine
            </button>
          </div>

          <div className="flex items-center gap-2">
            <BtnSecondary onClick={() => setSnapshotModalOpen(true)} className="flex items-center gap-1.5 text-xs">
              <Plus className="w-3.5 h-3.5 text-[#C27842]" /> Cost Snapshot
            </BtnSecondary>
            <BtnSecondary
              onClick={loadProfitability}
              disabled={loading}
              className="flex items-center gap-1.5 text-xs"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </BtnSecondary>
            {activeTab === "overview" && (
              <BtnPrimary onClick={handleExportExcel} className="flex items-center gap-1.5 text-xs">
                <Download className="w-3.5 h-3.5" /> Export Excel
              </BtnPrimary>
            )}
          </div>
        </div>

        {/* ── FILTER TOOLBAR FOR OVERVIEW TAB ────────────────────────────────── */}
        {activeTab === "overview" && (
          <Card className="p-4 bg-slate-50 border border-slate-200">
            <div className="flex flex-wrap gap-4 items-end justify-between">
              <div className="flex flex-wrap gap-4 items-end">
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Platform</label>
                  <select
                    value={platform}
                    onChange={(e) => setPlatform(e.target.value)}
                    className="border border-slate-300 rounded px-2.5 py-1.5 text-xs font-semibold bg-white text-slate-800"
                    data-testid="filter-platform"
                  >
                    <option value="">All Platforms</option>
                    <option value="myntra">Myntra</option>
                    <option value="ajio">Ajio</option>
                    <option value="flipkart">Flipkart</option>
                    <option value="amazon">Amazon</option>
                    <option value="nykaa">Nykaa</option>
                    <option value="tatacliq">Tata CLiQ</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">From Date</label>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    className="border border-slate-300 rounded px-2.5 py-1.5 text-xs font-semibold bg-white text-slate-800"
                    data-testid="filter-date-from"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">To Date</label>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    className="border border-slate-300 rounded px-2.5 py-1.5 text-xs font-semibold bg-white text-slate-800"
                    data-testid="filter-date-to"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Style Filter</label>
                  <select
                    value={styleId}
                    onChange={(e) => setStyleId(e.target.value)}
                    className="border border-slate-300 rounded px-2.5 py-1.5 text-xs font-semibold bg-white text-slate-800 max-w-xs"
                    data-testid="filter-style"
                  >
                    <option value="">All Styles</option>
                    {styles.map((s) => (
                      <option key={s._id} value={s._id}>
                        {s.code} - {s.name || s.category}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <BtnSecondary onClick={loadProfitability} disabled={loading} className="text-xs">
                Apply Filters
              </BtnSecondary>
            </div>
          </Card>
        )}

        {/* ── TAB 0: PROFITABILITY ENGINE (PHASE 4 COST VS REVENUE RECONCILIATION) ── */}
        {activeTab === "overview" && profitData && (
          <div className="space-y-6" data-testid="profitability-engine-overview">
            {/* Status & Signal Banner */}
            <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 p-6 text-white rounded-sm border-2 border-slate-700 shadow-md">
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-black text-base uppercase tracking-wider text-white">
                      Online Commerce Profitability Reconciliation
                    </h3>
                  </div>
                  <p className="text-xs text-slate-300 mt-1">
                    Revenue Source: <strong className="text-amber-300">{profitData.revenue_source_used}</strong>
                  </p>
                </div>
                <div className="flex flex-wrap gap-2 items-center" data-testid="top-level-status-badges">
                  {/* Distinct Revenue Status Badge */}
                  {profitData.is_estimated ? (
                    <span className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-bold rounded bg-amber-500/20 text-amber-300 border border-amber-500/40" title="Revenue incorporates un-reconciled order item fallback estimates" data-testid="badge-top-revenue-estimated">
                      <Clock className="w-3.5 h-3.5 text-amber-400" /> Revenue: Estimated
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-bold rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" title="Revenue 100% confirmed from settled payments" data-testid="badge-top-revenue-confirmed">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-400" /> Revenue: Confirmed
                    </span>
                  )}
                  {/* Distinct Cost Status Badge */}
                  {profitData.cost_is_estimated ? (
                    <span className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-bold rounded bg-amber-500/20 text-amber-300 border border-amber-500/40" title="One or more styles use planned/estimated labor costs" data-testid="badge-top-cost-estimated">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400" /> Cost: Estimated
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-bold rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" title="All styles use confirmed actual production job assignment rates" data-testid="badge-top-cost-actual">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-400" /> Cost: Actual
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* KPI Headline Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="profitability-kpi-grid">
              <Card className="p-5 border-l-4 border-l-blue-600">
                <div className="text-xs uppercase tracking-wider font-bold text-slate-500 mb-1">Net Units Sold</div>
                <div className="text-2xl font-black text-slate-900" data-testid="net-units-sold-value">
                  {profitData.net_units_sold}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">
                  Reconciled: {profitData.reconciled_units_count} | Unreconciled: {profitData.unreconciled_units_count}
                </div>
              </Card>

              <Card className="p-5 border-l-4 border-l-emerald-600">
                <div className="text-xs uppercase tracking-wider font-bold text-slate-500 mb-1">Total Revenue</div>
                <div className="text-2xl font-black text-emerald-700" data-testid="total-revenue-value">
                  {inr(profitData.total_revenue_settled)}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">
                  Pending: {inr(profitData.total_revenue_pending)} | Fees: {inr(profitData.total_platform_fees)}
                </div>
              </Card>

              <Card className="p-5 border-l-4 border-l-amber-600">
                <div className="text-xs uppercase tracking-wider font-bold text-slate-500 mb-1">Total Net COGS</div>
                <div className="text-2xl font-black text-amber-700" data-testid="total-cogs-value">
                  {inr(profitData.total_net_cogs)}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">
                  From BOM + Job Assignment Costing
                </div>
              </Card>

              <Card className={`p-5 border-l-4 ${profitData.gross_profit >= 0 ? "border-l-emerald-600" : "border-l-rose-600"}`}>
                <div className="text-xs uppercase tracking-wider font-bold text-slate-500 mb-1">Gross Profit / Margin</div>
                <div className={`text-2xl font-black ${profitData.gross_profit >= 0 ? "text-emerald-700" : "text-rose-700"}`} data-testid="gross-profit-value">
                  {inr(profitData.gross_profit)}
                </div>
                <div className="text-[11px] font-bold text-slate-600 mt-1">
                  Margin: {profitData.gross_margin_pct}%
                </div>
              </Card>
            </div>

            {/* Per-Style Breakdown Table with Independent Badges */}
            <Card className="overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-200 flex justify-between items-center bg-slate-50">
                <h4 className="font-bold text-xs uppercase tracking-wider text-slate-800 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-[#C27842]" /> Per-Style Cost & Profitability Breakdown
                </h4>
                <div className="text-xs text-slate-500 font-semibold">
                  {profitData.by_style?.length || 0} style(s) sold
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-separate border-spacing-0" data-testid="by-style-table">
                  <thead>
                    <tr className="bg-slate-100 text-slate-600 uppercase tracking-wider text-[10px] font-bold">
                      <th className="p-3 sticky left-0 z-20 bg-slate-100 border-b border-r border-slate-200 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.1)] min-w-[160px]">Style Code</th>
                      <th className="p-3 text-center border-b border-slate-200">Units Sold</th>
                      <th className="p-3 text-right border-b border-slate-200">Revenue</th>
                      <th className="p-3 text-right border-b border-slate-200">Platform Fees</th>
                      <th className="p-3 text-right border-b border-slate-200">Unit COGS</th>
                      <th className="p-3 text-right border-b border-slate-200">Total COGS</th>
                      <th className="p-3 text-right border-b border-slate-200">Net Profit</th>
                      <th className="p-3 text-right border-b border-slate-200">Margin %</th>
                      <th className="p-3 text-center border-b border-slate-200">Revenue Status</th>
                      <th className="p-3 text-center border-b border-slate-200">Cost Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {profitData.by_style && profitData.by_style.map((row) => (
                      <tr key={row.style_id || row.style_code} className="group hover:bg-slate-50 border-b border-slate-200">
                        <td className="p-3 font-bold font-mono text-slate-900 sticky left-0 z-10 bg-white group-hover:bg-slate-50 border-b border-r border-slate-200 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.1)] min-w-[160px]">
                          {row.style_code}
                          {row.color && <span className="text-slate-400 font-normal ml-1">({row.color})</span>}
                        </td>
                        <td className="p-3 text-center font-semibold text-slate-700 border-b border-slate-200">{row.units_sold}</td>
                        <td className="p-3 text-right font-bold text-slate-900 border-b border-slate-200">{inr(row.revenue_settled)}</td>
                        <td className="p-3 text-right text-rose-600 font-semibold border-b border-slate-200">{inr(row.platform_fees)}</td>
                        <td className="p-3 text-right font-mono text-slate-700 border-b border-slate-200">{inr(row.unit_cogs)}</td>
                        <td className="p-3 text-right font-bold text-amber-800 border-b border-slate-200">{inr(row.cogs)}</td>
                        <td className={`p-3 text-right font-black border-b border-slate-200 ${row.profit >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
                          {inr(row.profit)}
                        </td>
                        <td className={`p-3 text-right font-bold border-b border-slate-200 ${row.margin_pct >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                          {row.margin_pct}%
                        </td>
                        {/* Distinct Independent Revenue Badge */}
                        <td className="p-3 text-center border-b border-slate-200">
                          {row.is_estimated ? (
                            <span className="inline-block px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-300" title={row.revenue_source || "Estimated revenue"} data-testid={`badge-rev-est-${row.style_code}`}>
                              Revenue: Estimated
                            </span>
                          ) : (
                            <span className="inline-block px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-300" title={row.revenue_source || "Confirmed revenue"} data-testid={`badge-rev-conf-${row.style_code}`}>
                              Revenue: Confirmed
                            </span>
                          )}
                        </td>
                        {/* Distinct Independent Cost Badge */}
                        <td className="p-3 text-center border-b border-slate-200">
                          {row.cost_is_estimated ? (
                            <span className="inline-block px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-300" title="Cost: planned style BOM estimate" data-testid={`badge-cost-est-${row.style_code}`}>
                              Cost: Estimated
                            </span>
                          ) : (
                            <span className="inline-block px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-300" title="Cost: actual worker job assignment rate" data-testid={`badge-cost-act-${row.style_code}`}>
                              Cost: Actual
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}

        {/* ── TAB 1: MONTHLY PNL RECONCILIATION ── */}
        {activeTab === "monthly_pnl" && (
          <MonthlyPnLReconciliation />
        )}

        {/* ── TAB 2: RETURN REDUCTION ENGINE ── */}
        {activeTab === "returns_engine" && (
          <ReturnsIntelligenceTab />
        )}
      </div>

      {/* ── COST SNAPSHOT MODAL ────────────────────────────────────────────── */}
      {snapshotModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4" role="dialog">
          <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-md overflow-hidden">
            <div className="bg-[#0F172A] text-white px-5 py-3.5 flex items-center justify-between">
              <div className="font-bold text-sm uppercase tracking-wider flex items-center gap-2">
                <Plus className="w-4 h-4 text-[#C27842]" /> Create Historical Cost Snapshot
              </div>
              <button onClick={() => setSnapshotModalOpen(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleCreateSnapshot} className="p-5 space-y-4">
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-700 mb-1">Style Code *</label>
                <input
                  type="text"
                  placeholder="e.g. SSK-101"
                  value={snapshotForm.style_code}
                  onChange={(e) => setSnapshotForm({ ...snapshotForm, style_code: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-bold uppercase focus:border-slate-900"
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-bold uppercase text-slate-700 mb-1">Effective Date *</label>
                  <input
                    type="date"
                    value={snapshotForm.effective_date}
                    onChange={(e) => setSnapshotForm({ ...snapshotForm, effective_date: e.target.value })}
                    className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold focus:border-slate-900"
                    required
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold uppercase text-slate-700 mb-1">Total Unit Cost (₹) *</label>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="0.00"
                    value={snapshotForm.total_cost}
                    onChange={(e) => setSnapshotForm({ ...snapshotForm, total_cost: e.target.value })}
                    className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-bold focus:border-slate-900"
                    required
                  />
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-bold uppercase text-slate-700 mb-1">Notes</label>
                <input
                  type="text"
                  placeholder="Snapshot remarks or BOM version..."
                  value={snapshotForm.notes}
                  onChange={(e) => setSnapshotForm({ ...snapshotForm, notes: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-medium focus:border-slate-900"
                />
              </div>
              <div className="flex justify-end gap-2 pt-3 border-t">
                <BtnSecondary type="button" onClick={() => setSnapshotModalOpen(false)}>Cancel</BtnSecondary>
                <BtnPrimary type="submit"><Check className="w-4 h-4 mr-1 inline" /> Save Cost Snapshot</BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
