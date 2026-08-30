import { useState, useEffect, useCallback } from "react";
import { http, inr } from "../lib/api";
import { PageHeader, Card, Badge, BtnPrimary, BtnSecondary } from "../components/ui-kit";
import {
  Landmark,
  ArrowLeftRight,
  Upload,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Search,
  Filter,
  Plus,
  ArrowUpRight,
  ArrowDownLeft,
  FileSpreadsheet,
  Check,
  X,
  Sliders,
  Calendar,
  IndianRupee,
  Link as LinkIcon,
  Eye,
  Layers,
  HelpCircle,
  Clock,
  ShieldCheck,
  TrendingUp,
  TrendingDown,
} from "lucide-react";

export default function BankReconciliation() {
  const [accounts, setAccounts] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState("all");
  const [activeTab, setActiveTab] = useState("unmatched_lines"); // unmatched_lines | transfers | erp_expected | ledger
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState(null);

  // Statement lines
  const [statementLines, setStatementLines] = useState([]);
  const [statementFilter, setStatementFilter] = useState({
    status: "all",
    search: "",
    side: "all",
  });

  // Transfer suggestions
  const [suggestedTransfers, setSuggestedTransfers] = useState([]);
  const [transferLoading, setTransferLoading] = useState(false);

  // ERP Unmatched candidates
  const [erpCandidates, setErpCandidates] = useState([]);
  const [erpLoading, setErpLoading] = useState(false);
  const [erpSearch, setErpSearch] = useState("");

  // Modals state
  const [showImportModal, setShowImportModal] = useState(false);
  const [showAccountModal, setShowAccountModal] = useState(false);
  const [showManualMatchModal, setShowManualMatchModal] = useState(false);
  const [activeLineForMatch, setActiveLineForMatch] = useState(null);

  // Auto reconcile state
  const [reconciling, setReconciling] = useState(false);
  const [reconcileResult, setReconcileResult] = useState(null);

  // Toast / feedback
  const [msg, setMsg] = useState({ text: "", type: "info" });

  const notify = (text, type = "info") => {
    setMsg({ text, type });
    setTimeout(() => setMsg({ text: "", type: "info" }), 5000);
  };

  // ─────────────────────────────────────────────────────────────────────────────
  // Fetch Data Handlers
  // ─────────────────────────────────────────────────────────────────────────────

  const fetchAccounts = useCallback(async () => {
    try {
      const { data } = await http.get("/banking/accounts");
      setAccounts(Array.isArray(data) ? data : data.items || []);
    } catch (e) {
      notify(e.message || "Failed to load bank accounts", "error");
    }
  }, []);

  const fetchSummary = useCallback(async () => {
    try {
      const params = {};
      if (selectedAccountId && selectedAccountId !== "all") {
        params.bank_account_id = selectedAccountId;
      }
      const { data } = await http.get("/banking/reconciliation/summary", { params });
      setSummary(data);
    } catch (e) {
      console.error(e);
    }
  }, [selectedAccountId]);

  const fetchStatementLines = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 500 };
      if (selectedAccountId && selectedAccountId !== "all") {
        params.bank_account_id = selectedAccountId;
      }
      if (statementFilter.status !== "all") {
        params.match_status = statementFilter.status;
      }
      if (statementFilter.search) {
        params.search = statementFilter.search;
      }
      const { data } = await http.get("/banking/statement-lines", { params });
      setStatementLines(data.items || []);
    } catch (e) {
      notify(e.message || "Failed to load statement lines", "error");
    } finally {
      setLoading(false);
    }
  }, [selectedAccountId, statementFilter]);

  const fetchSuggestedTransfers = useCallback(async () => {
    setTransferLoading(true);
    try {
      const { data } = await http.get("/banking/transfers/suggested");
      setSuggestedTransfers(data.pairs || []);
    } catch (e) {
      console.error(e);
    } finally {
      setTransferLoading(false);
    }
  }, []);

  const fetchErpCandidates = useCallback(async () => {
    setErpLoading(true);
    try {
      const params = { limit: 100 };
      if (selectedAccountId && selectedAccountId !== "all") {
        params.bank_account_id = selectedAccountId;
      }
      if (erpSearch) {
        params.search = erpSearch;
      }
      const { data } = await http.get("/banking/unmatched-erp-candidates", { params });
      setErpCandidates(data.candidates || []);
    } catch (e) {
      console.error(e);
    } finally {
      setErpLoading(false);
    }
  }, [selectedAccountId, erpSearch]);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  useEffect(() => {
    fetchSummary();
    fetchStatementLines();
    fetchSuggestedTransfers();
    fetchErpCandidates();
  }, [selectedAccountId, fetchSummary, fetchStatementLines, fetchSuggestedTransfers, fetchErpCandidates]);

  // ─────────────────────────────────────────────────────────────────────────────
  // Action Handlers
  // ─────────────────────────────────────────────────────────────────────────────

  const handleRunAutoReconcile = async () => {
    if (selectedAccountId === "all") {
      notify("Please select a specific Bank Account to run auto-reconciliation.", "error");
      return;
    }
    setReconciling(true);
    try {
      const { data } = await http.post(`/banking/accounts/${selectedAccountId}/reconcile?date_window_days=3&amount_tolerance=1.0`);
      setReconcileResult(data);
      notify(
        `Auto-reconciliation complete: ${data.auto_matched_count} matches resolved, ${data.ambiguous_count} ambiguous lines left for review.`,
        "success"
      );
      fetchSummary();
      fetchStatementLines();
      fetchErpCandidates();
      fetchSuggestedTransfers();
    } catch (e) {
      notify(e.message || "Reconciliation failed", "error");
    } finally {
      setReconciling(false);
    }
  };

  const handleConfirmTransfer = async (fromId, toId) => {
    try {
      await http.post("/banking/transfers/confirm", {
        from_line_id: fromId,
        to_line_id: toId,
        notes: "Confirmed via UI Transfer Review",
      });
      notify("Transfer pair successfully confirmed and marked.", "success");
      fetchSuggestedTransfers();
      fetchSummary();
      fetchStatementLines();
    } catch (e) {
      notify(e.message || "Failed to confirm transfer", "error");
    }
  };

  const handleManualMatch = async (lineId, targetType, refId) => {
    try {
      await http.patch(`/banking/statement-lines/${lineId}/match`, {
        match_status: "matched",
        matched_to: { type: targetType, ref_id: refId },
      });
      notify("Statement line manually reconciled and linked!", "success");
      setShowManualMatchModal(false);
      setActiveLineForMatch(null);
      fetchSummary();
      fetchStatementLines();
      fetchErpCandidates();
    } catch (e) {
      notify(e.message || "Manual match failed", "error");
    }
  };

  const handleIgnoreLine = async (lineId) => {
    try {
      await http.patch(`/banking/statement-lines/${lineId}/match`, {
        match_status: "ignored",
      });
      notify("Statement line marked as ignored.", "info");
      fetchSummary();
      fetchStatementLines();
    } catch (e) {
      notify(e.message || "Failed to update line", "error");
    }
  };

  // ─────────────────────────────────────────────────────────────────────────────
  // Computed Account Summaries & Balances
  // ─────────────────────────────────────────────────────────────────────────────

  const selectedAccountDoc = accounts.find((a) => a.id === selectedAccountId);

  // Compute Balances
  const calculateAccountBalance = () => {
    if (!summary || !summary.accounts) {
      return { statementBal: 0, erpBal: 0, variance: 0 };
    }
    if (selectedAccountId === "all") {
      let totalOpening = 0;
      let totalNetMatched = 0;
      let totalNetStatement = 0;
      summary.accounts.forEach((acc) => {
        const op = acc.opening_balance || 0;
        totalOpening += op;
        totalNetMatched += (acc.matched_income || 0) - (acc.matched_expenses || 0) + (acc.transfers_in || 0) - (acc.transfers_out || 0);
        totalNetStatement += (acc.income || 0) - (acc.expenses || 0) + (acc.transfers_in || 0) - (acc.transfers_out || 0);
      });
      const erpBal = totalOpening + totalNetMatched;
      const statementBal = totalOpening + totalNetStatement;
      return {
        statementBal,
        erpBal,
        variance: Math.round((statementBal - erpBal) * 100) / 100,
      };
    } else {
      const acc = summary.accounts.find((a) => a.bank_account_id === selectedAccountId);
      if (!acc) return { statementBal: 0, erpBal: 0, variance: 0 };
      const op = acc.opening_balance || 0;
      const erpBal = op + (acc.matched_income || 0) - (acc.matched_expenses || 0) + (acc.transfers_in || 0) - (acc.transfers_out || 0);
      const statementBal = op + (acc.income || 0) - (acc.expenses || 0) + (acc.transfers_in || 0) - (acc.transfers_out || 0);
      return {
        statementBal,
        erpBal,
        variance: Math.round((statementBal - erpBal) * 100) / 100,
      };
    }
  };

  const { statementBal, erpBal, variance } = calculateAccountBalance();

  const unmatchedLines = statementLines.filter((l) => l.match_status === "unmatched");

  return (
    <div className="space-y-6 pb-12">
      {/* Toast Alert */}
      {msg.text && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg border text-sm font-medium flex items-center gap-2 animate-in fade-in ${
            msg.type === "error"
              ? "bg-rose-900/90 text-rose-100 border-rose-700"
              : msg.type === "success"
              ? "bg-emerald-900/90 text-emerald-100 border-emerald-700"
              : "bg-slate-900/90 text-slate-100 border-slate-700"
          }`}
        >
          {msg.type === "error" ? <AlertTriangle className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
          <span>{msg.text}</span>
          <button onClick={() => setMsg({ text: "", type: "info" })} className="ml-2 hover:opacity-75">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Header */}
      <PageHeader
        title="Bank Reconciliation"
        subtitle="Match bank statement lines against ERP payouts, client invoices, expenses, and inter-account transfers."
        actions={
          <div className="flex items-center gap-2.5 flex-wrap">
            <BtnSecondary onClick={() => setShowAccountModal(true)} className="flex items-center gap-2">
              <Plus className="w-4 h-4" /> Add Account
            </BtnSecondary>
            <BtnSecondary onClick={() => setShowImportModal(true)} className="flex items-center gap-2">
              <Upload className="w-4 h-4" /> Import Statement
            </BtnSecondary>
            <BtnPrimary
              onClick={handleRunAutoReconcile}
              disabled={reconciling || selectedAccountId === "all"}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700"
            >
              <RefreshCw className={`w-4 h-4 ${reconciling ? "animate-spin" : ""}`} />
              {reconciling ? "Reconciling..." : "Auto-Reconcile"}
            </BtnPrimary>
          </div>
        }
      />

      {/* Account Selector Tabs */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 border-b border-slate-700/60">
        <button
          onClick={() => setSelectedAccountId("all")}
          className={`px-4 py-2 rounded-t-lg font-medium text-sm transition-all flex items-center gap-2 ${
            selectedAccountId === "all"
              ? "bg-slate-800 text-indigo-400 border-b-2 border-indigo-500 shadow-sm"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
          }`}
        >
          <Layers className="w-4 h-4" /> All Accounts
        </button>
        {accounts.map((acc) => (
          <button
            key={acc.id}
            onClick={() => setSelectedAccountId(acc.id)}
            className={`px-4 py-2 rounded-t-lg font-medium text-sm transition-all flex items-center gap-2 ${
              selectedAccountId === acc.id
                ? "bg-slate-800 text-indigo-400 border-b-2 border-indigo-500 shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
            }`}
          >
            <Landmark className="w-4 h-4" />
            <span>{acc.name}</span>
            <span
              className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${
                acc.account_type === "online_channel" ? "bg-purple-900/60 text-purple-300" : "bg-blue-900/60 text-blue-300"
              }`}
            >
              {acc.account_type === "online_channel" ? "Online" : "B2B"}
            </span>
          </button>
        ))}
      </div>

      {/* Reconciliation Balance Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Statement Closing Balance */}
        <Card className="p-4 bg-slate-800/70 border-slate-700/60">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Statement Closing Balance</span>
            <FileSpreadsheet className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100">{inr(statementBal)}</div>
          <div className="text-xs text-slate-400 mt-2 flex items-center gap-1">
            <span>Opening: {inr(selectedAccountDoc ? selectedAccountDoc.opening_balance : summary?.accounts?.reduce((a, c) => a + (c.opening_balance || 0), 0) || 0)}</span>
          </div>
        </Card>

        {/* ERP-Recorded Balance */}
        <Card className="p-4 bg-slate-800/70 border-slate-700/60">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>ERP Reconciled Balance</span>
            <ShieldCheck className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100">{inr(erpBal)}</div>
          <div className="text-xs text-slate-400 mt-2 flex items-center gap-1">
            <span>Reconciled Payouts & Expenses</span>
          </div>
        </Card>

        {/* Variance Status Card */}
        <Card
          className={`p-4 border ${
            variance === 0
              ? "bg-emerald-950/30 border-emerald-700/50 text-emerald-200"
              : "bg-amber-950/30 border-amber-700/50 text-amber-200"
          }`}
        >
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider mb-1">
            <span>Reconciliation Variance</span>
            {variance === 0 ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <AlertTriangle className="w-4 h-4 text-amber-400" />}
          </div>
          <div className={`text-2xl font-bold ${variance === 0 ? "text-emerald-300" : "text-amber-300"}`}>
            {inr(Math.abs(variance))}
          </div>
          <div className="text-xs mt-2 flex items-center gap-1">
            {variance === 0 ? (
              <span className="text-emerald-400 font-medium">✓ In Perfect Balance (0.00)</span>
            ) : (
              <span className="text-amber-300 font-medium">
                {unmatchedLines.length} unmatched bank lines explaining variance
              </span>
            )}
          </div>
        </Card>

        {/* Net Operating Cash Flow */}
        <Card className="p-4 bg-slate-800/70 border-slate-700/60">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Net Operating Cashflow</span>
            <TrendingUp className="w-4 h-4 text-emerald-400" />
          </div>
          <div className={`text-2xl font-bold ${(summary?.summary?.net_operating_cashflow || 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {inr(summary?.summary?.net_operating_cashflow || 0)}
          </div>
          <div className="text-xs text-slate-400 mt-2 flex items-center justify-between">
            <span className="text-emerald-400">+{inr(summary?.summary?.total_income || 0)}</span>
            <span className="text-rose-400">-{inr(summary?.summary?.total_expenses || 0)}</span>
          </div>
        </Card>
      </div>

      {/* Main Content Tabs */}
      <div className="space-y-4">
        <div className="flex items-center gap-3 border-b border-slate-700/60 pb-2">
          <button
            onClick={() => setActiveTab("unmatched_lines")}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
              activeTab === "unmatched_lines"
                ? "bg-indigo-600 text-white shadow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
          >
            <AlertTriangle className="w-4 h-4" />
            <span>Unmatched Bank Lines</span>
            <span className="ml-1 bg-slate-900/60 px-1.5 py-0.5 rounded-full text-xs font-bold">
              {unmatchedLines.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("transfers")}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
              activeTab === "transfers"
                ? "bg-indigo-600 text-white shadow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
          >
            <ArrowLeftRight className="w-4 h-4" />
            <span>Suggested Transfers</span>
            {suggestedTransfers.length > 0 && (
              <span className="ml-1 bg-amber-500/20 text-amber-300 border border-amber-500/40 px-1.5 py-0.5 rounded-full text-xs font-bold">
                {suggestedTransfers.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab("erp_expected")}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
              activeTab === "erp_expected"
                ? "bg-indigo-600 text-white shadow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
          >
            <Clock className="w-4 h-4" />
            <span>Unmatched ERP Expected</span>
            <span className="ml-1 bg-slate-900/60 px-1.5 py-0.5 rounded-full text-xs font-bold">
              {erpCandidates.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("ledger")}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
              activeTab === "ledger"
                ? "bg-indigo-600 text-white shadow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
          >
            <FileSpreadsheet className="w-4 h-4" />
            <span>Statement Ledger</span>
            <span className="ml-1 bg-slate-900/60 px-1.5 py-0.5 rounded-full text-xs font-bold">
              {statementLines.length}
            </span>
          </button>
        </div>

        {/* TAB 1: UNMATCHED BANK STATEMENT LINES */}
        {activeTab === "unmatched_lines" && (
          <Card className="p-4 bg-slate-800/40 border-slate-700/60 space-y-4">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-slate-100 text-base">Unmatched Bank Transactions</h3>
                <span className="text-xs text-slate-400">
                  (Require manual linkage, new expense/income entry, or transfer confirmation)
                </span>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Search narration / ref..."
                  value={statementFilter.search}
                  onChange={(e) => setStatementFilter({ ...statementFilter, search: e.target.value })}
                  className="px-3 py-1.5 text-xs bg-slate-900 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 w-48"
                />
              </div>
            </div>

            {unmatchedLines.length === 0 ? (
              <div className="text-center py-12 text-slate-400 space-y-2">
                <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-400 opacity-80" />
                <p className="font-medium text-slate-300">All imported statement lines are fully reconciled!</p>
                <p className="text-xs text-slate-500">No unmatched bank transactions pending review.</p>
              </div>
            ) : (
              <div className="overflow-x-auto border border-slate-700/60 rounded-lg">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-900/80 text-xs uppercase font-semibold text-slate-400 border-b border-slate-700/60">
                    <tr>
                      <th className="p-3">Date</th>
                      <th className="p-3">Account</th>
                      <th className="p-3">Narration / Description</th>
                      <th className="p-3">Reference No</th>
                      <th className="p-3 text-right">Debit (Out)</th>
                      <th className="p-3 text-right">Credit (In)</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {unmatchedLines.map((line) => {
                      const acc = accounts.find((a) => a.id === line.bank_account_id);
                      const isCredit = (line.credit_amount || 0) > 0;
                      return (
                        <tr key={line.id} className="hover:bg-slate-800/50 transition-colors">
                          <td className="p-3 font-mono text-xs text-slate-300 whitespace-nowrap">{line.date}</td>
                          <td className="p-3 whitespace-nowrap">
                            <span className="text-xs font-medium text-slate-300">{acc ? acc.name : "Account"}</span>
                          </td>
                          <td className="p-3 max-w-xs truncate text-slate-200 text-xs font-medium" title={line.narration}>
                            {line.narration}
                          </td>
                          <td className="p-3 text-xs font-mono text-slate-400">{line.reference_no || "-"}</td>
                          <td className="p-3 text-right font-mono text-xs text-rose-400">
                            {line.debit_amount > 0 ? inr(line.debit_amount) : "-"}
                          </td>
                          <td className="p-3 text-right font-mono text-xs text-emerald-400 font-semibold">
                            {line.credit_amount > 0 ? inr(line.credit_amount) : "-"}
                          </td>
                          <td className="p-3 text-right whitespace-nowrap">
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                onClick={() => {
                                  setActiveLineForMatch(line);
                                  setShowManualMatchModal(true);
                                }}
                                className="px-2 py-1 bg-indigo-600/80 hover:bg-indigo-600 text-white rounded text-xs font-medium flex items-center gap-1 shadow-sm"
                              >
                                <LinkIcon className="w-3 h-3" /> Match ERP
                              </button>
                              <button
                                onClick={() => handleIgnoreLine(line.id)}
                                className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 rounded text-xs"
                                title="Ignore this line"
                              >
                                Ignore
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}

        {/* TAB 2: SUGGESTED INTER-ACCOUNT TRANSFERS */}
        {activeTab === "transfers" && (
          <Card className="p-4 bg-slate-800/40 border-slate-700/60 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-100 text-base">Suggested Inter-Account Transfers (Stage 4)</h3>
                <p className="text-xs text-slate-400">
                  Transfers move funds between your own bank accounts. When confirmed, they are strictly excluded from income/expense totals.
                </p>
              </div>
              <button
                onClick={fetchSuggestedTransfers}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs flex items-center gap-1.5"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${transferLoading ? "animate-spin" : ""}`} /> Refresh
              </button>
            </div>

            {suggestedTransfers.length === 0 ? (
              <div className="text-center py-12 text-slate-400 space-y-2">
                <CheckCircle2 className="w-8 h-8 mx-auto text-slate-500 opacity-60" />
                <p className="font-medium text-slate-300">No unconfirmed transfer pairs detected.</p>
                <p className="text-xs text-slate-500">
                  Matching debit & credit transactions across different bank accounts will surface here for confirmation.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3">
                {suggestedTransfers.map((pair) => (
                  <div
                    key={pair.pair_id}
                    className="p-4 bg-slate-900/80 border border-slate-700 rounded-xl flex items-center justify-between gap-4 flex-wrap"
                  >
                    {/* From Account (Debit) */}
                    <div className="flex-1 min-w-[240px] space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-rose-900/60 text-rose-300 border border-rose-700/50 rounded text-[10px] font-bold uppercase">
                          Sending Account
                        </span>
                        <span className="text-xs font-semibold text-slate-200">{pair.from_line.bank_account_name}</span>
                      </div>
                      <div className="text-sm font-mono text-rose-400 font-bold">-{inr(pair.from_line.amount)}</div>
                      <div className="text-xs text-slate-400 truncate" title={pair.from_line.narration}>
                        {pair.from_line.narration} ({pair.from_line.date})
                      </div>
                    </div>

                    {/* Arrow Divider */}
                    <div className="flex flex-col items-center justify-center px-4 py-2 bg-slate-800/80 rounded-lg border border-slate-700/50">
                      <ArrowLeftRight className="w-5 h-5 text-indigo-400" />
                      <span className="text-[10px] text-slate-400 font-mono mt-0.5">
                        {pair.day_diff === 0 ? "Same Day" : `±${pair.day_diff} Day(s)`}
                      </span>
                    </div>

                    {/* To Account (Credit) */}
                    <div className="flex-1 min-w-[240px] space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 bg-emerald-900/60 text-emerald-300 border border-emerald-700/50 rounded text-[10px] font-bold uppercase">
                          Receiving Account
                        </span>
                        <span className="text-xs font-semibold text-slate-200">{pair.to_line.bank_account_name}</span>
                      </div>
                      <div className="text-sm font-mono text-emerald-400 font-bold">+{inr(pair.to_line.amount)}</div>
                      <div className="text-xs text-slate-400 truncate" title={pair.to_line.narration}>
                        {pair.to_line.narration} ({pair.to_line.date})
                      </div>
                    </div>

                    {/* Confirmation Button */}
                    <div className="flex items-center">
                      <button
                        onClick={() => handleConfirmTransfer(pair.from_line.id, pair.to_line.id)}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-md transition-colors"
                      >
                        <Check className="w-4 h-4" /> Confirm Transfer
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}

        {/* TAB 3: UNMATCHED ERP EXPECTED TRANSACTIONS */}
        {activeTab === "erp_expected" && (
          <Card className="p-4 bg-slate-800/40 border-slate-700/60 space-y-4">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div>
                <h3 className="font-semibold text-slate-100 text-base">Unmatched / Expected ERP Transactions</h3>
                <p className="text-xs text-slate-400">
                  Invoiced client amounts, online settlements, and recorded expenses not yet confirmed on bank statements.
                </p>
              </div>
              <input
                type="text"
                placeholder="Search ERP transactions..."
                value={erpSearch}
                onChange={(e) => setErpSearch(e.target.value)}
                className="px-3 py-1.5 text-xs bg-slate-900 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 w-56"
              />
            </div>

            {erpCandidates.length === 0 ? (
              <div className="text-center py-12 text-slate-400 space-y-2">
                <CheckCircle2 className="w-8 h-8 mx-auto text-slate-500 opacity-60" />
                <p className="font-medium text-slate-300">No unreconciled ERP records found.</p>
              </div>
            ) : (
              <div className="overflow-x-auto border border-slate-700/60 rounded-lg">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-900/80 text-xs uppercase font-semibold text-slate-400 border-b border-slate-700/60">
                    <tr>
                      <th className="p-3">Date</th>
                      <th className="p-3">Type</th>
                      <th className="p-3">Party / Channel</th>
                      <th className="p-3">Description</th>
                      <th className="p-3">Reference</th>
                      <th className="p-3 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {erpCandidates.map((c) => (
                      <tr key={`${c.type}-${c.id}`} className="hover:bg-slate-800/50 transition-colors">
                        <td className="p-3 font-mono text-xs text-slate-300 whitespace-nowrap">{c.date}</td>
                        <td className="p-3 whitespace-nowrap">
                          <span
                            className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                              c.type === "settlement"
                                ? "bg-purple-900/60 text-purple-300"
                                : c.type === "payment"
                                ? "bg-emerald-900/60 text-emerald-300"
                                : "bg-rose-900/60 text-rose-300"
                            }`}
                          >
                            {c.type}
                          </span>
                        </td>
                        <td className="p-3 text-xs font-medium text-slate-200">{c.party}</td>
                        <td className="p-3 text-xs text-slate-300 max-w-xs truncate">{c.description}</td>
                        <td className="p-3 font-mono text-xs text-slate-400">{c.reference || "-"}</td>
                        <td
                          className={`p-3 text-right font-mono text-xs font-semibold ${
                            c.side === "credit" ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {inr(c.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}

        {/* TAB 4: STATEMENT LEDGER */}
        {activeTab === "ledger" && (
          <Card className="p-4 bg-slate-800/40 border-slate-700/60 space-y-4">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <select
                  value={statementFilter.status}
                  onChange={(e) => setStatementFilter({ ...statementFilter, status: e.target.value })}
                  className="px-3 py-1.5 text-xs bg-slate-900 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-indigo-500"
                >
                  <option value="all">All Match Statuses</option>
                  <option value="matched">Matched Only</option>
                  <option value="unmatched">Unmatched Only</option>
                  <option value="transfer">Transfers Only</option>
                  <option value="ignored">Ignored Only</option>
                </select>

                <input
                  type="text"
                  placeholder="Search narration..."
                  value={statementFilter.search}
                  onChange={(e) => setStatementFilter({ ...statementFilter, search: e.target.value })}
                  className="px-3 py-1.5 text-xs bg-slate-900 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 w-52"
                />
              </div>

              <div className="text-xs text-slate-400">Total lines: {statementLines.length}</div>
            </div>

            <div className="overflow-x-auto border border-slate-700/60 rounded-lg max-h-[600px]">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-900/90 sticky top-0 text-xs uppercase font-semibold text-slate-400 border-b border-slate-700/60 z-10">
                  <tr>
                    <th className="p-3">Date</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Narration</th>
                    <th className="p-3">Ref No</th>
                    <th className="p-3 text-right">Debit</th>
                    <th className="p-3 text-right">Credit</th>
                    <th className="p-3 text-right">Running Balance</th>
                    <th className="p-3">Matched Entity</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {statementLines.map((line) => (
                    <tr key={line.id} className="hover:bg-slate-800/50 transition-colors">
                      <td className="p-3 font-mono text-xs text-slate-300 whitespace-nowrap">{line.date}</td>
                      <td className="p-3 whitespace-nowrap">
                        <span
                          className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                            line.match_status === "matched"
                              ? "bg-emerald-900/60 text-emerald-300 border border-emerald-700/40"
                              : line.match_status === "transfer"
                              ? "bg-indigo-900/60 text-indigo-300 border border-indigo-700/40"
                              : line.match_status === "ignored"
                              ? "bg-slate-800 text-slate-400"
                              : "bg-amber-900/60 text-amber-300 border border-amber-700/40"
                          }`}
                        >
                          {line.match_status}
                        </span>
                      </td>
                      <td className="p-3 text-xs text-slate-200 max-w-xs truncate" title={line.narration}>
                        {line.narration}
                      </td>
                      <td className="p-3 font-mono text-xs text-slate-400">{line.reference_no || "-"}</td>
                      <td className="p-3 text-right font-mono text-xs text-rose-400">
                        {line.debit_amount > 0 ? inr(line.debit_amount) : "-"}
                      </td>
                      <td className="p-3 text-right font-mono text-xs text-emerald-400 font-semibold">
                        {line.credit_amount > 0 ? inr(line.credit_amount) : "-"}
                      </td>
                      <td className="p-3 text-right font-mono text-xs text-slate-300">
                        {line.running_balance != null ? inr(line.running_balance) : "-"}
                      </td>
                      <td className="p-3 text-xs text-slate-400">
                        {line.matched_to ? (
                          <span className="font-mono text-[11px] text-indigo-300 bg-indigo-950/60 px-1.5 py-0.5 rounded border border-indigo-800/40">
                            {line.matched_to.type} #{String(line.matched_to.ref_id).slice(-6)}
                          </span>
                        ) : (
                          "-"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </div>

      {/* ─────────────────────────────────────────────────────────────────────────
          MODALS
         ───────────────────────────────────────────────────────────────────────── */}

      {/* 1. MANUAL MATCH MODAL */}
      {showManualMatchModal && activeLineForMatch && (
        <ManualMatchModal
          line={activeLineForMatch}
          accounts={accounts}
          onClose={() => {
            setShowManualMatchModal(false);
            setActiveLineForMatch(null);
          }}
          onMatch={handleManualMatch}
        />
      )}

      {/* 2. IMPORT STATEMENT MODAL */}
      {showImportModal && (
        <ImportStatementModal
          accounts={accounts}
          selectedAccountId={selectedAccountId !== "all" ? selectedAccountId : accounts[0]?.id}
          onClose={() => setShowImportModal(false)}
          onSuccess={() => {
            setShowImportModal(false);
            notify("Statement imported successfully!", "success");
            fetchSummary();
            fetchStatementLines();
            fetchSuggestedTransfers();
          }}
        />
      )}

      {/* 3. ADD BANK ACCOUNT MODAL */}
      {showAccountModal && (
        <AddBankAccountModal
          onClose={() => setShowAccountModal(false)}
          onSuccess={() => {
            setShowAccountModal(false);
            notify("Bank account created!", "success");
            fetchAccounts();
          }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-Modal: Manual Match Modal
// ─────────────────────────────────────────────────────────────────────────────
function ManualMatchModal({ line, accounts, onClose, onMatch }) {
  const [candidates, setCandidates] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const isCredit = (line.credit_amount || 0) > 0;
  const targetSide = isCredit ? "credit" : "debit";
  const amount = isCredit ? line.credit_amount : line.debit_amount;

  useEffect(() => {
    const fetchCandidates = async () => {
      setLoading(true);
      try {
        const { data } = await http.get("/banking/unmatched-erp-candidates", {
          params: {
            bank_account_id: line.bank_account_id,
            side: targetSide,
            search,
            limit: 50,
          },
        });
        setCandidates(data.candidates || []);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchCandidates();
  }, [line.bank_account_id, targetSide, search]);

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl space-y-4">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-800/80 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <LinkIcon className="w-5 h-5 text-indigo-400" />
            <h3 className="font-semibold text-slate-100 text-base">Manual Link & Reconcile</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Selected Bank Line Banner */}
        <div className="mx-6 p-3.5 bg-slate-800/60 border border-slate-700/80 rounded-xl space-y-1">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Statement Line to Match</div>
          <div className="flex items-center justify-between">
            <span className="font-medium text-sm text-slate-200 truncate">{line.narration}</span>
            <span className={`font-mono text-sm font-bold ${isCredit ? "text-emerald-400" : "text-rose-400"}`}>
              {isCredit ? `+${inr(amount)}` : `-${inr(amount)}`}
            </span>
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-3">
            <span>Date: {line.date}</span>
            {line.reference_no && <span>Ref: {line.reference_no}</span>}
          </div>
        </div>

        {/* Search Candidates */}
        <div className="px-6">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search ERP candidate payouts, payments, invoices, or payees..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>

        {/* Candidate List */}
        <div className="px-6 max-h-72 overflow-y-auto space-y-2">
          {loading ? (
            <div className="text-center py-8 text-slate-500">Searching ERP candidates...</div>
          ) : candidates.length === 0 ? (
            <div className="text-center py-8 text-slate-400">No matching unallocated ERP transactions found.</div>
          ) : (
            candidates.map((c) => {
              const diff = Math.abs(c.amount - amount);
              return (
                <div
                  key={`${c.type}-${c.id}`}
                  className="p-3 bg-slate-800/70 border border-slate-700 rounded-xl flex items-center justify-between gap-4 hover:border-indigo-500/60 transition-colors"
                >
                  <div className="space-y-0.5 flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-indigo-900/60 text-indigo-300">
                        {c.type}
                      </span>
                      <span className="text-xs font-semibold text-slate-200 truncate">{c.description}</span>
                    </div>
                    <div className="text-xs text-slate-400 flex items-center gap-3">
                      <span>Date: {c.date}</span>
                      <span>Party: {c.party}</span>
                      {diff <= 1.0 && <span className="text-emerald-400 font-medium">✓ Amount Match</span>}
                    </div>
                  </div>
                  <div className="text-right whitespace-nowrap">
                    <div className="font-mono text-sm font-bold text-slate-100">{inr(c.amount)}</div>
                    <button
                      onClick={() => onMatch(line.id, c.type, c.id)}
                      className="mt-1 px-3 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-semibold flex items-center gap-1 shadow"
                    >
                      <Check className="w-3.5 h-3.5" /> Link This
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-slate-800/80 border-t border-slate-700 flex justify-end">
          <BtnSecondary onClick={onClose}>Close</BtnSecondary>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-Modal: Import Statement Modal
// ─────────────────────────────────────────────────────────────────────────────
function ImportStatementModal({ accounts, selectedAccountId, onClose, onSuccess }) {
  const [accId, setAccId] = useState(selectedAccountId || accounts[0]?.id || "");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");

  const handlePreviewOrImport = async (dryRun = true) => {
    if (!accId) {
      setError("Please select a bank account.");
      return;
    }
    if (!file) {
      setError("Please choose a statement file (.csv or .xlsx).");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const { data } = await http.post(`/banking/accounts/${accId}/statement/import?dry_run=${dryRun}`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      if (dryRun) {
        setPreview(data);
      } else {
        onSuccess();
      }
    } catch (e) {
      setError(e.message || "Import failed. Please check the file column layout.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl space-y-4">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-800/80 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Upload className="w-5 h-5 text-indigo-400" />
            <h3 className="font-semibold text-slate-100 text-base">Import Bank Statement</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-rose-950/60 border border-rose-700/60 text-rose-200 rounded-lg text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Account Selection */}
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300">Select Target Bank Account</label>
            <select
              value={accId}
              onChange={(e) => setAccId(e.target.value)}
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.bank_name}) — {a.account_type === "online_channel" ? "Online Channel" : "B2B Client"}
                </option>
              ))}
            </select>
          </div>

          {/* File Upload Box */}
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300">Statement File (.CSV or .XLSX)</label>
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(e) => {
                setFile(e.target.files[0] || null);
                setPreview(null);
              }}
              className="w-full text-xs text-slate-400 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-600 file:text-white hover:file:bg-indigo-500 cursor-pointer bg-slate-950 p-2 border border-slate-700 rounded-lg"
            />
          </div>

          {/* Preview Details */}
          {preview && (
            <div className="p-3.5 bg-slate-800/80 border border-slate-700 rounded-xl space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-emerald-400">
                <span>✓ Verified Layout: {preview.parsed_count} transactions parsed</span>
                <span>Total Rows: {preview.total_file_rows}</span>
              </div>
              <div className="text-[11px] text-slate-400 space-y-1">
                {preview.sample?.slice(0, 2).map((s, idx) => (
                  <div key={idx} className="flex justify-between border-b border-slate-700/40 pb-1">
                    <span className="truncate max-w-[240px]">{s.narration} ({s.date})</span>
                    <span className="font-mono text-slate-200">
                      {s.credit_amount > 0 ? `+${inr(s.credit_amount)}` : `-${inr(s.debit_amount)}`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 bg-slate-800/80 border-t border-slate-700 flex items-center justify-between">
          <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          <div className="flex gap-2">
            {!preview ? (
              <BtnPrimary onClick={() => handlePreviewOrImport(true)} disabled={loading || !file}>
                {loading ? "Parsing..." : "Preview Layout"}
              </BtnPrimary>
            ) : (
              <BtnPrimary onClick={() => handlePreviewOrImport(false)} disabled={loading} className="bg-emerald-600 hover:bg-emerald-500">
                {loading ? "Importing..." : "Confirm & Import Rows"}
              </BtnPrimary>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-Modal: Add Bank Account Modal
// ─────────────────────────────────────────────────────────────────────────────
function AddBankAccountModal({ onClose, onSuccess }) {
  const [formData, setFormData] = useState({
    name: "",
    bank_name: "HDFC",
    account_number_last4: "",
    account_type: "b2b_client",
    opening_balance: 0,
    opening_balance_date: new Date().toISOString().slice(0, 10),
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name || !formData.account_number_last4) {
      setError("Please fill in Account Name and Last 4 digits.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await http.post("/banking/accounts", {
        ...formData,
        opening_balance: parseFloat(formData.opening_balance) || 0,
      });
      onSuccess();
    } catch (err) {
      setError(err.message || "Failed to create account");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl space-y-4">
        <div className="px-6 py-4 bg-slate-800/80 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Landmark className="w-5 h-5 text-indigo-400" />
            <h3 className="font-semibold text-slate-100 text-base">Add Bank Account</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-3.5">
          {error && (
            <div className="p-3 bg-rose-950/60 border border-rose-700 text-rose-200 rounded-lg text-xs">
              {error}
            </div>
          )}

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300">Account Display Name</label>
            <input
              type="text"
              placeholder="e.g. HDFC - Online Payouts"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300">Bank Name</label>
              <input
                type="text"
                placeholder="e.g. HDFC, UCO Bank"
                value={formData.bank_name}
                onChange={(e) => setFormData({ ...formData, bank_name: e.target.value })}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300">Last 4 Digits</label>
              <input
                type="text"
                maxLength={6}
                placeholder="e.g. 4321"
                value={formData.account_number_last4}
                onChange={(e) => setFormData({ ...formData, account_number_last4: e.target.value })}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300">Account Category / Purpose</label>
            <select
              value={formData.account_type}
              onChange={(e) => setFormData({ ...formData, account_type: e.target.value })}
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="online_channel">Online Channel Account (Myntra / Flipkart Settlements)</option>
              <option value="b2b_client">B2B Offline Account (Client Invoices & General Operations)</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300">Opening Balance (₹)</label>
              <input
                type="number"
                step="0.01"
                value={formData.opening_balance}
                onChange={(e) => setFormData({ ...formData, opening_balance: e.target.value })}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300">Opening Date</label>
              <input
                type="date"
                value={formData.opening_balance_date}
                onChange={(e) => setFormData({ ...formData, opening_balance_date: e.target.value })}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              />
            </div>
          </div>

          <div className="pt-3 flex items-center justify-end gap-2 border-t border-slate-700">
            <BtnSecondary onClick={onClose} type="button">Cancel</BtnSecondary>
            <BtnPrimary type="submit" disabled={loading}>
              {loading ? "Creating..." : "Save Account"}
            </BtnPrimary>
          </div>
        </form>
      </div>
    </div>
  );
}
