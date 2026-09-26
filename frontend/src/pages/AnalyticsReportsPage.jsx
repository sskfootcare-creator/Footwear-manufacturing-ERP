import React, { useState, useEffect } from "react";
import {
  Activity, TrendingUp, ShieldCheck, DollarSign,
  Grid, Compass, RefreshCw, AlertTriangle, Layers, MapPin, Box
} from "lucide-react";
import AnalyticsDashboard from "../components/AnalyticsDashboard";

/**
 * AnalyticsReportsPage (A-001..A-006, U-009)
 * Unified Enterprise Analytics & Intelligence Reporting Center.
 */
export default function AnalyticsReportsPage() {
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(false);

  // Tab states
  const [deadStockData, setDeadStockData] = useState(null);
  const [supplierData, setSupplierData] = useState(null);
  const [costVarianceData, setCostVarianceData] = useState(null);
  const [warehouseHeatmap, setWarehouseHeatmap] = useState(null);
  const [safetyStockData, setSafetyStockData] = useState(null);
  const [demandForecast, setDemandForecast] = useState(null);

  useEffect(() => {
    loadTabData(activeTab);
  }, [activeTab]);

  const loadTabData = async (tab) => {
    try {
      setLoading(true);
      if (tab === "dead_stock" && !deadStockData) {
        const res = await fetch("/api/reports/dead-stock?idle_days_threshold=90");
        if (res.ok) setDeadStockData(await res.json());
      } else if (tab === "scorecards" && !supplierData) {
        const [sup, cust] = await Promise.all([
          fetch("/api/reports/supplier-scorecards").then((r) => r.json()),
          fetch("/api/reports/customer-scorecards").then((r) => r.json()),
        ]);
        setSupplierData({ suppliers: sup.suppliers || [], clients: cust.clients || [] });
      } else if (tab === "costing" && !costVarianceData) {
        const res = await fetch("/api/reports/cost-variance");
        if (res.ok) setCostVarianceData(await res.json());
      } else if (tab === "warehouse" && !warehouseHeatmap) {
        const res = await fetch("/api/wms/analytics/utilization-heatmap");
        if (res.ok) setWarehouseHeatmap(await res.json());
      } else if (tab === "forecasting" && !safetyStockData) {
        const [ss, df] = await Promise.all([
          fetch("/api/reports/safety-stock").then((r) => r.json()),
          fetch("/api/reports/demand-forecasting").then((r) => r.json()),
        ]);
        setSafetyStockData(ss);
        setDemandForecast(df);
      }
    } catch (e) {
      console.warn("Failed to load tab data:", e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 text-white">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-800 pb-5">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2.5">
            <Activity className="w-7 h-7 text-blue-500" />
            Enterprise Analytics & Intelligence
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Real-time stage velocity, working capital turnover, scorecards, and warehouse heatmaps.
          </p>
        </div>

        <button
          onClick={() => loadTabData(activeTab)}
          className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold flex items-center gap-2 border border-slate-700 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh Metrics
        </button>
      </div>

      {/* Navigation Tabs */}
      <div className="flex gap-2 overflow-x-auto pb-2 border-b border-slate-800">
        {[
          { key: "overview", label: "Executive Dashboard", icon: <Grid className="w-4 h-4" /> },
          { key: "dead_stock", label: "Inventory & Dead Stock", icon: <TrendingUp className="w-4 h-4" /> },
          { key: "scorecards", label: "Supplier & Client Scorecards", icon: <ShieldCheck className="w-4 h-4" /> },
          { key: "costing", label: "Budget vs Actual Costing", icon: <DollarSign className="w-4 h-4" /> },
          { key: "warehouse", label: "Warehouse Cell Heatmap", icon: <MapPin className="w-4 h-4" /> },
          { key: "forecasting", label: "Demand Forecast & Safety Stock", icon: <Compass className="w-4 h-4" /> },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2.5 rounded-2xl text-xs font-bold whitespace-nowrap flex items-center gap-2 transition-all ${
              activeTab === tab.key
                ? "bg-blue-600 text-white shadow-lg shadow-blue-500/20"
                : "bg-slate-900/80 text-slate-400 hover:text-white hover:bg-slate-800 border border-slate-800"
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab 1: Executive Overview */}
      {activeTab === "overview" && (
        <AnalyticsDashboard onNavigateTab={(target) => setActiveTab(target)} />
      )}

      {/* Tab 2: Dead Stock & Working Capital (A-002) */}
      {activeTab === "dead_stock" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl">
              <span className="text-xs uppercase font-bold text-slate-400">Idle Items (>90d)</span>
              <div className="text-2xl font-black mt-2 text-rose-400">
                {deadStockData?.total_dead_stock_count || 0} SKUs
              </div>
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl">
              <span className="text-xs uppercase font-bold text-slate-400">Locked Working Capital</span>
              <div className="text-2xl font-black mt-2 text-amber-400">
                ₹{deadStockData?.total_locked_capital?.toLocaleString() || "0"}
              </div>
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl">
              <span className="text-xs uppercase font-bold text-slate-400">Liquidation Action</span>
              <div className="text-sm font-semibold mt-2 text-emerald-400">
                Promotional Volume Bundle & Outlet Salvage
              </div>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl">
            <div className="p-4 border-b border-slate-800 font-bold text-sm">
              Detected Dead & Slow-Moving SKUs
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-800/60 text-slate-400 uppercase font-semibold">
                  <tr>
                    <th className="p-3">SKU</th>
                    <th className="p-3">Style & Color</th>
                    <th className="p-3">Idle Days</th>
                    <th className="p-3">Quantity</th>
                    <th className="p-3">Locked Capital</th>
                    <th className="p-3">Recommended Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {(deadStockData?.items || []).map((it, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/40">
                      <td className="p-3 font-mono font-bold text-slate-200">{it.sku}</td>
                      <td className="p-3">{it.style_code} ({it.color}) Sz {it.size}</td>
                      <td className="p-3 text-rose-400 font-bold">{it.days_idle} days</td>
                      <td className="p-3 font-semibold">{it.quantity} pairs</td>
                      <td className="p-3 text-amber-300 font-bold">₹{it.locked_capital}</td>
                      <td className="p-3 text-slate-300">{it.recommended_action}</td>
                    </tr>
                  ))}
                  {(!deadStockData?.items || deadStockData.items.length === 0) && (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-slate-500">
                        No dead stock items exceeding the 90-day idle threshold!
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Supplier & Customer Scorecards (A-003) */}
      {activeTab === "scorecards" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Supplier Performance */}
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4">
            <h3 className="font-bold text-base flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-purple-400" />
              Supplier Quality & Delivery Scorecards
            </h3>
            <div className="space-y-3">
              {(supplierData?.suppliers || []).map((s, idx) => (
                <div key={idx} className="bg-slate-800/60 p-3.5 rounded-2xl border border-slate-700/60 flex justify-between items-center text-xs">
                  <div>
                    <div className="font-bold text-white text-sm">{s.vendor_name}</div>
                    <div className="text-slate-400 mt-1">
                      On-Time: <strong className="text-emerald-400">{s.on_time_delivery_rate}%</strong> • Defect Rate: {s.defect_rate}%
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="px-2.5 py-1 rounded-xl bg-purple-500/20 text-purple-300 font-black text-sm border border-purple-500/30">
                      {s.grade}
                    </span>
                    <span className="block text-[10px] text-slate-400 mt-1">Score: {s.composite_score}/100</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Customer DSO & Credit Health */}
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl space-y-4">
            <h3 className="font-bold text-base flex items-center gap-2">
              <DollarSign className="w-5 h-5 text-emerald-400" />
              Client Payment & DSO Scorecards
            </h3>
            <div className="space-y-3">
              {(supplierData?.clients || []).map((c, idx) => (
                <div key={idx} className="bg-slate-800/60 p-3.5 rounded-2xl border border-slate-700/60 flex justify-between items-center text-xs">
                  <div>
                    <div className="font-bold text-white text-sm">{c.client_name}</div>
                    <div className="text-slate-400 mt-1">
                      DSO: <strong className="text-blue-400">{c.days_sales_outstanding} days</strong> • On-Time: {c.on_time_payment_rate}%
                    </div>
                  </div>
                  <div className="text-right">
                    <span className={`px-2.5 py-1 rounded-xl font-bold text-xs ${
                      c.risk_level === "LOW" ? "bg-emerald-500/20 text-emerald-300" : "bg-amber-500/20 text-amber-300"
                    }`}>
                      {c.risk_level}
                    </span>
                    <span className="block text-[10px] text-slate-400 mt-1">Health: {c.credit_health_score}/100</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Budget vs Actual Cost Variance (A-004) */}
      {activeTab === "costing" && (
        <div className="space-y-6">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl flex justify-between items-center">
            <div>
              <span className="text-xs font-bold uppercase text-slate-400">Net Production Variance</span>
              <div className="text-2xl font-black mt-1 text-white">
                ₹{costVarianceData?.summary?.net_variance_amount?.toLocaleString() || "0"}
                <span className="text-xs font-semibold text-slate-400 ml-2">
                  ({costVarianceData?.summary?.net_variance_percentage || 0}%)
                </span>
              </div>
            </div>
            <span className="px-3 py-1.5 rounded-xl bg-slate-800 border border-slate-700 text-xs font-bold text-slate-300">
              Evaluated: {costVarianceData?.summary?.total_jobs || 0} jobs
            </span>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl">
            <div className="p-4 border-b border-slate-800 font-bold text-sm">
              Job-by-Job Costing Variance Analysis
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-800/60 text-slate-400 uppercase font-semibold">
                  <tr>
                    <th className="p-3">Job / PO</th>
                    <th className="p-3">Style</th>
                    <th className="p-3">Pairs</th>
                    <th className="p-3">Budgeted / Pair</th>
                    <th className="p-3">Actual / Pair</th>
                    <th className="p-3">Variance</th>
                    <th className="p-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {(costVarianceData?.jobs || []).map((j, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/40">
                      <td className="p-3 font-mono font-bold text-slate-200">
                        {j.job_number || "JOB-CARD"} / {j.po_number || "PO-001"}
                      </td>
                      <td className="p-3">{j.style_code}</td>
                      <td className="p-3 font-semibold">{j.pairs} pairs</td>
                      <td className="p-3">₹{j.budgeted_cost_per_pair}</td>
                      <td className="p-3 font-bold">₹{j.actual_cost_per_pair}</td>
                      <td className={`p-3 font-bold ${j.variance_amount > 0 ? "text-rose-400" : "text-emerald-400"}`}>
                        {j.variance_amount > 0 ? `+₹${j.variance_amount}` : `-₹${Math.abs(j.variance_amount)}`}
                      </td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          j.status === "COST_OVERRUN" ? "bg-rose-500/20 text-rose-300" : "bg-emerald-500/20 text-emerald-300"
                        }`}>
                          {j.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 5: Warehouse Cell Heatmap (A-005) */}
      {activeTab === "warehouse" && (
        <div className="space-y-6">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl flex justify-between items-center">
            <div>
              <span className="text-xs font-bold uppercase text-slate-400">Overall Warehouse Occupancy</span>
              <div className="text-2xl font-black mt-1 text-white">
                {warehouseHeatmap?.summary?.overall_utilization_pct || "62"}%
                <span className="text-xs font-semibold text-slate-400 ml-2">
                  ({warehouseHeatmap?.summary?.total_occupied_pairs} / {warehouseHeatmap?.summary?.total_capacity_pairs} pairs)
                </span>
              </div>
            </div>
            <div className="flex gap-2">
              <span className="flex items-center gap-1.5 text-xs text-slate-400">
                <span className="w-3 h-3 rounded bg-emerald-500" /> Optimal (1-75%)
              </span>
              <span className="flex items-center gap-1.5 text-xs text-slate-400">
                <span className="w-3 h-3 rounded bg-amber-500" /> High (76-90%)
              </span>
              <span className="flex items-center gap-1.5 text-xs text-slate-400">
                <span className="w-3 h-3 rounded bg-rose-500" /> Full / Congested
              </span>
            </div>
          </div>

          {/* Visual Heatmap Grid */}
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
            <h3 className="font-bold text-sm text-slate-200">Racks & Cells Occupancy Heatmap</h3>
            <div className="grid grid-cols-4 sm:grid-cols-8 md:grid-cols-12 gap-2 max-h-96 overflow-y-auto p-2 bg-slate-950/60 rounded-2xl border border-slate-800">
              {(warehouseHeatmap?.heatmap || []).slice(0, 72).map((cell, idx) => (
                <div
                  key={idx}
                  title={`${cell.location_code}: ${cell.occupied_pairs}/${cell.capacity_pairs} pairs (${cell.utilization_pct}%)`}
                  className={`h-10 rounded-xl flex items-center justify-center font-mono text-[10px] font-bold cursor-pointer transition-transform hover:scale-105 border ${
                    cell.intensity === 4
                      ? "bg-rose-600/80 text-white border-rose-500"
                      : cell.intensity === 3
                      ? "bg-amber-600/80 text-white border-amber-500"
                      : cell.intensity === 2
                      ? "bg-blue-600/60 text-white border-blue-500"
                      : cell.intensity === 1
                      ? "bg-emerald-600/40 text-emerald-200 border-emerald-500/50"
                      : "bg-slate-800 text-slate-500 border-slate-700"
                  }`}
                >
                  {cell.location_code?.split("-")?.[2] || `C${idx + 1}`}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab 6: Demand Forecast & Safety Stock (A-006) */}
      {activeTab === "forecasting" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl">
              <span className="text-xs font-bold uppercase text-slate-400">Critical Stockout SKUs</span>
              <div className="text-2xl font-black text-rose-400 mt-1">
                {safetyStockData?.critical_items_count || 0} SKUs
              </div>
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 shadow-xl">
              <span className="text-xs font-bold uppercase text-slate-400">Replenishment Reorders Needed</span>
              <div className="text-2xl font-black text-amber-400 mt-1">
                {safetyStockData?.reorder_needed_count || 0} SKUs
              </div>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-xl">
            <div className="p-4 border-b border-slate-800 font-bold text-sm">
              Demand Forecast & Dynamic Reorder Point Analysis
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-800/60 text-slate-400 uppercase font-semibold">
                  <tr>
                    <th className="p-3">SKU</th>
                    <th className="p-3">Current Stock</th>
                    <th className="p-3">Daily Demand</th>
                    <th className="p-3">Safety Stock</th>
                    <th className="p-3">Reorder Point</th>
                    <th className="p-3">Recommended Order</th>
                    <th className="p-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {(safetyStockData?.recommendations || []).slice(0, 20).map((r, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/40">
                      <td className="p-3 font-mono font-bold text-slate-200">{r.sku}</td>
                      <td className="p-3 font-semibold">{r.current_ready_stock} pairs</td>
                      <td className="p-3">{r.daily_demand} / day</td>
                      <td className="p-3 text-slate-300">{r.safety_stock}</td>
                      <td className="p-3 font-bold text-amber-300">{r.reorder_point}</td>
                      <td className="p-3 text-emerald-400 font-black">
                        {r.recommended_order_qty > 0 ? `+${r.recommended_order_qty} pairs` : "—"}
                      </td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          r.status === "STOCKOUT_CRITICAL"
                            ? "bg-rose-500/20 text-rose-300"
                            : r.status === "REORDER_NOW"
                            ? "bg-amber-500/20 text-amber-300"
                            : "bg-emerald-500/20 text-emerald-300"
                        }`}>
                          {r.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
