import { useEffect, useMemo, useState, useCallback } from "react";
import { http, inr, num } from "../lib/api";
import {
  PageHeader,
  Card,
  StatTile,
  Input,
  Select,
  BtnPrimary,
  BtnSecondary,
  Badge,
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
  AlertTriangle,
  TrendingUp,
  ShoppingBag,
  RotateCcw,
  Loader2,
  Info,
  DollarSign,
  Upload,
} from "lucide-react";
import { SettlementImportDrawer } from "./OnlineOrders";

const PALETTE = {
  packed:    "#2563EB",
  returned:  "#DC2626",
  netSold:   "#16A34A",
  revenue:   "#0F172A",
  cogs:      "#C27842",
  profit:    "#16A34A",
  commission:      "#DC2626",
  fixed_fee:       "#F59E0B",
  logistics_fwd:   "#2563EB",
  logistics_rev:   "#7C3AED",
  pick_and_pack:   "#0EA5E9",
  tech_enablement: "#94A3B8",
  royalty:         "#A65D24",
};

const FEE_LABELS = {
  commission:      "Commission",
  fixed_fee:       "Fixed Fee",
  logistics_fwd:   "Logistics (Fwd)",
  logistics_rev:   "Logistics (Rev)",
  pick_and_pack:   "Pick & Pack",
  tech_enablement: "Tech Enablement",
  royalty:         "Royalty",
};

const isoToday = () => new Date().toISOString().slice(0, 10);
const isoDaysAgo = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

