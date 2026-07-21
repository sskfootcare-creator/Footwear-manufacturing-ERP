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
  FileSpreadsheet,
  FileText,
  CheckCircle,
  Clock,
  AlertOctagon,
  HelpCircle,
  Plus,
  X,
  Check,
} from "lucide-react";
import { SettlementImportDrawer } from "./OnlineOrders";

const isoToday = () => new Date().toISOString().slice(0, 10);
const isoDaysAgo = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

export default function OnlineProfitability() {
  // Navigation tabs: 'overview', 'reconciliation', 'import', 'returns_deductions', 'unreconciled'
  const [activeTab, setActiveTab] = useState("reconciliation");

  // Filters & State
  const [platform, setPlatform] = useState("myntra");
  const [dateFrom, setDateFrom] = useState(isoDaysAgo(30));
  const [dateTo, setDateTo] = useState(isoToday());
  const [styleId, setStyleId] = useState("");
  const [bucket, setBucket] = useState("day");
  const [styles, setStyles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [settlementOpen, setSettlementOpen] = useState(false);

  // Reconciliation summary state
  const [recSummary, setRecSummary] = useState(null);
  const [recLoading, setRecLoading] = useState(false);

  // File import statuses
  const [uploadingState, setUploadingState] = useState({
    dailyPayments: false,
    settled: false,
    unsettled: false,
    monthlyReport: false,
  });
  const [uploadMessage, setUploadMessage] = useState("");

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

  // Load Reconciliation Engine Data
  const loadReconciliation = useCallback(async () => {
    setRecLoading(true);
    setError("");
    try {
      const { data } = await http.get("/online-reconciliation/summary", {
        params: { from_date: dateFrom, to_date: dateTo },
      });
      setRecSummary(data);
    } catch (err) {
      console.error("Failed to load reconciliation data:", err);
      setError("Failed to load reconciliation engine summary.");
    } finally {
      setRecLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => {
    loadReconciliation();
  }, [loadReconciliation]);

  // File import handlers
  const handleFileUpload = async (endpoint, file, stateKey) => {
    if (!file) return;
    setUploadingState((prev) => ({ ...prev, [stateKey]: true }));
    setUploadMessage("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await http.post(`/online-reconciliation/${endpoint}`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setUploadMessage(`Successfully imported ${res.data.filename || file.name}`);
      loadReconciliation();
    } catch (err) {
      setUploadMessage(`Error: ${err?.response?.data?.detail || err?.message || "Import failed"}`);
    } finally {
      setUploadingState((prev) => ({ ...prev, [stateKey]: false }));
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
      loadReconciliation();
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
              onClick={() => setActiveTab("reconciliation")}
              className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors flex items-center gap-2 ${
                activeTab === "reconciliation"
                  ? "bg-[#0F172A] text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
              data-testid="tab-reconciliation"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Reconciliation Engine
            </button>
            <button
              onClick={() => setActiveTab("import")}
              className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors flex items-center gap-2 ${
                activeTab === "import"
                  ? "bg-[#0F172A] text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
              data-testid="tab-import"
            >
              <Upload className="w-3.5 h-3.5" /> File Import Suite (5 Reports)
            </button>
            <button
              onClick={() => setActiveTab("returns_deductions")}
              className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors flex items-center gap-2 ${
                activeTab === "returns_deductions"
                  ? "bg-[#0F172A] text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
              data-testid="tab-returns"
            >
              <RotateCcw className="w-3.5 h-3.5" /> Return Charges & Deductions
            </button>
            <button
              onClick={() => setActiveTab("unreconciled")}
              className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors flex items-center gap-2 ${
                activeTab === "unreconciled"
                  ? "bg-[#0F172A] text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
              data-testid="tab-unreconciled"
            >
              <AlertOctagon className="w-3.5 h-3.5 text-amber-400" /> Unreconciled Orders
            </button>
          </div>

          <div className="flex items-center gap-2">
            <BtnSecondary onClick={() => setSnapshotModalOpen(true)} className="flex items-center gap-1.5 text-xs">
              <Plus className="w-3.5 h-3.5 text-[#C27842]" /> Cost Snapshot
            </BtnSecondary>
            <BtnSecondary onClick={loadReconciliation} disabled={recLoading} className="flex items-center gap-1.5 text-xs">
              <RefreshCw className={`w-3.5 h-3.5 ${recLoading ? "animate-spin" : ""}`} /> Refresh Engine
            </BtnSecondary>
          </div>
        </div>

        {uploadMessage && (
          <div className="bg-slate-900 text-white text-xs font-semibold px-4 py-2.5 rounded-sm flex items-center justify-between">
            <span>{uploadMessage}</span>
            <button onClick={() => setUploadMessage("")} className="text-slate-400 hover:text-white">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* ── TAB 1: RECONCILIATION ENGINE OVERVIEW & KPI CARDS ──────────────── */}
        {activeTab === "reconciliation" && recSummary && (
          <div className="space-y-6">
            {/* Rates & Badges Banner */}
            <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 p-6 text-white rounded-sm border-2 border-slate-700 shadow-md">
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                  <h3 className="font-black text-base uppercase tracking-wider flex items-center gap-2 text-white">
                    <CheckCircle className="w-5 h-5 text-emerald-400" /> 5-Report Reconciliation Status
                  </h3>
                  <p className="text-xs text-slate-300 mt-1">
                    Matched monthly order lines against 3-header settled/unsettled files & daily payments
                  </p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <div className="bg-slate-800/90 border border-emerald-500/50 px-4 py-2 text-center rounded-sm">
                    <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Report Join Rate</div>
                    <div className="text-xl font-black text-emerald-400" data-testid="report-join-rate-value">
                      {recSummary.join_rate_pct}%
                    </div>
                  </div>
                  <div className="bg-slate-800/90 border border-blue-500/50 px-4 py-2 text-center rounded-sm">
                    <div className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">COGS Resolution Rate</div>
                    <div className="text-xl font-black text-blue-400" data-testid="cogs-resolution-rate-value">
                      {recSummary.cogs_resolution_rate_pct}%
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Reconciliation KPI Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="reconciliation-kpi-grid">
              <Card className="p-5 border-l-4 border-l-emerald-600">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs uppercase tracking-wider font-bold text-slate-500">Settled Orders</span>
                  <Badge variant="green">Settled</Badge>
                </div>
                <div className="text-2xl font-black text-slate-900" data-testid="settled-count-value">
                  {recSummary.settled_count}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">Order lines reconciled to settled.xlsx</div>
              </Card>

              <Card className="p-5 border-l-4 border-l-blue-600">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs uppercase tracking-wider font-bold text-slate-500">Pending Settlement</span>
                  <Badge variant="blue">≤ 30 Days</Badge>
                </div>
                <div className="text-2xl font-black text-slate-900" data-testid="pending-count-value">
                  {recSummary.pending_count}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">Matched to unsettled.xlsx</div>
              </Card>

              <Card className="p-5 border-l-4 border-l-amber-500">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs uppercase tracking-wider font-bold text-slate-500">Aged Pending</span>
                  <Badge variant="yellow">&gt; 30 Days</Badge>
                </div>
                <div className="text-2xl font-black text-amber-700" data-testid="aged-pending-count-value">
                  {recSummary.aged_pending_count}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">Unsettled over 30 days old</div>
              </Card>

              <Card className="p-5 border-l-4 border-l-red-600">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs uppercase tracking-wider font-bold text-slate-500">Unmatched / Absent</span>
                  <Badge variant="red">FLAGGED</Badge>
                </div>
                <div className="text-2xl font-black text-red-600" data-testid="unmatched-count-value">
                  {recSummary.unmatched_count}
                </div>
                <div className="text-[11px] text-slate-500 mt-1">Delivered/active but absent from settlements</div>
              </Card>
            </div>

            {/* NEFT Cross-Check Warnings */}
            {recSummary.neft_mismatches && recSummary.neft_mismatches.length > 0 && (
              <Card className="p-5 border-2 border-red-300 bg-red-50/50">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle className="w-5 h-5 text-red-600" />
                  <h4 className="font-bold text-red-900 text-xs uppercase tracking-wider">
                    NEFT Cross-Check Mismatches (Daily Payments vs Settled.xlsx)
                  </h4>
                </div>
                <div className="space-y-2">
                  {recSummary.neft_mismatches.map((m, idx) => (
                    <div key={idx} className="bg-white p-3 border border-red-200 text-xs flex justify-between items-center">
                      <div>
                        <span className="font-bold font-mono text-slate-800">NEFT Ref: {m.neft_ref}</span>
                        <span className="text-slate-500 ml-3">Daily Payment: {inr(m.daily_payment_amount)}</span>
                        <span className="text-slate-500 ml-3">Settlement File: {inr(m.settlement_file_amount)}</span>
                      </div>
                      <Badge variant="red">Diff: {inr(m.difference)}</Badge>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Profitability Table by Style */}
            <Card className="overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-200 flex justify-between items-center bg-slate-50">
                <h4 className="font-bold text-xs uppercase tracking-wider text-slate-800 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-[#C27842]" /> Per-Style Online Profitability (Real Settlement + Actual COGS)
                </h4>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-100 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[10px] font-bold">
                      <th className="p-3">Style Code</th>
                      <th className="p-3 text-center">Units Sold</th>
                      <th className="p-3 text-right">Settled Revenue</th>
                      <th className="p-3 text-right">Platform Fees</th>
                      <th className="p-3 text-right">Actual COGS</th>
                      <th className="p-3 text-right">Net Profit</th>
                      <th className="p-3 text-center">COGS Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {recSummary.profitability_by_style.map((row) => (
                      <tr key={row.style_code} className="hover:bg-slate-50">
                        <td className="p-3 font-bold text-slate-900">{row.style_code}</td>
                        <td className="p-3 text-center font-semibold text-slate-700">{row.units}</td>
                        <td className="p-3 text-right font-black text-slate-900">{inr(row.settled_amount)}</td>
                        <td className="p-3 text-right text-red-600 font-semibold">{inr(row.platform_fees)}</td>
                        <td className="p-3 text-right font-bold text-amber-700">{inr(row.actual_cogs)}</td>
                        <td className={`p-3 text-right font-black ${row.net_profit >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                          {inr(row.net_profit)}
                        </td>
                        <td className="p-3 text-center">
                          {row.cost_estimated_count > 0 ? (
                            <Badge variant="yellow" title={`${row.cost_estimated_count} units used fallback estimate`}>
                              Cost Estimated ({row.cost_estimated_count})
                            </Badge>
                          ) : (
                            <Badge variant="green">Exact Snapshot</Badge>
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

        {/* ── TAB 2: FILE IMPORT SUITE ───────────────────────────────────────── */}
        {activeTab === "import" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6" data-testid="file-import-suite">
            {/* Slot 1: Daily Payments */}
            <Card className="p-5 border-t-4 border-t-blue-600 space-y-3">
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-600" />
                <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900">
                  1. Daily Payment Files (prepaid.csv / postpaid.csv)
                </h4>
              </div>
              <p className="text-xs text-slate-500">
                Parses order-line payment rows. <strong>Payment_Type</strong> column is parsed automatically; filename is ignored.
              </p>
              <input
                type="file"
                accept=".csv"
                onChange={(e) => handleFileUpload("import-daily-payments", e.target.files[0], "dailyPayments")}
                disabled={uploadingState.dailyPayments}
                className="block w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:border-0 file:text-xs file:font-bold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer"
                data-testid="input-daily-payments"
              />
            </Card>

            {/* Slot 2: Settled Orders */}
            <Card className="p-5 border-t-4 border-t-emerald-600 space-y-3">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-emerald-600" />
                <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900">
                  2. Settled Excel File (settled.xlsx)
                </h4>
              </div>
              <p className="text-xs text-slate-500">
                Multi-sheet Excel with 3-row header. Parses <strong>forward_settled</strong>, <strong>reverse_settled</strong>, and <strong>non_order_deduction</strong> sheets.
              </p>
              <input
                type="file"
                accept=".xlsx"
                onChange={(e) => handleFileUpload("import-settlements", e.target.files[0], "settled")}
                disabled={uploadingState.settled}
                className="block w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:border-0 file:text-xs file:font-bold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100 cursor-pointer"
                data-testid="input-settled-excel"
              />
            </Card>

            {/* Slot 3: Unsettled Orders */}
            <Card className="p-5 border-t-4 border-t-amber-500 space-y-3">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-amber-600" />
                <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900">
                  3. Unsettled Excel File (unsettled.xlsx)
                </h4>
              </div>
              <p className="text-xs text-slate-500">
                Multi-sheet Excel with 3-row header. Parses <strong>forward_unsettled</strong> and <strong>reverse_unsettled</strong> sheets for pending order status.
              </p>
              <input
                type="file"
                accept=".xlsx"
                onChange={(e) => handleFileUpload("import-settlements", e.target.files[0], "unsettled")}
                disabled={uploadingState.unsettled}
                className="block w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:border-0 file:text-xs file:font-bold file:bg-amber-50 file:text-amber-700 hover:file:bg-amber-100 cursor-pointer"
                data-testid="input-unsettled-excel"
              />
            </Card>

            {/* Slot 4: Monthly Order Report */}
            <Card className="p-5 border-t-4 border-t-purple-600 space-y-3">
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-purple-600" />
                <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900">
                  4. Monthly Order Report (monthly_order_report.csv)
                </h4>
              </div>
              <p className="text-xs text-slate-500">
                1 row = 1 unit order line. Used to reconcile every order unit against settled & unsettled records.
              </p>
              <input
                type="file"
                accept=".csv"
                onChange={(e) => handleFileUpload("import-monthly-report", e.target.files[0], "monthlyReport")}
                disabled={uploadingState.monthlyReport}
                className="block w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:border-0 file:text-xs file:font-bold file:bg-purple-50 file:text-purple-700 hover:file:bg-purple-100 cursor-pointer"
                data-testid="input-monthly-report"
              />
            </Card>
          </div>
        )}

        {/* ── TAB 3: RETURN CHARGES & NON-ORDER DEDUCTIONS ────────────────────── */}
        {activeTab === "returns_deductions" && recSummary && (
          <div className="space-y-6">
            {/* Return Charges by Style Table */}
            <Card className="p-5">
              <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900 mb-3 flex items-center gap-2 border-b pb-2">
                <RotateCcw className="w-4 h-4 text-purple-600" /> Return Charges Report by Style
              </h4>
              <p className="text-xs text-slate-500 mb-4">
                Sum of <strong>Logistics_Cost_Reverse_incl_Tax</strong> + <strong>Reverse_additional_charges</strong> from reverse settlement sheets.
              </p>
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-100 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[10px] font-bold">
                    <th className="p-3">Style Code</th>
                    <th className="p-3 text-right">Reverse Logistics & Additional Charges Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {Object.entries(recSummary.return_charges_by_style).map(([styleCode, amt]) => (
                    <tr key={styleCode} className="hover:bg-slate-50">
                      <td className="p-3 font-bold text-slate-900">{styleCode}</td>
                      <td className="p-3 text-right font-black text-purple-700">{inr(amt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            {/* Non-Order Deductions Ledger */}
            <Card className="p-5">
              <div className="flex justify-between items-center border-b pb-3 mb-3">
                <div>
                  <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900 flex items-center gap-2">
                    <DollarSign className="w-4 h-4 text-amber-600" /> Non-Order Deductions Ledger
                  </h4>
                  <p className="text-xs text-slate-500">Deductions not attributed to any specific order line</p>
                </div>
                <div className="text-right">
                  <div className="text-[10px] uppercase font-bold text-slate-500">Total Non-Order Deductions</div>
                  <div className="text-xl font-black text-red-600">{inr(recSummary.total_non_order_deductions)}</div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-100 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[10px] font-bold">
                      <th className="p-3">Date</th>
                      <th className="p-3">Seller ID</th>
                      <th className="p-3">Type</th>
                      <th className="p-3">UTR / Ref</th>
                      <th className="p-3">Description</th>
                      <th className="p-3 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {recSummary.non_order_deductions_ledger.map((ded) => (
                      <tr key={ded.id} className="hover:bg-slate-50">
                        <td className="p-3 font-mono font-semibold text-slate-700">{ded.settlement_date || "—"}</td>
                        <td className="p-3 font-bold text-slate-900">{ded.seller_id || "—"}</td>
                        <td className="p-3 whitespace-nowrap"><Badge variant="yellow">{ded.settlement_type || "Deduction"}</Badge></td>
                        <td className="p-3 font-mono text-slate-600">{ded.utr || ded.invoice_ref || "—"}</td>
                        <td className="p-3 text-slate-600">{ded.settlement_description || "—"}</td>
                        <td className="p-3 text-right font-black text-red-600">{inr(ded.settlement_amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}

        {/* ── TAB 4: UNRECONCILED ORDERS DRILL-DOWN ───────────────────────────── */}
        {activeTab === "unreconciled" && recSummary && (
          <Card className="p-5">
            <div className="flex justify-between items-center border-b pb-3 mb-4">
              <div>
                <h4 className="font-bold text-xs uppercase tracking-wider text-red-700 flex items-center gap-2">
                  <AlertOctagon className="w-4 h-4 text-red-600" /> Unreconciled / Flagged Orders ({recSummary.unreconciled_orders.length})
                </h4>
                <p className="text-xs text-slate-500">
                  Delivered/active orders absent from settlements or missing cost snapshots
                </p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse" data-testid="unreconciled-orders-table">
                <thead>
                  <tr className="bg-slate-100 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[10px] font-bold">
                    <th className="p-3">Seller Order ID</th>
                    <th className="p-3">Release ID</th>
                    <th className="p-3">Seller SKU Code</th>
                    <th className="p-3">Order Status</th>
                    <th className="p-3">Packed Date</th>
                    <th className="p-3">Flagged Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {recSummary.unreconciled_orders.map((u, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="p-3 font-bold font-mono text-slate-900">{u.seller_order_id}</td>
                      <td className="p-3 font-mono text-slate-700">{u.order_release_id}</td>
                      <td className="p-3 font-semibold text-slate-800">{u.seller_sku_code}</td>
                      <td className="p-3"><Badge variant="blue">{u.order_status}</Badge></td>
                      <td className="p-3 font-mono text-slate-600">{u.packed_on}</td>
                      <td className="p-3">
                        <div className="flex flex-wrap gap-1">
                          {u.reasons.map((r, rIdx) => (
                            <Badge key={rIdx} variant="red">{r}</Badge>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
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
