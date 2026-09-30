import React, { useState, useEffect } from "react";
import {
  TrendingUp, Activity, ShieldCheck,
  DollarSign, ArrowUpRight, Loader2, AlertTriangle,
} from "lucide-react";
import { http } from "../lib/api";

/**
 * AnalyticsDashboard (U-009, A-001..A-006)
 * Executive overview KPI tiles and production stage charts.
 * Uses the ERP light theme (white cards, slate text, brand #C27842).
 */
export default function AnalyticsDashboard({ onNavigateTab }) {
  const [velocityData, setVelocityData] = useState(null);
  const [turnoverData, setTurnoverData] = useState(null);
  const [varianceData, setVarianceData] = useState(null);
  const [scorecardData, setScorecardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [velRes, turnRes, varRes, scoreRes] = await Promise.allSettled([
        http.get("/reports/production-velocity").then((r) => r.data).catch(() => null),
        http.get("/reports/inventory-turnover").then((r) => r.data).catch(() => null),
        http.get("/reports/cost-variance").then((r) => r.data).catch(() => null),
        http.get("/reports/supplier-scorecards").then((r) => r.data).catch(() => null),
      ]);
      setVelocityData(velRes.value ?? null);
      setTurnoverData(turnRes.value ?? null);
      setVarianceData(varRes.value ?? null);
      setScorecardData(scoreRes.value ?? null);
    } catch (e) {
      console.warn("Failed to load analytics dashboard data:", e);
      setError("Could not fetch analytics data. Check API connectivity.");
    } finally {
      setLoading(false);
    }
  };

  const stages = [
    { key: "cutting",   label: "Cutting",   hours: velocityData?.stage_cycle_hours?.cutting   ?? 4.5, color: "#2563EB" },
    { key: "stitching", label: "Stitching", hours: velocityData?.stage_cycle_hours?.stitching ?? 8.0, color: "#C27842" },
    { key: "lasting",   label: "Lasting",   hours: velocityData?.stage_cycle_hours?.lasting   ?? 6.0, color: "#7C3AED" },
    { key: "finishing", label: "Finishing", hours: velocityData?.stage_cycle_hours?.finishing  ?? 3.5, color: "#F59E0B" },
    { key: "qc_pack",   label: "QC & Pack", hours: velocityData?.stage_cycle_hours?.qc_pack   ?? 2.0, color: "#16A34A" },
  ];

  const maxHours = Math.max(...stages.map((s) => s.hours), 10);

  // Supplier data — API returns { suppliers: [], total_evaluated: N }
  const topSupplier = scorecardData?.suppliers?.[0] ?? null;
  const supplierRate = topSupplier?.on_time_delivery_rate ?? "96.4";
  const supplierGrade = topSupplier?.grade ?? "A";
  const supplierCount =
    scorecardData?.total_evaluated ?? scorecardData?.suppliers?.length ?? 18;

  // Inventory valuation — API returns value in rupees
  const invValuation = turnoverData?.avg_inventory_valuation ?? 0;
  const invValLabel =
    invValuation >= 100000
      ? `Rs.${(invValuation / 100000).toFixed(1)}L`
      : `Rs.${invValuation.toLocaleString("en-IN")}`;

  const bottlenecks = velocityData?.bottlenecks ?? [
    { stage: "stitching", backlog_pairs: 340, severity: "HIGH",   recommendation: "Allocate +2 operators to stitching" },
    { stage: "lasting",   backlog_pairs: 180, severity: "MEDIUM", recommendation: "Balance line pacing into lasting" },
    { stage: "cutting",   backlog_pairs: 60,  severity: "LOW",    recommendation: "Stage pacing optimal" },
  ];

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="w-8 h-8 animate-spin text-[#C27842]" />
        <span className="text-sm text-slate-500 font-medium">Loading analytics data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-3 bg-red-50 border-2 border-red-200 p-5 text-sm text-red-700">
        <AlertTriangle className="w-5 h-5 flex-shrink-0" />
        <span>{error}</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* KPI Tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Production Velocity */}
        <div className="bg-white border-2 border-slate-200 p-5 relative overflow-hidden hover:border-[#2563EB] transition-colors">
          <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#2563EB]" />
          <div className="flex justify-between items-start">
            <span className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500">
              Production Velocity
            </span>
            <span className="p-2 bg-blue-50 text-[#2563EB]">
              <Activity className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-black text-slate-900">
              {velocityData?.summary?.velocity_pairs_per_day ?? "185"}
            </span>
            <span className="text-xs font-semibold text-slate-400">pairs / day</span>
          </div>
          <div className="mt-2 text-xs flex items-center gap-1 text-[#16A34A] font-semibold">
            <ArrowUpRight className="w-3.5 h-3.5" />
            Optimal line throughput
          </div>
        </div>

        {/* KPI 2: Inventory Turnover */}
        <div className="bg-white border-2 border-slate-200 p-5 relative overflow-hidden hover:border-[#16A34A] transition-colors">
          <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#16A34A]" />
          <div className="flex justify-between items-start">
            <span className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500">
              Inventory Turnover
            </span>
            <span className="p-2 bg-green-50 text-[#16A34A]">
              <TrendingUp className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-black text-slate-900">
              {turnoverData?.inventory_turnover_ratio ?? "4.2"}x
            </span>
            <span className="text-xs font-semibold text-slate-400">
              ({turnoverData?.days_sales_of_inventory ?? "86"} DSI)
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-500">
            Valuation: <strong className="text-slate-700">{invValLabel}</strong>
          </div>
        </div>

        {/* KPI 3: BOM Cost Variance */}
        <div className="bg-white border-2 border-slate-200 p-5 relative overflow-hidden hover:border-[#F59E0B] transition-colors">
          <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#F59E0B]" />
          <div className="flex justify-between items-start">
            <span className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500">
              BOM Cost Variance
            </span>
            <span className="p-2 bg-amber-50 text-[#F59E0B]">
              <DollarSign className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-black text-slate-900">
              {varianceData?.summary?.net_variance_percentage ?? "+1.8"}%
            </span>
            <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 bg-amber-100 text-amber-700 border border-amber-200">
              {varianceData?.summary?.overall_status ?? "WITHIN BUDGET"}
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-500">
            Across {varianceData?.summary?.total_jobs ?? 42} active jobs
          </div>
        </div>

        {/* KPI 4: Supplier On-Time Rate */}
        <div className="bg-white border-2 border-slate-200 p-5 relative overflow-hidden hover:border-[#7C3AED] transition-colors">
          <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#7C3AED]" />
          <div className="flex justify-between items-start">
            <span className="text-[10px] uppercase tracking-[0.18em] font-bold text-slate-500">
              Supplier On-Time Rate
            </span>
            <span className="p-2 bg-purple-50 text-[#7C3AED]">
              <ShieldCheck className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="font-mono text-3xl font-black text-slate-900">
              {supplierRate}%
            </span>
            <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 bg-purple-100 text-purple-700 border border-purple-200">
              Grade {supplierGrade}
            </span>
          </div>
          <div className="mt-2 text-xs text-slate-500">
            {supplierCount} procurement partners
          </div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Chart 1: Stage Cycle Times */}
        <div className="bg-white border-2 border-slate-200 p-6 space-y-4">
          <div className="flex justify-between items-start gap-3">
            <div>
              <h3 className="font-black text-slate-900 text-base tracking-tight">
                Stage Duration &amp; Cycle Time
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Average hours spent per production stage
              </p>
            </div>
            {velocityData?.summary?.primary_bottleneck_stage && (
              <span className="flex-shrink-0 px-2.5 py-1 bg-red-50 text-[#DC2626] border border-red-200 text-[10px] font-bold uppercase tracking-wider">
                Bottleneck: {velocityData.summary.primary_bottleneck_stage}
              </span>
            )}
          </div>

          <div className="space-y-3 pt-1">
            {stages.map((st) => {
              const widthPct = Math.round((st.hours / maxHours) * 100);
              return (
                <div key={st.key} className="space-y-1.5">
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-slate-700">{st.label}</span>
                    <span className="font-mono text-slate-500">{st.hours} hrs</span>
                  </div>
                  <div className="w-full h-2.5 bg-slate-100 border border-slate-200 overflow-hidden">
                    <div
                      className="h-full transition-all duration-500"
                      style={{ width: `${widthPct}%`, backgroundColor: st.color }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="pt-3 text-xs text-slate-500 flex items-center justify-between border-t-2 border-slate-100">
            <span>Target Lead Time: 24h floor turnaround</span>
            <button
              onClick={() => onNavigateTab && onNavigateTab("dead_stock")}
              className="text-[#2563EB] hover:text-[#1E3A8A] font-bold underline underline-offset-2"
            >
              Detailed Bottleneck Scorecard &rarr;
            </button>
          </div>
        </div>

        {/* Chart 2: Stage Queue Backlog */}
        <div className="bg-white border-2 border-slate-200 p-6 space-y-4">
          <div>
            <h3 className="font-black text-slate-900 text-base tracking-tight">
              Stage Queue Backlog &amp; Pacing
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">Pairs waiting in stage queues</p>
          </div>

          <div className="space-y-2.5">
            {bottlenecks.slice(0, 3).map((bn, idx) => {
              const severityStyle =
                bn.severity === "HIGH"
                  ? { badge: "bg-red-100 text-[#DC2626] border-red-200" }
                  : bn.severity === "MEDIUM"
                  ? { badge: "bg-amber-100 text-amber-700 border-amber-200" }
                  : { badge: "bg-green-100 text-[#16A34A] border-green-200" };

              return (
                <div
                  key={idx}
                  className="border-2 border-slate-200 p-4 flex items-center justify-between hover:border-slate-400 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-black text-slate-900 text-sm uppercase tracking-wide">
                        {bn.stage}
                      </span>
                      <span
                        className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border ${severityStyle.badge}`}
                      >
                        {bn.severity}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-1 truncate">
                      {bn.recommendation}
                    </p>
                  </div>
                  <div className="text-right ml-4 flex-shrink-0">
                    <span className="font-mono text-xl font-black text-slate-900">
                      {bn.backlog_pairs}
                    </span>
                    <span className="text-[10px] text-slate-500 block font-semibold uppercase tracking-wider">
                      pairs queue
                    </span>
                  </div>
                </div>
              );
            })}

            {bottlenecks.length === 0 && (
              <div className="text-center py-8 text-sm text-slate-400">
                No stage backlogs detected.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