export default function OnlineProfitability() {
  const [platform, setPlatform] = useState("myntra");
  const [dateFrom, setDateFrom] = useState(isoDaysAgo(30));
  const [dateTo, setDateTo] = useState(isoToday());
  const [styleId, setStyleId] = useState("");
  const [bucket, setBucket] = useState("day");
  const [styles, setStyles] = useState([]);
  const [summary, setSummary] = useState(null);
  const [trend, setTrend] = useState([]);
  const [loading, setLoading] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [error, setError] = useState("");
  const [settlementOpen, setSettlementOpen] = useState(false);

  // Load styles for the dropdown once
  useEffect(() => {
    http.get("/styles")
      .then((r) => setStyles(r.data || []))
      .catch(() => setStyles([]));
  }, []);

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const params = { platform, date_from: dateFrom, date_to: dateTo };
      if (styleId) params.style_id = styleId;

      const [sumRes, trRes] = await Promise.all([
        http.get("/reports/online-profitability", { params }),
        http.get("/reports/online-profitability/trend", {
          params: { ...params, bucket },
        }),
      ]);
      setSummary(sumRes.data);
      setTrend(trRes.data?.rows || []);
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to load profitability data.";
      setError(String(msg));
      setSummary(null);
      setTrend([]);
    } finally {
      setLoading(false);
    }
  }, [platform, dateFrom, dateTo, styleId, bucket]);

  useEffect(() => {
    load();
  }, [load]);

  const rebuild = async () => {
    setRebuilding(true);
    try {
      await http.post(
        "/reports/online-profitability/rebuild",
        {},
        { params: { platform, date_from: dateFrom, date_to: dateTo } }
      );
      await load();
    } catch (err) {
      setError(
        err?.response?.data?.detail || err?.message || "Rebuild failed."
      );
    } finally {
      setRebuilding(false);
    }
  };

  const download = async () => {
    try {
      const params = new URLSearchParams({
        platform,
        date_from: dateFrom,
        date_to: dateTo,
      });
      if (styleId) params.append("style_id", styleId);
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/reports/online-profitability/export?${params.toString()}`;
      const res = await http.get(
        `/reports/online-profitability/export?${params.toString()}`,
        { responseType: "blob" }
      );
      const blob = new Blob([res.data], {
        type:
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `profitability_${platform}_${dateFrom}_${dateTo}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      setError(
        err?.response?.data?.detail || err?.message || "Download failed."
      );
    }
  };

  // Derived: return/RTO rate for headline card
  const returnRate = useMemo(() => {
    if (!summary) return 0;
    const sold = summary.net_units_sold || 0;
    const returned = (summary.by_style || []).reduce(
      (a, r) => a + (r.returned_units || 0),
      0
    );
    const denom = sold + returned;
    return denom > 0 ? (returned / denom) * 100 : 0;
  }, [summary]);

  const byStyleSorted = useMemo(() => {
    if (!summary?.by_style) return [];
    return [...summary.by_style].sort(
      (a, b) => (a.profit || 0) - (b.profit || 0)
    );
  }, [summary]);

  const trendChartData = useMemo(() => {
    return (trend || []).map((r) => ({
      date: r.date,
      Packed: r.units_packed,
      Returned: r.units_returned,
      "Net Sold": r.net_units_sold,
    }));
  }, [trend]);

  const revenueChartData = useMemo(() => {
    return (trend || []).map((r) => ({
      date: r.date,
      Revenue: r.revenue_effective,
      COGS: r.cogs,
      Profit: r.gross_profit,
    }));
  }, [trend]);

  const feesChartData = useMemo(() => {
    return (trend || []).map((r) => ({
      date: r.date,
      ...(r.fees || {}),
    }));
  }, [trend]);

  return (
    <div data-testid="online-profitability-page">
      <PageHeader
        testId="profitability-header"
        title="Online Profitability"
        subtitle="Reports / Online Profitability"
        action={
          <div className="flex gap-2">
            <BtnSecondary
              onClick={() => setSettlementOpen(true)}
              data-testid="import-settlement-btn"
            >
              <span className="inline-flex items-center gap-1">
                <DollarSign className="w-3.5 h-3.5" /> Import Settlement
              </span>
            </BtnSecondary>
            <BtnSecondary
              onClick={rebuild}
              disabled={rebuilding || loading}
              data-testid="rebuild-rollup-btn"
            >
              {rebuilding ? (
                <span className="inline-flex items-center gap-1">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Rebuilding
                </span>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <RefreshCw className="w-3.5 h-3.5" /> Rebuild Rollup
                </span>
              )}
            </BtnSecondary>
            <BtnPrimary onClick={download} data-testid="download-report-btn">
              <span className="inline-flex items-center gap-1">
                <Download className="w-3.5 h-3.5" /> Download Report
              </span>
            </BtnPrimary>
          </div>
        }
      />

      {/* Filters */}
      <div className="px-4 sm:px-8 py-5 bg-white border-b border-slate-200">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <Select
            label="Platform"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            testId="platform-select"
          >
            <option value="myntra">Myntra</option>
            <option value="ajio">Ajio</option>
            <option value="flipkart">Flipkart</option>
            <option value="nykaa">Nykaa</option>
            <option value="website">Website</option>
          </Select>
          <Input
            label="From"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            testId="date-from-input"
          />
          <Input
            label="To"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            testId="date-to-input"
          />
          <Select
            label="Style (optional)"
            value={styleId}
            onChange={(e) => setStyleId(e.target.value)}
            testId="style-select"
          >
            <option value="">All styles</option>
            {styles.map((s) => (
              <option key={s.id} value={s.id}>
                {s.code} — {s.name}
              </option>
            ))}
          </Select>
          <Select
            label="Bucket"
            value={bucket}
            onChange={(e) => setBucket(e.target.value)}
            testId="bucket-select"
          >
            <option value="day">Daily</option>
            <option value="week">Weekly</option>
          </Select>
          <div className="flex items-end">
            <BtnPrimary
              onClick={load}
              disabled={loading}
              className="w-full"
              data-testid="apply-filters-btn"
            >
              {loading ? (
                <span className="inline-flex items-center gap-1 justify-center">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading
                </span>
              ) : (
                "Apply"
              )}
            </BtnPrimary>
          </div>
        </div>
      </div>

      {error && (
        <div
          className="mx-4 sm:mx-8 mt-5 border-2 border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 flex items-start gap-2"
          data-testid="profitability-error"
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>{error}</div>
        </div>
      )}

      <div className="p-4 sm:p-8 space-y-6">
        {/* Interpretation banner */}
        {summary && (!summary.phase_3_available || summary.is_estimated) && (
          <div
            className="border-2 border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 flex flex-wrap items-center justify-between gap-3"
            data-testid="phase3-warning-banner"
          >
            <div className="flex items-start gap-2 max-w-3xl">
              <Info className="w-4 h-4 mt-0.5 shrink-0 text-amber-700" />
              <div>
                <span className="font-bold">Phase 3 settlements not fully reconciled.</span>{" "}
                Revenue is estimated from item file prices until you import settlement advice payout files (forward / reverse payouts).
                Reconciled numbers refine automatically once settlement CSVs are committed.
              </div>
            </div>
            <BtnPrimary
              onClick={() => setSettlementOpen(true)}
              className="shrink-0 bg-amber-800 hover:bg-amber-900 border-amber-800 text-white"
            >
              <span className="inline-flex items-center gap-1.5 text-xs">
                <Upload className="w-3.5 h-3.5" /> Upload Settlement File
              </span>
            </BtnPrimary>
          </div>
        )}

        {/* Headline metric cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          <StatTile
            label="Net Units Sold"
            value={num(summary?.net_units_sold || 0, 0)}
            sub={`over ${trend.length} ${bucket}(s)`}
            testId="stat-net-units-sold"
            accent="#16A34A"
          />
          <StatTile
            label="Total COGS"
            value={inr(summary?.total_net_cogs || 0)}
            sub="BOM × units"
            testId="stat-total-cogs"
            accent="#C27842"
          />
          <StatTile
            label="Revenue Settled"
            value={inr(summary?.total_revenue_settled || 0)}
            sub={summary?.is_estimated ? "Estimated (fallback)" : "Reconciled (payouts matched)"}
            testId="stat-revenue-settled"
            accent={summary?.is_estimated ? "#F59E0B" : "#16A34A"}
          />
          <StatTile
            label="Gross Profit"
            value={inr(summary?.gross_profit || 0)}
            sub={summary?.revenue_source_used}
            testId="stat-gross-profit"
            accent="#2563EB"
          />
          <StatTile
            label="Gross Margin"
            value={`${num(summary?.gross_margin_pct || 0, 2)}%`}
            testId="stat-gross-margin"
            accent="#16A34A"
          />
          <StatTile
            label="Return / RTO Rate"
            value={`${num(returnRate, 2)}%`}
            sub="returned / (returned + sold)"
            testId="stat-return-rate"
            accent="#DC2626"
          />
          <StatTile
            label="Return Logistics Cost"
            value={inr(summary?.cost_of_returns_logistics || 0)}
            sub="reverse-leg fees"
            testId="stat-return-logistics"
            accent="#7C3AED"
          />
        </div>

        {/* Revenue Pending — clearly separate */}
        <Card className="p-5 border-blue-300 bg-blue-50" data-testid="pending-callout">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-blue-700 font-bold mb-1">
                Revenue Pending — NOT YET RECEIVED
              </div>
              <div className="text-2xl font-mono font-bold text-blue-900">
                {inr(summary?.total_revenue_pending || 0)}
              </div>
              <div className="text-xs text-blue-700 mt-1">
                This is a receivable sitting on unsettled sheets — do not count it
                as realised profit. It will move into &quot;Revenue Settled&quot;
                as Myntra clears the settlement cycle.
              </div>
            </div>
            <Badge color="blue">Receivable</Badge>
          </div>
        </Card>

        {/* Fees Interpretation */}
        {summary?.fees_interpretation?.available && (
          <Card
            className="p-4 border-slate-300 bg-slate-50 text-xs"
            data-testid="fees-interpretation-panel"
          >
            <div className="uppercase tracking-[0.2em] font-bold text-slate-500 mb-1 flex items-center gap-2">
              <Info className="w-3 h-3" /> Sample validation of fee treatment
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono">
              <div>
                <div className="text-slate-500">Sample size</div>
                <div className="font-bold">
                  {summary.fees_interpretation.sample_size}
                </div>
              </div>
              <div>
                <div className="text-slate-500">Σ Settled</div>
                <div className="font-bold">
                  {inr(summary.fees_interpretation.settled_sum)}
                </div>
              </div>
              <div>
                <div className="text-slate-500">Σ Fees</div>
                <div className="font-bold">
                  {inr(summary.fees_interpretation.fees_sum)}
                </div>
              </div>
              <div>
                <div className="text-slate-500">Σ Customer Paid</div>
                <div className="font-bold">
                  {inr(summary.fees_interpretation.customer_paid_sum)}
                </div>
              </div>
            </div>
            <div className="mt-2 text-slate-600">
              Interpretation:{" "}
              <span className="font-bold">
                {summary.fees_interpretation.interpretation}
              </span>{" "}
              — fees treated as{" "}
              <span className="font-bold uppercase">
                {summary.fees_interpretation.treated_as}
              </span>
            </div>
          </Card>
        )}

        {/* Chart 1 — Trend of units */}
        <Card className="p-5" data-testid="chart-units-trend">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">
                Units Trend
              </div>
              <div className="text-lg font-bold">
                Packed vs Returned vs Net Sold
              </div>
            </div>
            <div className="hidden md:flex gap-4 text-[10px] uppercase tracking-wider font-bold text-slate-500">
              <div className="flex items-center gap-1">
                <div className="w-2.5 h-2.5" style={{ background: PALETTE.packed }} /> Packed
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2.5 h-2.5" style={{ background: PALETTE.returned }} /> Returned
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2.5 h-2.5" style={{ background: PALETTE.netSold }} /> Net Sold
              </div>
            </div>
          </div>
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <LineChart data={trendChartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="Packed" stroke={PALETTE.packed} strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Returned" stroke={PALETTE.returned} strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Net Sold" stroke={PALETTE.netSold} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Chart 2 — Revenue vs COGS vs Profit */}
        <Card className="p-5" data-testid="chart-revenue-cogs">
          <div className="mb-3">
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">
              P&amp;L by {bucket}
            </div>
            <div className="text-lg font-bold">
              Revenue vs COGS vs Profit
            </div>
          </div>
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={revenueChartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => inr(v)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Revenue" fill={PALETTE.revenue} />
                <Bar dataKey="COGS"    fill={PALETTE.cogs} />
                <Bar dataKey="Profit"  fill={PALETTE.profit} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Chart 3 — Platform Fees Stacked */}
        <Card className="p-5" data-testid="chart-fees-breakdown">
          <div className="mb-3">
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">
              Fee Creep
            </div>
            <div className="text-lg font-bold">Platform Fees Breakdown</div>
          </div>
          <div style={{ width: "100%", height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={feesChartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => inr(v)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {Object.keys(FEE_LABELS).map((key) => (
                  <Bar
                    key={key}
                    dataKey={key}
                    name={FEE_LABELS[key]}
                    stackId="fees"
                    fill={PALETTE[key]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 text-xs text-slate-500">
            Note: Myntra typically nets these fees OUT of{" "}
            <code>Settled_Amount</code>, so they&apos;re shown here for
            visibility — <span className="font-bold">not subtracted again</span>{" "}
            from Revenue Settled.
          </div>
        </Card>

        {/* Table — By Style (worst first) */}
        <Card className="overflow-hidden" data-testid="by-style-table-card">
          <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">
                By Style — worst performers first
              </div>
              <div className="text-lg font-bold flex items-center gap-2">
                Liquidation Candidates
                <Badge color="red">Sorted by profit ↑</Badge>
              </div>
            </div>
            <div className="text-xs text-slate-500">
              {byStyleSorted.length} styles
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="by-style-table">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  {[
                    "Style",
                    "Color",
                    "Sold",
                    "Returned",
                    "Return %",
                    "Unit COGS",
                    "COGS",
                    "Revenue",
                    "Profit",
                    "Margin",
                    "Source",
                  ].map((h) => (
                    <th
                      key={h}
                      className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-600"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {byStyleSorted.length === 0 && (
                  <tr>
                    <td
                      colSpan={11}
                      className="px-3 py-8 text-center text-sm text-slate-400"
                      data-testid="by-style-empty"
                    >
                      No net-sold items in this period.
                    </td>
                  </tr>
                )}
                {byStyleSorted.map((r) => {
                  const loss = (r.profit || 0) < 0;
                  const highReturn = (r.return_rate_pct || 0) >= 20;
                  return (
                    <tr
                      key={`${r.style_id}-${r.color}`}
                      className={`border-b border-slate-100 hover:bg-slate-50 ${
                        loss ? "bg-red-50" : ""
                      }`}
                      data-testid={`by-style-row-${r.style_code}`}
                    >
                      <td className="px-3 py-2 font-mono text-xs font-bold">
                        {r.style_code}
                        {loss && (
                          <span className="ml-2">
                            <Badge color="red">LOSS</Badge>
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">{r.color || "—"}</td>
                      <td className="px-3 py-2 font-mono">{r.units_sold}</td>
                      <td className="px-3 py-2 font-mono">
                        {r.returned_units}
                      </td>
                      <td className="px-3 py-2">
                        {highReturn ? (
                          <Badge color="red">
                            {num(r.return_rate_pct, 2)}%
                          </Badge>
                        ) : (
                          <span className="font-mono">
                            {num(r.return_rate_pct, 2)}%
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono">
                        {inr(r.unit_cogs)}
                      </td>
                      <td className="px-3 py-2 font-mono">{inr(r.cogs)}</td>
                      <td className="px-3 py-2 font-mono">
                        {inr(r.revenue_settled)}
                      </td>
                      <td
                        className={`px-3 py-2 font-mono font-bold ${
                          loss ? "text-red-700" : "text-emerald-700"
                        }`}
                      >
                        {inr(r.profit)}
                      </td>
                      <td className="px-3 py-2 font-mono">
                        {num(r.margin_pct, 2)}%
                      </td>
                      <td className="px-3 py-2 text-[10px] text-slate-500">
                        <div className="flex items-center gap-1">
                          <Badge color={r.is_estimated ? "orange" : "green"}>
                            {r.is_estimated ? "Estimated" : "Reconciled"}
                          </Badge>
                          <span className="text-[10px] text-slate-400 font-mono">({r.revenue_source || "—"})</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Notes */}
        {summary?.notes?.length > 0 && (
          <Card className="p-5 bg-slate-50" data-testid="notes-panel">
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 mb-2">
              Interpretation Notes
            </div>
            <ul className="text-xs text-slate-700 space-y-1 list-disc pl-4">
              {summary.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {settlementOpen && (
        <SettlementImportDrawer onClose={() => setSettlementOpen(false)} onDone={load} />
      )}
    </div>
  );
}
