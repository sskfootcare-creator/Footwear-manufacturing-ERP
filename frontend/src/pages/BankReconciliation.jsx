import { useState, useEffect, useCallback } from "react";
import { http, inr, formatApiError } from "../lib/api";
import { PageHeader, Card, Badge, BtnPrimary, BtnSecondary, Input, Select } from "../components/ui-kit";
import {
  Landmark,
  ArrowLeftRight,
  Upload,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Search,
  Plus,
  ArrowUpRight,
  ArrowDownLeft,
  FileSpreadsheet,
  Check,
  X,
  Link as LinkIcon,
  Layers,
  Clock,
  ShieldCheck,
  TrendingUp,
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
      let totalReconciledIn = 0;
      let totalReconciledOut = 0;
      let totalStatementDiff = 0;

      summary.accounts.forEach((acc) => {
        totalOpening += acc.opening_balance || 0;
        totalReconciledIn += acc.total_reconciled_credits || 0;
        totalReconciledOut += acc.total_reconciled_debits || 0;
        totalStatementDiff += acc.net_statement_flow || 0;
      });

      const erpBal = totalOpening + totalReconciledIn - totalReconciledOut;
      const statementBal = totalOpening + totalStatementDiff;
      const variance = statementBal - erpBal;
      return { statementBal, erpBal, variance };
    }

    const current = summary.accounts.find((a) => a.bank_account_id === selectedAccountId);
    if (!current) {
      return {
        statementBal: selectedAccountDoc?.opening_balance || 0,
        erpBal: selectedAccountDoc?.opening_balance || 0,
        variance: 0,
      };
    }

    const erpBal = (current.opening_balance || 0) + (current.total_reconciled_credits || 0) - (current.total_reconciled_debits || 0);
    const statementBal = (current.opening_balance || 0) + (current.net_statement_flow || 0);
    const variance = statementBal - erpBal;
    return { statementBal, erpBal, variance };
  };

  const { statementBal, erpBal, variance } = calculateAccountBalance();

  const unmatchedLines = statementLines.filter((l) => l.match_status === "unmatched");

  return (
    <div>
      {/* Toast Alert */}
      {msg.text && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-3 border-2 shadow-2xl text-xs font-bold uppercase tracking-wider flex items-center gap-2 animate-in fade-in ${
            msg.type === "error"
              ? "bg-red-50 text-red-900 border-red-600"
              : msg.type === "success"
              ? "bg-emerald-50 text-emerald-900 border-emerald-600"
              : "bg-slate-900 text-white border-slate-900"
          }`}
        >
          {msg.type === "error" ? <AlertTriangle className="w-4 h-4 text-red-600" /> : <CheckCircle2 className="w-4 h-4 text-emerald-600" />}
          <span>{msg.text}</span>
          <button onClick={() => setMsg({ text: "", type: "info" })} className="ml-2 hover:opacity-75">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Header */}
      <PageHeader
        title="Bank Reconciliation"
        subtitle="Finance / Bank Reconciliation"
        testId="bank-reconciliation-header"
        action={
          <div className="flex items-center gap-2 flex-wrap">
            <BtnSecondary onClick={() => setShowAccountModal(true)} className="flex items-center gap-1.5" testId="add-account-btn">
              <Plus className="w-3.5 h-3.5" /> Add Account
            </BtnSecondary>
            <BtnSecondary onClick={() => setShowImportModal(true)} className="flex items-center gap-1.5" testId="import-statement-btn">
              <Upload className="w-3.5 h-3.5" /> Import Statement
            </BtnSecondary>
            <BtnPrimary
              onClick={handleRunAutoReconcile}
              disabled={reconciling || selectedAccountId === "all"}
              className="flex items-center gap-1.5 bg-[#1E3A8A] border-[#1E3A8A] hover:bg-[#172554]"
              testId="auto-reconcile-btn"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${reconciling ? "animate-spin" : ""}`} />
              {reconciling ? "Reconciling..." : "Auto-Reconcile"}
            </BtnPrimary>
          </div>
        }
      />

      <div className="p-2 sm:p-4 lg:p-8 space-y-6">
        {/* Account Selector Tabs */}
        <div className="flex items-center gap-2 border-b border-slate-200 overflow-x-auto overflow-y-hidden">
          <button
            onClick={() => setSelectedAccountId("all")}
            data-testid="tab-account-all"
            className={`px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px flex items-center gap-2 ${
              selectedAccountId === "all"
                ? "border-[#1E3A8A] text-[#1E3A8A] bg-slate-50"
                : "border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50/50"
            }`}
          >
            <Layers className="w-3.5 h-3.5" /> All Accounts
          </button>
          {accounts.map((acc) => (
            <button
              key={acc.id}
              onClick={() => setSelectedAccountId(acc.id)}
              data-testid={`tab-account-${acc.id}`}
              className={`px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px flex items-center gap-2 whitespace-nowrap ${
                selectedAccountId === acc.id
                  ? "border-[#1E3A8A] text-[#1E3A8A] bg-slate-50"
                  : "border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50/50"
              }`}
            >
              <Landmark className="w-3.5 h-3.5" />
              <span>{acc.name}</span>
              <span
                className={`text-[10px] uppercase font-bold px-1.5 py-0.5 border ${
                  acc.account_type === "online_channel"
                    ? "bg-purple-100 text-purple-800 border-purple-300"
                    : "bg-blue-100 text-blue-800 border-blue-300"
                }`}
              >
                {acc.account_type === "online_channel" ? "Online" : "B2B"}
              </span>
            </button>
          ))}
        </div>

        {/* Reconciliation Balance Overview Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="reconcile-overview-cards">
          {/* Statement Closing Balance */}
          <Card className="p-5 border-l-4 border-l-slate-700 bg-gradient-to-br from-white to-slate-50/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">Statement Closing Balance</span>
              <div className="w-8 h-8 rounded-full bg-slate-100 text-slate-700 grid place-items-center">
                <FileSpreadsheet className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-black font-mono text-slate-900" data-testid="statement-balance-val">
              {inr(statementBal)}
            </div>
            <div className="text-xs text-slate-500 font-medium mt-2 pt-2 border-t border-slate-100">
              Opening: {inr(selectedAccountDoc ? selectedAccountDoc.opening_balance : summary?.accounts?.reduce((a, c) => a + (c.opening_balance || 0), 0) || 0)}
            </div>
          </Card>

          {/* ERP-Recorded Balance */}
          <Card className="p-5 border-l-4 border-l-blue-600 bg-gradient-to-br from-white to-blue-50/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">ERP Reconciled Balance</span>
              <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 grid place-items-center">
                <ShieldCheck className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-black font-mono text-slate-900" data-testid="erp-balance-val">
              {inr(erpBal)}
            </div>
            <div className="text-xs text-slate-500 font-medium mt-2 pt-2 border-t border-slate-100">
              Reconciled Payouts & Expenses
            </div>
          </Card>

          {/* Variance Status Card */}
          <Card
            className={`p-5 border-l-4 ${
              variance === 0
                ? "border-l-emerald-600 bg-gradient-to-br from-white to-emerald-50/30"
                : "border-l-amber-500 bg-gradient-to-br from-white to-amber-50/30"
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">Reconciliation Variance</span>
              <div
                className={`w-8 h-8 rounded-full grid place-items-center ${
                  variance === 0 ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
                }`}
              >
                {variance === 0 ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
              </div>
            </div>
            <div
              className={`text-2xl font-black font-mono ${variance === 0 ? "text-emerald-700" : "text-amber-700"}`}
              data-testid="variance-val"
            >
              {inr(Math.abs(variance))}
            </div>
            <div className="text-xs font-medium mt-2 pt-2 border-t border-slate-100">
              {variance === 0 ? (
                <span className="text-emerald-700 font-bold">✓ In Perfect Balance (0.00)</span>
              ) : (
                <span className="text-amber-700 font-bold">
                  {unmatchedLines.length} unmatched line(s) pending
                </span>
              )}
            </div>
          </Card>

          {/* Net Operating Cash Flow */}
          <Card className="p-5 border-l-4 border-l-[#C27842] bg-gradient-to-br from-white to-orange-50/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">Net Operating Cashflow</span>
              <div className="w-8 h-8 rounded-full bg-orange-100 text-[#C27842] grid place-items-center">
                <TrendingUp className="w-4 h-4" />
              </div>
            </div>
            <div
              className={`text-2xl font-black font-mono ${(summary?.summary?.net_operating_cashflow || 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}
              data-testid="cashflow-val"
            >
              {inr(summary?.summary?.net_operating_cashflow || 0)}
            </div>
            <div className="text-xs text-slate-500 font-medium mt-2 pt-2 border-t border-slate-100 flex items-center justify-between">
              <span className="text-emerald-700 font-bold">+{inr(summary?.summary?.total_income || 0)}</span>
              <span className="text-red-700 font-bold">-{inr(summary?.summary?.total_expenses || 0)}</span>
            </div>
          </Card>
        </div>

        {/* Main Section Navigation Tabs */}
        <div className="space-y-4">
          <div className="flex items-center gap-1 border-b border-slate-200 overflow-x-auto overflow-y-hidden">
            <button
              onClick={() => setActiveTab("unmatched_lines")}
              data-testid="tab-unmatched-lines"
              className={`px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px flex items-center gap-2 whitespace-nowrap ${
                activeTab === "unmatched_lines"
                  ? "border-[#0F172A] text-[#0F172A] bg-slate-50"
                  : "border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50/50"
              }`}
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Unmatched Bank Lines</span>
              <span
                className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded-full ${
                  activeTab === "unmatched_lines" ? "bg-[#0F172A] text-white" : "bg-slate-200 text-slate-700"
                }`}
              >
                {unmatchedLines.length}
              </span>
            </button>

            <button
              onClick={() => setActiveTab("transfers")}
              data-testid="tab-transfers"
              className={`px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px flex items-center gap-2 whitespace-nowrap ${
                activeTab === "transfers"
                  ? "border-[#0F172A] text-[#0F172A] bg-slate-50"
                  : "border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50/50"
              }`}
            >
              <ArrowLeftRight className="w-3.5 h-3.5" />
              <span>Suggested Transfers</span>
              {suggestedTransfers.length > 0 && (
                <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded-full bg-amber-500 text-white">
                  {suggestedTransfers.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("erp_expected")}
              data-testid="tab-erp-expected"
              className={`px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px flex items-center gap-2 whitespace-nowrap ${
                activeTab === "erp_expected"
                  ? "border-[#0F172A] text-[#0F172A] bg-slate-50"
                  : "border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50/50"
              }`}
            >
              <Clock className="w-3.5 h-3.5" />
              <span>Unmatched ERP Expected</span>
              <span
                className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded-full ${
                  activeTab === "erp_expected" ? "bg-[#0F172A] text-white" : "bg-slate-200 text-slate-700"
                }`}
              >
                {erpCandidates.length}
              </span>
            </button>

            <button
              onClick={() => setActiveTab("ledger")}
              data-testid="tab-ledger"
              className={`px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px flex items-center gap-2 whitespace-nowrap ${
                activeTab === "ledger"
                  ? "border-[#0F172A] text-[#0F172A] bg-slate-50"
                  : "border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50/50"
              }`}
            >
              <FileSpreadsheet className="w-3.5 h-3.5" />
              <span>Statement Ledger</span>
              <span
                className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded-full ${
                  activeTab === "ledger" ? "bg-[#0F172A] text-white" : "bg-slate-200 text-slate-700"
                }`}
              >
                {statementLines.length}
              </span>
            </button>
          </div>

          {/* TAB 1: UNMATCHED BANK STATEMENT LINES */}
          {activeTab === "unmatched_lines" && (
            <Card className="p-4 sm:p-6 space-y-4">
              <div className="flex items-center justify-between gap-4 flex-wrap pb-3 border-b-2 border-slate-100">
                <div>
                  <h3 className="font-black text-slate-900 text-sm uppercase tracking-wide">Unmatched Bank Transactions</h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Statement lines requiring manual linkage, ERP expense/income allocation, or transfer confirmation.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      placeholder="Search narration / ref..."
                      value={statementFilter.search}
                      onChange={(e) => setStatementFilter({ ...statementFilter, search: e.target.value })}
                      className="pl-8 pr-3 py-1.5 text-xs font-mono border-2 border-slate-300 bg-white focus:border-[#2563EB] focus:outline-none w-56"
                    />
                  </div>
                </div>
              </div>

              {unmatchedLines.length === 0 ? (
                <div className="text-center py-12 text-slate-500 space-y-2">
                  <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-600 opacity-80" />
                  <p className="font-bold text-slate-900 text-sm">All imported statement lines are fully reconciled!</p>
                  <p className="text-xs text-slate-500">No unmatched bank transactions pending review.</p>
                </div>
              ) : (
                <div className="overflow-x-auto border-2 border-slate-200">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-slate-50 text-[10px] uppercase font-bold text-slate-600 tracking-wider border-b-2 border-slate-200">
                      <tr>
                        <th className="px-4 py-3">Date</th>
                        <th className="px-4 py-3">Account</th>
                        <th className="px-4 py-3">Narration / Description</th>
                        <th className="px-4 py-3">Reference No</th>
                        <th className="px-4 py-3 text-right">Debit (Out)</th>
                        <th className="px-4 py-3 text-right">Credit (In)</th>
                        <th className="px-4 py-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {unmatchedLines.map((line) => {
                        const acc = accounts.find((a) => a.id === line.bank_account_id);
                        return (
                          <tr key={line.id} className="hover:bg-slate-50/80 transition-colors">
                            <td className="px-4 py-3 font-mono text-slate-700 whitespace-nowrap">{line.date}</td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <span className="font-bold text-slate-900">{acc ? acc.name : "Account"}</span>
                            </td>
                            <td className="px-4 py-3 max-w-xs truncate text-slate-800 font-medium" title={line.narration}>
                              {line.narration}
                            </td>
                            <td className="px-4 py-3 font-mono text-slate-500">{line.reference_no || "-"}</td>
                            <td className="px-4 py-3 text-right font-mono font-bold text-red-600">
                              {line.debit_amount > 0 ? inr(line.debit_amount) : "-"}
                            </td>
                            <td className="px-4 py-3 text-right font-mono font-bold text-emerald-700">
                              {line.credit_amount > 0 ? inr(line.credit_amount) : "-"}
                            </td>
                            <td className="px-4 py-3 text-right whitespace-nowrap">
                              <div className="flex items-center justify-end gap-1.5">
                                <button
                                  onClick={() => {
                                    setActiveLineForMatch(line);
                                    setShowManualMatchModal(true);
                                  }}
                                  className="bg-[#1E3A8A] text-white font-bold uppercase tracking-wider text-[10px] px-2.5 py-1.5 border-2 border-[#1E3A8A] shadow-ind hover:bg-[#172554] flex items-center gap-1"
                                >
                                  <LinkIcon className="w-3 h-3" /> Match ERP
                                </button>
                                <button
                                  onClick={() => handleIgnoreLine(line.id)}
                                  className="bg-white text-slate-700 font-bold uppercase tracking-wider text-[10px] px-2 py-1.5 border-2 border-slate-300 hover:border-slate-500"
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
            <Card className="p-4 sm:p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b-2 border-slate-100">
                <div>
                  <h3 className="font-black text-slate-900 text-sm uppercase tracking-wide">Suggested Inter-Account Transfers</h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Transfers move funds between your own bank accounts. When confirmed, they are strictly excluded from income/expense totals.
                  </p>
                </div>
                <BtnSecondary onClick={fetchSuggestedTransfers} className="flex items-center gap-1.5 py-1.5">
                  <RefreshCw className={`w-3.5 h-3.5 ${transferLoading ? "animate-spin" : ""}`} /> Refresh
                </BtnSecondary>
              </div>

              {suggestedTransfers.length === 0 ? (
                <div className="text-center py-12 text-slate-500 space-y-2">
                  <CheckCircle2 className="w-10 h-10 mx-auto text-slate-400 opacity-60" />
                  <p className="font-bold text-slate-900 text-sm">No unconfirmed transfer pairs detected.</p>
                  <p className="text-xs text-slate-500">
                    Matching debit & credit transactions across different bank accounts will surface here for confirmation.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3">
                  {suggestedTransfers.map((pair) => (
                    <div
                      key={pair.pair_id}
                      className="p-4 bg-white border-2 border-slate-200 flex items-center justify-between gap-4 flex-wrap hover:border-slate-400 transition-colors"
                    >
                      {/* From Account (Debit) */}
                      <div className="flex-1 min-w-[240px] space-y-1">
                        <div className="flex items-center gap-2">
                          <Badge color="red">Sending Account</Badge>
                          <span className="text-xs font-bold text-slate-900">{pair.from_line.bank_account_name}</span>
                        </div>
                        <div className="text-base font-mono text-red-600 font-bold">-{inr(pair.from_line.amount)}</div>
                        <div className="text-xs text-slate-500 truncate" title={pair.from_line.narration}>
                          {pair.from_line.narration} ({pair.from_line.date})
                        </div>
                      </div>

                      {/* Arrow Divider */}
                      <div className="flex flex-col items-center justify-center px-4 py-2 bg-slate-100 border border-slate-200">
                        <ArrowLeftRight className="w-4 h-4 text-slate-700" />
                        <span className="text-[10px] text-slate-600 font-mono font-bold mt-0.5">
                          {pair.day_diff === 0 ? "Same Day" : `±${pair.day_diff} Day(s)`}
                        </span>
                      </div>

                      {/* To Account (Credit) */}
                      <div className="flex-1 min-w-[240px] space-y-1">
                        <div className="flex items-center gap-2">
                          <Badge color="green">Receiving Account</Badge>
                          <span className="text-xs font-bold text-slate-900">{pair.to_line.bank_account_name}</span>
                        </div>
                        <div className="text-base font-mono text-emerald-700 font-bold">+{inr(pair.to_line.amount)}</div>
                        <div className="text-xs text-slate-500 truncate" title={pair.to_line.narration}>
                          {pair.to_line.narration} ({pair.to_line.date})
                        </div>
                      </div>

                      {/* Confirmation Button */}
                      <div className="flex items-center">
                        <button
                          onClick={() => handleConfirmTransfer(pair.from_line.id, pair.to_line.id)}
                          className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold uppercase tracking-wider text-xs px-4 py-2 border-2 border-emerald-600 shadow-ind flex items-center gap-1.5 transition-colors"
                        >
                          <Check className="w-3.5 h-3.5" /> Confirm Transfer
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
            <Card className="p-4 sm:p-6 space-y-4">
              <div className="flex items-center justify-between gap-4 flex-wrap pb-3 border-b-2 border-slate-100">
                <div>
                  <h3 className="font-black text-slate-900 text-sm uppercase tracking-wide">Unmatched / Expected ERP Transactions</h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Invoiced client amounts, online settlements, and recorded expenses not yet confirmed on bank statements.
                  </p>
                </div>
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search ERP transactions..."
                    value={erpSearch}
                    onChange={(e) => setErpSearch(e.target.value)}
                    className="pl-8 pr-3 py-1.5 text-xs font-mono border-2 border-slate-300 bg-white focus:border-[#2563EB] focus:outline-none w-56"
                  />
                </div>
              </div>

              {erpCandidates.length === 0 ? (
                <div className="text-center py-12 text-slate-500 space-y-2">
                  <CheckCircle2 className="w-10 h-10 mx-auto text-slate-400 opacity-60" />
                  <p className="font-bold text-slate-900 text-sm">No unreconciled ERP records found.</p>
                </div>
              ) : (
                <div className="overflow-x-auto border-2 border-slate-200">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-slate-50 text-[10px] uppercase font-bold text-slate-600 tracking-wider border-b-2 border-slate-200">
                      <tr>
                        <th className="px-4 py-3">Date</th>
                        <th className="px-4 py-3">Type</th>
                        <th className="px-4 py-3">Party / Channel</th>
                        <th className="px-4 py-3">Description</th>
                        <th className="px-4 py-3">Reference</th>
                        <th className="px-4 py-3 text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {erpCandidates.map((c) => (
                        <tr key={`${c.type}-${c.id}`} className="hover:bg-slate-50/80 transition-colors">
                          <td className="px-4 py-3 font-mono text-slate-700 whitespace-nowrap">{c.date}</td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            <Badge
                              color={
                                c.type === "settlement"
                                  ? "purple"
                                  : c.type === "payment"
                                  ? "green"
                                  : "red"
                              }
                            >
                              {c.type}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-xs font-bold text-slate-900">{c.party}</td>
                          <td className="px-4 py-3 text-xs text-slate-600 max-w-xs truncate">{c.description}</td>
                          <td className="px-4 py-3 font-mono text-slate-500">{c.reference || "-"}</td>
                          <td
                            className={`px-4 py-3 text-right font-mono font-bold ${
                              c.side === "credit" ? "text-emerald-700" : "text-red-600"
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
            <Card className="p-4 sm:p-6 space-y-4">
              <div className="flex items-center justify-between gap-4 flex-wrap pb-3 border-b-2 border-slate-100">
                <div className="flex items-center gap-3">
                  <select
                    value={statementFilter.status}
                    onChange={(e) => setStatementFilter({ ...statementFilter, status: e.target.value })}
                    className="border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-bold uppercase focus:border-[#2563EB] focus:outline-none"
                  >
                    <option value="all">All Match Statuses</option>
                    <option value="matched">Matched Only</option>
                    <option value="unmatched">Unmatched Only</option>
                    <option value="transfer">Transfers Only</option>
                    <option value="ignored">Ignored Only</option>
                  </select>

                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      placeholder="Search narration..."
                      value={statementFilter.search}
                      onChange={(e) => setStatementFilter({ ...statementFilter, search: e.target.value })}
                      className="pl-8 pr-3 py-1.5 text-xs font-mono border-2 border-slate-300 bg-white focus:border-[#2563EB] focus:outline-none w-56"
                    />
                  </div>
                </div>

                <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Total lines: <span className="font-mono text-slate-900">{statementLines.length}</span>
                </div>
              </div>

              <div className="overflow-x-auto border-2 border-slate-200 max-h-[600px]">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-50 sticky top-0 text-[10px] uppercase font-bold text-slate-600 tracking-wider border-b-2 border-slate-200 z-10">
                    <tr>
                      <th className="px-4 py-3">Date</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Narration</th>
                      <th className="px-4 py-3">Ref No</th>
                      <th className="px-4 py-3 text-right">Debit</th>
                      <th className="px-4 py-3 text-right">Credit</th>
                      <th className="px-4 py-3 text-right">Running Balance</th>
                      <th className="px-4 py-3">Matched Entity</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {statementLines.map((line) => (
                      <tr key={line.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="px-4 py-3 font-mono text-slate-700 whitespace-nowrap">{line.date}</td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <Badge
                            color={
                              line.match_status === "matched"
                                ? "green"
                                : line.match_status === "transfer"
                                ? "blue"
                                : line.match_status === "ignored"
                                ? "slate"
                                : "yellow"
                            }
                          >
                            {line.match_status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-800 font-medium max-w-xs truncate" title={line.narration}>
                          {line.narration}
                        </td>
                        <td className="px-4 py-3 font-mono text-slate-500">{line.reference_no || "-"}</td>
                        <td className="px-4 py-3 text-right font-mono font-bold text-red-600">
                          {line.debit_amount > 0 ? inr(line.debit_amount) : "-"}
                        </td>
                        <td className="px-4 py-3 text-right font-mono font-bold text-emerald-700">
                          {line.credit_amount > 0 ? inr(line.credit_amount) : "-"}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-slate-900 font-bold">
                          {line.running_balance != null ? inr(line.running_balance) : "-"}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-600">
                          {line.matched_to ? (
                            <span className="font-mono text-[10px] text-blue-800 bg-blue-50 px-1.5 py-0.5 border border-blue-200 font-bold">
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
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-2xl overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between bg-slate-50">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Finance / Reconciliation</div>
            <h3 className="font-bold text-base text-slate-900 mt-0.5 flex items-center gap-2">
              <LinkIcon className="w-4 h-4 text-[#1E3A8A]" /> Manual Link & Reconcile
            </h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Selected Bank Line Banner */}
        <div className="p-5 space-y-4">
          <div className="p-3.5 bg-slate-50 border-2 border-slate-200 space-y-1">
            <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Statement Line to Match</div>
            <div className="flex items-center justify-between">
              <span className="font-bold text-sm text-slate-900 truncate">{line.narration}</span>
              <span className={`font-mono text-sm font-bold ${isCredit ? "text-emerald-700" : "text-red-600"}`}>
                {isCredit ? `+${inr(amount)}` : `-${inr(amount)}`}
              </span>
            </div>
            <div className="text-xs text-slate-500 flex items-center gap-3">
              <span>Date: <strong className="text-slate-700 font-mono">{line.date}</strong></span>
              {line.reference_no && <span>Ref: <strong className="text-slate-700 font-mono">{line.reference_no}</strong></span>}
            </div>
          </div>

          {/* Search Candidates */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search ERP candidate payouts, payments, invoices, or payees..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 border-2 border-slate-300 bg-white text-xs font-mono focus:border-[#2563EB] focus:outline-none"
            />
          </div>

          {/* Candidate List */}
          <div className="max-h-72 overflow-y-auto space-y-2 border-2 border-slate-100 p-2 bg-slate-50/50">
            {loading ? (
              <div className="text-center py-8 text-xs font-bold uppercase text-slate-500">Searching ERP candidates...</div>
            ) : candidates.length === 0 ? (
              <div className="text-center py-8 text-xs font-bold text-slate-500">No matching unallocated ERP transactions found.</div>
            ) : (
              candidates.map((c) => {
                const diff = Math.abs(c.amount - amount);
                return (
                  <div
                    key={`${c.type}-${c.id}`}
                    className="p-3 bg-white border-2 border-slate-200 flex items-center justify-between gap-4 hover:border-slate-400 transition-colors"
                  >
                    <div className="space-y-0.5 flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge color={c.type === "settlement" ? "purple" : c.type === "payment" ? "green" : "red"}>
                          {c.type}
                        </Badge>
                        <span className="text-xs font-bold text-slate-900 truncate">{c.description}</span>
                      </div>
                      <div className="text-xs text-slate-500 flex items-center gap-3">
                        <span>Date: <strong className="font-mono text-slate-700">{c.date}</strong></span>
                        <span>Party: <strong className="text-slate-700">{c.party}</strong></span>
                        {diff <= 1.0 && <span className="text-emerald-700 font-bold">✓ Amount Match</span>}
                      </div>
                    </div>
                    <div className="text-right whitespace-nowrap">
                      <div className="font-mono text-sm font-bold text-slate-900">{inr(c.amount)}</div>
                      <button
                        onClick={() => onMatch(line.id, c.type, c.id)}
                        className="mt-1 px-3 py-1 bg-[#1E3A8A] text-white font-bold uppercase tracking-wider text-[10px] border border-[#1E3A8A] hover:bg-[#172554] flex items-center gap-1 shadow-sm"
                      >
                        <Check className="w-3 h-3" /> Link This
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-4 bg-slate-50 border-t-2 border-slate-200 flex justify-end">
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
  const [confirmAccountUpdate, setConfirmAccountUpdate] = useState(true);
  const [error, setError] = useState("");

  const handlePreviewOrImport = async (dryRun = true) => {
    if (!accId) {
      setError("Please select a bank account.");
      return;
    }
    if (!file) {
      setError("Please choose a statement file (.xls, .xlsx, or .csv).");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const url = `/banking/accounts/${accId}/statement/import?dry_run=${dryRun}&confirm_account_update=${confirmAccountUpdate}`;
      const { data } = await http.post(url, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      if (dryRun) {
        setPreview(data);
      } else {
        onSuccess();
      }
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || e.response?.data?.detail || e.message || "Import failed. Please check the file column layout.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-lg overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between bg-slate-50">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Finance / Bank Statements</div>
            <h3 className="font-bold text-base text-slate-900 mt-0.5 flex items-center gap-2">
              <Upload className="w-4 h-4 text-[#1E3A8A]" /> Import Bank Statement
            </h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border-2 border-red-300 text-red-800 text-xs font-medium flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 text-red-600" />
              <span>{error}</span>
            </div>
          )}

          {/* Account Selection */}
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Target Bank Account</div>
            <select
              value={accId}
              onChange={(e) => setAccId(e.target.value)}
              className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none"
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
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Statement File (.XLS, .XLSX, or .CSV)</div>
            <input
              type="file"
              accept=".xls,.xlsx,.csv"
              onChange={(e) => {
                setFile(e.target.files[0] || null);
                setPreview(null);
              }}
              className="w-full border-2 border-slate-300 bg-white p-2 text-xs font-mono focus:border-[#2563EB] focus:outline-none"
            />
          </div>

          {/* Preview Details */}
          {preview && (
            <div className="p-3.5 bg-slate-50 border-2 border-slate-200 space-y-2.5">
              <div className="flex items-center justify-between text-xs font-bold text-emerald-800">
                <span>✓ Layout Verified: {preview.parsed_count} transactions parsed</span>
                <span className="font-mono">Total rows in file: {preview.total_file_rows}</span>
              </div>

              {preview.suggested_account_update && (
                <div className="p-2.5 bg-blue-50 border border-blue-200 rounded text-xs text-blue-900 space-y-1.5">
                  <div className="font-bold flex items-center gap-1.5">
                    <span>💡 Bank Details Detected in Header</span>
                  </div>
                  <div className="text-[11px] font-mono grid grid-cols-2 gap-1 text-slate-700">
                    {preview.suggested_account_update.ifsc && <div>IFSC: <strong>{preview.suggested_account_update.ifsc}</strong></div>}
                    {preview.suggested_account_update.account_number && <div>A/C: <strong>{preview.suggested_account_update.account_number}</strong></div>}
                    {preview.suggested_account_update.branch && <div className="col-span-2">Branch: <strong>{preview.suggested_account_update.branch}</strong></div>}
                  </div>
                  <label className="flex items-center gap-2 cursor-pointer pt-1 font-semibold text-[11px]">
                    <input
                      type="checkbox"
                      checked={confirmAccountUpdate}
                      onChange={(e) => setConfirmAccountUpdate(e.target.checked)}
                      className="rounded text-[#1E3A8A] focus:ring-[#1E3A8A]"
                    />
                    <span>Save detected IFSC & Account details to this Bank Account</span>
                  </label>
                </div>
              )}

              <div className="text-[11px] text-slate-600 space-y-1 border-t border-slate-200 pt-2">
                <div className="font-bold text-slate-700 text-[10px] uppercase tracking-wider mb-1">Sample Parsed Rows:</div>
                {preview.sample?.slice(0, 3).map((s, idx) => (
                  <div key={idx} className="flex justify-between items-center border-b border-slate-100 pb-1">
                    <span className="truncate max-w-[240px] font-medium">{s.narration} ({s.date})</span>
                    <span className="font-mono font-bold text-slate-900">
                      {s.credit_amount > 0 ? `+${inr(s.credit_amount)}` : `-${inr(s.debit_amount)}`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-5 py-4 bg-slate-50 border-t-2 border-slate-200 flex items-center justify-between">
          <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          <div className="flex gap-2">
            {!preview ? (
              <BtnPrimary onClick={() => handlePreviewOrImport(true)} disabled={loading || !file} testId="preview-layout-btn">
                {loading ? "Parsing..." : "Preview Layout"}
              </BtnPrimary>
            ) : (
              <button
                onClick={() => handlePreviewOrImport(false)}
                disabled={loading}
                className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold uppercase tracking-wider text-xs px-5 py-2.5 border-2 border-emerald-600 shadow-ind transition-colors"
                data-testid="confirm-import-btn"
              >
                {loading ? "Importing..." : "Confirm & Import Rows"}
              </button>
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
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-md overflow-hidden">
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between bg-slate-50">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-bold">Finance / Bank Setup</div>
            <h3 className="font-bold text-base text-slate-900 mt-0.5 flex items-center gap-2">
              <Landmark className="w-4 h-4 text-[#1E3A8A]" /> Add Bank Account
            </h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border-2 border-red-300 text-red-800 text-xs font-medium">
              {error}
            </div>
          )}

          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Account Display Name</div>
            <input
              type="text"
              placeholder="e.g. HDFC - Online Payouts"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Bank Name</div>
              <input
                type="text"
                placeholder="e.g. HDFC, UCO Bank"
                value={formData.bank_name}
                onChange={(e) => setFormData({ ...formData, bank_name: e.target.value })}
                className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none"
              />
            </div>
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Last 4 Digits</div>
              <input
                type="text"
                maxLength={6}
                placeholder="e.g. 4321"
                value={formData.account_number_last4}
                onChange={(e) => setFormData({ ...formData, account_number_last4: e.target.value })}
                className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm font-mono focus:border-[#2563EB] focus:outline-none"
              />
            </div>
          </div>

          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Account Category / Purpose</div>
            <select
              value={formData.account_type}
              onChange={(e) => setFormData({ ...formData, account_type: e.target.value })}
              className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#2563EB] focus:outline-none"
            >
              <option value="online_channel">Online Channel Account (Myntra / Flipkart Settlements)</option>
              <option value="b2b_client">B2B Offline Account (Client Invoices & General Operations)</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Opening Balance (₹)</div>
              <input
                type="number"
                step="0.01"
                value={formData.opening_balance}
                onChange={(e) => setFormData({ ...formData, opening_balance: e.target.value })}
                className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm font-mono focus:border-[#2563EB] focus:outline-none"
              />
            </div>
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Opening Date</div>
              <input
                type="date"
                value={formData.opening_balance_date}
                onChange={(e) => setFormData({ ...formData, opening_balance_date: e.target.value })}
                className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm font-mono focus:border-[#2563EB] focus:outline-none"
              />
            </div>
          </div>

          <div className="pt-3 flex items-center justify-end gap-2 border-t-2 border-slate-200">
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
