import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { http, inr } from "../lib/api";
import { Card, BtnPrimary, BtnSecondary, Input, Select, Badge, PaginationControls } from "./ui-kit";
import { Drawer } from "../pages/Materials";
import {
  Upload, RefreshCw, ScrollText, Download, Edit2, TrendingUp,
  Layers, Building2, SlidersHorizontal, AlertTriangle, CheckCircle2,
  ChevronDown, Search, ArrowUpRight, ArrowDownRight, Package, Truck,
  DollarSign, Percent, ShieldAlert, Award, RotateCcw, IndianRupee,
  Eye, Image as ImageIcon
} from "lucide-react";

// ═══════════════════════════════════════════════════════════════════════
// Classification Badges (Dry Run Preview)
// ═══════════════════════════════════════════════════════════════════════
function ClassificationBadges({ r }) {
  if (r.has_dispatch_discrepancy) {
    return (
      <div className="text-amber-800 text-[10px] leading-tight">
        <Badge color="orange">dispatch discrepancy</Badge>
        <div className="mt-1 max-w-[200px] text-amber-700 font-semibold">{r.discrepancy_reason || "Internal dispatch record found"}</div>
      </div>
    );
  }
  if (!r.matched) {
    return (
      <div className="text-red-700 text-[10px] leading-tight">
        <Badge color="red">unresolved</Badge>
        <div className="mt-1 max-w-[200px]">{r.exception_reason}</div>
      </div>
    );
  }
  if (r.is_net_sold) return <Badge color="green">net sold</Badge>;
  if (r.was_returned_to_stock) return <Badge color="red">returned · {r.return_reason}</Badge>;
  if (r.is_pending) return <Badge color="yellow">pending</Badge>;
  if (r.never_touched_inventory) return <Badge color="slate">never packed</Badge>;
  return <Badge color="slate">—</Badge>;
}

