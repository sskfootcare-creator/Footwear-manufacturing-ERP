import React, { useState } from "react";
import {
  Activity, TrendingUp, ShieldCheck, DollarSign,
  Grid, Compass, RefreshCw, MapPin, Loader2, AlertTriangle,
} from "lucide-react";
import { PageHeader } from "../components/ui-kit";
import AnalyticsDashboard from "../components/AnalyticsDashboard";
import { http } from "../lib/api";

/**
 * AnalyticsReportsPage (A-001..A-006, U-009)
 * Unified Enterprise Analytics & Intelligence Reporting Center.
 * Follows the ERP light theme: white bg, slate borders, brand #C27842.
 */
export default function AnalyticsReportsPage() {
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Tab data states — null = not yet loaded
  const [deadStockData, setDeadStockData] = useState(null);
  const [supplierData, setSupplierData] = useState(null);
  const [costVarianceData, setCostVarianceData] = useState(null);
  const [warehouseHeatmap, setWarehouseHeatmap] = useState(null);
  const [safetyStockData, setSafetyStockData] = useState(null);

  /** Force-refresh current tab (clears existing data so it re-fetches). */
  const handleRefresh = () => {
    setError(null);
    switch (activeTab) {
      case "dead_stock":   setDeadStockData(null);   break;
      case "scorecards":   setSupplierData(null);    break;
      case "costing":      setCostVarianceData(null); break;
      case "warehouse":    setWarehouseHeatmap(null); break;
      case "forecasting":  setSafetyStockData(null); break;
      default: break;
    }
    // overview tab refreshes via AnalyticsDashboard's own state; this triggers re-mount.
    if (activeTab !== "overview") loadTabData(activeTab, true);
  };

  const loadTabData = async (tab, force = false) => {
    try {
      setLoading(true);
      setError(null);

      if (tab === "dead_stock" && (force || !deadStockData)) {
        const res = await http.get("/reports/dead-stock?idle_days_threshold=90");
        setDeadStockData(res.data);

      } else if (tab === "scorecards" && (force || !supplierData)) {
        const [sup, cust] = await Promise.all([
          http.get("/reports/supplier-scorecards").then((r) => r.data),
          http.get("/reports/customer-scorecards").then((r) => r.data),
        ]);
        setSupplierData({
          suppliers: sup.suppliers || [],
          clients: cust.clients || [],
        });

      } else if (tab === "costing" && (force || !costVarianceData)) {
        const res = await http.get("/reports/cost-variance");
        setCostVarianceData(res.data);

      } else if (tab === "warehouse" && (force || !warehouseHeatmap)) {
        const res = await http.get("/wms/analytics/utilization-heatmap");
        setWarehouseHeatmap(res.data);

      } else if (tab === "forecasting" && (force || !safetyStockData)) {
        const [ss, df] = await Promise.all([
          http.get("/reports/safety-stock").then((r) => r.data),
          http.get("/reports/demand-forecasting").then((r) => r.data),
        ]);
        setSafetyStockData({ ...ss, demandForecast: df });
      }
    } catch (e) {
      console.warn("Failed to load tab data:", e);
      const status = e?.response?.status;
      if (status === 401) {
        setError("Session expired. Please refresh the page.");
      } else {
        setError(e?.response?.data?.detail || e?.message || "Failed to load data. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleTabChange = (tab) => {
    setError(null);
    setActiveTab(tab);
    if (tab !== "overview") loadTabData(tab);
  };

  const TABS = [
    { key: "overview",    label: "Executive Dashboard",         icon: <Grid className="w-3.5 h-3.5" /> },
    { key: "dead_stock",  label: "Inventory & Dead Stock",      icon: <TrendingUp className="w-3.5 h-3.5" /> },
    { key: "scorecards",  label: "Supplier & Client Scorecards",icon: <ShieldCheck className="w-3.5 h-3.5" /> },
    { key: "costing",     label: "Budget vs Actual Costing",    icon: <DollarSign className="w-3.5 h-3.5" /> },
    { key: "warehouse",   label: "Warehouse Cell Heatmap",      icon: <MapPin className="w-3.5 h-3.5" /> },
    { key: "forecasting", label: "Demand Forecast & Safety Stock", icon: <Compass className="w-3.5 h-3.5" /> },
  ];

  return (
    <div>
      {/* ERP-standard page header */}
      <PageHeader
        title="Analytics & Intelligence"
        subtitle="Analytics"
        testId="analytics-header"
        action={
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="flex items-center gap-2 bg-white text-slate-900 font-bold uppercase tracking-wider text-xs px-4 py-2 border-2 border-slate-300 hover:border-[#0F172A] transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh Metrics
          </button>
        }
      />

      <div className="px-4 sm:px-8 py-6 space-y-6">
        {/* Sub-header description */}
        <p className="text-xs text-slate-500">
          Real-time stage velocity, working capital turnover, scorecards, and warehouse heatmaps.
        </p>

        {/* Navigation Tabs */}
        <div className="flex gap-1.5 overflow-x-auto pb-1 border-b-2 border-slate-200 no-scrollbar">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => handleTabChange(tab.key)}
              className={`px-3.5 py-2 text-[11px] font-bold whitespace-nowrap flex items-center gap-1.5 transition-all border-b-2 -mb-0.5 ${
                activeTab === tab.key
                  ? "border-[#C27842] text-[#C27842] bg-amber-50"
                  : "border-transparent text-slate-500 hover:text-slate-900 hover:bg-slate-100"
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        {/* Error Banner */}
        {error && (
          <div className="flex items-center gap-3 bg-red-50 border-2 border-red-200 p-4 text-sm text-red-700">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              className="ml-auto text-red-400 hover:text-red-600 font-bold text-xs uppercase"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Tab Loading Skeleton */}
        {loading && activeTab !== "overview" && (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Loader2 className="w-7 h-7 animate-spin text-[#C27842]" />
            <span className="text-sm text-slate-500 font-medium">Loading {TABS.find(t => t.key === activeTab)?.label}…</span>
          </div>
        )}

        {/* ── Tab 1: Executive Overview ── */}
        {activeTab === "overview" && (
          <AnalyticsDashboard onNavigateTab={(target) => handleTabChange(target)} />
        )}

        {/* ── Tab 2: Dead Stock & Working Capital (A-002) ── */}
        {activeTab === "dead_stock" && !loading && (
          <div className="space-y-6">
            {/* Summary KPIs */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-white border-2 border-slate-200 p-5 relative overflow-hidden">
                <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#DC2626]" />
                <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500">
                  Idle Items (&gt;90 days)
                </div>
                <div className="font-mono text-3xl font-black mt-3 text-[#DC2626]">
                  {deadStockData?.total_dead_stock_count ?? 0}
                  <span className="text-sm font-semibold text-slate-400 ml-1">SKUs</span>
                </div>
              </div>

              <div className="bg-white border-2 border-slate-200 p-5 relative overflow-hidden">
                <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#F59E0B]" />
                <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500">
                  Locked Working Capital
                </div>
                <div className="font-mono text-3xl font-black mt-3 text-[#F59E0B]">
                  Rs.{(deadStockData?.total_locked_capital ?? 0).toLocaleString("en-IN")}
                </div>
              </div>

              <div className="bg-white border-2 border-slate-200 p-5 relative overflow-hidden">
                <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#16A34A]" />
                <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500">
                  Recommended Liquidation
                </div>
                <div className="text-sm font-semibold mt-3 text-[#16A34A]">
                  Promotional Volume Bundle &amp; Outlet Salvage
                </div>
              </div>
            </div>

            {/* Dead Stock Table */}
            <div className="bg-white border-2 border-slate-200 overflow-hidden">
              <div className="px-5 py-3.5 border-b-2 border-slate-200 flex items-center justify-between">
                <h3 className="font-black text-slate-900 text-sm tracking-tight">
                  Detected Dead &amp; Slow-Moving SKUs
                </h3>
                {deadStockData?.items?.length > 0 && (
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    {deadStockData.items.length} items
                  </span>
                )}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-b-2 border-slate-200 text-slate-500 uppercase font-bold tracking-wider">
                    <tr>
                      <th className="px-4 py-3">SKU</th>
                      <th className="px-4 py-3">Style &amp; Color</th>
                      <th className="px-4 py-3">Idle Days</th>
                      <th className="px-4 py-3">Quantity</th>
                      <th className="px-4 py-3">Locked Capital</th>
                      <th className="px-4 py-3">Recommended Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(deadStockData?.items || []).map((it, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-mono font-bold text-slate-900">{it.sku}</td>
                        <td className="px-4 py-3 text-slate-700">
                          {it.style_code} ({it.color}) Sz {it.size}
                        </td>
                        <td className="px-4 py-3 font-bold text-[#DC2626]">{it.days_idle} days</td>
                        <td className="px-4 py-3 font-semibold text-slate-700">{it.quantity} pairs</td>
                        <td className="px-4 py-3 font-bold text-[#F59E0B]">
                          Rs.{(it.locked_capital ?? 0).toLocaleString("en-IN")}
                        </td>
                        <td className="px-4 py-3 text-slate-600">{it.recommended_action}</td>
                      </tr>
                    ))}
                    {(!deadStockData?.items || deadStockData.items.length === 0) && (
                      <tr>
                        <td colSpan={6} className="px-4 py-10 text-center text-slate-400 text-sm">
                          No dead stock items exceeding the 90-day idle threshold.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ── Tab 3: Supplier & Customer Scorecards (A-003) ── */}
        {activeTab === "scorecards" && !loading && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Supplier Performance */}
            <div className="bg-white border-2 border-slate-200">
              <div className="px-5 py-3.5 border-b-2 border-slate-200 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-[#7C3AED]" />
                <h3 className="font-black text-slate-900 text-sm tracking-tight">
                  Supplier Quality &amp; Delivery Scorecards
                </h3>
              </div>
              <div className="divide-y divide-slate-100">
                {(supplierData?.suppliers || []).map((s, idx) => (
                  <div key={idx} className="px-5 py-4 flex items-center justify-between hover:bg-slate-50">
                    <div>
                      <div className="font-bold text-slate-900 text-sm">{s.vendor_name}</div>
                      <div className="text-xs text-slate-500 mt-1">
                        On-Time:{" "}
                        <strong className="text-[#16A34A]">{s.on_time_delivery_rate}%</strong>
                        {" "}&bull;{" "}
                        Defect Rate: {s.defect_rate}%
                      </div>
                    </div>
                    <div className="text-right ml-4 flex-shrink-0">
                      <span className="inline-block px-3 py-1 bg-purple-100 text-purple-700 border border-purple-200 font-black text-sm">
                        {s.grade}
                      </span>
                      <span className="block text-[10px] text-slate-400 mt-1 font-semibold">
                        Score: {s.composite_score}/100
                      </span>
                    </div>
                  </div>
                ))}
                {(!supplierData?.suppliers || supplierData.suppliers.length === 0) && (
                  <div className="px-5 py-10 text-center text-slate-400 text-sm">
                    No supplier scorecard data available.
                  </div>
                )}
              </div>
            </div>

            {/* Customer DSO & Credit Health */}
            <div className="bg-white border-2 border-slate-200">
              <div className="px-5 py-3.5 border-b-2 border-slate-200 flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-[#16A34A]" />
                <h3 className="font-black text-slate-900 text-sm tracking-tight">
                  Client Payment &amp; DSO Scorecards
                </h3>
              </div>
              <div className="divide-y divide-slate-100">
                {(supplierData?.clients || []).map((c, idx) => {
                  const riskBadge =
                    c.risk_level === "LOW"
                      ? "bg-green-100 text-[#16A34A] border-green-200"
                      : c.risk_level === "HIGH"
                      ? "bg-red-100 text-[#DC2626] border-red-200"
                      : "bg-amber-100 text-amber-700 border-amber-200";
                  return (
                    <div key={idx} className="px-5 py-4 flex items-center justify-between hover:bg-slate-50">
                      <div>
                        <div className="font-bold text-slate-900 text-sm">{c.client_name}</div>
                        <div className="text-xs text-slate-500 mt-1">
                          DSO:{" "}
                          <strong className="text-[#2563EB]">{c.days_sales_outstanding} days</strong>
                          {" "}&bull;{" "}
                          On-Time: {c.on_time_payment_rate}%
                        </div>
                      </div>
                      <div className="text-right ml-4 flex-shrink-0">
                        <span className={`inline-block px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider border ${riskBadge}`}>
                          {c.risk_level}
                        </span>
                        <span className="block text-[10px] text-slate-400 mt-1 font-semibold">
                          Health: {c.credit_health_score}/100
                        </span>
                      </div>
                    </div>
                  );
                })}
                {(!supplierData?.clients || supplierData.clients.length === 0) && (
                  <div className="px-5 py-10 text-center text-slate-400 text-sm">
                    No client scorecard data available.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── Tab 4: Budget vs Actual Cost Variance (A-004) ── */}
        {activeTab === "costing" && !loading && (
          <div className="space-y-6">
            {/* Summary bar */}
            <div className="bg-white border-2 border-slate-200 p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500">
                  Net Production Variance
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="font-mono text-3xl font-black text-slate-900">
                    Rs.{(costVarianceData?.summary?.net_variance_amount ?? 0).toLocaleString("en-IN")}
                  </span>
                  <span className="text-sm font-semibold text-slate-400">
                    ({costVarianceData?.summary?.net_variance_percentage ?? 0}%)
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {costVarianceData?.summary?.overall_status && (
                  <span className={`px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider border ${
                    costVarianceData.summary.overall_status === "WITHIN_BUDGET" || costVarianceData.summary.overall_status === "WITHIN BUDGET"
                      ? "bg-green-100 text-[#16A34A] border-green-200"
                      : "bg-red-100 text-[#DC2626] border-red-200"
                  }`}>
                    {costVarianceData.summary.overall_status}
                  </span>
                )}
                <span className="px-3 py-1.5 bg-slate-100 border-2 border-slate-200 text-xs font-bold text-slate-600">
                  {costVarianceData?.summary?.total_jobs ?? 0} jobs evaluated
                </span>
              </div>
            </div>

            {/* Job Variance Table */}
            <div className="bg-white border-2 border-slate-200 overflow-hidden">
              <div className="px-5 py-3.5 border-b-2 border-slate-200">
                <h3 className="font-black text-slate-900 text-sm tracking-tight">
                  Job-by-Job Costing Variance Analysis
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-b-2 border-slate-200 text-slate-500 uppercase font-bold tracking-wider">
                    <tr>
                      <th className="px-4 py-3">Job / PO</th>
                      <th className="px-4 py-3">Style</th>
                      <th className="px-4 py-3">Pairs</th>
                      <th className="px-4 py-3">Budgeted / Pair</th>
                      <th className="px-4 py-3">Actual / Pair</th>
                      <th className="px-4 py-3">Variance</th>
                      <th className="px-4 py-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(costVarianceData?.jobs || []).map((j, idx) => {
                      const isOverrun = j.variance_amount > 0;
                      return (
                        <tr key={idx} className="hover:bg-slate-50">
                          <td className="px-4 py-3 font-mono font-bold text-slate-900">
                            {j.job_number || "JOB-CARD"} / {j.po_number || "PO-001"}
                          </td>
                          <td className="px-4 py-3 text-slate-700">{j.style_code}</td>
                          <td className="px-4 py-3 font-semibold text-slate-700">{j.pairs} pairs</td>
                          <td className="px-4 py-3 text-slate-700">
                            Rs.{(j.budgeted_cost_per_pair ?? 0).toLocaleString("en-IN")}
                          </td>
                          <td className="px-4 py-3 font-bold text-slate-900">
                            Rs.{(j.actual_cost_per_pair ?? 0).toLocaleString("en-IN")}
                          </td>
                          <td className={`px-4 py-3 font-bold ${isOverrun ? "text-[#DC2626]" : "text-[#16A34A]"}`}>
                            {isOverrun
                              ? `+Rs.${j.variance_amount}`
                              : `-Rs.${Math.abs(j.variance_amount)}`}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border ${
                              j.status === "COST_OVERRUN"
                                ? "bg-red-100 text-[#DC2626] border-red-200"
                                : "bg-green-100 text-[#16A34A] border-green-200"
                            }`}>
                              {j.status?.replace(/_/g, " ")}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                    {(!costVarianceData?.jobs || costVarianceData.jobs.length === 0) && (
                      <tr>
                        <td colSpan={7} className="px-4 py-10 text-center text-slate-400 text-sm">
                          No job costing data available.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ── Tab 5: Warehouse Cell Heatmap (A-005) ── */}
        {activeTab === "warehouse" && !loading && (
          <div className="space-y-6">
            {/* Summary + Legend */}
            <div className="bg-white border-2 border-slate-200 p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500">
                  Overall Warehouse Occupancy
                </div>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="font-mono text-3xl font-black text-slate-900">
                    {warehouseHeatmap?.summary?.overall_utilization_pct ?? "62"}%
                  </span>
                  {warehouseHeatmap?.summary?.total_occupied_pairs != null && (
                    <span className="text-sm font-semibold text-slate-400">
                      ({warehouseHeatmap.summary.total_occupied_pairs?.toLocaleString("en-IN")} /{" "}
                      {warehouseHeatmap.summary.total_capacity_pairs?.toLocaleString("en-IN")} pairs)
                    </span>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-4">
                {[
                  { color: "bg-[#16A34A]", label: "Optimal (1–75%)" },
                  { color: "bg-[#F59E0B]", label: "High (76–90%)" },
                  { color: "bg-[#DC2626]", label: "Full / Congested" },
                  { color: "bg-slate-300", label: "Empty" },
                ].map((l) => (
                  <span key={l.label} className="flex items-center gap-1.5 text-xs text-slate-600 font-semibold">
                    <span className={`w-3 h-3 ${l.color}`} />
                    {l.label}
                  </span>
                ))}
              </div>
            </div>

            {/* Heatmap Grid */}
            <div className="bg-white border-2 border-slate-200 p-6 space-y-4">
              <h3 className="font-black text-slate-900 text-sm tracking-tight">
                Racks &amp; Cells Occupancy Heatmap
              </h3>
              <div className="grid grid-cols-4 sm:grid-cols-8 md:grid-cols-12 gap-2 max-h-96 overflow-y-auto p-3 bg-slate-50 border-2 border-slate-200">
                {(warehouseHeatmap?.heatmap || []).slice(0, 72).map((cell, idx) => {
                  const cellStyle =
                    cell.intensity === 4
                      ? "bg-[#DC2626] text-white border-red-700"
                      : cell.intensity === 3
                      ? "bg-[#F59E0B] text-white border-amber-600"
                      : cell.intensity === 2
                      ? "bg-[#2563EB] text-white border-blue-700"
                      : cell.intensity === 1
                      ? "bg-[#16A34A] text-white border-green-700"
                      : "bg-slate-200 text-slate-500 border-slate-300";

                  return (
                    <div
                      key={idx}
                      title={`${cell.location_code}: ${cell.occupied_pairs}/${cell.capacity_pairs} pairs (${cell.utilization_pct}%)`}
                      className={`h-10 flex items-center justify-center font-mono text-[9px] font-bold cursor-pointer transition-transform hover:scale-110 border-2 ${cellStyle}`}
                    >
                      {cell.location_code?.split("-")?.[2] || `C${idx + 1}`}
                    </div>
                  );
                })}
                {(!warehouseHeatmap?.heatmap || warehouseHeatmap.heatmap.length === 0) && (
                  <div className="col-span-12 py-10 text-center text-slate-400 text-sm">
                    No heatmap data available.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── Tab 6: Demand Forecast & Safety Stock (A-006) ── */}
        {activeTab === "forecasting" && !loading && (
          <div className="space-y-6">
            {/* Summary KPIs */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="bg-white border-2 border-slate-200 p-5 relative overflow-hidden">
                <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#DC2626]" />
                <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500">
                  Critical Stockout SKUs
                </div>
                <div className="font-mono text-3xl font-black text-[#DC2626] mt-3">
                  {safetyStockData?.critical_items_count ?? 0}
                  <span className="text-sm font-semibold text-slate-400 ml-1">SKUs</span>
                </div>
              </div>
              <div className="bg-white border-2 border-slate-200 p-5 relative overflow-hidden">
                <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#F59E0B]" />
                <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500">
                  Replenishment Reorders Needed
                </div>
                <div className="font-mono text-3xl font-black text-[#F59E0B] mt-3">
                  {safetyStockData?.reorder_needed_count ?? 0}
                  <span className="text-sm font-semibold text-slate-400 ml-1">SKUs</span>
                </div>
              </div>
            </div>

            {/* Forecasting Table */}
            <div className="bg-white border-2 border-slate-200 overflow-hidden">
              <div className="px-5 py-3.5 border-b-2 border-slate-200">
                <h3 className="font-black text-slate-900 text-sm tracking-tight">
                  Demand Forecast &amp; Dynamic Reorder Point Analysis
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-b-2 border-slate-200 text-slate-500 uppercase font-bold tracking-wider">
                    <tr>
                      <th className="px-4 py-3">SKU</th>
                      <th className="px-4 py-3">Current Stock</th>
                      <th className="px-4 py-3">Daily Demand</th>
                      <th className="px-4 py-3">Safety Stock</th>
                      <th className="px-4 py-3">Reorder Point</th>
                      <th className="px-4 py-3">Recommended Order</th>
                      <th className="px-4 py-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(safetyStockData?.recommendations || []).slice(0, 20).map((r, idx) => {
                      const statusStyle =
                        r.status === "STOCKOUT_CRITICAL"
                          ? "bg-red-100 text-[#DC2626] border-red-200"
                          : r.status === "REORDER_NOW"
                          ? "bg-amber-100 text-amber-700 border-amber-200"
                          : "bg-green-100 text-[#16A34A] border-green-200";
                      return (
                        <tr key={idx} className="hover:bg-slate-50">
                          <td className="px-4 py-3 font-mono font-bold text-slate-900">{r.sku}</td>
                          <td className="px-4 py-3 font-semibold text-slate-700">
                            {r.current_ready_stock} pairs
                          </td>
                          <td className="px-4 py-3 text-slate-600">{r.daily_demand} / day</td>
                          <td className="px-4 py-3 text-slate-700">{r.safety_stock}</td>
                          <td className="px-4 py-3 font-bold text-[#F59E0B]">{r.reorder_point}</td>
                          <td className="px-4 py-3 font-black text-[#16A34A]">
                            {r.recommended_order_qty > 0
                              ? `+${r.recommended_order_qty} pairs`
                              : "—"}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border ${statusStyle}`}>
                              {r.status?.replace(/_/g, " ")}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                    {(!safetyStockData?.recommendations || safetyStockData.recommendations.length === 0) && (
                      <tr>
                        <td colSpan={7} className="px-4 py-10 text-center text-slate-400 text-sm">
                          No safety stock or demand forecast data available.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
