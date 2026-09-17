import { useState, useEffect, useMemo } from "react";
import { http, formatApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  PageHeader,
  Card,
  BtnPrimary,
  BtnSecondary,
  Input,
  Select,
  Badge,
} from "../components/ui-kit";
import {
  Landmark,
  Scale,
  BookOpen,
  Plus,
  Lock,
  Unlock,
  CheckCircle2,
  AlertTriangle,
  Search,
  Calendar,
  Layers,
  ArrowDownRight,
  ArrowUpRight,
  ShieldCheck,
  RefreshCw,
  FileText,
  DollarSign,
  ChevronRight,
  Building,
} from "lucide-react";

export default function FinanceLedgers() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState("accounts");
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Chart of Accounts State
  const [accounts, setAccounts] = useState([]);
  const [accountTypeFilter, setAccountTypeFilter] = useState("ALL");
  const [accountSearch, setAccountSearch] = useState("");
  const [newAccountModal, setNewAccountModal] = useState(false);
  const [newAccountForm, setNewAccountForm] = useState({
    code: "",
    name: "",
    account_type: "ASSET",
    sub_type: "CURRENT_ASSET",
    description: "",
    is_reconcilable: false,
  });

  // General Ledger State
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [glDateFrom, setGlDateFrom] = useState("");
  const [glDateTo, setGlDateTo] = useState("");
  const [glReport, setGlReport] = useState(null);
  const [glLoading, setGlLoading] = useState(false);

  // Journal Entries State
  const [journalEntries, setJournalEntries] = useState([]);
  const [selectedJournal, setSelectedJournal] = useState(null);
  const [newJournalModal, setNewJournalModal] = useState(false);
  const [newJournalForm, setNewJournalForm] = useState({
    entry_date: new Date().toISOString().slice(0, 10),
    entry_type: "MANUAL_JOURNAL",
    narration: "",
    source_document_ref: "",
    lines: [
      { account_id: "", description: "", debit: 0, credit: 0 },
      { account_id: "", description: "", debit: 0, credit: 0 },
    ],
  });

  // Trial Balance State
  const [tbDate, setTbDate] = useState(new Date().toISOString().slice(0, 10));
  const [trialBalance, setTrialBalance] = useState(null);
  const [tbLoading, setTbLoading] = useState(false);

  // Period Locks State
  const [periodLocks, setPeriodLocks] = useState([]);
  const [newLockModal, setNewLockModal] = useState(false);
  const [newLockForm, setNewLockForm] = useState({
    period_from: "",
    period_to: "",
    lock_reason: "Monthly financial closure",
  });
  const [unlockModal, setUnlockModal] = useState(null);
  const [unlockReason, setUnlockReason] = useState("");

  // ── Initial Fetch ──────────────────────────────────────────────────────────
  const fetchStatus = async () => {
    try {
      const { data } = await http.get("/finance/status");
      setStatus(data);
    } catch (e) {
      console.warn("Finance status error:", e);
    }
  };

  const fetchAccounts = async () => {
    try {
      const { data } = await http.get("/finance/chart-of-accounts");
      setAccounts(data || []);
      if (!selectedAccountId && data && data.length > 0) {
        // Default to Cash or AR
        const def = data.find((a) => a.code === "1030") || data[0];
        setSelectedAccountId(def.id);
      }
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || e.message);
    }
  };

  const fetchPeriodLocks = async () => {
    try {
      const { data } = await http.get("/finance/periods/locks");
      setPeriodLocks(data || []);
    } catch (e) {
      console.warn("Error fetching locks:", e);
    }
  };

  const fetchJournalEntries = async () => {
    try {
      const { data } = await http.get("/finance/journal-entries?limit=50");
      setJournalEntries(data || []);
    } catch (e) {
      console.warn("Error fetching journal entries:", e);
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchAccounts();
    fetchPeriodLocks();
    fetchJournalEntries();
  }, []);

  // ── Tab 2: Load General Ledger ─────────────────────────────────────────────
  const loadGeneralLedger = async () => {
    if (!selectedAccountId) return;
    setGlLoading(true);
    setError("");
    try {
      let url = `/finance/ledger/${selectedAccountId}?`;
      if (glDateFrom) url += `from_date=${glDateFrom}&`;
      if (glDateTo) url += `to_date=${glDateTo}&`;
      const { data } = await http.get(url);
      setGlReport(data);
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || e.message);
    } finally {
      setGlLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "ledger" && selectedAccountId) {
      loadGeneralLedger();
    }
  }, [activeTab, selectedAccountId, glDateFrom, glDateTo]);

  // ── Tab 4: Load Trial Balance ──────────────────────────────────────────────
  const loadTrialBalance = async () => {
    setTbLoading(true);
    setError("");
    try {
      const { data } = await http.get(`/finance/trial-balance?as_of_date=${tbDate}`);
      setTrialBalance(data);
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || e.message);
    } finally {
      setTbLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "trial_balance") {
      loadTrialBalance();
    }
  }, [activeTab, tbDate]);

  // ── Account Creation ───────────────────────────────────────────────────────
  const handleCreateAccount = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await http.post("/finance/chart-of-accounts", newAccountForm);
      setNewAccountModal(false);
      setNewAccountForm({
        code: "",
        name: "",
        account_type: "ASSET",
        sub_type: "CURRENT_ASSET",
        description: "",
        is_reconcilable: false,
      });
      fetchAccounts();
      fetchStatus();
    } catch (e2) {
      setError(formatApiError(e2.response?.data?.detail) || e2.message);
    }
  };

  // ── Journal Entry Submission ───────────────────────────────────────────────
  const journalBalance = useMemo(() => {
    const totDeb = newJournalForm.lines.reduce((acc, l) => acc + (parseFloat(l.debit) || 0), 0);
    const totCred = newJournalForm.lines.reduce((acc, l) => acc + (parseFloat(l.credit) || 0), 0);
    const diff = Math.abs(totDeb - totCred);
    return {
      totalDebit: totDeb,
      totalCredit: totCred,
      difference: diff,
      isBalanced: diff < 0.001 && totDeb > 0,
    };
  }, [newJournalForm.lines]);

  const addJournalLine = () => {
    setNewJournalForm({
      ...newJournalForm,
      lines: [
        ...newJournalForm.lines,
        { account_id: "", description: "", debit: 0, credit: 0 },
      ],
    });
  };

  const removeJournalLine = (index) => {
    if (newJournalForm.lines.length <= 2) return;
    const updated = newJournalForm.lines.filter((_, idx) => idx !== index);
    setNewJournalForm({ ...newJournalForm, lines: updated });
  };

  const updateJournalLine = (index, field, val) => {
    const updated = [...newJournalForm.lines];
    updated[index][field] = val;
    setNewJournalForm({ ...newJournalForm, lines: updated });
  };

  const handlePostJournal = async (e) => {
    e.preventDefault();
    if (!journalBalance.isBalanced) {
      setError("Journal Entry must be balanced (Total Debits == Total Credits > 0).");
      return;
    }
    setError("");
    try {
      await http.post("/finance/journal-entries", {
        entry_date: newJournalForm.entry_date,
        entry_type: newJournalForm.entry_type,
        narration: newJournalForm.narration,
        source_document_ref: newJournalForm.source_document_ref,
        lines: newJournalForm.lines.map((l) => ({
          account_id: l.account_id,
          description: l.description,
          debit: parseFloat(l.debit) || 0,
          credit: parseFloat(l.credit) || 0,
        })),
      });
      setNewJournalModal(false);
      fetchJournalEntries();
      if (activeTab === "ledger") loadGeneralLedger();
      if (activeTab === "trial_balance") loadTrialBalance();
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || err.message);
    }
  };

  // ── Period Locking ─────────────────────────────────────────────────────────
  const handleLockPeriod = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await http.post("/finance/periods/lock", newLockForm);
      setNewLockModal(false);
      fetchPeriodLocks();
    } catch (e2) {
      setError(formatApiError(e2.response?.data?.detail) || e2.message);
    }
  };

  const handleUnlockPeriod = async () => {
    if (!unlockModal) return;
    setError("");
    try {
      await http.post("/finance/periods/unlock", {
        lock_id: unlockModal.id,
        unlock_reason: unlockReason || "Admin authorized reopening",
      });
      setUnlockModal(null);
      setUnlockReason("");
      fetchPeriodLocks();
    } catch (e2) {
      setError(formatApiError(e2.response?.data?.detail) || e2.message);
    }
  };

  // ── Filtered Accounts ──────────────────────────────────────────────────────
  const filteredAccounts = useMemo(() => {
    return accounts.filter((a) => {
      const matchType = accountTypeFilter === "ALL" || a.account_type === accountTypeFilter;
      const matchSearch =
        !accountSearch ||
        a.code.toLowerCase().includes(accountSearch.toLowerCase()) ||
        a.name.toLowerCase().includes(accountSearch.toLowerCase()) ||
        a.sub_type.toLowerCase().includes(accountSearch.toLowerCase());
      return matchType && matchSearch;
    });
  }, [accounts, accountTypeFilter, accountSearch]);

  const accountTypeColor = {
    ASSET: "blue",
    LIABILITY: "orange",
    EQUITY: "purple",
    REVENUE: "green",
    EXPENSE: "red",
  };

  return (
    <div className="space-y-4 pb-12">
      <PageHeader
        title="Relational Financial Core & Double-Entry Ledgers"
        subtitle="ACID Compliant Accounting Core &middot; Indian Footwear Standard Chart of Accounts"
        testId="finance-header"
        action={
          <div className="flex gap-2">
            <BtnSecondary onClick={() => setNewLockModal(true)}>
              <Lock className="w-3.5 h-3.5 inline -mt-0.5 mr-1 text-amber-600" /> Lock Period
            </BtnSecondary>
            <BtnPrimary onClick={() => setNewJournalModal(true)}>
              <Plus className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Post Journal Entry
            </BtnPrimary>
          </div>
        }
      />

      <div className="p-2 sm:p-4 lg:p-8 space-y-6">
        {/* Top Status & Metrics Strip */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <Card className="p-3.5 flex items-center gap-3">
            <div className="p-2.5 bg-blue-50 text-blue-600 rounded-lg">
              <Landmark className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                Chart of Accounts
              </div>
              <div className="text-xl font-black text-slate-900 font-mono">
                {status?.chart_of_accounts_count ?? accounts.length}
              </div>
              <div className="text-[10px] text-slate-500">Seeded Indian Standard</div>
            </div>
          </Card>

          <Card className="p-3.5 flex items-center gap-3">
            <div className="p-2.5 bg-emerald-50 text-emerald-600 rounded-lg">
              <Scale className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                Double-Entry Invariant
              </div>
              <div className="text-sm font-bold text-emerald-600 flex items-center gap-1 mt-0.5">
                <CheckCircle2 className="w-4 h-4" /> &Sigma;Debits == &Sigma;Credits
              </div>
              <div className="text-[10px] text-slate-500">Strict Balance Check</div>
            </div>
          </Card>

          <Card className="p-3.5 flex items-center gap-3">
            <div className="p-2.5 bg-purple-50 text-purple-600 rounded-lg">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                SQL Engine & Dialect
              </div>
              <div className="text-sm font-bold text-slate-800 font-mono mt-0.5">
                {status?.engine_dialect?.toUpperCase() || "POSTGRESQL / SQLITE"}
              </div>
              <div className="text-[10px] text-purple-700">
                {status?.supabase?.configured ? "Supabase Cloud Configured" : "Local / Portable Engine"}
              </div>
            </div>
          </Card>

          <Card className="p-3.5 flex items-center gap-3">
            <div className="p-2.5 bg-amber-50 text-amber-600 rounded-lg">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                Period Lock Guard
              </div>
              <div className="text-xl font-black text-slate-900 font-mono">
                {periodLocks.filter((l) => l.is_active).length}
              </div>
              <div className="text-[10px] text-slate-500">Active Locked Periods</div>
            </div>
          </Card>
        </div>

        {/* Global Error Banner */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-xs font-semibold flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError("")} className="text-red-500 hover:text-red-800">
              &times;
            </button>
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="border-b border-slate-200">
          <nav className="flex gap-4 overflow-x-auto text-sm font-medium">
            <button
              onClick={() => setActiveTab("accounts")}
              className={`pb-3 border-b-2 flex items-center gap-1.5 transition-colors duration-150 ${
                activeTab === "accounts"
                  ? "border-blue-600 text-blue-600 font-bold"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <Landmark className="w-4 h-4" /> Chart of Accounts
            </button>
            <button
              onClick={() => setActiveTab("ledger")}
              className={`pb-3 border-b-2 flex items-center gap-1.5 transition-colors duration-150 ${
                activeTab === "ledger"
                  ? "border-blue-600 text-blue-600 font-bold"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <BookOpen className="w-4 h-4" /> General Ledger
            </button>
            <button
              onClick={() => setActiveTab("journals")}
              className={`pb-3 border-b-2 flex items-center gap-1.5 transition-colors duration-150 ${
                activeTab === "journals"
                  ? "border-blue-600 text-blue-600 font-bold"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <FileText className="w-4 h-4" /> Journal Entries
            </button>
            <button
              onClick={() => setActiveTab("trial_balance")}
              className={`pb-3 border-b-2 flex items-center gap-1.5 transition-colors duration-150 ${
                activeTab === "trial_balance"
                  ? "border-blue-600 text-blue-600 font-bold"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <Scale className="w-4 h-4" /> Trial Balance
            </button>
            <button
              onClick={() => setActiveTab("period_locks")}
              className={`pb-3 border-b-2 flex items-center gap-1.5 transition-colors duration-150 ${
                activeTab === "period_locks"
                  ? "border-blue-600 text-blue-600 font-bold"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <Lock className="w-4 h-4" /> Accounting Period Locks
            </button>
          </nav>
        </div>

        {/* ── TAB 1: CHART OF ACCOUNTS ───────────────────────────────────────── */}
        {activeTab === "accounts" && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <div className="relative flex-1 sm:w-72">
                  <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search by code, account name, sub-type..."
                    value={accountSearch}
                    onChange={(e) => setAccountSearch(e.target.value)}
                    className="pl-9 pr-3 py-1.5 text-xs w-full border border-slate-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <select
                  value={accountTypeFilter}
                  onChange={(e) => setAccountTypeFilter(e.target.value)}
                  className="px-2.5 py-1.5 text-xs border border-slate-200 rounded-md bg-white focus:outline-none"
                >
                  <option value="ALL">All Account Types</option>
                  <option value="ASSET">Assets</option>
                  <option value="LIABILITY">Liabilities</option>
                  <option value="EQUITY">Equity</option>
                  <option value="REVENUE">Revenue</option>
                  <option value="EXPENSE">Expenses</option>
                </select>
              </div>
              <BtnSecondary onClick={() => setNewAccountModal(true)} className="text-xs">
                <Plus className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> New GL Account
              </BtnSecondary>
            </div>

            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase font-bold text-[10px]">
                    <tr>
                      <th className="px-4 py-2.5 text-left">Code</th>
                      <th className="px-4 py-2.5 text-left">Account Name</th>
                      <th className="px-4 py-2.5 text-left">Account Type</th>
                      <th className="px-4 py-2.5 text-left">Sub Type</th>
                      <th className="px-4 py-2.5 text-center">Currency</th>
                      <th className="px-4 py-2.5 text-center">Reconcilable</th>
                      <th className="px-4 py-2.5 text-center">Status</th>
                      <th className="px-4 py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredAccounts.map((a) => (
                      <tr key={a.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="px-4 py-2.5 font-mono font-bold text-slate-800">{a.code}</td>
                        <td className="px-4 py-2.5 font-medium text-slate-900">{a.name}</td>
                        <td className="px-4 py-2.5">
                          <Badge color={accountTypeColor[a.account_type] || "slate"}>
                            {a.account_type}
                          </Badge>
                        </td>
                        <td className="px-4 py-2.5 font-mono text-[11px] text-slate-600">{a.sub_type}</td>
                        <td className="px-4 py-2.5 text-center font-mono">{a.currency}</td>
                        <td className="px-4 py-2.5 text-center">
                          {a.is_reconcilable ? (
                            <span className="text-emerald-600 font-bold">&#10003; Yes</span>
                          ) : (
                            <span className="text-slate-400">&mdash;</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          <Badge color={a.is_active ? "green" : "red"}>
                            {a.is_active ? "Active" : "Inactive"}
                          </Badge>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <button
                            onClick={() => {
                              setSelectedAccountId(a.id);
                              setActiveTab("ledger");
                            }}
                            className="text-blue-600 hover:text-blue-800 font-semibold text-[11px]"
                          >
                            View Ledger &rarr;
                          </button>
                        </td>
                      </tr>
                    ))}
                    {filteredAccounts.length === 0 && (
                      <tr>
                        <td colSpan={8} className="py-8 text-center text-slate-400 italic">
                          No accounts match current filters.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}

        {/* ── TAB 2: GENERAL LEDGER ─────────────────────────────────────────── */}
        {activeTab === "ledger" && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-3 bg-slate-50 p-3 rounded-lg border border-slate-200">
              <div className="w-72">
                <label className="block text-[10px] font-bold text-slate-600 uppercase mb-1">
                  Select General Ledger Account
                </label>
                <select
                  value={selectedAccountId}
                  onChange={(e) => setSelectedAccountId(e.target.value)}
                  className="w-full text-xs border border-slate-200 rounded p-1.5 bg-white font-medium focus:ring-2 focus:ring-blue-500"
                >
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.code} &mdash; {a.name} ({a.account_type})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-600 uppercase mb-1">
                  From Date
                </label>
                <input
                  type="date"
                  value={glDateFrom}
                  onChange={(e) => setGlDateFrom(e.target.value)}
                  className="text-xs border border-slate-200 rounded p-1.5 bg-white"
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-slate-600 uppercase mb-1">
                  To Date
                </label>
                <input
                  type="date"
                  value={glDateTo}
                  onChange={(e) => setGlDateTo(e.target.value)}
                  className="text-xs border border-slate-200 rounded p-1.5 bg-white"
                />
              </div>

              <BtnSecondary onClick={loadGeneralLedger} className="text-xs">
                <RefreshCw className={`w-3.5 h-3.5 inline mr-1 ${glLoading ? "animate-spin" : ""}`} />
                Refresh
              </BtnSecondary>
            </div>

            {glReport && (
              <div className="space-y-4">
                {/* Summary Strip */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="bg-slate-100 p-3 rounded border border-slate-200">
                    <div className="text-[10px] uppercase font-bold text-slate-500">Opening Balance</div>
                    <div className="text-base font-black font-mono mt-0.5">
                      &#8377;{glReport.opening_balance?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-blue-50/50 p-3 rounded border border-blue-200">
                    <div className="text-[10px] uppercase font-bold text-blue-700">Period Debits</div>
                    <div className="text-base font-black font-mono text-blue-700 mt-0.5">
                      &#8377;{glReport.period_debits?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-amber-50/50 p-3 rounded border border-amber-200">
                    <div className="text-[10px] uppercase font-bold text-amber-700">Period Credits</div>
                    <div className="text-base font-black font-mono text-amber-700 mt-0.5">
                      &#8377;{glReport.period_credits?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div className="bg-emerald-50/60 p-3 rounded border border-emerald-200">
                    <div className="text-[10px] uppercase font-bold text-emerald-800">Closing Balance</div>
                    <div className="text-base font-black font-mono text-emerald-800 mt-0.5">
                      &#8377;{glReport.closing_balance?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>

                {/* Ledger Transactions Table */}
                <Card className="overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase font-bold text-[10px]">
                        <tr>
                          <th className="px-4 py-2.5 text-left">Date</th>
                          <th className="px-4 py-2.5 text-left">Entry #</th>
                          <th className="px-4 py-2.5 text-left">Narration / Description</th>
                          <th className="px-4 py-2.5 text-left">Ref Document</th>
                          <th className="px-4 py-2.5 text-right">Debit (&#8377;)</th>
                          <th className="px-4 py-2.5 text-right">Credit (&#8377;)</th>
                          <th className="px-4 py-2.5 text-right">Running Balance (&#8377;)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 font-mono">
                        {glReport.lines?.map((line, idx) => (
                          <tr key={idx} className="hover:bg-slate-50/80 transition-colors">
                            <td className="px-4 py-2 text-slate-600">{line.entry_date}</td>
                            <td className="px-4 py-2 text-blue-600 font-bold">{line.entry_number}</td>
                            <td className="px-4 py-2 font-sans text-slate-900">{line.narration || line.description}</td>
                            <td className="px-4 py-2 text-slate-500">{line.source_document_ref || "&mdash;"}</td>
                            <td className="px-4 py-2 text-right text-blue-700 font-semibold">
                              {line.debit > 0 ? line.debit.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : ""}
                            </td>
                            <td className="px-4 py-2 text-right text-amber-700 font-semibold">
                              {line.credit > 0 ? line.credit.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : ""}
                            </td>
                            <td className="px-4 py-2 text-right font-bold text-slate-900">
                              {line.running_balance.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                            </td>
                          </tr>
                        ))}
                        {(!glReport.lines || glReport.lines.length === 0) && (
                          <tr>
                            <td colSpan={7} className="py-8 text-center text-slate-400 italic font-sans">
                              No transaction lines recorded for this period.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>
            )}
          </div>
        )}

        {/* ── TAB 3: JOURNAL ENTRIES ────────────────────────────────────────── */}
        {activeTab === "journals" && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <div className="text-xs text-slate-500">
                Displaying most recent balanced journal entries from PostgreSQL financial ledger.
              </div>
              <BtnPrimary onClick={() => setNewJournalModal(true)} className="text-xs">
                <Plus className="w-3.5 h-3.5 inline mr-1" /> New Journal Entry
              </BtnPrimary>
            </div>

            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase font-bold text-[10px]">
                    <tr>
                      <th className="px-4 py-2.5 text-left">Date</th>
                      <th className="px-4 py-2.5 text-left">Entry #</th>
                      <th className="px-4 py-2.5 text-left">Type</th>
                      <th className="px-4 py-2.5 text-left">Narration</th>
                      <th className="px-4 py-2.5 text-left">Source Ref</th>
                      <th className="px-4 py-2.5 text-right">Debit (&#8377;)</th>
                      <th className="px-4 py-2.5 text-right">Credit (&#8377;)</th>
                      <th className="px-4 py-2.5 text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono">
                    {journalEntries.map((je) => (
                      <tr key={je.id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-4 py-2.5 text-slate-600">{je.entry_date}</td>
                        <td className="px-4 py-2.5 font-bold text-blue-600">{je.entry_number}</td>
                        <td className="px-4 py-2.5 font-sans">
                          <span className="px-1.5 py-0.5 bg-slate-100 rounded text-[10px] font-mono text-slate-700">
                            {je.entry_type}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 font-sans text-slate-900 max-w-xs truncate">{je.narration}</td>
                        <td className="px-4 py-2.5 text-slate-500 font-sans">{je.source_document_ref || "&mdash;"}</td>
                        <td className="px-4 py-2.5 text-right font-semibold text-slate-800">
                          {je.total_debit?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="px-4 py-2.5 text-right font-semibold text-slate-800">
                          {je.total_credit?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="px-4 py-2.5 text-center font-sans">
                          <Badge color="green">POSTED</Badge>
                        </td>
                      </tr>
                    ))}
                    {journalEntries.length === 0 && (
                      <tr>
                        <td colSpan={8} className="py-8 text-center text-slate-400 italic font-sans">
                          No journal entries found.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}

        {/* ── TAB 4: TRIAL BALANCE ──────────────────────────────────────────── */}
        {activeTab === "trial_balance" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between bg-slate-50 p-3 rounded-lg border border-slate-200">
              <div className="flex items-center gap-3">
                <label className="text-xs font-bold text-slate-700">As of Date:</label>
                <input
                  type="date"
                  value={tbDate}
                  onChange={(e) => setTbDate(e.target.value)}
                  className="text-xs border border-slate-200 rounded p-1.5 bg-white font-medium"
                />
                <BtnSecondary onClick={loadTrialBalance} className="text-xs">
                  <RefreshCw className={`w-3.5 h-3.5 inline mr-1 ${tbLoading ? "animate-spin" : ""}`} />
                  Recalculate
                </BtnSecondary>
              </div>

              {trialBalance && (
                <div>
                  {trialBalance.is_balanced ? (
                    <span className="px-3 py-1 bg-emerald-100 text-emerald-800 rounded-full text-xs font-bold flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4" /> Trial Balance is Mathematically Balanced
                    </span>
                  ) : (
                    <span className="px-3 py-1 bg-red-100 text-red-800 rounded-full text-xs font-bold flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4" /> Out of Balance by &#8377;{trialBalance.difference}
                    </span>
                  )}
                </div>
              )}
            </div>

            {trialBalance && (
              <Card className="overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase font-bold text-[10px]">
                      <tr>
                        <th className="px-4 py-2.5 text-left">Code</th>
                        <th className="px-4 py-2.5 text-left">Account Name</th>
                        <th className="px-4 py-2.5 text-left">Type</th>
                        <th className="px-4 py-2.5 text-right">Debit Balance (&#8377;)</th>
                        <th className="px-4 py-2.5 text-right">Credit Balance (&#8377;)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono">
                      {trialBalance.accounts?.map((acc) => (
                        <tr key={acc.account_id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-4 py-2 font-bold text-slate-800">{acc.code}</td>
                          <td className="px-4 py-2 font-sans font-medium text-slate-900">{acc.name}</td>
                          <td className="px-4 py-2 font-sans">
                            <Badge color={accountTypeColor[acc.account_type] || "slate"}>
                              {acc.account_type}
                            </Badge>
                          </td>
                          <td className="px-4 py-2 text-right text-blue-700 font-semibold">
                            {acc.balance_debit > 0
                              ? acc.balance_debit.toLocaleString("en-IN", { minimumFractionDigits: 2 })
                              : ""}
                          </td>
                          <td className="px-4 py-2 text-right text-amber-700 font-semibold">
                            {acc.balance_credit > 0
                              ? acc.balance_credit.toLocaleString("en-IN", { minimumFractionDigits: 2 })
                              : ""}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="bg-slate-100 border-t-2 border-slate-300 font-mono font-bold text-xs">
                      <tr>
                        <td colSpan={3} className="px-4 py-3 font-sans uppercase">
                          Grand Totals
                        </td>
                        <td className="px-4 py-3 text-right text-blue-800 text-sm">
                          &#8377;
                          {trialBalance.total_debit?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="px-4 py-3 text-right text-amber-800 text-sm">
                          &#8377;
                          {trialBalance.total_credit?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </Card>
            )}
          </div>
        )}

        {/* ── TAB 5: ACCOUNTING PERIOD LOCKS ─────────────────────────────────── */}
        {activeTab === "period_locks" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-xs text-slate-600">
                Period locks block back-dated postings to closed fiscal periods. Immutability guaranteed at database level.
              </div>
              <BtnPrimary onClick={() => setNewLockModal(true)} className="text-xs">
                <Lock className="w-3.5 h-3.5 inline mr-1" /> Lock Accounting Period
              </BtnPrimary>
            </div>

            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase font-bold text-[10px]">
                    <tr>
                      <th className="px-4 py-2.5 text-left">Period From</th>
                      <th className="px-4 py-2.5 text-left">Period To</th>
                      <th className="px-4 py-2.5 text-left">Lock Reason</th>
                      <th className="px-4 py-2.5 text-left">Locked By</th>
                      <th className="px-4 py-2.5 text-center">Status</th>
                      <th className="px-4 py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {periodLocks.map((l) => (
                      <tr key={l.id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-4 py-2.5 font-mono font-bold">{l.period_from}</td>
                        <td className="px-4 py-2.5 font-mono font-bold">{l.period_to}</td>
                        <td className="px-4 py-2.5 text-slate-800">{l.lock_reason}</td>
                        <td className="px-4 py-2.5 text-slate-600">{l.locked_by}</td>
                        <td className="px-4 py-2.5 text-center">
                          <Badge color={l.is_active ? "amber" : "slate"}>
                            {l.is_active ? "LOCKED" : "UNLOCKED"}
                          </Badge>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          {l.is_active ? (
                            <button
                              onClick={() => setUnlockModal(l)}
                              className="text-amber-600 hover:text-amber-800 font-semibold text-xs inline-flex items-center gap-1"
                            >
                              <Unlock className="w-3 h-3" /> Unlock Period
                            </button>
                          ) : (
                            <span className="text-slate-400 text-[11px]">
                              Unlocked by {l.unlocked_by}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                    {periodLocks.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-slate-400 italic">
                          No accounting periods are currently locked.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}
      </div>

      {/* ── MODAL: CREATE GL ACCOUNT ────────────────────────────────────────── */}
      {newAccountModal && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h3 className="text-base font-bold text-slate-900">Create Chart of Accounts Entry</h3>
            <form onSubmit={handleCreateAccount} className="space-y-3 text-xs">
              <Input
                label="Account Code"
                placeholder="e.g. 1050, 4020, 5030"
                value={newAccountForm.code}
                onChange={(e) => setNewAccountForm({ ...newAccountForm, code: e.target.value })}
                required
              />
              <Input
                label="Account Name"
                placeholder="e.g. GST Advance Pool, Mould Amortization"
                value={newAccountForm.name}
                onChange={(e) => setNewAccountForm({ ...newAccountForm, name: e.target.value })}
                required
              />
              <div>
                <label className="block text-[10px] font-bold text-slate-600 uppercase mb-1">
                  Account Type
                </label>
                <select
                  value={newAccountForm.account_type}
                  onChange={(e) => setNewAccountForm({ ...newAccountForm, account_type: e.target.value })}
                  className="w-full text-xs border border-slate-200 rounded p-2 bg-white"
                >
                  <option value="ASSET">ASSET</option>
                  <option value="LIABILITY">LIABILITY</option>
                  <option value="EQUITY">EQUITY</option>
                  <option value="REVENUE">REVENUE</option>
                  <option value="EXPENSE">EXPENSE</option>
                </select>
              </div>
              <Input
                label="Sub Type (Classification)"
                placeholder="e.g. CURRENT_ASSET, OPERATING_REVENUE"
                value={newAccountForm.sub_type}
                onChange={(e) => setNewAccountForm({ ...newAccountForm, sub_type: e.target.value })}
                required
              />
              <Input
                label="Description (Optional)"
                value={newAccountForm.description}
                onChange={(e) => setNewAccountForm({ ...newAccountForm, description: e.target.value })}
              />
              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="rec_chk"
                  checked={newAccountForm.is_reconcilable}
                  onChange={(e) => setNewAccountForm({ ...newAccountForm, is_reconcilable: e.target.checked })}
                  className="rounded border-slate-300 text-blue-600"
                />
                <label htmlFor="rec_chk" className="text-slate-700">
                  Bank / Statement Reconcilable Account
                </label>
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t">
                <BtnSecondary type="button" onClick={() => setNewAccountModal(false)}>
                  Cancel
                </BtnSecondary>
                <BtnPrimary type="submit">Save Account</BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: POST JOURNAL ENTRY ────────────────────────────────────────── */}
      {newJournalModal && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-3xl w-full p-6 space-y-4 shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Scale className="w-5 h-5 text-blue-600" /> Post Double-Entry Journal Entry
              </h3>
              <div className="text-xs">
                {journalBalance.isBalanced ? (
                  <Badge color="green">Balanced (&#8377;{journalBalance.totalDebit})</Badge>
                ) : (
                  <Badge color="red">Difference: &#8377;{journalBalance.difference.toFixed(2)}</Badge>
                )}
              </div>
            </div>

            <form onSubmit={handlePostJournal} className="space-y-4 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <Input
                  label="Entry Date"
                  type="date"
                  value={newJournalForm.entry_date}
                  onChange={(e) => setNewJournalForm({ ...newJournalForm, entry_date: e.target.value })}
                  required
                />
                <Input
                  label="Source Document / Ref"
                  placeholder="e.g. JV-1092, CHQ-5544"
                  value={newJournalForm.source_document_ref}
                  onChange={(e) => setNewJournalForm({ ...newJournalForm, source_document_ref: e.target.value })}
                />
                <Input
                  label="Narration / Purpose"
                  placeholder="Explanation of transaction"
                  value={newJournalForm.narration}
                  onChange={(e) => setNewJournalForm({ ...newJournalForm, narration: e.target.value })}
                  required
                />
              </div>

              {/* Dynamic Line Rows */}
              <div className="border border-slate-200 rounded-lg p-3 bg-slate-50 space-y-2">
                <div className="flex items-center justify-between text-[11px] font-bold text-slate-700 uppercase">
                  <span>Debits & Credits Breakdown</span>
                  <button
                    type="button"
                    onClick={addJournalLine}
                    className="text-blue-600 hover:text-blue-800 underline lowercase"
                  >
                    + add row
                  </button>
                </div>

                <div className="space-y-2">
                  {newJournalForm.lines.map((line, idx) => (
                    <div key={idx} className="flex items-center gap-2 bg-white p-2 rounded border border-slate-200">
                      <div className="w-52">
                        <select
                          value={line.account_id}
                          onChange={(e) => updateJournalLine(idx, "account_id", e.target.value)}
                          required
                          className="w-full text-xs border border-slate-200 rounded p-1.5 bg-white font-medium"
                        >
                          <option value="">-- Select GL Account --</option>
                          {accounts.map((a) => (
                            <option key={a.id} value={a.id}>
                              {a.code} - {a.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <input
                        type="text"
                        placeholder="Line description (optional)"
                        value={line.description}
                        onChange={(e) => updateJournalLine(idx, "description", e.target.value)}
                        className="flex-1 text-xs border border-slate-200 rounded p-1.5"
                      />
                      <div className="w-28">
                        <input
                          type="number"
                          step="0.01"
                          placeholder="Debit (₹)"
                          value={line.debit || ""}
                          onChange={(e) => updateJournalLine(idx, "debit", e.target.value)}
                          className="w-full text-xs border border-slate-200 rounded p-1.5 text-right font-mono"
                        />
                      </div>
                      <div className="w-28">
                        <input
                          type="number"
                          step="0.01"
                          placeholder="Credit (₹)"
                          value={line.credit || ""}
                          onChange={(e) => updateJournalLine(idx, "credit", e.target.value)}
                          className="w-full text-xs border border-slate-200 rounded p-1.5 text-right font-mono"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => removeJournalLine(idx)}
                        disabled={newJournalForm.lines.length <= 2}
                        className="text-slate-400 hover:text-red-600 disabled:opacity-30 p-1"
                      >
                        &times;
                      </button>
                    </div>
                  ))}
                </div>

                {/* Balance footer */}
                <div className="flex justify-between items-center pt-2 font-mono text-xs font-bold border-t border-slate-200">
                  <span>Total Sums</span>
                  <div className="flex gap-6 pr-6">
                    <span className="text-blue-700">
                      Debit: &#8377;{journalBalance.totalDebit.toFixed(2)}
                    </span>
                    <span className="text-amber-700">
                      Credit: &#8377;{journalBalance.totalCredit.toFixed(2)}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t">
                <BtnSecondary type="button" onClick={() => setNewJournalModal(false)}>
                  Cancel
                </BtnSecondary>
                <BtnPrimary type="submit" disabled={!journalBalance.isBalanced}>
                  Commit & Post Voucher
                </BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: LOCK ACCOUNTING PERIOD ─────────────────────────────────────── */}
      {newLockModal && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Lock className="w-5 h-5 text-amber-600" /> Lock Accounting Period
            </h3>
            <form onSubmit={handleLockPeriod} className="space-y-3 text-xs">
              <Input
                label="Period From"
                type="date"
                value={newLockForm.period_from}
                onChange={(e) => setNewLockForm({ ...newLockForm, period_from: e.target.value })}
                required
              />
              <Input
                label="Period To"
                type="date"
                value={newLockForm.period_to}
                onChange={(e) => setNewLockForm({ ...newLockForm, period_to: e.target.value })}
                required
              />
              <Input
                label="Lock Reason"
                placeholder="e.g. Month-end statutory audit completed"
                value={newLockForm.lock_reason}
                onChange={(e) => setNewLockForm({ ...newLockForm, lock_reason: e.target.value })}
                required
              />
              <div className="flex justify-end gap-2 pt-4 border-t">
                <BtnSecondary type="button" onClick={() => setNewLockModal(false)}>
                  Cancel
                </BtnSecondary>
                <BtnPrimary type="submit">Enforce Period Lock</BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: UNLOCK ACCOUNTING PERIOD ───────────────────────────────────── */}
      {unlockModal && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Unlock className="w-5 h-5 text-amber-600" /> Reopen Accounting Period
            </h3>
            <p className="text-xs text-slate-600">
              Reopening period {unlockModal.period_from} &mdash; {unlockModal.period_to} will allow new postings. An immutable audit trail entry will be recorded.
            </p>
            <Input
              label="Unlock Justification / Audit Note"
              placeholder="e.g. Auditor adjustments for March tax return"
              value={unlockReason}
              onChange={(e) => setUnlockReason(e.target.value)}
              required
            />
            <div className="flex justify-end gap-2 pt-4 border-t">
              <BtnSecondary onClick={() => setUnlockModal(null)}>Cancel</BtnSecondary>
              <BtnPrimary onClick={handleUnlockPeriod}>Confirm Reopening</BtnPrimary>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