// ═══════════════════════════════════════════════════════════════════════
// Funnel Visualization
// ═══════════════════════════════════════════════════════════════════════
function FunnelViz({ stats, breakdown }) {
  const total = stats.total_rows ?? 0;
  const packed = stats.packed ?? 0;
  const returned = stats.returned_to_stock ?? 0;
  const pending = stats.pending ?? 0;
  const netSold = stats.net_sold ?? 0;
  const neverTouched = stats.never_touched_inventory ?? 0;
  const barW = (n) => (total > 0 ? Math.max(4, Math.round((Math.abs(n) / total) * 100)) : 0);

  const stages = [
    { label: "Total rows", count: total, color: "bg-slate-700", text: "text-white" },
    { label: "Never packed (ignore)", count: neverTouched, color: "bg-slate-300", text: "text-slate-800" },
    { label: "Packed", count: packed, color: "bg-blue-600", text: "text-white" },
    { label: "− Returned to stock", count: -returned, color: "bg-red-500", text: "text-white", sub: breakdown },
    { label: "− Still in transit", count: -pending, color: "bg-amber-400", text: "text-amber-900" },
    { label: "= Net sold", count: netSold, color: "bg-emerald-600", text: "text-white", emphasize: true },
  ];

  return (
    <div className="bg-white border-2 border-slate-200 rounded p-4 space-y-2">
      <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">Funnel</div>
      {stages.map((s) => (
        <div key={s.label} className={`flex items-center gap-3 ${s.emphasize ? "pt-2 mt-1 border-t border-slate-200" : ""}`}>
          <div className={`text-xs font-semibold ${s.emphasize ? "text-emerald-700" : "text-slate-700"}`} style={{ minWidth: 190 }}>
            {s.label}
          </div>
          <div className={`h-6 flex items-center px-2 font-mono text-xs font-bold ${s.color} ${s.text}`}
            style={{ width: `${Math.min(100, barW(s.count))}%`, minWidth: 40 }}>
            {s.count >= 0 ? s.count : `${s.count}`}
          </div>

          {s.sub && Object.values(s.sub).some((v) => v > 0) && (
            <div className="text-[10px] text-slate-500 font-mono ml-2 whitespace-nowrap">
              (rto: {s.sub.rto}, cust: {s.sub.customer_return}, cxl-post-pack: {s.sub.cancelled_after_pack})
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Operational Cost Adjustment Modal
// ═══════════════════════════════════════════════════════════════════════
function OperationalCostModal({ overview, isOpen, onClose, onSave }) {
  const currentOp = overview?.operational_expenses || {};
  const [rent, setRent] = useState(currentOp.factory_rent ?? 75000);
  const [electricity, setElectricity] = useState(currentOp.electricity_power ?? 20000);
  const [salaries, setSalaries] = useState(currentOp.staff_worker_salaries ?? 35000);
  const [otherBasic, setOtherBasic] = useState(currentOp.other_basic_sundry ?? 7500);
  const [allocationPct, setAllocationPct] = useState(currentOp.allocation_pct ?? 50);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (overview?.operational_expenses) {
      const op = overview.operational_expenses;
      setRent(op.factory_rent ?? 75000);
      setElectricity(op.electricity_power ?? 20000);
      setSalaries(op.staff_worker_salaries ?? 35000);
      setOtherBasic(op.other_basic_sundry ?? 7500);
      setAllocationPct(op.allocation_pct ?? 50);
    }
  }, [overview]);

  if (!isOpen) return null;

  const totalMonthly = Number(rent) + Number(electricity) + Number(salaries) + Number(otherBasic);
  const allocatedOverhead = Math.round(totalMonthly * (Number(allocationPct) / 100));

  const platformEarnings = overview?.platform_earnings ?? overview?.pnl_summary?.earnings_on_platform ?? 0;
  const totalCogs = overview?.total_cost_of_production ?? 0;
  const netSoldRev = overview?.net_sold_revenue ?? 0;
  const projectedNetProfit = Math.round(platformEarnings - totalCogs - allocatedOverhead);
  const projectedNetMargin = netSoldRev > 0 ? ((projectedNetProfit / netSoldRev) * 100).toFixed(2) : "0.00";
  const isProfit = projectedNetProfit >= 0;

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({
        platform: overview?.platform || "myntra",
        month: overview?.month,
        factory_rent: Number(rent),
        electricity_power: Number(electricity),
        staff_worker_salaries: Number(salaries),
        other_basic_sundry: Number(otherBasic),
        allocation_pct: Number(allocationPct),
      });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-lg w-full border border-slate-200 overflow-hidden">
        <div className="bg-slate-900 text-white px-5 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Building2 className="w-5 h-5 text-indigo-400" />
            <h3 className="font-bold text-sm">Monthly Operational Overhead Allocation</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-lg font-bold">✕</button>
        </div>

        <form onSubmit={handleSave} className="p-5 space-y-4 text-xs">
          <p className="text-slate-600 text-xs leading-relaxed">
            Configure factory & warehouse fixed operational costs. SSK ERP applies the designated allocation percentage (default <strong>50%</strong>) against online marketplace sales to determine <strong>Actual Net Business Profit</strong>.
          </p>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-bold text-slate-700 mb-1 text-[11px]">Factory & Warehouse Rent (₹)</label>
              <input
                type="number"
                step="100"
                value={rent}
                onChange={(e) => setRent(e.target.value)}
                className="w-full px-3 py-1.5 border border-slate-300 rounded font-mono text-sm focus:outline-none focus:border-slate-800"
                required
              />
            </div>
            <div>
              <label className="block font-bold text-slate-700 mb-1 text-[11px]">Electricity & Power (₹)</label>
              <input
                type="number"
                step="50"
                value={electricity}
                onChange={(e) => setElectricity(e.target.value)}
                className="w-full px-3 py-1.5 border border-slate-300 rounded font-mono text-sm focus:outline-none focus:border-slate-800"
                required
              />
            </div>
            <div>
              <label className="block font-bold text-slate-700 mb-1 text-[11px]">Staff & Worker Salaries (₹)</label>
              <input
                type="number"
                step="100"
                value={salaries}
                onChange={(e) => setSalaries(e.target.value)}
                className="w-full px-3 py-1.5 border border-slate-300 rounded font-mono text-sm focus:outline-none focus:border-slate-800"
                required
              />
            </div>
            <div>
              <label className="block font-bold text-slate-700 mb-1 text-[11px]">Other Factory Basic Sundry (₹)</label>
              <input
                type="number"
                step="50"
                value={otherBasic}
                onChange={(e) => setOtherBasic(e.target.value)}
                className="w-full px-3 py-1.5 border border-slate-300 rounded font-mono text-sm focus:outline-none focus:border-slate-800"
                required
              />
            </div>
          </div>

          <div className="bg-slate-50 border border-slate-200 p-3 rounded space-y-2">
            <div className="flex items-center justify-between">
              <label className="font-bold text-slate-800 text-[11px]">Online Channel Allocation %</label>
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={allocationPct}
                  onChange={(e) => setAllocationPct(e.target.value)}
                  className="w-14 px-2 py-0.5 border border-slate-300 rounded text-right font-mono font-bold"
                />
                <span className="font-bold text-slate-600">%</span>
              </div>
            </div>
            <input
              type="range"
              min="1"
              max="100"
              value={allocationPct}
              onChange={(e) => setAllocationPct(Number(e.target.value))}
              className="w-full accent-indigo-600 cursor-pointer"
            />
          </div>

          <div className="bg-indigo-50/70 border-2 border-indigo-200 rounded p-3 text-xs space-y-2">
            <div className="flex justify-between text-slate-700">
              <span>Total Monthly Factory Cost:</span>
              <span className="font-mono font-bold">₹{totalMonthly.toLocaleString()}</span>
            </div>
            <div className="flex justify-between text-indigo-900 font-semibold border-b border-indigo-200 pb-1.5">
              <span>Allocated Overhead ({allocationPct}%):</span>
              <span className="font-mono font-bold text-indigo-700">₹{allocatedOverhead.toLocaleString()}</span>
            </div>
            <div className="flex justify-between items-center pt-0.5">
              <span className="font-bold text-slate-800">Projected Actual Net Profit:</span>
              <span className={`font-mono font-black text-sm ${isProfit ? "text-emerald-700" : "text-rose-700"}`}>
                ₹{projectedNetProfit.toLocaleString()} ({projectedNetMargin}%)
              </span>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
            <BtnSecondary type="button" onClick={onClose} disabled={saving}>Cancel</BtnSecondary>
            <BtnPrimary type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save & Recalculate Profit"}
            </BtnPrimary>
          </div>
        </form>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Monthly Style Overview Table with Inline Cost Editing
// ═══════════════════════════════════════════════════════════════════════
function MonthlyStyleOverviewTable({ overview, onUpdateCost, readOnly = false }) {
  const [search, setSearch] = useState("");
  const [editingStyle, setEditingStyle] = useState(null);
  const [editCost, setEditCost] = useState("");
  const [saving, setSaving] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);

  const styles = useMemo(() => {
    const list = overview?.styles || [];
    if (!search.trim()) return list;
    const q = search.toLowerCase().trim();
    return list.filter(
      (s) =>
        s.style_code?.toLowerCase().includes(q) ||
        s.myntra_style_id?.toLowerCase().includes(q) ||
        s.erp_style_code?.toLowerCase().includes(q) ||
        s.brand?.toLowerCase().includes(q) ||
        s.style_name?.toLowerCase().includes(q) ||
        s.article_type?.toLowerCase().includes(q)
    );
  }, [overview, search]);

  const handleStartEdit = (s) => {
    setEditingStyle(s.style_code);
    setEditCost(String(s.unit_production_cost ?? 210));
  };

  const handleSaveEdit = async (s) => {
    if (!onUpdateCost) return;
    const numVal = parseFloat(editCost);
    if (isNaN(numVal) || numVal < 0) return;
    setSaving(true);
    try {
      await onUpdateCost(s.style_code, numVal);
      setEditingStyle(null);
    } finally {
      setSaving(false);
    }
  };

  const exportCsv = () => {
    if (!styles.length) return;
    const headers = [
      "Style Code", "Myntra Style ID", "ERP Style Code", "Brand", "Style Name", "Article Type", "Colors", "Sizes Breakdown",
      "Total Orders", "Packed Qty", "Returned Qty", "RTO Qty", "Cancelled Qty", "Net Sold Qty",
      "Return Rate %", "Total Seller Price", "Net Sold Seller Price", "Unit Production Cost",
      "Total Production Cost", "Gross Profit", "Margin %"
    ];
    const csvRows = styles.map((s) => [
      `"${s.style_code}"`,
      `"${s.myntra_style_id || ""}"`,
      `"${s.erp_style_code || ""}"`,
      `"${s.brand || ""}"`,
      `"${(s.style_name || "").replace(/"/g, '""')}"`,
      `"${s.article_type || ""}"`,
      `"${(s.colors || []).join(", ")}"`,
      `"${Object.entries(s.sizes || {}).map(([sz, qty]) => `${sz}:${qty}`).join("; ")}"`,
      s.total_orders,
      s.packed_qty,
      s.returned_qty,
      s.rto_qty,
      s.cancelled_qty,
      s.net_sold_qty,
      s.return_rate_pct ?? 0,
      s.total_seller_price,
      s.net_sold_seller_price,
      s.unit_production_cost,
      s.total_production_cost,
      s.gross_profit,
      s.margin_pct,
    ]);
    const csvContent = [headers.join(","), ...csvRows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `monthly_reconciliation_${overview?.platform || "all"}_${overview?.month || "overview"}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-1 max-w-md">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search style (e.g. FL_DB_016), Myntra ID, ERP code, brand, article…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-white border border-slate-300 rounded focus:border-slate-800 focus:outline-none"
            />
          </div>
          {search && (
            <button onClick={() => setSearch("")} className="text-xs text-slate-500 hover:text-slate-800 underline">
              Clear
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-slate-500 font-semibold">
            {styles.length} of {overview?.styles_count ?? styles.length} styles
          </span>
          <button
            onClick={exportCsv}
            disabled={!styles.length}
            className="px-2.5 py-1 text-xs font-semibold bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 rounded inline-flex items-center gap-1.5 transition-colors"
          >
            <Download className="w-3.5 h-3.5" /> Export CSV
          </button>
        </div>
      </div>

      <div className="border-2 border-slate-200 rounded overflow-hidden">
        <div className="max-h-[500px] overflow-y-auto overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-100 sticky top-0 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                <th className="text-left p-2.5 border-b sticky left-0 z-10 bg-slate-100 min-w-[280px]">Style & Codes / Article</th>
                <th className="text-left p-2.5 border-b">Colors</th>
                <th className="text-left p-2.5 border-b">Grouped Sizes</th>
                <th className="text-right p-2.5 border-b">Packed</th>
                <th className="text-right p-2.5 border-b">Ret / RTO</th>
                <th className="text-right p-2.5 border-b font-bold text-emerald-800">Net Sold</th>
                <th className="text-right p-2.5 border-b">Unit Cost (₹)</th>
                <th className="text-right p-2.5 border-b">Total COGS</th>
                <th className="text-right p-2.5 border-b">Net Revenue</th>
                <th className="text-right p-2.5 border-b">Gross Profit</th>
                <th className="text-right p-2.5 border-b">Margin %</th>
              </tr>
            </thead>
            <tbody>
              {styles.map((s) => {
                const isEditing = editingStyle === s.style_code;
                const isProfit = (s.gross_profit ?? 0) >= 0;
                return (
                  <tr key={s.style_code} className="border-b border-slate-100 hover:bg-slate-50/80">
                    <td className="p-2.5 sticky left-0 z-10 bg-white min-w-[280px]">
                      <div className="flex items-center gap-3">
                        {/* Style Photo Thumbnail with click-to-preview */}
                        <div
                          className="relative w-12 h-12 rounded border border-slate-300 bg-slate-50 overflow-hidden shadow-sm shrink-0 cursor-pointer group"
                          onClick={() => s.image_url && setPreviewImage(s.image_url)}
                          title="Click to view full style photo"
                        >
                          {s.image_url ? (
                            <img
                              src={s.image_url}
                              alt={s.style_code}
                              className="w-full h-full object-cover transition-transform group-hover:scale-110"
                            />
                          ) : (
                            <div className="w-full h-full flex flex-col items-center justify-center bg-slate-100 text-slate-400">
                              <ImageIcon className="w-4 h-4" />
                            </div>
                          )}
                          <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white">
                            <Eye className="w-3.5 h-3.5" />
                          </div>
                        </div>

                        {/* Style Details & Identifiers */}
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-mono font-bold text-slate-900 text-[13px]">{s.style_code}</span>
                            {s.brand && (
                              <span className="text-[9px] uppercase tracking-wider font-bold text-indigo-700 bg-indigo-50 px-1 py-0.5 rounded border border-indigo-200">
                                {s.brand}
                              </span>
                            )}
                          </div>

                          {/* Myntra Style ID & ERP Style Code badges */}
                          <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                            {s.myntra_style_id ? (
                              <span
                                className="text-[10px] font-mono font-bold text-amber-900 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200 inline-flex items-center gap-1"
                                title="Myntra Marketplace Style ID"
                              >
                                <span className="text-amber-600 font-semibold">Myntra ID:</span>
                                {s.myntra_style_id}
                              </span>
                            ) : (
                              <span className="text-[10px] font-mono text-slate-400 bg-slate-50 px-1 py-0.5 rounded border border-slate-200">
                                Myntra ID: —
                              </span>
                            )}

                            {s.erp_style_code ? (
                              <span
                                className="text-[10px] font-mono font-bold text-emerald-900 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200 inline-flex items-center gap-1"
                                title="Internal SSK ERP Style Code"
                              >
                                <span className="text-emerald-700 font-semibold">ERP:</span>
                                {s.erp_style_code}
                              </span>
                            ) : (
                              <span
                                className="text-[10px] font-mono text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200"
                                title="ERP Style Code"
                              >
                                ERP: {s.style_code.startsWith("SSK") ? s.style_code : "Unmapped"}
                              </span>
                            )}
                          </div>

                          <div className="text-[11px] text-slate-600 max-w-[220px] truncate" title={s.style_name}>
                            {s.style_name || s.style_code}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="p-2.5">
                      <div className="flex flex-wrap gap-1 max-w-[120px]">
                        {(s.colors || []).map((col) => (
                          <span key={col} className="text-[10px] font-mono px-1.5 py-0.5 bg-slate-100 border border-slate-200 rounded font-semibold text-slate-700">
                            {col}
                          </span>
                        ))}
                        {(!s.colors || s.colors.length === 0) && <span className="text-slate-400">—</span>}
                      </div>
                    </td>
                    <td className="p-2.5">
                      <div className="flex flex-wrap gap-1 max-w-[220px]">
                        {Object.entries(s.sizes || {}).map(([sz, count]) => (
                          <span
                            key={sz}
                            className="inline-flex items-center text-[10px] font-mono px-1.5 py-0.5 bg-blue-50 border border-blue-200 text-blue-900 rounded font-bold"
                            title={`Size ${sz}: ${count} units`}
                          >
                            <span className="font-semibold text-blue-700">{sz}:</span>
                            <span className="ml-1 text-slate-900">{count}</span>
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="p-2.5 text-right font-mono text-slate-700 font-semibold">{s.packed_qty}</td>
                    <td className="p-2.5 text-right font-mono text-rose-700">
                      {s.returned_qty + s.rto_qty}
                      <span className="text-[10px] text-slate-400 ml-1">({s.returned_qty}r/{s.rto_qty}o)</span>
                    </td>
                    <td className="p-2.5 text-right font-mono font-black text-emerald-700 bg-emerald-50/40 text-[13px]">
                      {s.net_sold_qty}
                    </td>
                    <td className="p-2.5 text-right font-mono">
                      {isEditing ? (
                        <div className="flex items-center justify-end gap-1">
                          <input
                            type="number"
                            step="0.01"
                            value={editCost}
                            onChange={(e) => setEditCost(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleSaveEdit(s);
                              if (e.key === "Escape") setEditingStyle(null);
                            }}
                            className="w-16 px-1 py-0.5 text-xs text-right border border-slate-400 rounded focus:outline-none focus:ring-1 focus:ring-emerald-500"
                            autoFocus
                            disabled={saving}
                          />
                          <button
                            onClick={() => handleSaveEdit(s)}
                            disabled={saving}
                            className="px-1.5 py-0.5 bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] font-bold rounded transition-colors disabled:opacity-50"
                            title="Save (Enter)"
                          >
                            {saving ? "…" : "✓"}
                          </button>
                          <button
                            onClick={() => setEditingStyle(null)}
                            disabled={saving}
                            className="px-1.5 py-0.5 bg-slate-300 hover:bg-slate-400 text-slate-700 text-[10px] font-bold rounded transition-colors"
                            title="Cancel (Esc)"
                          >
                            ✕
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-1">
                          <span>₹{(s.unit_production_cost ?? 210).toFixed(2)}</span>
                          {!readOnly && onUpdateCost && (
                            <button
                              onClick={() => handleStartEdit(s)}
                              className="text-slate-400 hover:text-slate-700 p-0.5 rounded"
                              title="Edit unit production cost"
                            >
                              <Edit2 className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="p-2.5 text-right font-mono text-slate-700 font-semibold">
                      ₹{Math.round(s.total_production_cost || 0).toLocaleString()}
                    </td>
                    <td className="p-2.5 text-right font-mono text-slate-900 font-semibold">
                      ₹{Math.round(s.net_sold_seller_price || 0).toLocaleString()}
                    </td>
                    <td className={`p-2.5 text-right font-mono font-bold ${isProfit ? "text-emerald-700" : "text-rose-700"}`}>
                      ₹{Math.round(s.gross_profit || 0).toLocaleString()}
                    </td>
                    <td className="p-2.5 text-right font-mono">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        (s.margin_pct ?? 0) >= 20
                          ? "bg-emerald-100 text-emerald-800"
                          : (s.margin_pct ?? 0) > 0
                          ? "bg-amber-100 text-amber-800"
                          : "bg-rose-100 text-rose-800"
                      }`}>
                        {s.margin_pct}%
                      </span>
                    </td>
                  </tr>
                );
              })}
              {styles.length === 0 && (
                <tr>
                  <td colSpan={11} className="p-6 text-center text-sm text-slate-400 italic">
                    No styles match the current search filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── IMAGE ENLARGED MODAL PREVIEW ─────────────────────────── */}
      {previewImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setPreviewImage(null)}
        >
          <div className="relative max-w-lg max-h-[85vh] bg-white rounded p-3 shadow-2xl space-y-2" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b pb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-700">Style Photo Preview</span>
              <button
                type="button"
                onClick={() => setPreviewImage(null)}
                className="w-6 h-6 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold flex items-center justify-center"
              >
                ✕
              </button>
            </div>
            <img src={previewImage} alt="Style Preview" className="max-w-full max-h-[75vh] rounded object-contain mx-auto" />
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Monthly SKU Bifurcation Drilldown Table
// ═══════════════════════════════════════════════════════════════════════
function MonthlySkuBifurcationTable({ skuList = [], overview = null }) {
  const [search, setSearch] = useState("");
  const [filterMapped, setFilterMapped] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [previewImage, setPreviewImage] = useState(null);

  // Map style metadata (photo, ERP code, Myntra style ID, brand) from overview.styles
  const styleMap = useMemo(() => {
    const map = new Map();
    (overview?.styles || []).forEach((st) => {
      if (st.style_code) {
        map.set(st.style_code.toLowerCase().trim(), st);
      }
    });
    return map;
  }, [overview]);

  const filtered = useMemo(() => {
    let list = skuList;
    if (filterMapped === "mapped") list = list.filter((s) => s.is_mapped);
    if (filterMapped === "unmapped") list = list.filter((s) => !s.is_mapped);
    if (!search.trim()) return list;
    const q = search.toLowerCase().trim();
    return list.filter((s) => {
      const st = styleMap.get(s.style_root?.toLowerCase()?.trim()) || {};
      const erp = s.erp_style_code || st.erp_style_code || "";
      const myntra = s.myntra_style_id || st.myntra_style_id || "";
      return (
        s.sku_code?.toLowerCase().includes(q) ||
        s.style_root?.toLowerCase().includes(q) ||
        erp.toLowerCase().includes(q) ||
        myntra.toLowerCase().includes(q) ||
        s.brand?.toLowerCase().includes(q) ||
        st.brand?.toLowerCase().includes(q) ||
        s.color?.toLowerCase().includes(q) ||
        s.size?.toLowerCase().includes(q)
      );
    });
  }, [skuList, search, filterMapped, styleMap]);

  useEffect(() => { setPage(1); }, [search, filterMapped]);

  const paginated = useMemo(() => {
    if (pageSize === "all") return filtered;
    const start = (page - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page, pageSize]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 flex-1 max-w-md">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search SKU code, root style, color, size…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-white border border-slate-300 rounded focus:border-slate-800 focus:outline-none"
            />
          </div>
          {search && (
            <button onClick={() => setSearch("")} className="text-xs text-slate-500 hover:text-slate-800 underline">
              Clear
            </button>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 text-xs">
            <span className="text-slate-500 font-semibold">Mapping:</span>
            <button
              onClick={() => setFilterMapped("all")}
              className={`px-2 py-0.5 rounded text-[11px] font-semibold ${filterMapped === "all" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"}`}
            >
              All ({skuList.length})
            </button>
            <button
              onClick={() => setFilterMapped("mapped")}
              className={`px-2 py-0.5 rounded text-[11px] font-semibold ${filterMapped === "mapped" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600"}`}
            >
              Mapped ({skuList.filter((s) => s.is_mapped).length})
            </button>
            <button
              onClick={() => setFilterMapped("unmapped")}
              className={`px-2 py-0.5 rounded text-[11px] font-semibold ${filterMapped === "unmapped" ? "bg-amber-600 text-white" : "bg-slate-100 text-slate-600"}`}
            >
              Fallback ({skuList.filter((s) => !s.is_mapped).length})
            </button>
          </div>
          <span className="text-xs font-mono text-slate-500 font-semibold">
            {filtered.length} SKUs
          </span>
        </div>
      </div>

      <div className="border-2 border-slate-200 rounded overflow-hidden">
        <div className="max-h-[500px] overflow-y-auto overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-100 sticky top-0 text-[10px] uppercase tracking-wider text-slate-600">
              <tr>
                <th className="text-left p-2.5 border-b sticky left-0 z-10 bg-slate-100 min-w-[280px]">SKU Code & Style Identifiers</th>
                <th className="text-left p-2.5 border-b">Root Style</th>
                <th className="text-center p-2.5 border-b">Color</th>
                <th className="text-center p-2.5 border-b">Size</th>
                <th className="text-right p-2.5 border-b">Gross / Ret</th>
                <th className="text-right p-2.5 border-b font-bold text-emerald-800">Net Sold</th>
                <th className="text-right p-2.5 border-b">Net Sales</th>
                <th className="text-right p-2.5 border-b">Platform Fees</th>
                <th className="text-right p-2.5 border-b">Payout</th>
                <th className="text-right p-2.5 border-b">Unit Cost</th>
                <th className="text-right p-2.5 border-b">COGS</th>
                <th className="text-right p-2.5 border-b">Contribution</th>
                <th className="text-right p-2.5 border-b">Margin %</th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((sk, idx) => {
                const isPositive = (sk.contribution_after_platform ?? 0) >= 0;
                const st = styleMap.get(sk.style_root?.toLowerCase()?.trim()) || {};
                const imgUrl = sk.image_url || st.image_url || null;
                const styleCode = sk.style_root || st.style_code || "—";
                const erpCode = sk.erp_style_code || st.erp_style_code || (styleCode.startsWith("SSK") ? styleCode : "");
                const myntraId = sk.myntra_style_id || st.myntra_style_id || "";
                const brandName = sk.brand || st.brand || "";

                return (
                  <tr key={sk.sku_code || idx} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="p-2.5 sticky left-0 z-10 bg-white min-w-[280px]">
                      <div className="flex items-center gap-2.5">
                        {/* Style Photo Thumbnail with click-to-preview */}
                        <div
                          className="relative w-10 h-10 rounded border border-slate-300 bg-slate-50 overflow-hidden shadow-sm shrink-0 cursor-pointer group"
                          onClick={() => imgUrl && setPreviewImage(imgUrl)}
                          title="Click to view full style photo"
                        >
                          {imgUrl ? (
                            <img
                              src={imgUrl}
                              alt={styleCode}
                              className="w-full h-full object-cover transition-transform group-hover:scale-110"
                            />
                          ) : (
                            <div className="w-full h-full flex flex-col items-center justify-center bg-slate-100 text-slate-400">
                              <ImageIcon className="w-4 h-4" />
                            </div>
                          )}
                          <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white">
                            <Eye className="w-3 h-3" />
                          </div>
                        </div>

                        <div className="space-y-0.5 min-w-0">
                          <div className="font-mono font-bold text-slate-900 text-xs">{sk.sku_code}</div>
                          <div className="flex items-center gap-1 flex-wrap">
                            <span className="text-[10px] font-mono font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 rounded px-1.5 py-0.5" title="Style Code">
                              {`Style: ${styleCode}`}
                            </span>
                            {erpCode ? (
                              <span className="text-[10px] font-mono font-bold text-emerald-800 bg-emerald-50 border border-emerald-200 rounded px-1.5 py-0.5" title="Internal ERP Style Code">
                                {`ERP: ${erpCode}`}
                              </span>
                            ) : (
                              <span className="text-[10px] font-mono text-slate-400 bg-slate-50 border border-slate-200 rounded px-1.5 py-0.5" title="ERP Style Code">
                                ERP: Unmapped
                              </span>
                            )}
                            {myntraId && (
                              <span className="text-[9px] font-mono font-bold text-amber-800 bg-amber-50 border border-amber-200 rounded px-1 py-0.5" title="Myntra Marketplace Style ID">
                                {`ID: ${myntraId}`}
                              </span>
                            )}
                          </div>
                          {brandName && (
                            <div className="text-[9px] text-slate-400 uppercase font-semibold">{brandName}</div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="p-2.5 font-mono">
                      {sk.is_mapped ? (
                        <span className="text-indigo-700 font-bold bg-indigo-50 border border-indigo-200 rounded px-1.5 py-0.5 text-[11px]">
                          {sk.style_root}
                        </span>
                      ) : (
                        <span className="text-slate-500 font-semibold">{sk.style_root || "—"}</span>
                      )}
                      {myntraId && (
                        <div className="text-[10px] text-amber-800 font-mono mt-0.5 font-bold">ID: {myntraId}</div>
                      )}
                      {erpCode && (
                        <div className="text-[10px] text-emerald-700 font-mono mt-0.5 font-bold">ERP: {erpCode}</div>
                      )}
                    </td>
                    <td className="p-2 text-center font-mono">
                      {sk.color ? (
                        <span className="px-1.5 py-0.5 bg-slate-100 border border-slate-200 rounded text-[10px] font-semibold text-slate-700">
                          {sk.color}
                        </span>
                      ) : "—"}
                    </td>
                    <td className="p-2 text-center font-mono font-bold text-blue-900">
                      {sk.size ? (
                        <span className="px-1.5 py-0.5 bg-blue-50 border border-blue-200 rounded text-[10px]">
                          {sk.size}
                        </span>
                      ) : "—"}
                    </td>
                    <td className="p-2 text-right font-mono text-[11px] text-slate-600">
                      {sk.gross_units} / <span className="text-rose-600">{sk.returns_units}</span>
                    </td>
                    <td className="p-2 text-right font-mono font-black text-emerald-800 bg-emerald-50/40 text-[12px]">
                      {sk.net_units}
                    </td>
                    <td className="p-2 text-right font-mono text-slate-900 font-semibold">
                      ₹{Math.round(sk.net_sales || 0).toLocaleString()}
                    </td>
                    <td className="p-2 text-right font-mono text-rose-700">
                      ₹{Math.round(sk.platform_expenses || 0).toLocaleString()}
                    </td>
                    <td className="p-2 text-right font-mono text-slate-800 font-semibold">
                      ₹{Math.round(sk.platform_earnings || 0).toLocaleString()}
                    </td>
                    <td className="p-2 text-right font-mono text-slate-700">
                      ₹{(sk.unit_production_cost ?? 210).toFixed(2)}
                    </td>
                    <td className="p-2 text-right font-mono text-slate-700">
                      ₹{Math.round(sk.total_production_cost || 0).toLocaleString()}
                    </td>
                    <td className={`p-2 text-right font-mono font-black ${isPositive ? "text-emerald-700" : "text-rose-700"}`}>
                      ₹{Math.round(sk.contribution_after_platform || 0).toLocaleString()}
                    </td>
                    <td className="p-2 text-right font-mono">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        (sk.margin_pct ?? 0) >= 20
                          ? "bg-emerald-100 text-emerald-800"
                          : (sk.margin_pct ?? 0) > 0
                          ? "bg-amber-100 text-amber-800"
                          : "bg-rose-100 text-rose-800"
                      }`}>
                        {sk.margin_pct}%
                      </span>
                    </td>
                  </tr>
                );
              })}
              {paginated.length === 0 && (
                <tr>
                  <td colSpan={13} className="p-6 text-center text-sm text-slate-400 italic">
                    No SKUs match the current filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="p-2.5 bg-slate-50 border-t border-slate-200">
          <PaginationControls
            currentPage={page}
            totalItems={filtered.length}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
            pageSizeOptions={[25, 50, 100, 200]}
            allowAll
            rangeTextFormat="compact"
            showFirstLast={false}
            className="pt-0 border-t-0"
          />
        </div>
      </div>

      {/* ── IMAGE ENLARGED MODAL PREVIEW ─────────────────────────── */}
      {previewImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setPreviewImage(null)}
        >
          <div className="relative max-w-lg max-h-[85vh] bg-white rounded p-3 shadow-2xl space-y-2" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b pb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-700">Style Photo Preview</span>
              <button
                type="button"
                onClick={() => setPreviewImage(null)}
                className="w-6 h-6 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold flex items-center justify-center"
              >
                ✕
              </button>
            </div>
            <img src={previewImage} alt="Style Preview" className="max-w-full max-h-[75vh] rounded object-contain mx-auto" />
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Monthly Report Import Drawer
// ═══════════════════════════════════════════════════════════════════════
function MonthlyReportDrawer({ onClose, onDone }) {
  const [platform, setPlatform] = useState("myntra");
  const [file, setFile] = useState(null);
  const [step, setStep] = useState("choose");
  const [preview, setPreview] = useState(null);
  const [committing, setCommitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef();

  const handleFileChange = (e) => {
    const chosen = e.target.files[0] || null;
    setFile(chosen);
    if (chosen?.name) {
      const lower = chosen.name.toLowerCase();
      if (lower.includes("flipkart")) {
        setPlatform("flipkart");
      } else if (lower.includes("pnlreport") || lower.includes("myntra")) {
        setPlatform("myntra");
      }
    }
  };

  async function runPreview() {
    setError("");
    if (!file) return setError("Please select a file.");
    setPreviewing(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await http.post(
        `/online-orders/monthly-report-import?platform=${encodeURIComponent(platform)}&dry_run=true`,
        fd
      );
      setPreview(r.data);
      setStep("preview");
    } catch (e) {
      const raw = e.response?.data?.detail;
      setError(typeof raw === "string" ? raw : (raw?.[0]?.msg || e.message || "Preview failed."));
    } finally {
      setPreviewing(false);
    }
  }

  async function runCommit() {
    setError("");
    setCommitting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await http.post(
        `/online-orders/monthly-report-import?platform=${encodeURIComponent(platform)}&dry_run=false`,
        fd
      );
      setStep("done");
      onDone();
    } catch (e) {
      const raw = e.response?.data?.detail;
      setError(typeof raw === "string" ? raw : (raw?.[0]?.msg || e.message || "Commit failed."));
    } finally {
      setCommitting(false);
    }
  }

  function reset() {
    setPreview(null);
    setStep("choose");
    setError("");
    setFile(null);
  }

  return (
    <Drawer
      onClose={onClose}
      title={
        step === "choose" ? "Import Monthly Marketplace PnL Report" :
          step === "preview" ? "Review & Commit Monthly Reconciliation" :
            "Monthly Reconciliation Completed"
      }
      width="max-w-6xl"
    >
      <div className="space-y-5">
        {step === "choose" && (
          <>
            <div className="bg-indigo-50 border-2 border-indigo-200 px-4 py-3 text-sm text-indigo-900 rounded">
              <div className="font-bold mb-1 flex items-center gap-2">
                <ScrollText className="w-4 h-4 text-indigo-700" /> Dedicated Marketplace Monthly PnL & Financial Reconciliation
              </div>
              <div className="text-xs leading-snug space-y-1">
                <div>
                  Upload official Myntra (<span className="font-mono font-bold">PnLReport_*.xlsx</span>) or Flipkart (<span className="font-mono font-bold">flipkartPnL.xlsx</span>) PnL reports to automatically parse platform summaries, SKU metrics, and return financials.
                </div>
                <div className="text-indigo-800 font-semibold pt-0.5">
                  • Style Master COGS: Calculates direct manufacturing production cost per net unit sold.
                </div>
                <div className="text-indigo-800 font-semibold">
                  • Actual Net Profit: Applies 50% factory operational overhead (Rent, Electricity, Salaries, and Sundry) to compute true net business profit.
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Platform *</label>
                <select
                  value={platform}
                  onChange={(e) => setPlatform(e.target.value)}
                  className="w-full border border-slate-300 rounded px-2.5 py-1.5 text-xs font-semibold bg-white text-slate-800"
                >
                  <option value="myntra">Myntra</option>
                  <option value="flipkart">Flipkart</option>
                  <option value="nykaa">Nykaa</option>
                  <option value="amazon">Amazon</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Upload PnL Spreadsheet (.xlsx / .csv) *</label>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  onChange={handleFileChange}
                  className="block w-full text-xs text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-slate-900 file:text-white hover:file:bg-slate-800"
                />
              </div>
            </div>

            {error && (
              <div className="bg-red-50 border-2 border-red-300 text-red-800 px-3 py-2 text-xs rounded font-semibold flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
              <BtnPrimary onClick={runPreview} disabled={previewing || !file}>
                <span className="flex items-center gap-2">
                  <Upload className="w-4 h-4" />
                  {previewing ? "Analyzing Report…" : "Analyze & Preview"}
                </span>
              </BtnPrimary>
            </div>
          </>
        )}

        {step === "preview" && preview && (
          <div className="space-y-4">
            <div className="bg-emerald-50 border border-emerald-300 p-3 rounded text-xs flex justify-between items-center text-emerald-900">
              <div>
                Report preview ready for <strong>{preview.platform?.toUpperCase()}</strong> ({preview.month || "Current Month"}).
                Found <strong>{preview.style_overview?.styles_count || 0} styles</strong> across <strong>{preview.total_rows || 0} SKU lines</strong>.
              </div>
              <button onClick={reset} className="text-xs font-bold underline text-emerald-800">
                Choose another file
              </button>
            </div>

            {preview.funnel && (
              <FunnelViz stats={preview.funnel} breakdown={preview.funnel?.return_reasons} />
            )}

            {preview.style_overview && (
              <MonthlyStyleOverviewTable overview={preview.style_overview} readOnly />
            )}

            {error && (
              <div className="bg-red-50 border-2 border-red-300 text-red-800 px-3 py-2 text-xs rounded font-semibold">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <BtnSecondary onClick={reset} disabled={committing}>Back</BtnSecondary>
              <BtnPrimary onClick={runCommit} disabled={committing}>
                <span className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" />
                  {committing ? "Committing Reconciliation…" : "Commit Reconciliation to Database"}
                </span>
              </BtnPrimary>
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="py-12 text-center space-y-4">
            <div className="w-12 h-12 bg-emerald-100 text-emerald-700 rounded-full flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-slate-900">Reconciliation Committed Successfully!</h3>
            <p className="text-xs text-slate-600 max-w-md mx-auto">
              The monthly marketplace PnL, style costs, return metrics, and true net business margins are now synchronized.
            </p>
            <div className="pt-2">
              <BtnPrimary onClick={onClose}>Close & View Dashboard</BtnPrimary>
            </div>
          </div>
        )}
      </div>
    </Drawer>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Main MonthlyPnLReconciliation Component
// ═══════════════════════════════════════════════════════════════════════
export default function MonthlyPnLReconciliation() {
  const [platform, setPlatform] = useState("");
  const [month, setMonth] = useState("");
  const [data, setData] = useState(null);
  const [recSummary, setRecSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeSubTab, setActiveSubTab] = useState("overview"); // "overview" | "styles" | "skus" | "returns_deductions"
  const [showOpModal, setShowOpModal] = useState(false);
  const [showImportDrawer, setShowImportDrawer] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const params = new URLSearchParams();
      if (platform) params.append("platform", platform);
      if (month) params.append("month", month);
      const [r, recRes] = await Promise.allSettled([
        http.get(`/online-orders/reconciliation-summary?${params.toString()}`),
        http.get("/online-reconciliation/summary"),
      ]);
      if (r.status === "fulfilled") {
        setData(r.value.data);
      } else if (!silent) {
        setData(null);
      }
      if (recRes.status === "fulfilled") {
        setRecSummary(recRes.value.data);
      } else if (!silent) {
        setRecSummary(null);
      }
    } catch {
      if (!silent) {
        setData(null);
        setRecSummary(null);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, [platform, month]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleUpdateCost = async (style_code, new_cost) => {
    if (!data?.overview) return;
    try {
      const res = await http.put("/online-orders/monthly-reconciliation-overview/cost", {
        platform: data.overview.platform,
        month: data.overview.month,
        style_code,
        unit_production_cost: new_cost,
      });
      // In-place update: directly update data.overview with recalculated stats from backend
      if (res?.data) {
        setData((prev) => (prev ? { ...prev, overview: res.data } : prev));
      }
    } catch (e) {
      alert(e.response?.data?.detail || "Failed to update style production cost");
    }
  };

  const handleUpdateOperationalCost = async (payload) => {
    try {
      const res = await http.put("/online-orders/monthly-reconciliation-overview/operational-cost", payload);
      // In-place update: directly update data.overview with recalculated stats from backend
      if (res?.data) {
        setData((prev) => (prev ? { ...prev, overview: res.data } : prev));
      }
    } catch (e) {
      alert(e.response?.data?.detail || "Failed to update operational expenses");
    }
  };

  const overview = data?.overview;
  const returnAnalytics = overview?.return_analytics;
  const profitRankings = overview?.profit_rankings;
  const feeBreakdown = overview?.platform_fee_breakdown;

  const actualNetProfit = overview?.actual_net_profit ?? Math.round(
    (overview?.platform_earnings || overview?.pnl_summary?.earnings_on_platform || 0) -
    (overview?.total_cost_of_production || 0) -
    (overview?.allocated_operational_cost || overview?.operational_expenses?.allocated_operational_cost || 0)
  );
  const isProfit = actualNetProfit >= 0;
  const actualNetMargin = overview?.actual_net_margin_pct ?? (
    overview?.net_sold_revenue > 0 ? ((actualNetProfit / overview.net_sold_revenue) * 100).toFixed(2) : "0.00"
  );
  const allocatedOverhead = overview?.allocated_operational_cost ?? overview?.operational_expenses?.allocated_operational_cost ?? 68750;
  const platformEarnings = overview?.platform_earnings ?? overview?.pnl_summary?.earnings_on_platform ?? 0;

  return (
    <div className="space-y-6">
      {/* ── Top Filter Bar ────────────────────────────────────────── */}
      <Card className="p-4 bg-slate-50 border border-slate-200">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Platform</label>
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                className="border border-slate-300 rounded px-2.5 py-1.5 text-xs font-semibold bg-white text-slate-800"
              >
                <option value="">All Platforms</option>
                <option value="myntra">Myntra</option>
                <option value="flipkart">Flipkart</option>
                <option value="nykaa">Nykaa</option>
                <option value="amazon">Amazon</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Month (YYYY-MM)</label>
              <input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                className="border border-slate-300 rounded px-2.5 py-1.5 text-xs font-semibold bg-white text-slate-800"
              />
            </div>
            {(platform || month) && (
              <button
                onClick={() => { setPlatform(""); setMonth(""); }}
                className="text-xs text-slate-500 hover:text-slate-800 underline self-end mb-1"
              >
                Clear Filters
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <BtnSecondary onClick={loadData} disabled={loading} className="text-xs">
              <span className="flex items-center gap-1.5">
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
              </span>
            </BtnSecondary>
            <BtnPrimary onClick={() => setShowImportDrawer(true)} className="text-xs">
              <span className="flex items-center gap-1.5">
                <Upload className="w-3.5 h-3.5" /> Import Monthly PnL
              </span>
            </BtnPrimary>
          </div>
        </div>
      </Card>

      {/* ── Main Content Area ─────────────────────────────────────── */}
      {loading ? (
        <Card className="p-12 text-center text-sm text-slate-400 italic">
          Loading monthly PnL reconciliation data…
        </Card>
      ) : !data || (data.total_rows === 0 && !overview) ? (
        <Card className="p-12 text-center space-y-3 border-2 border-dashed border-slate-200">
          <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto">
            <ScrollText className="w-6 h-6" />
          </div>
          <h3 className="font-bold text-base text-slate-800">No Monthly Reconciliation Found</h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Upload an official monthly marketplace PnL report (e.g. Myntra <span className="font-mono font-semibold">PnLReport_*.xlsx</span>) to compute true net profits after production COGS and 50% factory overhead.
          </p>
          <div className="pt-2">
            <BtnPrimary onClick={() => setShowImportDrawer(true)}>
              <span className="flex items-center gap-2"><Upload className="w-4 h-4" /> Import Monthly Report</span>
            </BtnPrimary>
          </div>
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Executive Financial Summary Grid */}
          {overview && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <div className="bg-slate-50 border-2 border-slate-200 p-3.5 rounded">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Net Sales Revenue</div>
                  <div className="text-2xl font-black font-mono text-slate-900 mt-1">
                    ₹{Math.round(overview.net_sold_revenue || 0).toLocaleString()}
                  </div>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    {overview.total_net_sold} net units ({overview.styles_count} styles)
                  </div>
                </div>

                <div className="bg-blue-50/60 border-2 border-blue-200 p-3.5 rounded">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-blue-800">Platform Payout</div>
                  <div className="text-2xl font-black font-mono text-blue-900 mt-1">
                    ₹{Math.round(platformEarnings).toLocaleString()}
                  </div>
                  <div className="text-[11px] text-blue-700 mt-0.5">Marketplace Net Payout</div>
                </div>

                <div className="bg-amber-50/60 border-2 border-amber-200 p-3.5 rounded">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-amber-800">Production COGS</div>
                  <div className="text-2xl font-black font-mono text-amber-900 mt-1">
                    ₹{Math.round(overview.total_cost_of_production || 0).toLocaleString()}
                  </div>
                  <div className="text-[11px] text-amber-700 mt-0.5">From Style Master Master BOM</div>
                </div>

                <div className="bg-purple-50/60 border-2 border-purple-200 p-3.5 rounded">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-purple-800">50% Factory Overhead</div>
                  <div className="text-2xl font-black font-mono text-purple-900 mt-1">
                    ₹{Math.round(allocatedOverhead).toLocaleString()}
                  </div>
                  <div className="flex items-center justify-between mt-0.5">
                    <span className="text-[11px] text-purple-700">Rent, Power, Salaries</span>
                    <button
                      type="button"
                      onClick={() => setShowOpModal(true)}
                      className="text-[11px] font-bold text-indigo-700 hover:text-indigo-900 underline inline-flex items-center gap-1 ml-1"
                    >
                      <SlidersHorizontal className="w-3 h-3" /> Adjust
                    </button>
                  </div>
                </div>

                <div className={`border-2 p-3.5 rounded ${isProfit ? "bg-emerald-50 border-emerald-400" : "bg-rose-50 border-rose-400"}`}>
                  <div className={`text-[10px] uppercase tracking-wider font-bold ${isProfit ? "text-emerald-800" : "text-rose-800"}`}>
                    ACTUAL NET PROFIT
                  </div>
                  <div className={`text-2xl font-black font-mono mt-1 ${isProfit ? "text-emerald-900" : "text-rose-900"}`}>
                    ₹{Math.round(actualNetProfit).toLocaleString()}
                  </div>
                  <div className={`text-[11px] font-bold font-mono mt-0.5 ${isProfit ? "text-emerald-700" : "text-rose-700"}`}>
                    {actualNetMargin}% True Business Margin
                  </div>
                </div>
              </div>

              {/* Waterfall Ribbon */}
              {overview.pnl_summary && (
                <div className="bg-slate-50 border border-slate-200 p-2.5 rounded text-xs flex flex-wrap items-center justify-between gap-2 text-slate-700 font-mono">
                  <div>Gross: <span className="font-bold">₹{Math.round(overview.pnl_summary.gross_sales || 0).toLocaleString()}</span> ({overview.pnl_summary.gross_units} u)</div>
                  <div>Returns: <span className="font-bold text-rose-700">₹{Math.round(overview.pnl_summary.returns_amount || 0).toLocaleString()}</span> ({overview.pnl_summary.returns_units} u)</div>
                  <div>Net Sales: <span className="font-bold text-emerald-800">₹{Math.round(overview.pnl_summary.net_sales || 0).toLocaleString()}</span> ({overview.pnl_summary.net_units} u)</div>
                  <div>Platform Fees: <span className="font-bold text-rose-700">₹{Math.round(overview.pnl_summary.total_expenses || 0).toLocaleString()}</span></div>
                  <div>Payout: <span className="font-bold text-blue-800">₹{Math.round(platformEarnings).toLocaleString()}</span></div>
                  <div>COGS: <span className="font-bold text-amber-800">₹{Math.round(overview.total_cost_of_production || 0).toLocaleString()}</span></div>
                  <div>True Net: <span className={`font-bold ${isProfit ? "text-emerald-700" : "text-rose-700"}`}>₹{Math.round(actualNetProfit).toLocaleString()}</span></div>
                </div>
              )}
            </div>
          )}

          {/* Sub Navigation Tabs */}
          <div className="flex border-b border-slate-200 gap-4 pt-2">
            <button
              type="button"
              onClick={() => setActiveSubTab("overview")}
              className={`pb-2.5 text-xs font-bold transition-colors inline-flex items-center gap-1.5 border-b-2 -mb-px ${
                activeSubTab === "overview"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <TrendingUp className="w-4 h-4" />
              Returns & Profitability Intelligence
            </button>
            <button
              type="button"
              onClick={() => setActiveSubTab("styles")}
              className={`pb-2.5 text-xs font-bold transition-colors inline-flex items-center gap-1.5 border-b-2 -mb-px ${
                activeSubTab === "styles"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <Layers className="w-4 h-4" />
              Style Breakdown & COGS ({overview?.styles_count || overview?.styles?.length || 0} Styles)
            </button>
            <button
              type="button"
              onClick={() => setActiveSubTab("skus")}
              className={`pb-2.5 text-xs font-bold transition-colors inline-flex items-center gap-1.5 border-b-2 -mb-px ${
                activeSubTab === "skus"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <ScrollText className="w-4 h-4" />
              SKU Drill-down ({overview?.sku_bifurcation?.length || overview?.total_skus || 0} SKUs)
            </button>
            <button
              type="button"
              onClick={() => setActiveSubTab("returns_deductions")}
              className={`pb-2.5 text-xs font-bold transition-colors inline-flex items-center gap-1.5 border-b-2 -mb-px ${
                activeSubTab === "returns_deductions"
                  ? "border-slate-900 text-slate-900"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <RotateCcw className="w-4 h-4 text-purple-600" />
              Return Charges & Deductions
            </button>
          </div>

          {/* ── SUB-TAB 1: EXTENSIVE RETURNS & PROFIT INTELLIGENCE ───── */}
          {activeSubTab === "overview" && (
            <div className="space-y-6">
              {/* Return & RTO Impact Analysis Card */}
              {returnAnalytics && (
                <Card className="p-5 border-2 border-rose-200/80 bg-rose-50/20 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ShieldAlert className="w-5 h-5 text-rose-600" />
                      <h4 className="font-bold text-sm text-slate-900 uppercase tracking-wider">
                        Return & RTO Impact Analysis
                      </h4>
                    </div>
                    <Badge color="red">
                      {returnAnalytics.overall_return_rate_pct}% Overall Return Rate
                    </Badge>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="bg-white border border-rose-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Total Returned Units</div>
                      <div className="text-xl font-black font-mono text-rose-700 mt-1">
                        {returnAnalytics.total_returned_units}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">
                        RTO (Courier): <strong>{returnAnalytics.rto_vs_rvp?.rto_units ?? 0}</strong> ({returnAnalytics.rto_vs_rvp?.rto_pct ?? 0}%) · Customer: <strong>{returnAnalytics.rto_vs_rvp?.rvp_units ?? 0}</strong> ({returnAnalytics.rto_vs_rvp?.rvp_pct ?? 0}%)
                      </div>
                    </div>

                    <div className="bg-white border border-rose-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Gross Sales Value Lost</div>
                      <div className="text-xl font-black font-mono text-rose-800 mt-1">
                        ₹{Math.round(returnAnalytics.total_return_amount_lost || 0).toLocaleString()}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">Reversed customer billing</div>
                    </div>

                    <div className="bg-white border border-rose-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Reverse Logistics Cost</div>
                      <div className="text-xl font-black font-mono text-amber-700 mt-1">
                        ₹{Math.round(returnAnalytics.total_reverse_logistics_cost || 0).toLocaleString()}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">Marketplace freight penalty</div>
                    </div>

                    <div className="bg-rose-100/70 border border-rose-300 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-rose-900">Total Financial Return Damage</div>
                      <div className="text-xl font-black font-mono text-rose-950 mt-1">
                        ₹{Math.round(returnAnalytics.total_return_financial_damage || 0).toLocaleString()}
                      </div>
                      <div className="text-[10px] text-rose-800 font-semibold mt-0.5">Lost Value + Reverse Freight</div>
                    </div>
                  </div>

                  {/* Most Returned Styles Leaderboard */}
                  {returnAnalytics.most_returned_styles?.length > 0 && (
                    <div className="space-y-2 pt-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-slate-700 uppercase tracking-wider text-[11px]">
                          Worst Returned Styles Leaderboard
                        </span>
                        <span className="text-slate-400 font-mono text-[10px]">Ranked by total return volume</span>
                      </div>
                      <div className="border border-slate-200 rounded overflow-hidden bg-white">
                        <table className="w-full text-xs">
                          <thead className="bg-slate-100 text-[10px] uppercase tracking-wider text-slate-600">
                            <tr>
                              <th className="p-2 text-center w-12 border-b">Rank</th>
                              <th className="p-2 text-left border-b">Style Code</th>
                              <th className="p-2 text-left border-b">Brand</th>
                              <th className="p-2 text-right border-b">Gross Units</th>
                              <th className="p-2 text-right border-b">Returns</th>
                              <th className="p-2 text-right border-b">Return Rate %</th>
                              <th className="p-2 text-right border-b">Net Sold</th>
                              <th className="p-2 text-right border-b">Lost Revenue</th>
                            </tr>
                          </thead>
                          <tbody>
                            {returnAnalytics.most_returned_styles.slice(0, 10).map((st) => (
                              <tr key={st.style_code} className="border-b border-slate-100 hover:bg-rose-50/40">
                                <td className="p-2 text-center font-bold text-slate-500">#{st.return_rank}</td>
                                <td className="p-2 font-mono font-bold text-slate-900">{st.style_code}</td>
                                <td className="p-2 text-slate-600">{st.brand || "—"}</td>
                                <td className="p-2 text-right font-mono text-slate-700">{st.gross_units}</td>
                                <td className="p-2 text-right font-mono font-bold text-rose-700">{st.returned_qty}</td>
                                <td className="p-2 text-right font-mono">
                                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                    (st.return_rate_pct ?? 0) > 40 ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"
                                  }`}>
                                    {st.return_rate_pct}%
                                  </span>
                                </td>
                                <td className="p-2 text-right font-mono font-bold text-emerald-700">{st.net_sold_qty}</td>
                                <td className="p-2 text-right font-mono text-rose-700">
                                  ₹{Math.round(st.return_amount_lost || 0).toLocaleString()}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </Card>
              )}

              {/* Profit Champions vs Loss Drivers */}
              {profitRankings && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Top Profit Styles */}
                  <Card className="p-4 border-2 border-emerald-200 bg-emerald-50/20 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Award className="w-5 h-5 text-emerald-600" />
                        <h4 className="font-bold text-sm text-emerald-950 uppercase tracking-wider">
                          Top 10 Profit Drivers
                        </h4>
                      </div>
                      <Badge color="green">Value Creators</Badge>
                    </div>

                    <div className="border border-emerald-200 rounded overflow-hidden bg-white">
                      <table className="w-full text-xs">
                        <thead className="bg-emerald-100/60 text-[10px] uppercase text-emerald-900">
                          <tr>
                            <th className="p-2 text-left border-b">Style</th>
                            <th className="p-2 text-right border-b">Net Sold</th>
                            <th className="p-2 text-right border-b">Net Rev</th>
                            <th className="p-2 text-right border-b">COGS</th>
                            <th className="p-2 text-right border-b">Net Profit</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(profitRankings.top_profit_styles || []).map((s) => (
                            <tr key={s.style_code} className="border-b border-emerald-50 hover:bg-emerald-50/50">
                              <td className="p-2 font-mono font-bold text-slate-900">{s.style_code}</td>
                              <td className="p-2 text-right font-mono text-slate-700">{s.net_sold_qty}</td>
                              <td className="p-2 text-right font-mono text-slate-900">₹{Math.round(s.net_sold_seller_price || 0).toLocaleString()}</td>
                              <td className="p-2 text-right font-mono text-slate-600">₹{Math.round(s.total_production_cost || 0).toLocaleString()}</td>
                              <td className="p-2 text-right font-mono font-black text-emerald-700">
                                ₹{Math.round(s.contribution ?? s.gross_profit ?? 0).toLocaleString()}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>

                  {/* Top Loss Styles */}
                  <Card className="p-4 border-2 border-rose-200 bg-rose-50/20 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="w-5 h-5 text-rose-600" />
                        <h4 className="font-bold text-sm text-rose-950 uppercase tracking-wider">
                          Top 10 Value Destroyers / Loss Styles
                        </h4>
                      </div>
                      <Badge color="red">Attention Needed</Badge>
                    </div>

                    <div className="border border-rose-200 rounded overflow-hidden bg-white">
                      <table className="w-full text-xs">
                        <thead className="bg-rose-100/60 text-[10px] uppercase text-rose-900">
                          <tr>
                            <th className="p-2 text-left border-b">Style</th>
                            <th className="p-2 text-right border-b">Net Sold</th>
                            <th className="p-2 text-right border-b">Net Rev</th>
                            <th className="p-2 text-right border-b">COGS</th>
                            <th className="p-2 text-right border-b">Net Profit / Loss</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(profitRankings.top_loss_styles || []).map((s) => (
                            <tr key={s.style_code} className="border-b border-rose-50 hover:bg-rose-50/50">
                              <td className="p-2 font-mono font-bold text-slate-900">{s.style_code}</td>
                              <td className="p-2 text-right font-mono text-slate-700">{s.net_sold_qty}</td>
                              <td className="p-2 text-right font-mono text-slate-900">₹{Math.round(s.net_sold_seller_price || 0).toLocaleString()}</td>
                              <td className="p-2 text-right font-mono text-slate-600">₹{Math.round(s.total_production_cost || 0).toLocaleString()}</td>
                              <td className="p-2 text-right font-mono font-black text-rose-700">
                                ₹{Math.round(s.contribution ?? s.gross_profit ?? 0).toLocaleString()}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>
                </div>
              )}

              {/* Platform Fee Breakdown */}
              {feeBreakdown && (
                <Card className="p-5 border-2 border-slate-200 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <DollarSign className="w-5 h-5 text-indigo-600" />
                      <h4 className="font-bold text-sm text-slate-900 uppercase tracking-wider">
                        Marketplace Fee Deductions Breakdown
                      </h4>
                    </div>
                    <span className="font-mono font-bold text-rose-700 text-sm">
                      Total Platform Deductions: ₹{Math.round(feeBreakdown.total_fees || 0).toLocaleString()}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                    <div className="bg-slate-50 border border-slate-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Commission</div>
                      <div className="text-lg font-black font-mono text-slate-800 mt-1">
                        ₹{Math.round(feeBreakdown.commission || 0).toLocaleString()}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">Platform referral fee</div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Forward Shipping</div>
                      <div className="text-lg font-black font-mono text-slate-800 mt-1">
                        ₹{Math.round(feeBreakdown.forward_shipping || 0).toLocaleString()}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">Customer logistics</div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Reverse Shipping</div>
                      <div className="text-lg font-black font-mono text-rose-700 mt-1">
                        ₹{Math.round(feeBreakdown.reverse_shipping || 0).toLocaleString()}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">Return freight fees</div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Fixed Platform Fee</div>
                      <div className="text-lg font-black font-mono text-slate-800 mt-1">
                        ₹{Math.round(feeBreakdown.fixed_fee || 0).toLocaleString()}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">Closing & tech charges</div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">GST on Platform Services</div>
                      <div className="text-lg font-black font-mono text-slate-800 mt-1">
                        ₹{Math.round(feeBreakdown.taxes_gst || 0).toLocaleString()}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">18% GST on marketplace fees</div>
                    </div>
                  </div>
                </Card>
              )}
            </div>
          )}

          {/* ── SUB-TAB 2: STYLE BREAKDOWN TABLE ─────────────────────── */}
          {activeSubTab === "styles" && overview && (
            <MonthlyStyleOverviewTable overview={overview} onUpdateCost={handleUpdateCost} />
          )}

          {/* ── SUB-TAB 3: SKU DRILLDOWN TABLE ───────────────────────── */}
          {activeSubTab === "skus" && overview && (
            <MonthlySkuBifurcationTable skuList={overview.sku_bifurcation || []} overview={overview} />
          )}

          {/* ── SUB-TAB 4: RETURN CHARGES & DEDUCTIONS ───────────────── */}
          {activeSubTab === "returns_deductions" && overview && (
            <div className="space-y-6" data-testid="returns-deductions-tab">
              {/* Headline Metric Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-white border-2 border-rose-200 p-4 rounded shadow-sm">
                  <div className="flex items-center justify-between">
                    <div className="text-[10px] uppercase font-bold text-slate-500">Returned Units</div>
                    <Badge color="red">{returnAnalytics?.overall_return_rate_pct ?? 0}% Rate</Badge>
                  </div>
                  <div className="text-2xl font-black font-mono text-rose-700 mt-1">
                    {returnAnalytics?.total_returned_units ?? 0}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">
                    RTO: <strong>{returnAnalytics?.rto_vs_rvp?.rto_units ?? 0}</strong> ({returnAnalytics?.rto_vs_rvp?.rto_pct ?? 0}%) · Cust: <strong>{returnAnalytics?.rto_vs_rvp?.rvp_units ?? 0}</strong> ({returnAnalytics?.rto_vs_rvp?.rvp_pct ?? 0}%)
                  </div>
                </div>

                <div className="bg-white border-2 border-amber-200 p-4 rounded shadow-sm">
                  <div className="text-[10px] uppercase font-bold text-slate-500">Reverse Logistics Charges</div>
                  <div className="text-2xl font-black font-mono text-amber-700 mt-1">
                    {inr(returnAnalytics?.total_reverse_logistics_cost || feeBreakdown?.reverse_shipping || 0)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">Marketplace return freight fees</div>
                </div>

                <div className="bg-white border-2 border-rose-200 p-4 rounded shadow-sm">
                  <div className="text-[10px] uppercase font-bold text-slate-500">Gross Sales Value Lost</div>
                  <div className="text-2xl font-black font-mono text-rose-800 mt-1">
                    {inr(returnAnalytics?.total_return_amount_lost || 0)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">Reversed customer billing</div>
                </div>

                <div className="bg-white border-2 border-purple-200 p-4 rounded shadow-sm">
                  <div className="text-[10px] uppercase font-bold text-slate-500">Non-Order Deductions</div>
                  <div className="text-2xl font-black font-mono text-purple-700 mt-1">
                    {inr(recSummary?.total_non_order_deductions || 0)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">Storage, ad spend & penalties</div>
                </div>
              </div>

              {/* Marketplace Fee Deductions Breakdown */}
              {feeBreakdown && (
                <Card className="p-5 border-2 border-slate-200 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                    <div className="flex items-center gap-2">
                      <IndianRupee className="w-5 h-5 text-indigo-600" />
                      <div>
                        <h4 className="font-bold text-sm text-slate-900 uppercase tracking-wider">
                          Marketplace Fee Deductions Breakdown
                        </h4>
                        <p className="text-xs text-slate-500">All fees debited by marketplace on orders and return logistics</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Total Marketplace Deductions</div>
                      <span className="font-mono font-bold text-rose-700 text-base">
                        {inr(feeBreakdown.total_fees || 0)}
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                    <div className="bg-slate-50 border border-slate-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Commission</div>
                      <div className="text-lg font-black font-mono text-slate-800 mt-1">
                        {inr(feeBreakdown.commission || 0)}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">Platform referral fee</div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Forward Shipping</div>
                      <div className="text-lg font-black font-mono text-slate-800 mt-1">
                        {inr(feeBreakdown.forward_shipping || 0)}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">Customer logistics</div>
                    </div>

                    <div className="bg-slate-50 border border-rose-200 bg-rose-50/20 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-rose-800">Reverse Shipping</div>
                      <div className="text-lg font-black font-mono text-rose-700 mt-1">
                        {inr(feeBreakdown.reverse_shipping || 0)}
                      </div>
                      <div className="text-[10px] text-rose-600 mt-0.5">Return freight fees</div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">Fixed Platform Fee</div>
                      <div className="text-lg font-black font-mono text-slate-800 mt-1">
                        {inr(feeBreakdown.fixed_fee || 0)}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">Closing & tech charges</div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 p-3 rounded">
                      <div className="text-[10px] uppercase font-bold text-slate-500">GST on Platform Services</div>
                      <div className="text-lg font-black font-mono text-slate-800 mt-1">
                        {inr(feeBreakdown.taxes_gst || 0)}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">18% GST on marketplace fees</div>
                    </div>
                  </div>
                </Card>
              )}

              {/* Return Charges & Reverse Freight by Style */}
              <Card className="p-5 border-2 border-slate-200 space-y-4">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div>
                    <h4 className="font-bold text-sm text-slate-900 uppercase tracking-wider flex items-center gap-2">
                      <RotateCcw className="w-4 h-4 text-purple-600" /> Return Charges & Reverse Freight by Style
                    </h4>
                    <p className="text-xs text-slate-500">
                      Per-style return rate, reverse logistics penalties, and revenue lost due to returns
                    </p>
                  </div>
                  <span className="text-xs font-mono text-slate-400">
                    {(overview?.styles || []).length} Styles Reconciled
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-xs" data-testid="returns-by-style-table">
                    <thead className="bg-slate-100 text-[10px] uppercase tracking-wider text-slate-600 border-b border-slate-200">
                      <tr>
                        <th className="p-2.5 text-left min-w-[280px]">Style & Codes / Article</th>
                        <th className="p-2.5 text-left">Brand</th>
                        <th className="p-2.5 text-right">Gross Units</th>
                        <th className="p-2.5 text-right">Returned Units</th>
                        <th className="p-2.5 text-right">Return Rate %</th>
                        <th className="p-2.5 text-right">Reverse Logistics (₹)</th>
                        <th className="p-2.5 text-right">Sales Value Lost (₹)</th>
                        <th className="p-2.5 text-right">Total Return Damage (₹)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {(overview?.styles || []).map((s) => {
                        const retDmg = s.total_return_cost || ((s.reverse_logistics_cost || 0) + (s.return_amount_lost || 0));
                        const returnChargesFromSettlement = recSummary?.return_charges_by_style?.[s.style_code];
                        const revCost = s.reverse_logistics_cost || returnChargesFromSettlement || 0;
                        return (
                          <tr key={s.style_code} className="hover:bg-slate-50/80 transition-colors">
                            <td className="p-2.5 min-w-[280px]">
                              <div className="flex items-center gap-3">
                                {/* Style Photo Thumbnail with click-to-preview */}
                                <div
                                  className="relative w-12 h-12 rounded border border-slate-300 bg-slate-50 overflow-hidden shadow-sm shrink-0 cursor-pointer group"
                                  onClick={() => s.image_url && setPreviewImage(s.image_url)}
                                  title="Click to view full style photo"
                                >
                                  {s.image_url ? (
                                    <img
                                      src={s.image_url}
                                      alt={s.style_code}
                                      className="w-full h-full object-cover transition-transform group-hover:scale-110"
                                    />
                                  ) : (
                                    <div className="w-full h-full flex flex-col items-center justify-center bg-slate-100 text-slate-400">
                                      <ImageIcon className="w-4 h-4" />
                                    </div>
                                  )}
                                  <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white">
                                    <Eye className="w-3.5 h-3.5" />
                                  </div>
                                </div>

                                {/* Style Details & Identifiers */}
                                <div className="space-y-0.5">
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    <span className="font-mono font-bold text-slate-900 text-[13px]">{s.style_code}</span>
                                    {s.brand && (
                                      <span className="text-[9px] uppercase tracking-wider font-bold text-indigo-700 bg-indigo-50 px-1 py-0.5 rounded border border-indigo-200">
                                        {s.brand}
                                      </span>
                                    )}
                                  </div>

                                  {/* Myntra Style ID & ERP Style Code badges */}
                                  <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                                    {s.myntra_style_id ? (
                                      <span
                                        className="text-[10px] font-mono font-bold text-amber-900 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200 inline-flex items-center gap-1"
                                        title="Myntra Marketplace Style ID"
                                      >
                                        <span className="text-amber-600 font-semibold">Myntra ID:</span>
                                        {s.myntra_style_id}
                                      </span>
                                    ) : (
                                      <span className="text-[10px] font-mono text-slate-400 bg-slate-50 px-1 py-0.5 rounded border border-slate-200">
                                        Myntra ID: —
                                      </span>
                                    )}

                                    {s.erp_style_code ? (
                                      <span
                                        className="text-[10px] font-mono font-bold text-emerald-900 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200 inline-flex items-center gap-1"
                                        title="Internal SSK ERP Style Code"
                                      >
                                        <span className="text-emerald-700 font-semibold">ERP:</span>
                                        {s.erp_style_code}
                                      </span>
                                    ) : (
                                      <span
                                        className="text-[10px] font-mono text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200"
                                        title="ERP Style Code"
                                      >
                                        ERP: {s.style_code.startsWith("SSK") ? s.style_code : "Unmapped"}
                                      </span>
                                    )}
                                  </div>

                                  <div className="text-[11px] text-slate-600 max-w-[220px] truncate" title={s.style_name}>
                                    {s.style_name || s.style_code}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td className="p-2.5 text-slate-600 font-semibold">{s.brand || "—"}</td>
                            <td className="p-2.5 text-right font-mono text-slate-700">{s.gross_units ?? s.total_orders ?? "—"}</td>
                            <td className="p-2.5 text-right font-mono font-bold text-rose-700">{s.returned_qty ?? 0}</td>
                            <td className="p-2.5 text-right font-mono">
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                (s.return_rate_pct ?? 0) > 35 ? "bg-rose-100 text-rose-800" :
                                (s.return_rate_pct ?? 0) > 20 ? "bg-amber-100 text-amber-800" :
                                "bg-emerald-100 text-emerald-800"
                              }`}>
                                {s.return_rate_pct ?? 0}%
                              </span>
                            </td>
                            <td className="p-2.5 text-right font-mono font-bold text-amber-700">
                              {inr(revCost)}
                            </td>
                            <td className="p-2.5 text-right font-mono text-rose-700">
                              {inr(s.return_amount_lost || 0)}
                            </td>
                            <td className="p-2.5 text-right font-mono font-black text-rose-900">
                              {inr(retDmg)}
                            </td>
                          </tr>
                        );
                      })}
                      {(overview?.styles || []).length === 0 && (
                        <tr>
                          <td colSpan={8} className="p-6 text-center text-slate-400 italic">
                            No style return records found for this period.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </Card>

              {/* Non-Order Deductions Ledger */}
              <Card className="p-5 border-2 border-slate-200 space-y-4">
                <div className="flex justify-between items-center border-b border-slate-100 pb-3">
                  <div>
                    <h4 className="font-bold text-sm uppercase tracking-wider text-slate-900 flex items-center gap-2">
                      <IndianRupee className="w-4 h-4 text-amber-600" /> Non-Order Deductions Ledger
                    </h4>
                    <p className="text-xs text-slate-500">
                      Deductions not attributed to specific orders (e.g. storage fees, ad spend, operational penalties)
                    </p>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] uppercase font-bold text-slate-500">Total Non-Order Deductions</div>
                    <div className="text-xl font-black text-rose-600">
                      {inr(recSummary?.total_non_order_deductions || 0)}
                    </div>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse" data-testid="non-order-deductions-table">
                    <thead>
                      <tr className="bg-slate-100 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[10px] font-bold">
                        <th className="p-2.5">Date</th>
                        <th className="p-2.5">Seller ID</th>
                        <th className="p-2.5">Type</th>
                        <th className="p-2.5">UTR / Ref</th>
                        <th className="p-2.5">Description</th>
                        <th className="p-2.5 text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {recSummary?.non_order_deductions_ledger && recSummary.non_order_deductions_ledger.length > 0 ? (
                        recSummary.non_order_deductions_ledger.map((ded, dIdx) => (
                          <tr key={ded.id || dIdx} className="hover:bg-slate-50/80 transition-colors">
                            <td className="p-2.5 font-mono font-semibold text-slate-700">{ded.settlement_date || "—"}</td>
                            <td className="p-2.5 font-bold text-slate-900">{ded.seller_id || "—"}</td>
                            <td className="p-2.5 whitespace-nowrap">
                              <Badge color="yellow">{ded.settlement_type || "Deduction"}</Badge>
                            </td>
                            <td className="p-2.5 font-mono text-slate-600">{ded.utr || ded.invoice_ref || "—"}</td>
                            <td className="p-2.5 text-slate-600">{ded.settlement_description || "—"}</td>
                            <td className="p-2.5 text-right font-black text-rose-600">{inr(ded.settlement_amount)}</td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan={6} className="p-6 text-center text-slate-400 italic">
                            No non-order deductions recorded in settlement files.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          )}

          {/* ── Modals & Drawers ─────────────────────────────────────── */}
          <OperationalCostModal
            overview={overview}
            isOpen={showOpModal}
            onClose={() => setShowOpModal(false)}
            onSave={handleUpdateOperationalCost}
          />

          {showImportDrawer && (
            <MonthlyReportDrawer
              onClose={() => setShowImportDrawer(false)}
              onDone={() => {
                setShowImportDrawer(false);
                loadData();
              }}
            />
          )}

          {/* ── Image Enlarged Preview Modal ─────────────────────────── */}
          {previewImage && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
              onClick={() => setPreviewImage(null)}
            >
              <div className="relative max-w-lg max-h-[85vh] bg-white rounded p-3 shadow-2xl space-y-2" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between border-b pb-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-700">Style Photo Preview</span>
                  <button
                    type="button"
                    onClick={() => setPreviewImage(null)}
                    className="w-6 h-6 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold flex items-center justify-center"
                  >
                    ✕
                  </button>
                </div>
                <img src={previewImage} alt="Style Preview" className="max-w-full max-h-[75vh] rounded object-contain mx-auto" />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
