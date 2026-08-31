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
  Coins,
  Wallet,
  Lock,
  Unlock,
} from "lucide-react";

const isCashWithdrawalCandidate = (line) => {
  if (!line || Number(line.debit_amount || 0) <= 0) return false;
  const n = line.narration || "";
  return /(?:^|[\s\-_/.,:])(ATM|CASH|SELF|CWDR|NFS|EAW|CSH|SELF\s*CHQ|SELF\s*CHEQUE|CASH\s*WDL|CASH\s*WITHDRAWAL)(?:$|[\s\-_/.,:])/i.test(n);
};

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

  // Cash withdrawal suggestions
  const [suggestedCashWithdrawals, setSuggestedCashWithdrawals] = useState([]);
  const [cashLoading, setCashLoading] = useState(false);
  const [showCashModal, setShowCashModal] = useState(false);
  const [activeCashLine, setActiveCashLine] = useState(null);

  // Cash Breakdown Modal state
  const [showCashBreakdownModal, setShowCashBreakdownModal] = useState(false);
  const [selectedCashBreakdownId, setSelectedCashBreakdownId] = useState(null);
  const [selectedCashLine, setSelectedCashLine] = useState(null);

  // ERP Unmatched candidates
  const [erpCandidates, setErpCandidates] = useState([]);
  const [erpLoading, setErpLoading] = useState(false);
  const [erpSearch, setErpSearch] = useState("");

  // Modals state
  const [showImportModal, setShowImportModal] = useState(false);
  const [showAccountModal, setShowAccountModal] = useState(false);
  const [showManualMatchModal, setShowManualMatchModal] = useState(false);
  const [activeLineForMatch, setActiveLineForMatch] = useState(null);

  // Period Lock state
  const [showLockModal, setShowLockModal] = useState(false);
  const [showUnlockModal, setShowUnlockModal] = useState(false);
  const [lockFrom, setLockFrom] = useState(new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10));
  const [lockTo, setLockTo] = useState(new Date().toISOString().slice(0, 10));
  const [lockReason, setLockReason] = useState("Monthly reconciliation finalized for GST / Accounting");
  const [unlockReason, setUnlockReason] = useState("");
  const [periodLocks, setPeriodLocks] = useState([]);
  const [selectedLockToUnlock, setSelectedLockToUnlock] = useState(null);

  // Auto reconcile state
  const [reconciling, setReconciling] = useState(false);
  const [reconcileResult, setReconcileResult] = useState(null);
  const [minConfidenceThreshold, setMinConfidenceThreshold] = useState(95);

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
      setStatementLines(Array.isArray(data) ? data : data.items || []);
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

  const fetchSuggestedCashWithdrawals = useCallback(async () => {
    setCashLoading(true);
    try {
      const params = {};
      if (selectedAccountId && selectedAccountId !== "all") {
        params.bank_account_id = selectedAccountId;
      }
      const { data } = await http.get("/banking/cash-withdrawals/suggested", { params });
      setSuggestedCashWithdrawals(data.candidates || []);
    } catch (e) {
      console.error(e);
    } finally {
      setCashLoading(false);
    }
  }, [selectedAccountId]);

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

  const fetchPeriodLocks = useCallback(async () => {
    try {
      const params = {};
      if (selectedAccountId && selectedAccountId !== "all") {
        params.bank_account_id = selectedAccountId;
      }
      const { data } = await http.get("/banking/periods/locks", { params });
      setPeriodLocks(data.locks || []);
    } catch (e) {
      console.error(e);
    }
  }, [selectedAccountId]);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  useEffect(() => {
    fetchSummary();
    fetchStatementLines();
    fetchSuggestedTransfers();
    fetchSuggestedCashWithdrawals();
    fetchErpCandidates();
    fetchPeriodLocks();
  }, [selectedAccountId, fetchSummary, fetchStatementLines, fetchSuggestedTransfers, fetchSuggestedCashWithdrawals, fetchErpCandidates, fetchPeriodLocks]);

  // ─────────────────────────────────────────────────────────────────────────────
  // Action Handlers
  // ─────────────────────────────────────────────────────────────────────────────

  const handleLockPeriod = async () => {
    try {
      await http.post("/banking/periods/lock", {
        bank_account_id: selectedAccountId === "all" ? null : selectedAccountId,
        period_from: lockFrom,
        period_to: lockTo,
        reason: lockReason || "Monthly reconciliation finalized for GST / Accounting",
      });
      notify(`Reconciliation period ${lockFrom} to ${lockTo} successfully locked!`, "success");
      setShowLockModal(false);
      fetchPeriodLocks();
      fetchSummary();
    } catch (e) {
      notify(e.message || "Failed to lock period", "error");
    }
  };

  const handleUnlockPeriod = async () => {
    if (!selectedLockToUnlock) return;
    try {
      await http.post("/banking/periods/unlock", {
        bank_account_id: selectedLockToUnlock.bank_account_id === "all" ? null : selectedLockToUnlock.bank_account_id,
        period_from: selectedLockToUnlock.period_from,
        period_to: selectedLockToUnlock.period_to,
        reason: unlockReason || "Admin unlocked for correction",
      });
      notify(`Reconciliation period ${selectedLockToUnlock.period_from} to ${selectedLockToUnlock.period_to} unlocked by admin!`, "success");
      setShowUnlockModal(false);
      setSelectedLockToUnlock(null);
      setUnlockReason("");
      fetchPeriodLocks();
      fetchSummary();
    } catch (e) {
      notify(e.message || "Failed to unlock period (Admin required)", "error");
    }
  };

  const handleExportAccountantReport = async () => {
    try {
      const params = new URLSearchParams();
      if (selectedAccountId && selectedAccountId !== "all") {
        params.append("bank_account_id", selectedAccountId);
      }
      if (statementFilter.fromDate) {
        params.append("from_date", statementFilter.fromDate);
      }
      if (statementFilter.toDate) {
        params.append("to_date", statementFilter.toDate);
      }
      const token = localStorage.getItem("token") || "";
      const url = `/api/banking/reconciliation/export?${params.toString()}`;
      
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        throw new Error("Failed to generate export file");
      }
      const blob = await res.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = downloadUrl;
      const acc = accounts.find((a) => a.id === selectedAccountId);
      const accName = acc ? acc.name.replace(/\s+/g, "_") : "Consolidated";
      a.download = `Bank_Reconciliation_Statement_${accName}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(downloadUrl);
      notify("Reconciliation report exported successfully!", "success");
    } catch (e) {
      notify(e.message || "Failed to download export", "error");
    }
  };

  const handleRunAutoReconcile = async (threshold = minConfidenceThreshold) => {
    if (selectedAccountId === "all") {
      notify("Please select a specific Bank Account to run auto-reconciliation.", "error");
      return;
    }
    setReconciling(true);
    try {
      const { data } = await http.post(
        `/banking/accounts/${selectedAccountId}/reconcile?date_window_days=3&amount_tolerance=1.0&min_confidence=${threshold}`
      );
      setReconcileResult(data);
      const pendingMsg = data.pending_review_count > 0 ? ` (${data.pending_review_count} low-confidence left for review)` : "";
      notify(
        `Bulk auto-reconciliation complete: ${data.auto_matched_count} matches resolved (≥${data.min_confidence_percent}% confidence)${pendingMsg}.`,
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

  const handleConfirmCashWithdrawal = async (lineId, notes = "") => {
    try {
      await http.post("/banking/cash-withdrawals/confirm", {
        statement_line_id: lineId,
        notes: notes || "Confirmed cash withdrawal",
      });
      notify("Cash withdrawal confirmed and added to Cash in Hand ledger!", "success");
      setShowCashModal(false);
      setActiveCashLine(null);
      fetchSummary();
      fetchStatementLines();
      fetchSuggestedCashWithdrawals();
    } catch (e) {
      notify(e.message || "Failed to confirm cash withdrawal", "error");
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

  const handleUpdateRemarks = async (lineId, newRemarks) => {
    try {
      await http.patch(`/banking/statement-lines/${lineId}/match`, {
        remarks: newRemarks,
      });
      setStatementLines((prev) =>
        prev.map((l) => (l.id === lineId ? { ...l, remarks: newRemarks } : l))
      );
      notify("Remark saved successfully.", "success");
    } catch (e) {
      notify(e.message || "Failed to update remark", "error");
      throw e;
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
            <BtnSecondary
              onClick={handleExportAccountantReport}
              className="flex items-center gap-1.5 bg-white border-slate-300 text-slate-800 hover:bg-slate-50"
              testId="export-reconciliation-btn"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-700" /> Export Report (Excel)
            </BtnSecondary>
            <div className="flex items-center border-2 border-slate-300 bg-white">
              <span className="text-[10px] uppercase font-bold text-slate-500 px-2 border-r border-slate-200">
                Min Confidence:
              </span>
              <select
                value={minConfidenceThreshold}
                onChange={(e) => setMinConfidenceThreshold(Number(e.target.value))}
                className="text-xs font-bold py-1.5 px-2 bg-transparent text-slate-800 focus:outline-none"
                data-testid="confidence-threshold-select"
              >
                <option value={95}>95%+ (Exact Date & Amt)</option>
                <option value={90}>90%+ (±1 Day)</option>
                <option value={80}>80%+ (±2-3 Days)</option>
                <option value={70}>70%+ (Broad Match)</option>
              </select>
            </div>
            <BtnPrimary
              onClick={() => handleRunAutoReconcile(minConfidenceThreshold)}
              disabled={reconciling || selectedAccountId === "all"}
              className="flex items-center gap-1.5 bg-[#1E3A8A] border-[#1E3A8A] hover:bg-[#172554]"
              testId="auto-reconcile-btn"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${reconciling ? "animate-spin" : ""}`} />
              {reconciling ? "Reconciling..." : `Bulk Confirm (≥${minConfidenceThreshold}%)`}
            </BtnPrimary>

            {periodLocks.find(
              (l) =>
                l.status === "locked" &&
                (selectedAccountId === "all" || l.bank_account_id === "all" || l.bank_account_id === selectedAccountId)
            ) ? (
              <div className="flex items-center gap-2 bg-amber-50 border-2 border-amber-500 px-3 py-1 text-xs font-bold text-amber-900 shadow-sm">
                <Lock className="w-3.5 h-3.5 text-amber-600" />
                <span>
                  Period Locked:{" "}
                  {
                    periodLocks.find(
                      (l) =>
                        l.status === "locked" &&
                        (selectedAccountId === "all" || l.bank_account_id === "all" || l.bank_account_id === selectedAccountId)
                    ).period_from
                  }{" "}
                  →{" "}
                  {
                    periodLocks.find(
                      (l) =>
                        l.status === "locked" &&
                        (selectedAccountId === "all" || l.bank_account_id === "all" || l.bank_account_id === selectedAccountId)
                    ).period_to
                  }
                </span>
                <button
                  onClick={() => {
                    const lk = periodLocks.find(
                      (l) =>
                        l.status === "locked" &&
                        (selectedAccountId === "all" || l.bank_account_id === "all" || l.bank_account_id === selectedAccountId)
                    );
                    setSelectedLockToUnlock(lk);
                    setShowUnlockModal(true);
                  }}
                  className="ml-2 px-1.5 py-0.5 bg-amber-200 hover:bg-amber-300 text-amber-950 text-[10px] uppercase font-bold tracking-wider rounded border border-amber-400"
                  data-testid="unlock-period-btn"
                >
                  <Unlock className="w-2.5 h-2.5 inline mr-1" /> Unlock (Admin)
                </button>
              </div>
            ) : (
              <BtnSecondary
                onClick={() => setShowLockModal(true)}
                className="flex items-center gap-1.5 border-slate-400 bg-white hover:bg-slate-50 text-slate-800"
                testId="lock-period-btn"
              >
                <Lock className="w-3.5 h-3.5 text-slate-600" /> Lock Period
              </BtnSecondary>
            )}
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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4" data-testid="reconcile-overview-cards">
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

          {/* Total Cash in Hand (Prominent Balance Tile) */}
          <Card
            className="p-5 border-l-4 border-l-emerald-600 bg-gradient-to-br from-white to-emerald-50/40 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => setActiveTab("cash_in_hand")}
            data-testid="cash-in-hand-overview-card"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-emerald-800">Total Cash in Hand</span>
              <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 grid place-items-center">
                <Wallet className="w-4 h-4" />
              </div>
            </div>
            <div
              className="text-2xl font-black font-mono text-emerald-800"
              data-testid="total-cash-in-hand-val"
            >
              {inr(summary?.summary?.total_cash_in_hand || 0)}
            </div>
            <div className="text-xs text-slate-600 font-medium mt-2 pt-2 border-t border-slate-100 flex items-center justify-between">
              <span>Drawn: ₹{inr(summary?.summary?.total_cash_withdrawn || 0)}</span>
              <span className="text-[10px] uppercase font-bold text-emerald-700 hover:underline">View Pools →</span>
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
              onClick={() => setActiveTab("cash_withdrawals")}
              data-testid="tab-cash-withdrawals"
              className={`px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 -mb-px flex items-center gap-2 whitespace-nowrap ${
                activeTab === "cash_withdrawals"
                  ? "border-[#0F172A] text-[#0F172A] bg-slate-50"
                  : "border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50/50"
              }`}
            >
              <Coins className="w-3.5 h-3.5" />
              <span>Suggested Cash Withdrawals</span>
              {suggestedCashWithdrawals.length > 0 && (
                <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded-full bg-amber-500 text-white" data-testid="cash-suggestions-count">
                  {suggestedCashWithdrawals.length}
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
                        <th className="px-4 py-3">Remarks</th>
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
                            <td className="px-4 py-3 max-w-xs text-slate-800 font-medium">
                              <div className="truncate" title={line.narration}>{line.narration}</div>
                              {isCashWithdrawalCandidate(line) && (
                                <div className="mt-0.5">
                                  <span className="inline-flex items-center gap-1 text-[9px] font-mono font-bold uppercase bg-amber-100 text-amber-900 border border-amber-300 px-1.5 py-0.5 rounded" title="Narration pattern suggests cash withdrawal">
                                    ⚡ Suggested Cash Withdrawal
                                  </span>
                                </div>
                              )}
                            </td>
                            <td className="px-4 py-3 font-mono text-slate-500">{line.reference_no || "-"}</td>
                            <td className="px-4 py-3 text-right font-mono font-bold text-red-600">
                              {line.debit_amount > 0 ? inr(line.debit_amount) : "-"}
                            </td>
                            <td className="px-4 py-3 text-right font-mono font-bold text-emerald-700">
                              {line.credit_amount > 0 ? inr(line.credit_amount) : "-"}
                            </td>
                            <td className="px-4 py-3">
                              <InlineRemarkCell
                                lineId={line.id}
                                initialRemarks={line.remarks}
                                onSave={handleUpdateRemarks}
                              />
                            </td>
                            <td className="px-4 py-3 text-right whitespace-nowrap">
                              <div className="flex items-center justify-end gap-1.5">
                                {line.debit_amount > 0 && isCashWithdrawalCandidate(line) && (
                                  <button
                                    onClick={() => {
                                      setActiveCashLine(line);
                                      setShowCashModal(true);
                                    }}
                                    className="bg-amber-600 hover:bg-amber-700 text-white font-bold uppercase tracking-wider text-[10px] px-2.5 py-1.5 border-2 border-amber-600 shadow-ind flex items-center gap-1"
                                    title="Confirm this line as cash withdrawal into Cash in Hand ledger"
                                    data-testid={`confirm-cash-btn-${line.id}`}
                                  >
                                    <Coins className="w-3 h-3" /> Confirm Cash
                                  </button>
                                )}
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

          {/* TAB: SUGGESTED CASH WITHDRAWALS */}
          {activeTab === "cash_withdrawals" && (
            <Card className="p-4 sm:p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b-2 border-slate-100">
                <div>
                  <h3 className="font-black text-slate-900 text-sm uppercase tracking-wide">Suggested Cash Withdrawals</h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Unmatched debit transactions matching cash withdrawal indicators (ATM, CASH, SELF, etc.). Confirming adds to the Cash in Hand ledger.
                  </p>
                </div>
                <BtnSecondary onClick={fetchSuggestedCashWithdrawals} className="flex items-center gap-1.5 py-1.5">
                  <RefreshCw className={`w-3.5 h-3.5 ${cashLoading ? "animate-spin" : ""}`} /> Refresh
                </BtnSecondary>
              </div>

              {suggestedCashWithdrawals.length === 0 ? (
                <div className="text-center py-12 text-slate-500 space-y-2">
                  <CheckCircle2 className="w-10 h-10 mx-auto text-slate-400 opacity-60" />
                  <p className="font-bold text-slate-900 text-sm">No cash withdrawal suggestions found.</p>
                  <p className="text-xs text-slate-500">
                    Statement debits with ATM / Cash / Self in narrations will surface here for confirmation.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3">
                  {suggestedCashWithdrawals.map((line) => (
                    <div
                      key={line.id}
                      className="p-4 bg-white border-2 border-amber-200 hover:border-amber-400 flex items-center justify-between gap-4 flex-wrap transition-colors"
                    >
                      <div className="flex-1 min-w-[240px] space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-bold uppercase px-2 py-0.5 bg-amber-100 text-amber-900 border border-amber-300">
                            Cash In-Hand Candidate
                          </span>
                          <span className="text-xs font-bold text-slate-900">{line.bank_account_name || "Account"}</span>
                          <span className="text-xs font-mono text-slate-500">{line.date}</span>
                        </div>
                        <div className="text-base font-mono text-amber-900 font-bold">-{inr(line.amount || line.debit_amount)}</div>
                        <div className="text-xs text-slate-700 font-medium" title={line.narration}>
                          {line.narration}
                        </div>
                        <div className="text-[10px] text-slate-500 font-mono">
                          Ref: {line.reference_no || "-"} • {line.suggestion_reason || "Pattern match"}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => {
                            setActiveCashLine(line);
                            setShowCashModal(true);
                          }}
                          data-testid={`confirm-cash-suggestion-${line.id}`}
                          className="bg-amber-600 hover:bg-amber-700 text-white font-bold uppercase tracking-wider text-xs px-4 py-2 border-2 border-amber-600 shadow-ind flex items-center gap-1.5 transition-colors"
                        >
                          <Coins className="w-3.5 h-3.5" /> Confirm Cash In-Hand
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
                      <th className="px-4 py-3">Remarks</th>
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
                            line.matched_to.type === "cash_withdrawal" ? (
                              <button
                                onClick={() => {
                                  setSelectedCashBreakdownId(line.matched_to.ref_id);
                                  setSelectedCashLine(line);
                                  setShowCashBreakdownModal(true);
                                }}
                                data-testid={`cash-breakdown-btn-${line.id}`}
                                className="font-mono text-[10px] text-amber-900 bg-amber-50 hover:bg-amber-100 px-2 py-1 border border-amber-300 font-bold flex flex-col gap-0.5 text-left transition-colors cursor-pointer shadow-sm group rounded"
                                title="Click to view what this cash withdrawal funded (karigar disbursements & remaining balance)"
                              >
                                <div className="flex items-center gap-1">
                                  <Coins className="w-3 h-3 text-amber-600 group-hover:scale-110 transition-transform" />
                                  <span>Cash In-Hand #{String(line.matched_to.ref_id).slice(-6)}</span>
                                </div>
                                {line.cash_ledger_info && (
                                  <div className="text-[9px] text-amber-800 font-sans font-medium">
                                    {line.cash_ledger_info.wage_payment_count > 0 ? (
                                      <span>
                                        ₹{inr(line.cash_ledger_info.allocated_amount)} paid ({line.cash_ledger_info.wage_payment_count}) • ₹{inr(line.cash_ledger_info.remaining_balance)} rem
                                      </span>
                                    ) : (
                                      <span>₹{inr(line.cash_ledger_info.remaining_balance)} unallocated</span>
                                    )}
                                  </div>
                                )}
                              </button>
                            ) : (
                              <span className="font-mono text-[10px] text-blue-800 bg-blue-50 px-1.5 py-0.5 border border-blue-200 font-bold">
                                {line.matched_to.type} #{String(line.matched_to.ref_id).slice(-6)}
                              </span>
                            )
                          ) : (
                            "-"
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <InlineRemarkCell
                            lineId={line.id}
                            initialRemarks={line.remarks}
                            onSave={handleUpdateRemarks}
                          />
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

      {/* 4. CONFIRM CASH WITHDRAWAL MODAL */}
      {showCashModal && activeCashLine && (
        <ConfirmCashWithdrawalModal
          line={activeCashLine}
          accounts={accounts}
          onClose={() => {
            setShowCashModal(false);
            setActiveCashLine(null);
          }}
          onConfirm={handleConfirmCashWithdrawal}
        />
      )}

      {/* 5. CASH WITHDRAWAL BREAKDOWN / AUDIT TRAIL MODAL */}
      {showCashBreakdownModal && (selectedCashBreakdownId || selectedCashLine) && (
        <CashWithdrawalBreakdownModal
          cashLedgerId={selectedCashBreakdownId}
          line={selectedCashLine}
          accounts={accounts}
          onClose={() => {
            setShowCashBreakdownModal(false);
            setSelectedCashBreakdownId(null);
            setSelectedCashLine(null);
          }}
        />
      )}

      {/* 6. PERIOD LOCK MODAL */}
      {showLockModal && (
        <PeriodLockModal
          accounts={accounts}
          selectedAccountId={selectedAccountId}
          periodFrom={lockFrom}
          periodTo={lockTo}
          reason={lockReason}
          onPeriodFromChange={setLockFrom}
          onPeriodToChange={setLockTo}
          onReasonChange={setLockReason}
          onClose={() => setShowLockModal(false)}
          onLock={handleLockPeriod}
        />
      )}

      {/* 7. PERIOD UNLOCK MODAL (ADMIN ONLY) */}
      {showUnlockModal && selectedLockToUnlock && (
        <PeriodUnlockModal
          lockDoc={selectedLockToUnlock}
          accounts={accounts}
          unlockReason={unlockReason}
          onReasonChange={setUnlockReason}
          onClose={() => {
            setShowUnlockModal(false);
            setSelectedLockToUnlock(null);
          }}
          onUnlock={handleUnlockPeriod}
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
              {preview.skipped_count > 0 ? (
                <div className="p-2 bg-amber-50 border border-amber-200 text-amber-900 text-xs rounded space-y-0.5">
                  <div className="font-bold flex items-center justify-between">
                    <span>⚠️ {preview.new_count ?? (preview.parsed_count - preview.skipped_count)} new rows to import</span>
                    <span className="font-mono text-[11px] text-amber-700">{preview.skipped_count} duplicates skipped</span>
                  </div>
                  <div className="text-[11px] text-amber-700">
                    {preview.skipped_count} row(s) already exist in this bank account and will not be duplicated.
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between text-xs font-bold text-emerald-800">
                  <span>✓ Layout Verified: {preview.parsed_count} transactions parsed (all new)</span>
                  <span className="font-mono">Total rows in file: {preview.total_file_rows}</span>
                </div>
              )}

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

// ─────────────────────────────────────────────────────────────────────────────
// Sub-Modal: Confirm Cash Withdrawal Modal
// ─────────────────────────────────────────────────────────────────────────────
function ConfirmCashWithdrawalModal({ line, accounts, onClose, onConfirm }) {
  const [notes, setNotes] = useState(line.narration || "");
  const [loading, setLoading] = useState(false);
  const acc = accounts.find((a) => a.id === line.bank_account_id);
  const amount = line.amount || line.debit_amount || 0;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await onConfirm(line.id, notes);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white border-2 border-slate-900 max-w-md w-full shadow-2xl animate-in zoom-in-95">
        <div className="p-4 border-b-2 border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Coins className="w-5 h-5 text-amber-600" />
            <h3 className="font-black text-slate-900 text-sm uppercase">Confirm Cash Withdrawal</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div className="p-3 bg-amber-50 border border-amber-200 text-xs text-amber-900 space-y-1">
            <p className="font-bold">This transaction looks like a cash withdrawal.</p>
            <p className="text-[11px] text-amber-800">
              Confirming will create an entry in the <strong>Cash in Hand</strong> ledger with initial balance equal to withdrawal amount (₹{inr(amount)}), and mark this statement line as fully reconciled.
            </p>
          </div>

          <div className="p-3 bg-slate-50 border border-slate-200 text-xs space-y-1.5 font-mono">
            <div className="flex justify-between">
              <span className="text-slate-500">Bank Account:</span>
              <span className="font-bold text-slate-900">{acc ? acc.name : "Account"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Date:</span>
              <span className="text-slate-800">{line.date}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Amount Withdrawn:</span>
              <span className="text-base font-bold text-red-600 font-mono">-{inr(amount)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Narration:</span>
              <span className="text-slate-700 max-w-[200px] truncate text-right">{line.narration}</span>
            </div>
          </div>

          <div className="space-y-1">
            <label className="text-[10px] uppercase font-bold text-slate-600">Notes / Purpose (Optional)</label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Factory floor daily expenses / petty cash"
              className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs focus:border-[#2563EB] focus:outline-none"
            />
          </div>

          <div className="pt-2 flex items-center justify-end gap-2 border-t-2 border-slate-100">
            <BtnSecondary onClick={onClose} type="button">Cancel</BtnSecondary>
            <button
              type="submit"
              disabled={loading}
              data-testid="modal-confirm-cash-btn"
              className="bg-amber-600 hover:bg-amber-700 text-white font-bold uppercase tracking-wider text-xs px-4 py-2 border-2 border-amber-600 shadow-ind flex items-center gap-1.5 disabled:opacity-50"
            >
              {loading ? "Confirming..." : "Confirm Cash In-Hand"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
function InlineRemarkCell({ lineId, initialRemarks, onSave }) {
  const [val, setVal] = useState(initialRemarks || "");
  const [isSaving, setIsSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState(initialRemarks || "");

  useEffect(() => {
    setVal(initialRemarks || "");
    setLastSaved(initialRemarks || "");
  }, [initialRemarks]);

  const handleBlur = async () => {
    const trimmed = val;
    if (trimmed === lastSaved) return;
    setIsSaving(true);
    try {
      await onSave(lineId, trimmed);
      setLastSaved(trimmed);
    } catch {
      setVal(lastSaved);
    } finally {
      setIsSaving(false);
    }
  };

  const handleKeyDown = async (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      await handleBlur();
      e.target.blur();
    } else if (e.key === "Escape") {
      setVal(lastSaved);
      e.target.blur();
    }
  };

  return (
    <div className="relative flex items-center min-w-[140px] max-w-[220px]">
      <input
        type="text"
        value={val}
        placeholder="Add remark..."
        onChange={(e) => setVal(e.target.value)}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        data-testid={`remarks-input-${lineId}`}
        disabled={isSaving}
        className="w-full text-xs px-2.5 py-1.5 border border-slate-300 bg-white hover:border-slate-400 focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] focus:outline-none transition-colors text-slate-800 placeholder:text-slate-400 disabled:opacity-50"
      />
      {isSaving && (
        <span className="absolute right-2 text-[10px] text-[#2563EB] font-bold font-mono animate-pulse">...</span>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-Modal: Cash Withdrawal Audit Trail & Karigar Disbursements Breakdown
// ─────────────────────────────────────────────────────────────────────────────
function CashWithdrawalBreakdownModal({ cashLedgerId, line, accounts, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  const acc = line ? accounts.find((a) => a.id === line.bank_account_id) : null;

  useEffect(() => {
    let isMounted = true;
    const fetchDetail = async () => {
      setLoading(true);
      try {
        if (cashLedgerId) {
          const { data } = await http.get(`/banking/cash-ledger/${cashLedgerId}`);
          if (isMounted) setDetail(data);
        } else if (line?.cash_ledger_info) {
          if (isMounted) setDetail(line.cash_ledger_info);
        }
      } catch (err) {
        console.error("Failed to load cash ledger detail", err);
        if (line?.cash_ledger_info && isMounted) {
          setDetail(line.cash_ledger_info);
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    fetchDetail();
    return () => {
      isMounted = false;
    };
  }, [cashLedgerId, line]);

  const withdrawalAmount = Number(detail?.withdrawal_amount || line?.debit_amount || line?.cash_ledger_info?.withdrawal_amount || 0);
  const allocatedAmount = Number(detail?.allocated_amount ?? line?.cash_ledger_info?.allocated_amount ?? 0);
  const remainingBalance = Number(detail?.remaining_balance ?? line?.cash_ledger_info?.remaining_balance ?? (withdrawalAmount - allocatedAmount));
  const wagePayments = detail?.wage_payments || line?.cash_ledger_info?.wage_payments || [];
  const expenses = detail?.expenses || line?.cash_ledger_info?.expenses || [];

  // Build combined disbursements list if not already computed
  const disbursements = detail?.disbursements || line?.cash_ledger_info?.disbursements || [
    ...wagePayments.map((wp) => ({
      id: wp.id || wp._id,
      type: "wage_payment",
      type_label: "Karigar Wage",
      title: wp.worker_name || `Worker #${String(wp.worker_id).slice(-6)}`,
      amount: wp.amount,
      date: wp.date,
      period_from: wp.period_from,
      period_to: wp.period_to,
      notes: wp.notes || "",
      override_reason: wp.override_reason,
    })),
    ...expenses.map((e) => ({
      id: e.id || e._id,
      type: "expense",
      type_label: "Cash Expense",
      title: e.payee || "Payee",
      category: e.category || "Expense",
      amount: e.amount,
      date: e.date,
      notes: e.notes || "",
    })),
  ].sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));

  const pctAllocated = withdrawalAmount > 0 ? Math.min(100, Math.round((allocatedAmount / withdrawalAmount) * 100)) : 0;

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white border-2 border-slate-900 max-w-3xl w-full shadow-2xl animate-in zoom-in-95 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-4 border-b-2 border-slate-100 flex items-center justify-between bg-amber-50/50">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-amber-100 border border-amber-300 text-amber-900 rounded">
              <Coins className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-black text-slate-900 text-sm uppercase tracking-wide">
                Cash Withdrawal Audit Trail
              </h3>
              <p className="text-xs text-slate-500 font-mono">
                Ref: #{String(cashLedgerId || line?.matched_to?.ref_id || "ledger").slice(-8)} {line?.date ? `• Statement Date: ${line.date}` : ""}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-5 overflow-y-auto flex-1">
          {/* Statement metadata banner */}
          {line && (
            <div className="p-3 bg-slate-50 border border-slate-200 text-xs font-mono flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="text-slate-500">Bank Account: </span>
                <span className="font-bold text-slate-800">{acc ? acc.name : "Primary Account"}</span>
              </div>
              <div className="max-w-[300px] truncate" title={line.narration}>
                <span className="text-slate-500">Narration: </span>
                <span className="text-slate-700">{line.narration}</span>
              </div>
            </div>
          )}

          {/* KPI Metrics */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="p-3 bg-white border-2 border-slate-200">
              <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Withdrawn Amount</div>
              <div className="text-lg font-mono font-bold text-slate-900 mt-0.5">₹{inr(withdrawalAmount)}</div>
              <div className="text-[10px] text-slate-400 font-mono mt-0.5">Gross Bank Debit</div>
            </div>

            <div className="p-3 bg-white border-2 border-emerald-200 bg-emerald-50/20">
              <div className="text-[10px] uppercase font-bold text-emerald-800 tracking-wider">Disbursed to Karigars</div>
              <div className="text-lg font-mono font-bold text-emerald-700 mt-0.5">₹{inr(allocatedAmount)}</div>
              <div className="text-[10px] text-emerald-600 font-mono mt-0.5">
                {wagePayments.length} wage payout(s) • {expenses.length} general expense(s)
              </div>
            </div>

            <div className="p-3 bg-white border-2 border-amber-200 bg-amber-50/20">
              <div className="text-[10px] uppercase font-bold text-amber-900 tracking-wider">Unallocated Cash in Hand</div>
              <div className="text-lg font-mono font-bold text-amber-900 mt-0.5">₹{inr(remainingBalance)}</div>
              <div className="text-[10px] text-amber-700 font-mono mt-0.5">Available for future wages & expenses</div>
            </div>
          </div>

          {/* Allocation Progress */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs font-mono text-slate-600 font-bold">
              <span>Disbursement Progress: {pctAllocated}%</span>
              <span>₹{inr(allocatedAmount)} / ₹{inr(withdrawalAmount)}</span>
            </div>
            <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden">
              <div
                className="bg-emerald-600 h-full transition-all duration-300"
                style={{ width: `${pctAllocated}%` }}
              />
            </div>
          </div>

          {/* Linked Disbursements Table */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="font-bold text-xs uppercase tracking-wider text-slate-800">
                Where did this cash actually go? ({disbursements.length} Linked Disbursements)
              </h4>
            </div>

            {loading ? (
              <div className="py-8 text-center text-slate-500 font-mono text-xs">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-slate-400" />
                Loading linked disbursements...
              </div>
            ) : disbursements.length === 0 ? (
              <div className="p-6 text-center border-2 border-dashed border-slate-200 bg-slate-50 text-slate-500 space-y-1">
                <Wallet className="w-8 h-8 mx-auto text-slate-400 opacity-60" />
                <p className="font-bold text-xs text-slate-700">No wage or expense disbursements recorded yet from this withdrawal.</p>
                <p className="text-[11px] text-slate-500 max-w-sm mx-auto">
                  The full amount (₹{inr(withdrawalAmount)}) is currently sitting as unallocated cash in hand. When wage payouts or expenses are recorded with paid_via="cash" drawing from this withdrawal, they will automatically appear here.
                </p>
              </div>
            ) : (
              <div className="border-2 border-slate-200 overflow-x-auto max-h-64">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-100 sticky top-0 text-[10px] font-bold uppercase tracking-wider text-slate-600 border-b-2 border-slate-200">
                    <tr>
                      <th className="px-3 py-2">Date</th>
                      <th className="px-3 py-2">Type</th>
                      <th className="px-3 py-2">Recipient / Payee</th>
                      <th className="px-3 py-2 text-right">Amount Paid</th>
                      <th className="px-3 py-2">Period / Category</th>
                      <th className="px-3 py-2">Notes & Audit Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 font-mono">
                    {disbursements.map((d) => (
                      <tr key={d.id || `${d.type}-${d.date}-${d.amount}`} className="hover:bg-slate-50">
                        <td className="px-3 py-2 text-slate-700 whitespace-nowrap">{d.date}</td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {d.type === "wage_payment" ? (
                            <span className="inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-300">
                              👷 Karigar Wage
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 border border-blue-300">
                              🧾 Cash Expense
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 font-bold text-slate-900 font-sans">
                          {d.title}
                        </td>
                        <td className="px-3 py-2 text-right font-bold text-emerald-700 whitespace-nowrap">₹{inr(d.amount)}</td>
                        <td className="px-3 py-2 text-[11px] text-slate-600 whitespace-nowrap">
                          {d.type === "wage_payment" ? (
                            d.period_from && d.period_to ? `${d.period_from} → ${d.period_to}` : "Wage Payout"
                          ) : (
                            <span className="font-sans font-medium text-slate-700">{d.category || "General"}</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-slate-600 font-sans max-w-xs">
                          <div>{d.notes || "-"}</div>
                          {d.override_reason && (
                            <span className="inline-block mt-0.5 text-[9px] bg-red-100 text-red-900 border border-red-200 px-1 py-0.5 rounded font-mono font-bold">
                              ⚡ Overpayment Override: {d.override_reason}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t-2 border-slate-100 flex items-center justify-end bg-slate-50">
          <BtnSecondary onClick={onClose}>Close</BtnSecondary>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-Modal: Period Lock Modal
// ─────────────────────────────────────────────────────────────────────────────
function PeriodLockModal({
  accounts,
  selectedAccountId,
  periodFrom,
  periodTo,
  reason,
  onPeriodFromChange,
  onPeriodToChange,
  onReasonChange,
  onClose,
  onLock,
}) {
  const acc = accounts.find((a) => a.id === selectedAccountId);
  const accName = acc ? acc.name : "All Bank Accounts";

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-md overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between bg-amber-50">
          <div className="flex items-center gap-2">
            <Lock className="w-5 h-5 text-amber-700" />
            <div>
              <h3 className="font-bold text-sm text-slate-900">Lock Reconciliation Period</h3>
              <p className="text-[11px] text-slate-600">Finalize monthly statement & prevent further edits</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-amber-100 text-slate-600 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4">
          <div className="p-3 bg-amber-50/80 border border-amber-200 rounded text-xs text-amber-900 space-y-1">
            <div className="font-bold flex items-center gap-1">
              <ShieldCheck className="w-4 h-4 text-amber-600" />
              Finalization & Protection Guard
            </div>
            <p className="text-[11px] leading-relaxed">
              Locking protects all matched statement lines and cash/ERP links in this date range from accidental unmatching, re-matching, or deletions. Useful once monthly figures are verified for GST filing or accounting.
            </p>
          </div>

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Target Account</label>
              <input
                type="text"
                disabled
                value={accName}
                className="w-full bg-slate-100 border border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-700 rounded"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Period From</label>
                <input
                  type="date"
                  value={periodFrom}
                  onChange={(e) => onPeriodFromChange(e.target.value)}
                  className="w-full border-2 border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-800 focus:outline-none focus:border-slate-800"
                  data-testid="lock-period-from-input"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Period To</label>
                <input
                  type="date"
                  value={periodTo}
                  onChange={(e) => onPeriodToChange(e.target.value)}
                  className="w-full border-2 border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-800 focus:outline-none focus:border-slate-800"
                  data-testid="lock-period-to-input"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Reason / Notes</label>
              <input
                type="text"
                value={reason}
                onChange={(e) => onReasonChange(e.target.value)}
                placeholder="e.g. August 2026 Monthly Reconciliation Finalized for GST Filing"
                className="w-full border-2 border-slate-300 px-3 py-1.5 text-xs text-slate-800 focus:outline-none focus:border-slate-800"
                data-testid="lock-reason-input"
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t-2 border-slate-100 flex items-center justify-end gap-2 bg-slate-50">
          <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          <BtnPrimary
            onClick={onLock}
            className="flex items-center gap-1.5 bg-amber-700 border-amber-700 hover:bg-amber-800"
            testId="confirm-lock-period-btn"
          >
            <Lock className="w-3.5 h-3.5" /> Confirm Lock Period
          </BtnPrimary>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-Modal: Period Unlock Modal (Admin Only)
// ─────────────────────────────────────────────────────────────────────────────
function PeriodUnlockModal({
  lockDoc,
  accounts,
  unlockReason,
  onReasonChange,
  onClose,
  onUnlock,
}) {
  const acc = accounts.find((a) => a.id === lockDoc.bank_account_id);
  const accName = acc ? acc.name : "All Bank Accounts";

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-md overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between bg-red-50">
          <div className="flex items-center gap-2">
            <Unlock className="w-5 h-5 text-red-700" />
            <div>
              <h3 className="font-bold text-sm text-slate-900">Unlock Reconciliation Period</h3>
              <p className="text-[11px] text-red-700 font-bold">Admin-Only Logged Action</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-red-100 text-slate-600 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4">
          <div className="p-3 bg-red-50/80 border border-red-200 rounded text-xs text-red-900 space-y-1">
            <div className="font-bold flex items-center gap-1">
              <AlertTriangle className="w-4 h-4 text-red-600" />
              Administrative Unlock Required
            </div>
            <p className="text-[11px] leading-relaxed">
              Unlocking will permit modifications to statement lines between{" "}
              <strong className="font-mono">{lockDoc.period_from}</strong> and{" "}
              <strong className="font-mono">{lockDoc.period_to}</strong> for {accName}. This action will be permanently recorded in the audit history.
            </p>
          </div>

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Locked Period</label>
              <div className="font-mono text-xs font-bold bg-slate-100 p-2 border border-slate-300 rounded">
                {lockDoc.period_from} → {lockDoc.period_to} ({accName})
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">Original Lock Reason</label>
              <div className="text-xs text-slate-600 bg-slate-50 p-2 border border-slate-200 rounded italic">
                {lockDoc.lock_reason || "Reconciliation finalized"}
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Reason for Unlocking <span className="text-red-600">*</span>
              </label>
              <textarea
                rows={3}
                value={unlockReason}
                onChange={(e) => onReasonChange(e.target.value)}
                placeholder="Explain why this finalized period is being unlocked (e.g. Audit correction for invoice #1024)..."
                className="w-full border-2 border-slate-300 p-2 text-xs text-slate-800 focus:outline-none focus:border-red-600"
                data-testid="unlock-reason-input"
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t-2 border-slate-100 flex items-center justify-end gap-2 bg-slate-50">
          <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          <BtnPrimary
            onClick={onUnlock}
            disabled={!unlockReason.trim()}
            className="flex items-center gap-1.5 bg-red-700 border-red-700 hover:bg-red-800 disabled:opacity-50"
            testId="confirm-unlock-period-btn"
          >
            <Unlock className="w-3.5 h-3.5" /> Unlock Period (Admin)
          </BtnPrimary>
        </div>
      </div>
    </div>
  );
}



