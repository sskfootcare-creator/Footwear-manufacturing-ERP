import { useState, useEffect, useCallback, useMemo } from "react";
import { http, inr } from "../lib/api";
import {
  PageHeader,
  Card,
  StatTile,
  BtnPrimary,
  BtnSecondary,
  Badge,
} from "../components/ui-kit";
import {
  Landmark,
  Plus,
  RefreshCw,
  KeyRound,
  CheckCircle2,
  Clock,
  ArrowRightLeft,
  DollarSign,
  FileText,
  X,
  Loader2,
  AlertCircle,
  Search,
  Users,
  Check,
  TrendingUp,
  ReceiptIndianRupee,
  Layers,
  Sparkles,
  Eye,
  Info,
  Calendar,
  Building2,
  ChevronRight,
  ShieldCheck,
  CheckSquare,
  Square,
  CornerDownRight,
  ArrowRight,
  Printer,
  ArrowDownLeft,
  ArrowUpRight,
  Download,
} from "lucide-react";

export default function Investors() {
  const [activeTab, setActiveTab] = useState("advances"); // "advances" | "pending" | "investors" | "repayments"
  const [investors, setInvestors] = useState([]);
  const [advances, setAdvances] = useState([]);
  const [pendingInflows, setPendingInflows] = useState([]);
  const [repayments, setRepayments] = useState([]);
  const [posList, setPosList] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  // Multi-selection state for Bulk Settlement
  const [selectedAdvanceIds, setSelectedAdvanceIds] = useState([]);

  // Modals
  const [showAddInvestorModal, setShowAddInvestorModal] = useState(false);
  const [showCreateAdvanceModal, setShowCreateAdvanceModal] = useState(false);
  const [showPinModal, setShowPinModal] = useState(false);
  const [showRepayModal, setShowRepayModal] = useState(false);
  const [selectedAdvanceDetails, setSelectedAdvanceDetails] = useState(null);

  // Selected for modals
  const [selectedInvestorForPin, setSelectedInvestorForPin] = useState(null);
  const [pinValue, setPinValue] = useState("");

  // Create Advance Form state (Supports Multi-PO selection & Banking Inflow)
  const [selectedPoIds, setSelectedPoIds] = useState([]);
  const [poFilterQuery, setPoFilterQuery] = useState("");
  const [selectedInvestorId, setSelectedInvestorId] = useState("");
  const [selectedBankAccountId, setSelectedBankAccountId] = useState("");
  const [paymentMode, setPaymentMode] = useState("Bank Transfer");
  const [paymentReference, setPaymentReference] = useState("");
  const [includeOpex, setIncludeOpex] = useState(false);
  const [marginOverride, setMarginOverride] = useState("");
  const [advanceNotes, setAdvanceNotes] = useState("");
  const [submittingAdvance, setSubmittingAdvance] = useState(false);
  const [batchPreview, setBatchPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  // Repay / Reinvest Form state (Single or Bulk & Banking Outflow)
  const [advancesToSettle, setAdvancesToSettle] = useState([]);
  const [repayActionType, setRepayActionType] = useState("repay_in_full"); // "repay_in_full" | "reinvest"
  const [targetPoId, setTargetPoId] = useState("");
  const [repayMarginOverride, setRepayMarginOverride] = useState("");
  const [repayMode, setRepayMode] = useState("Bank Transfer");
  const [repayBankAccountId, setRepayBankAccountId] = useState("");
  const [submittingRepay, setSubmittingRepay] = useState(false);

  // New Investor Form state
  const [newInvestorName, setNewInvestorName] = useState("");
  const [newInvestorContact, setNewInvestorContact] = useState("");
  const [newInvestorPhone, setNewInvestorPhone] = useState("");
  const [newInvestorEmail, setNewInvestorEmail] = useState("");
  const [newInvestorMargin, setNewInvestorMargin] = useState("10.0");
  const [newInvestorPin, setNewInvestorPin] = useState("");
  const [submittingInvestor, setSubmittingInvestor] = useState(false);

  // Bank Statement Passbook State
  const [statementData, setStatementData] = useState(null);
  const [statementLoading, setStatementLoading] = useState(false);
  const [statementInvestorFilter, setStatementInvestorFilter] = useState("");
  const [statementCategoryFilter, setStatementCategoryFilter] = useState("all");
  const [statementSearchQuery, setStatementSearchQuery] = useState("");
  const [statementFromDate, setStatementFromDate] = useState("");
  const [statementToDate, setStatementToDate] = useState("");

  const loadBankStatement = useCallback(async () => {
    setStatementLoading(true);
    try {
      const params = {};
      if (statementInvestorFilter) params.investor_id = statementInvestorFilter;
      if (statementCategoryFilter && statementCategoryFilter !== "all") params.category = statementCategoryFilter;
      if (statementFromDate) params.from_date = statementFromDate;
      if (statementToDate) params.to_date = statementToDate;
      const res = await http.get("/investors/bank-statement", { params });
      setStatementData(res.data);
    } catch (err) {
      console.error("Failed to load bank statement", err);
    } finally {
      setStatementLoading(false);
    }
  }, [statementInvestorFilter, statementCategoryFilter, statementFromDate, statementToDate]);

  useEffect(() => {
    if (activeTab === "repayments") {
      loadBankStatement();
    }
  }, [activeTab, loadBankStatement]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [invRes, advRes, pendRes, repRes, poRes, bankRes] = await Promise.all([
        http.get("/investors"),
        http.get("/investors-advances/all"),
        http.get("/investors/advances/pending-client-payment"),
        http.get("/investors/repayments/all"),
        http.get("/pos?limit=150"),
        http.get("/banking/accounts", { params: { active: true } }).catch(() => ({ data: [] })),
      ]);
      setInvestors(invRes.data || []);
      setAdvances(advRes.data || []);
      setPendingInflows(pendRes.data || []);
      setRepayments(repRes.data || []);
      setPosList(poRes.data || []);
      const bAccounts = bankRes.data || [];
      setBankAccounts(bAccounts);
      if (bAccounts.length > 0) {
        setSelectedBankAccountId((prev) => prev || bAccounts[0]._id || bAccounts[0].id || "");
        setRepayBankAccountId((prev) => prev || bAccounts[0]._id || bAccounts[0].id || "");
      }
    } catch (err) {
      setError(err?.response?.data?.detail || "Failed to load investor data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Preview funding calculation when selecting POs or toggling OPEX
  useEffect(() => {
    if (selectedPoIds.length === 0) {
      setBatchPreview(null);
      return;
    }
    let isCancelled = false;
    const fetchPreview = async () => {
      setLoadingPreview(true);
      try {
        const res = await http.post("/investors-advances/preview-batch", {
          po_ids: selectedPoIds,
          include_opex: includeOpex,
        });
        if (!isCancelled) {
          setBatchPreview(res.data);
        }
      } catch (err) {
        if (!isCancelled) {
          setBatchPreview(null);
        }
      } finally {
        if (!isCancelled) {
          setLoadingPreview(false);
        }
      }
    };
    fetchPreview();
    return () => {
      isCancelled = true;
    };
  }, [selectedPoIds, includeOpex]);

  // Aggregate Stats
  const stats = useMemo(() => {
    const totalFunded = advances.reduce((sum, a) => sum + (a.amount || 0), 0);
    const activeAdvances = advances.filter((a) => a.status === "active");
    const activeBalance = activeAdvances.reduce((sum, a) => sum + (a.amount || 0), 0);
    const totalMargin = repayments.reduce((sum, r) => sum + (r.margin_amount || 0), 0);
    const totalRepaidPrincipal = repayments
      .filter((r) => !r.reinvested)
      .reduce((sum, r) => sum + (r.principal_amount || 0), 0);

    return {
      totalFunded,
      activeBalance,
      totalMargin,
      totalRepaidPrincipal,
      activeCount: activeAdvances.length,
      pendingCount: pendingInflows.length,
    };
  }, [advances, repayments, pendingInflows]);

  // Filtered advances
  const filteredAdvances = useMemo(() => {
    return advances.filter((adv) => {
      const q = searchQuery.toLowerCase();
      const matchSearch =
        !q ||
        (adv.po_number && adv.po_number.toLowerCase().includes(q)) ||
        (adv.investor_name && adv.investor_name.toLowerCase().includes(q)) ||
        (adv.batch_id && adv.batch_id.toLowerCase().includes(q));

      const matchStatus = statusFilter === "all" || adv.status === statusFilter;
      return matchSearch && matchStatus;
    });
  }, [advances, searchQuery, statusFilter]);

  // Active advances available for settlement
  const activeAdvancesList = useMemo(() => {
    return advances.filter((a) => a.status === "active");
  }, [advances]);

  // Selected advances for bulk actions
  const selectedAdvancesObjects = useMemo(() => {
    return advances.filter((a) => selectedAdvanceIds.includes(a._id || a.id));
  }, [advances, selectedAdvanceIds]);

  const bulkStats = useMemo(() => {
    const count = selectedAdvancesObjects.length;
    const principal = selectedAdvancesObjects.reduce((s, a) => s + (a.amount || 0), 0);
    const margin = selectedAdvancesObjects.reduce(
      (s, a) => s + (a.pairs || 0) * (a.margin_per_pair || 10.0),
      0
    );
    const totalPayout = principal + margin;
    return { count, principal, margin, totalPayout };
  }, [selectedAdvancesObjects]);

  // Selection handlers
  const toggleSelectAdvance = (id) => {
    setSelectedAdvanceIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const toggleSelectAllActive = () => {
    const activeIds = activeAdvancesList.map((a) => a._id || a.id);
    const allSelected = activeIds.length > 0 && activeIds.every((id) => selectedAdvanceIds.includes(id));
    if (allSelected) {
      setSelectedAdvanceIds([]);
    } else {
      setSelectedAdvanceIds(activeIds);
    }
  };

  // Filtered statement transactions for live client search
  const filteredStatementTransactions = useMemo(() => {
    if (!statementData || !statementData.transactions) return [];
    if (!statementSearchQuery.trim()) return statementData.transactions;
    const q = statementSearchQuery.toLowerCase();
    return statementData.transactions.filter((t) =>
      (t.narration && t.narration.toLowerCase().includes(q)) ||
      (t.voucher_no && t.voucher_no.toLowerCase().includes(q)) ||
      (t.po_number && t.po_number.toLowerCase().includes(q)) ||
      (t.investor_name && t.investor_name.toLowerCase().includes(q)) ||
      (t.channel && t.channel.toLowerCase().includes(q)) ||
      (t.status && t.status.toLowerCase().includes(q))
    );
  }, [statementData, statementSearchQuery]);

  // Open Settle modal for single advance
  const openSingleSettleModal = (adv) => {
    setAdvancesToSettle([adv]);
    setRepayActionType("repay_in_full");
    setTargetPoId("");
    setRepayMarginOverride(String(adv.margin_per_pair || 10.0));
    setShowRepayModal(true);
  };

  // Open Settle modal for bulk selection
  const openBulkSettleModal = (action = "repay_in_full") => {
    if (selectedAdvancesObjects.length === 0) return;
    setAdvancesToSettle(selectedAdvancesObjects);
    setRepayActionType(action);
    setTargetPoId("");
    setRepayMarginOverride("");
    setShowRepayModal(true);
  };

  // Filtered investors
  const filteredInvestors = useMemo(() => {
    if (!searchQuery) return investors;
    const q = searchQuery.toLowerCase();
    return investors.filter(
      (inv) =>
        (inv.name && inv.name.toLowerCase().includes(q)) ||
        (inv.contact && inv.contact.toLowerCase().includes(q)) ||
        (inv.phone && inv.phone.toLowerCase().includes(q)) ||
        (inv.email && inv.email.toLowerCase().includes(q))
    );
  }, [investors, searchQuery]);

  // Handle Create Investor
  const handleCreateInvestor = async (e) => {
    e.preventDefault();
    setSubmittingInvestor(true);
    try {
      await http.post("/investors", {
        name: newInvestorName.trim(),
        contact: newInvestorContact.trim(),
        phone: newInvestorPhone.trim(),
        email: newInvestorEmail.trim(),
        default_margin_per_pair: parseFloat(newInvestorMargin) || 10.0,
        pin: newInvestorPin ? newInvestorPin.trim() : undefined,
        active: true,
      });
      setShowAddInvestorModal(false);
      setNewInvestorName("");
      setNewInvestorContact("");
      setNewInvestorPhone("");
      setNewInvestorEmail("");
      setNewInvestorMargin("10.0");
      setNewInvestorPin("");
      loadData();
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to create investor");
    } finally {
      setSubmittingInvestor(false);
    }
  };

  // Handle Set PIN
  const handleSetPin = async (e) => {
    e.preventDefault();
    if (!selectedInvestorForPin) return;
    try {
      await http.post(`/investors/${selectedInvestorForPin._id}/pin`, {
        pin: pinValue.trim(),
      });
      setShowPinModal(false);
      setSelectedInvestorForPin(null);
      setPinValue("");
      loadData();
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to set PIN");
    }
  };

  // Handle Create Advance (Supports Multiple POs funded at once & Banking Inflow)
  const handleCreateAdvance = async (e) => {
    e.preventDefault();
    if (!selectedInvestorId || selectedPoIds.length === 0) return;
    setSubmittingAdvance(true);
    try {
      const payload = {
        include_opex: includeOpex,
        margin_per_pair: marginOverride ? parseFloat(marginOverride) : undefined,
        bank_account_id: selectedBankAccountId || undefined,
        payment_mode: paymentMode || "Bank Transfer",
        reference: paymentReference || "",
        notes: advanceNotes,
      };

      if (selectedPoIds.length === 1) {
        await http.post(`/investors/${selectedInvestorId}/advances`, {
          po_id: selectedPoIds[0],
          ...payload,
        });
      } else {
        await http.post(`/investors/${selectedInvestorId}/advances/batch`, {
          po_ids: selectedPoIds,
          ...payload,
        });
      }
      setShowCreateAdvanceModal(false);
      setSelectedPoIds([]);
      setSelectedInvestorId("");
      setPaymentReference("");
      setIncludeOpex(false);
      setMarginOverride("");
      setAdvanceNotes("");
      loadData();
    } catch (err) {
      const rawDetail = err?.response?.data?.detail;
      const errorMsg = Array.isArray(rawDetail)
        ? rawDetail.map((d) => d.msg || JSON.stringify(d)).join(", ")
        : typeof rawDetail === "string"
        ? rawDetail
        : err?.message || "Failed to create advance(s)";
      alert(errorMsg);
    } finally {
      setSubmittingAdvance(false);
    }
  };

  // Handle Repay / Reinvest Action (Supports Single and Multiple POs paid at once & Banking Outflow)
  const handleExecuteRepay = async (e) => {
    e.preventDefault();
    if (advancesToSettle.length === 0) return;
    setSubmittingRepay(true);
    try {
      const advIds = advancesToSettle.map((a) => a._id);
      await http.post("/investors/advances/bulk-repay", {
        advance_ids: advIds,
        action: repayActionType,
        target_po_id: repayActionType === "reinvest" ? targetPoId : undefined,
        margin_per_pair_override: repayMarginOverride ? parseFloat(repayMarginOverride) : undefined,
        mode: repayMode,
        bank_account_id: repayMode !== "Cash" ? (repayBankAccountId || undefined) : undefined,
      });

      setShowRepayModal(false);
      setAdvancesToSettle([]);
      setSelectedAdvanceIds((prev) => prev.filter((id) => !advIds.includes(id)));
      setTargetPoId("");
      setRepayMarginOverride("");
      loadData();
    } catch (err) {
      const rawDetail = err?.response?.data?.detail;
      const errorMsg = Array.isArray(rawDetail)
        ? rawDetail.map((d) => d.msg || JSON.stringify(d)).join(", ")
        : typeof rawDetail === "string"
        ? rawDetail
        : err?.message || "Failed to execute settlement";
      alert(errorMsg);
    } finally {
      setSubmittingRepay(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case "repaid":
        return <Badge color="green">REPAID</Badge>;
      case "reinvested":
        return <Badge color="blue">REINVESTED</Badge>;
      case "active":
        return <Badge color="yellow">ACTIVE</Badge>;
      default:
        return <Badge color="slate">{String(status).toUpperCase()}</Badge>;
    }
  };

  return (
    <div>
      {/* ── ERP SIGNATURE PAGE HEADER ────────────────────────────────────────── */}
      <PageHeader
        title="Investors & PO Funding"
        subtitle="Accounts / Commercial & Capital Lifecycle"
        testId="investors-page-header"
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={loadData}
              disabled={loading}
              className="p-2 border-2 border-slate-300 bg-white hover:border-[#0F172A] text-slate-700 transition"
              title="Refresh Data"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            <BtnSecondary onClick={() => setShowAddInvestorModal(true)}>
              <Users className="w-3.5 h-3.5 inline mr-1.5" />
              New Investor
            </BtnSecondary>
            <BtnPrimary onClick={() => setShowCreateAdvanceModal(true)}>
              <Plus className="w-3.5 h-3.5 inline mr-1.5" />
              Fund Purchase Orders
            </BtnPrimary>
          </div>
        }
      />

      <div className="p-2 sm:p-4 lg:p-8 space-y-5">
        {error && (
          <div className="p-4 bg-red-50 border-2 border-red-300 text-red-800 text-xs font-bold uppercase tracking-wider flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* ── ERP INDUSTRIAL STAT TILES ────────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatTile
            label="Total Capital Funded"
            value={inr(stats.totalFunded)}
            sub={`${advances.length} funding cycle(s)`}
            accent="#0F172A"
          />
          <StatTile
            label="Active Capital Out"
            value={inr(stats.activeBalance)}
            sub={`${stats.activeCount} active manufacturing cycle(s)`}
            accent="#C27842"
          />
          <StatTile
            label="Margin Yield Disbursed"
            value={inr(stats.totalMargin)}
            sub="Settled partner finance yield"
            accent="#16A34A"
          />
          <StatTile
            label="Pending Action Inflows"
            value={stats.pendingCount}
            sub={stats.pendingCount > 0 ? "Client receipts ready to settle" : "All cycles current"}
            accent="#2563EB"
          />
        </div>

        {/* ── ENTERPRISE NAVIGATION TABS ───────────────────────────────────────── */}
        <div className="flex border-b-2 border-slate-200 overflow-x-auto no-scrollbar gap-1 bg-white px-2 pt-2 shadow-sm">
          <button
            onClick={() => setActiveTab("advances")}
            className={`px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-4 -mb-0.5 transition-colors flex items-center gap-2 whitespace-nowrap ${
              activeTab === "advances"
                ? "border-[#C27842] text-slate-900 bg-slate-50"
                : "border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300"
            }`}
          >
            <FileText className={`w-4 h-4 ${activeTab === "advances" ? "text-[#C27842]" : "text-slate-400"}`} />
            <span>PO Advances</span>
            <span className="px-1.5 py-0.2 rounded font-mono text-[10px] bg-slate-200 text-slate-700">
              {advances.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("pending")}
            className={`px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-4 -mb-0.5 transition-colors flex items-center gap-2 whitespace-nowrap ${
              activeTab === "pending"
                ? "border-[#C27842] text-slate-900 bg-slate-50"
                : "border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300"
            }`}
          >
            <Clock className={`w-4 h-4 ${activeTab === "pending" ? "text-[#C27842]" : "text-slate-400"}`} />
            <span>Client Inflows Pending Action</span>
            {pendingInflows.length > 0 ? (
              <span className="px-1.5 py-0.2 rounded font-mono text-[10px] bg-amber-500 text-white font-black animate-pulse">
                {pendingInflows.length}
              </span>
            ) : (
              <span className="px-1.5 py-0.2 rounded font-mono text-[10px] bg-slate-200 text-slate-700">
                0
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab("investors")}
            className={`px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-4 -mb-0.5 transition-colors flex items-center gap-2 whitespace-nowrap ${
              activeTab === "investors"
                ? "border-[#C27842] text-slate-900 bg-slate-50"
                : "border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300"
            }`}
          >
            <Users className={`w-4 h-4 ${activeTab === "investors" ? "text-[#C27842]" : "text-slate-400"}`} />
            <span>Investors Directory</span>
            <span className="px-1.5 py-0.2 rounded font-mono text-[10px] bg-slate-200 text-slate-700">
              {investors.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("repayments")}
            className={`px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-4 -mb-0.5 transition-colors flex items-center gap-2 whitespace-nowrap ${
              activeTab === "repayments"
                ? "border-[#C27842] text-slate-900 bg-slate-50"
                : "border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300"
            }`}
          >
            <Landmark className={`w-4 h-4 ${activeTab === "repayments" ? "text-[#C27842]" : "text-slate-400"}`} />
            <span>Investor Ledger</span>
            <span className="px-1.5 py-0.2 rounded font-mono text-[10px] bg-slate-200 text-slate-700">
              {repayments.length}
            </span>
          </button>
        </div>

        {/* ── TAB CONTENT ──────────────────────────────────────────────────────── */}

        {/* TAB 1: PO ADVANCES */}
        {activeTab === "advances" && (
          <div className="space-y-4">
            {/* Search & Filter Toolbar */}
            <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
              <div className="relative w-full sm:w-80">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search PO, investor, or batch ID..."
                  className="w-full pl-9 pr-3 py-2 border-2 border-slate-300 bg-white text-xs font-mono focus:border-[#C27842] focus:outline-none"
                />
              </div>

              <div className="flex items-center gap-2 w-full sm:w-auto">
                <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Status:</span>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="border-2 border-slate-300 bg-white px-3 py-1.5 text-xs font-bold uppercase tracking-wider focus:border-[#C27842] focus:outline-none"
                >
                  <option value="all">ALL STATUSES ({advances.length})</option>
                  <option value="active">ACTIVE ({advances.filter((a) => a.status === "active").length})</option>
                  <option value="repaid">REPAID ({advances.filter((a) => a.status === "repaid").length})</option>
                  <option value="reinvested">REINVESTED ({advances.filter((a) => a.status === "reinvested").length})</option>
                </select>
              </div>
            </div>

            {/* ── FLOATING/PINNED BULK ACTION BAR WHEN MULTIPLE ADVANCES ARE CHECKED ── */}
            {selectedAdvanceIds.length > 0 && (
              <div className="bg-[#0F172A] text-white p-3 border-2 border-[#0F172A] shadow-ind-lg flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-in fade-in slide-in-from-top duration-200">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded bg-emerald-500 text-slate-900 grid place-items-center font-black text-sm">
                    {bulkStats.count}
                  </div>
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wider text-slate-200">
                      {bulkStats.count} Advance{bulkStats.count > 1 ? "s" : ""} Selected for Batch Settlement
                    </div>
                    <div className="text-[11px] font-mono text-slate-300 flex items-center gap-3 mt-0.5">
                      <span>Principal: <strong>{inr(bulkStats.principal)}</strong></span>
                      <span>·</span>
                      <span className="text-emerald-400">Margin: <strong>{inr(bulkStats.margin)}</strong></span>
                      <span>·</span>
                      <span className="text-amber-300">Total Payout: <strong>{inr(bulkStats.totalPayout)}</strong></span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => openBulkSettleModal("repay_in_full")}
                    className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold uppercase tracking-wider text-xs px-3.5 py-1.5 border border-emerald-400 shadow-sm transition flex items-center gap-1.5"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Batch Repay in Full ({inr(bulkStats.totalPayout)})
                  </button>

                  <button
                    onClick={() => openBulkSettleModal("reinvest")}
                    className="bg-blue-600 hover:bg-blue-500 text-white font-bold uppercase tracking-wider text-xs px-3.5 py-1.5 border border-blue-400 shadow-sm transition flex items-center gap-1.5"
                  >
                    <ArrowRightLeft className="w-3.5 h-3.5" />
                    Batch Reinvest
                  </button>

                  <button
                    onClick={() => setSelectedAdvanceIds([])}
                    className="text-xs text-slate-400 hover:text-white underline px-2 py-1"
                  >
                    Clear Selection
                  </button>
                </div>
              </div>
            )}

            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-slate-100 border-b-2 border-slate-200 text-slate-700 text-[10px] font-bold uppercase tracking-wider">
                    <tr>
                      <th className="py-3 px-3 text-center w-10">
                        <input
                          type="checkbox"
                          checked={
                            activeAdvancesList.length > 0 &&
                            activeAdvancesList.every((a) => selectedAdvanceIds.includes(a._id || a.id))
                          }
                          onChange={toggleSelectAllActive}
                          disabled={activeAdvancesList.length === 0}
                          className="w-4 h-4 border-2 border-slate-400 rounded text-[#0F172A] focus:ring-0 cursor-pointer"
                          title="Select all active advances"
                        />
                      </th>
                      <th className="py-3 px-3 font-bold">Advance Date</th>
                      <th className="py-3 px-4 font-bold">PO Reference</th>
                      <th className="py-3 px-4 font-bold">Investor Partner</th>
                      <th className="py-3 px-4 font-bold text-right">Pairs</th>
                      <th className="py-3 px-4 font-bold text-right">Funded Capital</th>
                      <th className="py-3 px-4 font-bold text-right">Margin / Pair</th>
                      <th className="py-3 px-4 font-bold text-right">Projected Yield</th>
                      <th className="py-3 px-4 font-bold text-center">Status</th>
                      <th className="py-3 px-4 font-bold text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {loading ? (
                      <tr>
                        <td colSpan={10} className="py-16 text-center text-slate-500">
                          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-[#0F172A]" />
                          <span className="font-bold uppercase tracking-wider text-[11px]">Loading Advances...</span>
                        </td>
                      </tr>
                    ) : filteredAdvances.length === 0 ? (
                      <tr>
                        <td colSpan={10} className="py-16 text-center">
                          <div className="max-w-sm mx-auto space-y-3">
                            <div className="w-12 h-12 rounded-full bg-slate-100 border-2 border-slate-300 text-slate-400 grid place-items-center mx-auto">
                              <FileText className="w-6 h-6" />
                            </div>
                            <div>
                              <div className="font-bold text-slate-800 text-sm uppercase tracking-wider">
                                No PO Advances Found
                              </div>
                              <p className="text-xs text-slate-500 mt-1">
                                {searchQuery || statusFilter !== "all"
                                  ? "No records match the current search or status filter."
                                  : "Commit an advance against one or multiple purchase orders to initiate capital tracking and repayment monitoring."}
                              </p>
                            </div>
                            {!searchQuery && statusFilter === "all" && (
                              <button
                                onClick={() => setShowCreateAdvanceModal(true)}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold uppercase tracking-wider bg-[#0F172A] text-white border-2 border-[#0F172A] shadow-ind hover:bg-slate-800 transition"
                              >
                                <Plus className="w-3.5 h-3.5" /> Fund Purchase Orders
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ) : (
                      filteredAdvances.map((adv) => {
                        const advId = adv._id || adv.id;
                        const isSelected = selectedAdvanceIds.includes(advId);
                        const isActive = adv.status === "active";
                        return (
                          <tr
                            key={advId}
                            className={`hover:bg-slate-50/80 transition-colors ${
                              isSelected ? "bg-amber-50/60" : ""
                            }`}
                          >
                            <td className="py-3 px-3 text-center">
                              {isActive ? (
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={() => toggleSelectAdvance(advId)}
                                  className="w-4 h-4 border-2 border-slate-400 rounded text-[#0F172A] focus:ring-0 cursor-pointer"
                                />
                              ) : (
                                <span className="text-slate-300">—</span>
                              )}
                            </td>
                            <td className="py-3 px-3 font-mono text-slate-700">{adv.advance_date}</td>
                            <td className="py-3 px-4 font-bold text-slate-900">
                              <div className="flex items-center gap-1.5">
                                <span>{adv.po_number || "PO"}</span>
                                {adv.batch_id && (
                                  <span
                                    className="text-[9px] bg-slate-200 text-slate-700 px-1 py-0.5 rounded font-mono font-bold"
                                    title={`Batch: ${adv.batch_id}`}
                                  >
                                    BATCH
                                  </span>
                                )}
                                {adv.breakdown?.opex_included && (
                                  <span
                                    className="text-[9px] bg-blue-100 text-blue-800 px-1 py-0.5 rounded font-mono font-bold"
                                    title="Includes investor recurring opex"
                                  >
                                    +OPEX
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="py-3 px-4 font-medium text-slate-800">
                              <div className="font-bold text-slate-900">{adv.investor_name}</div>
                              {adv.bank_name && (
                                <div className="text-[10px] text-slate-500 font-mono flex items-center gap-1 mt-0.5" title={`Received into: ${adv.bank_name}`}>
                                  <Landmark className="w-2.5 h-2.5 text-slate-400 shrink-0" />
                                  <span className="truncate max-w-[150px]">{adv.bank_name}</span>
                                  {adv.reference && <span className="text-slate-400">· {adv.reference}</span>}
                                </div>
                              )}
                            </td>
                            <td className="py-3 px-4 text-right font-mono font-medium text-slate-700">
                              {adv.pairs?.toLocaleString("en-IN") || 0}
                            </td>
                            <td className="py-3 px-4 text-right font-mono font-bold text-slate-900">
                              {inr(adv.amount)}
                            </td>
                            <td className="py-3 px-4 text-right font-mono font-bold text-emerald-700">
                              ₹{adv.margin_per_pair || 10.0}
                            </td>
                            <td className="py-3 px-4 text-right font-mono font-semibold text-slate-700">
                              {inr((adv.pairs || 0) * (adv.margin_per_pair || 10.0))}
                            </td>
                            <td className="py-3 px-4 text-center">{getStatusBadge(adv.status)}</td>
                            <td className="py-3 px-4 text-right">
                              <div className="flex items-center justify-end gap-1.5">
                                <button
                                  onClick={() => setSelectedAdvanceDetails(adv)}
                                  className="p-1 text-slate-500 hover:text-slate-900 border border-slate-300 hover:border-slate-800 bg-white transition"
                                  title="View Details"
                                >
                                  <Eye className="w-3.5 h-3.5" />
                                </button>
                                {isActive ? (
                                  <button
                                    onClick={() => openSingleSettleModal(adv)}
                                    className="bg-[#0F172A] text-white font-bold uppercase tracking-wider text-[10px] px-2.5 py-1 border border-[#0F172A] hover:bg-slate-800 transition"
                                  >
                                    Settle
                                  </button>
                                ) : (
                                  <span className="text-[10px] font-bold text-slate-400 uppercase">Settled</span>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}

        {/* TAB 2: PENDING CLIENT INFLOWS & STAGE 4 ACTIONS */}
        {activeTab === "pending" && (
          <div className="space-y-4">
            <div className="p-4 bg-amber-50 border-2 border-amber-300 text-amber-900 text-xs">
              <div className="font-bold uppercase tracking-wider flex items-center gap-1.5 mb-1 text-amber-950">
                <Clock className="w-4 h-4 text-amber-700" />
                Stage 4 Trigger — Client Inflow Settlement Queue
              </div>
              <p className="text-slate-700 leading-relaxed">
                When client payments land against invoices tied to funded POs, management executes either
                <strong> "Repay in Full"</strong> (cash payout) or <strong>"Pay Margin & Reinvest"</strong> (cash margin + non-cash rollover into next PO).
                Settlements are deliberate management decisions and never automated. Multiple PO advances can be settled simultaneously.
              </p>
            </div>

            {pendingInflows.length === 0 ? (
              <Card className="p-16 text-center text-slate-500">
                <CheckCircle2 className="w-10 h-10 text-emerald-600 mx-auto mb-3" />
                <div className="font-bold uppercase tracking-wider text-sm text-slate-800">
                  Settlement Queue Clear
                </div>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  No active advances currently have unprompted client payment receipts. When incoming client payments are recorded on funded POs, they appear here.
                </p>
              </Card>
            ) : (
              <div className="space-y-4">
                {pendingInflows.map((item, idx) => {
                  const adv = item.advance;
                  return (
                    <Card key={idx} className="p-5 border-l-4 border-l-[#C27842] space-y-4">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b-2 border-slate-100 pb-3">
                        <div>
                          <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">
                            Active Cycle Reference
                          </div>
                          <div className="text-lg font-black text-slate-900 mt-0.5">
                            {adv.po_number || "PO"} • {adv.investor_name}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge color="green">
                            Client Inflow: {inr(item.total_client_payments_received)}
                          </Badge>
                          <Badge color="yellow">ACTIVE ADVANCE</Badge>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div className="p-3 bg-slate-50 border border-slate-200">
                          <div className="text-[10px] uppercase font-bold text-slate-500">Principal Funded</div>
                          <div className="font-mono text-base font-bold text-slate-900 mt-1">
                            {inr(item.calculated_principal)}
                          </div>
                        </div>

                        <div className="p-3 bg-slate-50 border border-slate-200">
                          <div className="text-[10px] uppercase font-bold text-slate-500">
                            Margin (@₹{adv.margin_per_pair}/pr)
                          </div>
                          <div className="font-mono text-base font-bold text-emerald-700 mt-1">
                            {inr(item.calculated_margin)}
                          </div>
                        </div>

                        <div className="p-3 bg-slate-50 border border-slate-200">
                          <div className="text-[10px] uppercase font-bold text-slate-500">Total Settlement Out</div>
                          <div className="font-mono text-base font-bold text-slate-900 mt-1">
                            {inr(item.calculated_total_payout)}
                          </div>
                        </div>

                        <div className="p-3 bg-slate-50 border border-slate-200">
                          <div className="text-[10px] uppercase font-bold text-slate-500">Invoiced Status</div>
                          <div className="font-bold text-slate-800 text-sm mt-1">
                            {item.invoices_count} Invoice(s) on File
                          </div>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
                        <button
                          onClick={() => {
                            setAdvancesToSettle([adv]);
                            setRepayActionType("repay_in_full");
                            setShowRepayModal(true);
                          }}
                          className="bg-[#0F172A] hover:bg-slate-800 text-white font-bold uppercase tracking-wider text-xs px-4 py-2 border-2 border-[#0F172A] shadow-ind hover:shadow-ind-lg transition-all"
                        >
                          Action 1: Repay In Full ({inr(item.calculated_total_payout)})
                        </button>

                        <button
                          onClick={() => {
                            setAdvancesToSettle([adv]);
                            setRepayActionType("reinvest");
                            setShowRepayModal(true);
                          }}
                          className="bg-white hover:border-[#0F172A] text-slate-900 font-bold uppercase tracking-wider text-xs px-4 py-2 border-2 border-slate-300 transition-all"
                        >
                          Action 2: Pay Margin ({inr(item.calculated_margin)}) & Reinvest Principal
                        </button>
                      </div>
                    </Card>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: INVESTORS DIRECTORY */}
        {activeTab === "investors" && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-600">
                Registered Capital Partners ({investors.length})
              </div>
              <BtnPrimary onClick={() => setShowAddInvestorModal(true)}>
                <Plus className="w-3.5 h-3.5 inline mr-1.5" />
                Add Investor
              </BtnPrimary>
            </div>

            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-slate-100 border-b-2 border-slate-200 text-slate-700 text-[10px] font-bold uppercase tracking-wider">
                    <tr>
                      <th className="py-3 px-4 font-bold">Investor Name</th>
                      <th className="py-3 px-4 font-bold">Contact Person</th>
                      <th className="py-3 px-4 font-bold">Phone (Portal ID)</th>
                      <th className="py-3 px-4 font-bold">Email</th>
                      <th className="py-3 px-4 font-bold text-right">Default Margin / Pair</th>
                      <th className="py-3 px-4 font-bold text-center">Active Cycles</th>
                      <th className="py-3 px-4 font-bold text-center">Status</th>
                      <th className="py-3 px-4 font-bold text-right">Action / Security</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {filteredInvestors.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="py-16 text-center">
                          <div className="max-w-sm mx-auto space-y-3">
                            <div className="w-12 h-12 rounded-full bg-slate-100 border-2 border-slate-300 text-slate-400 grid place-items-center mx-auto">
                              <Users className="w-6 h-6" />
                            </div>
                            <div className="font-bold text-slate-800 text-sm uppercase tracking-wider">
                              No Investors Found
                            </div>
                            <p className="text-xs text-slate-500">
                              Register an investor profile to start tracking manufacturing advances and self-service portal access.
                            </p>
                            <button
                              onClick={() => setShowAddInvestorModal(true)}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold uppercase tracking-wider bg-[#0F172A] text-white border-2 border-[#0F172A] shadow-ind"
                            >
                              <Plus className="w-3.5 h-3.5" /> Add First Investor
                            </button>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      filteredInvestors.map((inv) => {
                        const invAdvances = advances.filter((a) => a.investor_id === inv._id && a.status === "active");
                        return (
                          <tr key={inv._id} className="hover:bg-slate-50/80 transition-colors">
                            <td className="py-3 px-4 font-bold text-slate-900">{inv.name}</td>
                            <td className="py-3 px-4 text-slate-600">{inv.contact || "—"}</td>
                            <td className="py-3 px-4 font-mono font-medium text-slate-700">{inv.phone || "—"}</td>
                            <td className="py-3 px-4 text-slate-600">{inv.email || "—"}</td>
                            <td className="py-3 px-4 text-right font-mono font-bold text-emerald-700">
                              ₹{inv.default_margin_per_pair || 10.0}
                            </td>
                            <td className="py-3 px-4 text-center font-mono font-bold text-slate-800">
                              {invAdvances.length}
                            </td>
                            <td className="py-3 px-4 text-center">
                              <Badge color="green">ACTIVE</Badge>
                            </td>
                            <td className="py-3 px-4 text-right">
                              <button
                                onClick={() => {
                                  setSelectedInvestorForPin(inv);
                                  setShowPinModal(true);
                                }}
                                className="bg-white text-slate-900 font-bold uppercase tracking-wider text-[10px] px-2.5 py-1.5 border-2 border-slate-300 hover:border-[#0F172A] transition inline-flex items-center gap-1"
                              >
                                <KeyRound className="w-3 h-3" />
                                Set PIN
                              </button>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}

        {/* TAB 4: INVESTOR LEDGER & STATEMENT OF ACCOUNT */}
        {activeTab === "repayments" && (
          <div id="investor-ledger-print-area" className="space-y-4">
            <style>{`
              @media print {
                body * { visibility: hidden !important; }
                #investor-ledger-print-area, #investor-ledger-print-area * { visibility: visible !important; }
                #investor-ledger-print-area {
                  position: absolute !important;
                  left: 0 !important;
                  top: 0 !important;
                  width: 100% !important;
                  background: #fff !important;
                  color: #000 !important;
                  padding: 10px !important;
                }
                .no-print { display: none !important; }
              }
            `}</style>

            {/* Institutional Statement Banner */}
            <div className="bg-slate-900 text-white p-5 border-2 border-slate-900 shadow-ind flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 bg-[#C27842] flex items-center justify-center text-white border-2 border-white shadow-sm flex-shrink-0">
                  <Landmark className="w-6 h-6" />
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-[0.25em] font-mono text-[#C27842] font-black">
                    SSK Footcare Industrial · Investor Commercial Accounts
                  </div>
                  <div className="text-lg font-black tracking-tight text-white flex items-center gap-2">
                    Investor Ledger & Statement of Account
                    <span className="text-[9px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-2 py-0.5 rounded font-mono uppercase tracking-wider">
                      Verified Double-Entry Ledger
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5 font-mono">
                    Statutory General Ledger: GL 2020-INV (Investor Advances Payable) & GL 5030-INV (Investor Margin Yield)
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 self-end md:self-auto no-print">
                <button
                  type="button"
                  onClick={() => window.print()}
                  className="inline-flex items-center gap-2 px-3.5 py-2 bg-white text-slate-900 text-xs font-bold uppercase tracking-wider border-2 border-slate-900 shadow-ind hover:bg-slate-100 transition active:translate-x-0.5 active:translate-y-0.5 cursor-pointer"
                >
                  <Printer className="w-4 h-4 text-slate-700" />
                  Print / Export Investor Ledger
                </button>
                <button
                  type="button"
                  onClick={loadBankStatement}
                  disabled={statementLoading}
                  className="p-2 bg-slate-800 text-white border-2 border-slate-700 hover:bg-slate-700 transition cursor-pointer"
                  title="Reload Ledger"
                >
                  <RefreshCw className={`w-4 h-4 ${statementLoading ? "animate-spin text-[#C27842]" : ""}`} />
                </button>
              </div>
            </div>

            {/* Account Details & Summary Strip */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              {/* Account Profile Card */}
              <div className="lg:col-span-4 bg-white border-2 border-slate-900 p-4 shadow-ind flex flex-col justify-between">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.2em] font-mono text-slate-500 font-bold mb-1">
                    Investor Account Profile
                  </div>
                  <div className="text-base font-black text-slate-900">
                    {statementData?.account_holder || (statementInvestorFilter ? investors.find((i) => i._id === statementInvestorFilter)?.name : "Consolidated Partner Syndicate")}
                  </div>
                  {statementData?.investor_info && (
                    <div className="mt-2 text-xs text-slate-600 font-mono space-y-0.5 border-t border-slate-200 pt-2">
                      <div>Contact: {statementData.investor_info.contact || "—"}</div>
                      <div>Phone: {statementData.investor_info.phone || "—"}</div>
                      <div>Email: {statementData.investor_info.email || "—"}</div>
                    </div>
                  )}
                </div>

                <div className="mt-3 pt-2 border-t border-slate-200 text-[11px] font-mono text-slate-500 space-y-1">
                  <div className="flex justify-between">
                    <span>Currency:</span>
                    <span className="font-bold text-slate-800">INR (₹)</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Ledger Date:</span>
                    <span className="font-bold text-slate-800">{statementData?.statement_date || "Live"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Audited Entries:</span>
                    <span className="font-bold text-slate-800">{statementData?.transactions_count || filteredStatementTransactions.length} items</span>
                  </div>
                </div>
              </div>

              {/* Summary Figures */}
              <div className="lg:col-span-8 grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-white border-2 border-slate-900 p-3 shadow-ind">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Total Capital Invested</div>
                  <div className="font-mono text-base font-black text-slate-900 mt-1">
                    {inr(statementData?.total_credit_inflow ?? advances.reduce((s, a) => s + (a.amount || 0), 0))}
                  </div>
                  <div className="text-[10px] font-mono text-blue-700 mt-1 flex items-center gap-1 font-bold">
                    <ArrowDownLeft className="w-3 h-3" /> Credit (GL 2020)
                  </div>
                </div>

                <div className="bg-white border-2 border-slate-900 p-3 shadow-ind">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Principal Repaid</div>
                  <div className="font-mono text-base font-black text-slate-900 mt-1">
                    {inr(statementData?.total_principal_repaid ?? repayments.reduce((s, r) => s + (r.principal_amount || 0), 0))}
                  </div>
                  <div className="text-[10px] font-mono text-rose-700 mt-1 flex items-center gap-1 font-bold">
                    <ArrowUpRight className="w-3 h-3" /> Debit (GL 2020)
                  </div>
                </div>

                <div className="bg-white border-2 border-slate-900 p-3 shadow-ind">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Margin Yields Disbursed</div>
                  <div className="font-mono text-base font-black text-emerald-700 mt-1">
                    {inr(statementData?.total_margin_paid ?? repayments.reduce((s, r) => s + (r.margin_amount || 0), 0))}
                  </div>
                  <div className="text-[10px] font-mono text-emerald-800 mt-1 flex items-center gap-1 font-bold">
                    <CheckCircle2 className="w-3 h-3" /> Margin (GL 5030)
                  </div>
                </div>

                <div className="bg-[#0F172A] text-white border-2 border-[#0F172A] p-3 shadow-ind">
                  <div className="text-[10px] uppercase tracking-wider text-slate-300 font-bold">Net Outstanding Balance</div>
                  <div className="font-mono text-base font-black text-amber-400 mt-1">
                    {inr(statementData?.closing_balance ?? stats.activeBalance)}
                  </div>
                  <div className="text-[10px] font-mono text-slate-300 mt-1 font-bold">
                    Active Capital Owed
                  </div>
                </div>
              </div>
            </div>

            {/* Filter & Toolbar (Hidden when printing) */}
            <div className="no-print bg-slate-50 border-2 border-slate-300 p-3 flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <div>
                  <select
                    value={statementInvestorFilter}
                    onChange={(e) => setStatementInvestorFilter(e.target.value)}
                    className="border-2 border-slate-300 bg-white px-2.5 py-1.5 font-bold text-slate-800 focus:outline-none focus:border-[#C27842]"
                  >
                    <option value="">-- All Investors (Consolidated Ledger) --</option>
                    {investors.map((inv) => (
                      <option key={inv._id} value={inv._id}>
                        {inv.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <select
                    value={statementCategoryFilter}
                    onChange={(e) => setStatementCategoryFilter(e.target.value)}
                    className="border-2 border-slate-300 bg-white px-2.5 py-1.5 font-bold text-slate-800 focus:outline-none focus:border-[#C27842]"
                  >
                    <option value="all">All Ledger Entries</option>
                    <option value="repayments">Principal Repayments Only</option>
                    <option value="reinvestments">Reinvestments Only</option>
                    <option value="advances">Capital Advances Only</option>
                  </select>
                </div>

                <div className="flex items-center gap-1">
                  <input
                    type="date"
                    value={statementFromDate}
                    onChange={(e) => setStatementFromDate(e.target.value)}
                    className="border-2 border-slate-300 bg-white px-2 py-1 text-xs font-mono"
                    title="From Date"
                  />
                  <span className="text-slate-400">to</span>
                  <input
                    type="date"
                    value={statementToDate}
                    onChange={(e) => setStatementToDate(e.target.value)}
                    className="border-2 border-slate-300 bg-white px-2 py-1 text-xs font-mono"
                    title="To Date"
                  />
                </div>
              </div>

              <div className="relative w-full md:w-64">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={statementSearchQuery}
                  onChange={(e) => setStatementSearchQuery(e.target.value)}
                  placeholder="Search voucher, PO, narrative..."
                  className="w-full pl-8 pr-3 py-1.5 border-2 border-slate-300 bg-white text-xs font-mono focus:outline-none focus:border-[#C27842]"
                />
              </div>
            </div>

            {/* Investor Ledger Table */}
            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-slate-100 border-b-2 border-slate-200 text-slate-700 text-[10px] font-bold uppercase tracking-wider">
                    <tr>
                      <th className="py-3 px-3 font-bold">Value Date</th>
                      <th className="py-3 px-3 font-bold">Voucher Ref</th>
                      <th className="py-3 px-4 font-bold">Transaction Narrative & Particulars</th>
                      <th className="py-3 px-3 font-bold text-center">Settlement Mode</th>
                      <th className="py-3 px-3 font-bold text-right">Debit (Repaid ₹)</th>
                      <th className="py-3 px-3 font-bold text-right">Margin Yield (₹)</th>
                      <th className="py-3 px-3 font-bold text-right">Credit (Invested ₹)</th>
                      <th className="py-3 px-4 font-bold text-right">Outstanding Balance (₹)</th>
                      <th className="py-3 px-3 font-bold text-center">Audit Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {statementLoading ? (
                      <tr>
                        <td colSpan={9} className="py-16 text-center text-slate-500">
                          <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-[#0F172A]" />
                          <span className="font-bold uppercase tracking-wider text-[11px]">Compiling Investor Ledger...</span>
                        </td>
                      </tr>
                    ) : filteredStatementTransactions.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="py-16 text-center">
                          <div className="max-w-sm mx-auto space-y-3">
                            <div className="w-12 h-12 rounded-full bg-slate-100 border-2 border-slate-300 text-slate-400 grid place-items-center mx-auto">
                              <Landmark className="w-6 h-6" />
                            </div>
                            <div className="font-bold text-slate-800 text-sm uppercase tracking-wider">
                              No Investor Ledger Records
                            </div>
                            <p className="text-xs text-slate-500">
                              Committed PO advances, margin distributions, and full settlement repayments will automatically post to this investor account ledger.
                            </p>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      filteredStatementTransactions.map((t, idx) => {
                        const isDebit = t.debit > 0;
                        const isCredit = t.credit > 0;
                        const isReinvest = t.type === "REINVESTMENT";
                        return (
                          <tr
                            key={t.id || idx}
                            className={`hover:bg-slate-50 transition-colors ${
                              isReinvest ? "bg-blue-50/30" : isDebit ? "bg-amber-50/20" : ""
                            }`}
                          >
                            <td className="py-3 px-3 font-mono text-slate-700 whitespace-nowrap">
                              {t.date}
                            </td>
                            <td className="py-3 px-3 font-mono text-[11px] font-bold text-slate-900 whitespace-nowrap">
                              <span className="bg-slate-200 px-1.5 py-0.5 rounded border border-slate-300">
                                {t.voucher_no || t.id}
                              </span>
                              {t.batch_id && (
                                <span className="block text-[9px] text-slate-500 font-normal mt-0.5" title={`Batch: ${t.batch_id}`}>
                                  {t.batch_id.slice(0, 14)}...
                                </span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-slate-800">
                              <div className="font-medium text-slate-900">{t.narration}</div>
                              <div className="text-[10px] text-slate-500 font-mono mt-0.5 flex items-center gap-2">
                                <span>Partner: <strong>{t.investor_name}</strong></span>
                                {t.po_number && <span>· PO: <strong>{t.po_number}</strong></span>}
                                {t.pairs > 0 && <span>· {t.pairs.toLocaleString("en-IN")} pairs</span>}
                              </div>
                            </td>
                            <td className="py-3 px-3 text-center whitespace-nowrap">
                              <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-slate-100 border border-slate-300 text-slate-700 font-bold">
                                {t.channel}
                              </span>
                            </td>
                            <td className="py-3 px-3 text-right font-mono font-bold whitespace-nowrap">
                              {isDebit ? (
                                <span className="text-rose-700">- {inr(t.debit)}</span>
                              ) : (
                                <span className="text-slate-300">—</span>
                              )}
                            </td>
                            <td className="py-3 px-3 text-right font-mono font-bold whitespace-nowrap">
                              {t.margin_paid > 0 ? (
                                <span className="text-emerald-700">+{inr(t.margin_paid)}</span>
                              ) : (
                                <span className="text-slate-300">—</span>
                              )}
                            </td>
                            <td className="py-3 px-3 text-right font-mono font-bold whitespace-nowrap">
                              {isCredit ? (
                                <span className="text-slate-900">+{inr(t.credit)}</span>
                              ) : (
                                <span className="text-slate-300">—</span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-right font-mono font-black text-slate-950 whitespace-nowrap bg-slate-50/80">
                              {inr(t.running_balance)}
                            </td>
                            <td className="py-3 px-3 text-center whitespace-nowrap">
                              {isReinvest ? (
                                <Badge color="blue">REINVESTED</Badge>
                              ) : isDebit ? (
                                <Badge color="green">SETTLED</Badge>
                              ) : (
                                <Badge color="slate">COMMITTED</Badge>
                              )}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              {/* Statement Certification Footer */}
              <div className="bg-slate-100 border-t-2 border-slate-200 p-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 text-xs">
                <div className="text-slate-600 font-mono text-[11px] space-y-0.5">
                  <div className="font-bold text-slate-800 flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-emerald-600" />
                    Digitally Verified Investor Ledger
                  </div>
                  <div>Accounts Balanced: 2020-INV (Investor Advances Payable) & 5030-INV (Investor Margin Yield)</div>
                  <div>Generated via SSK Footcare Manufacturing ERP · Commercial Accounting Module</div>
                </div>
                <div className="text-right text-[11px] font-mono text-slate-500">
                  <div>Statement Authority: Commercial & Treasury Officer</div>
                  <div className="text-[10px] text-slate-400">Strictly Confidential · For Registered Capital Partner Audit</div>
                </div>
              </div>
            </Card>
          </div>
        )}
      </div>

      {/* ── MODALS (ERP INDUSTRIAL DIALOG AESTHETIC) ────────────────────────── */}

      {/* MODAL 1: ADD INVESTOR */}
      {showAddInvestorModal && (
        <div className="fixed inset-0 z-[100] grid place-items-center bg-black/50 p-4 overflow-y-auto">
          <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-md my-auto flex flex-col">
            <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between bg-slate-50">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">Master Record</div>
                <div className="font-black text-base mt-0.5">Add Investor Partner</div>
              </div>
              <button
                onClick={() => setShowAddInvestorModal(false)}
                className="p-1 text-slate-400 hover:text-slate-900 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateInvestor} className="p-5 space-y-4 text-xs">
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                  Full Name / Entity Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={newInvestorName}
                  onChange={(e) => setNewInvestorName(e.target.value)}
                  placeholder="e.g. Apex Growth Capital"
                  className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#C27842] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                  Contact Person
                </label>
                <input
                  type="text"
                  value={newInvestorContact}
                  onChange={(e) => setNewInvestorContact(e.target.value)}
                  placeholder="e.g. Ramesh Patel"
                  className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#C27842] focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                    Phone (Portal Login)
                  </label>
                  <input
                    type="text"
                    value={newInvestorPhone}
                    onChange={(e) => setNewInvestorPhone(e.target.value)}
                    placeholder="10-digit mobile"
                    className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm font-mono focus:border-[#C27842] focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                    Default Margin / Pair (₹)
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    value={newInvestorMargin}
                    onChange={(e) => setNewInvestorMargin(e.target.value)}
                    className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm font-mono focus:border-[#C27842] focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                  Email Address
                </label>
                <input
                  type="email"
                  value={newInvestorEmail}
                  onChange={(e) => setNewInvestorEmail(e.target.value)}
                  placeholder="investor@partner.com"
                  className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#C27842] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                  Portal Login PIN (4–6 digits)
                </label>
                <input
                  type="password"
                  maxLength={6}
                  value={newInvestorPin}
                  onChange={(e) => setNewInvestorPin(e.target.value)}
                  placeholder="••••"
                  className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm font-mono tracking-widest focus:border-[#C27842] focus:outline-none"
                />
              </div>

              <div className="pt-2 flex justify-end gap-2 border-t border-slate-200">
                <BtnSecondary type="button" onClick={() => setShowAddInvestorModal(false)}>
                  Cancel
                </BtnSecondary>
                <BtnPrimary type="submit" disabled={submittingInvestor}>
                  {submittingInvestor ? "Saving..." : "Create Investor"}
                </BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: SET PIN */}
      {showPinModal && selectedInvestorForPin && (
        <div className="fixed inset-0 z-[100] grid place-items-center bg-black/50 p-4 overflow-y-auto">
          <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-sm my-auto flex flex-col">
            <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between bg-slate-50">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">Security Credentials</div>
                <div className="font-black text-base mt-0.5">Set Portal PIN</div>
              </div>
              <button
                onClick={() => {
                  setShowPinModal(false);
                  setSelectedInvestorForPin(null);
                }}
                className="p-1 text-slate-400 hover:text-slate-900 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSetPin} className="p-5 space-y-4 text-xs">
              <div className="p-2.5 bg-slate-100 border border-slate-200 text-slate-700">
                Partner: <span className="font-bold">{selectedInvestorForPin.name}</span>
              </div>

              <div>
                <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                  New 4–6 Digit Numeric PIN
                </label>
                <input
                  type="password"
                  required
                  maxLength={6}
                  value={pinValue}
                  onChange={(e) => setPinValue(e.target.value.replace(/\D/g, ""))}
                  placeholder="••••"
                  className="w-full border-2 border-slate-300 bg-white px-4 py-2.5 text-center text-xl tracking-widest font-mono focus:border-[#C27842] focus:outline-none"
                />
              </div>

              <div className="pt-2 flex justify-end gap-2 border-t border-slate-200">
                <BtnSecondary
                  type="button"
                  onClick={() => {
                    setShowPinModal(false);
                    setSelectedInvestorForPin(null);
                  }}
                >
                  Cancel
                </BtnSecondary>
                <BtnPrimary type="submit" disabled={pinValue.length < 4}>
                  Save PIN
                </BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: COMMIT ADVANCE (Supports Multiple POs funded at once) */}
      {showCreateAdvanceModal && (
        <div className="fixed inset-0 z-[100] grid place-items-center bg-black/50 p-4 overflow-y-auto">
          <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-2xl my-auto flex flex-col max-h-[92vh]">
            <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between bg-slate-50 flex-shrink-0">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">Commercial Commit</div>
                <div className="font-black text-base mt-0.5">Fund Purchase Order(s) Simultaneously</div>
              </div>
              <button
                onClick={() => setShowCreateAdvanceModal(false)}
                className="p-1 text-slate-400 hover:text-slate-900 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateAdvance} className="p-5 space-y-4 text-xs overflow-y-auto">
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                  Select Investor Partner <span className="text-red-500">*</span>
                </label>
                <select
                  required
                  value={selectedInvestorId}
                  onChange={(e) => {
                    setSelectedInvestorId(e.target.value);
                    const inv = investors.find((i) => i._id === e.target.value);
                    if (inv) setMarginOverride(String(inv.default_margin_per_pair || 10.0));
                  }}
                  className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs focus:border-[#C27842] focus:outline-none"
                >
                  <option value="">-- Choose Investor Partner --</option>
                  {investors.map((i) => (
                    <option key={i._id} value={i._id}>
                      {i.name} (Default Margin: ₹{i.default_margin_per_pair}/pr)
                    </option>
                  ))}
                </select>
              </div>

              {/* Receiving Company Bank Account Selector */}
              <div className="border-2 border-slate-200 p-3 bg-slate-50 space-y-3">
                <div className="flex items-center gap-1.5 font-bold text-slate-800 text-xs">
                  <Landmark className="w-4 h-4 text-[#C27842]" />
                  <span>Company Receiving Bank Account</span>
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                    Select Destination Bank Account <span className="text-red-500">*</span>
                  </label>
                  <select
                    required
                    value={selectedBankAccountId}
                    onChange={(e) => setSelectedBankAccountId(e.target.value)}
                    className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs focus:border-[#C27842] focus:outline-none"
                  >
                    <option value="">-- Select Company Bank Account --</option>
                    {bankAccounts.map((acc) => (
                      <option key={acc._id || acc.id} value={acc._id || acc.id}>
                        {acc.bank_name || acc.account_name} {acc.account_number ? `(••${acc.account_number.slice(-4)})` : ""} · Bal: {inr(acc.current_balance || 0)}
                      </option>
                    ))}
                  </select>
                  <p className="text-[10px] text-slate-500 mt-1">
                    Funds deposited will be credited to this bank account in real-time.
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                      Payment Inflow Mode
                    </label>
                    <select
                      value={paymentMode}
                      onChange={(e) => setPaymentMode(e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs focus:border-[#C27842] focus:outline-none"
                    >
                      <option value="Bank Transfer">Bank Transfer (NEFT/RTGS/IMPS)</option>
                      <option value="NEFT">NEFT</option>
                      <option value="RTGS">RTGS</option>
                      <option value="IMPS">IMPS</option>
                      <option value="Cheque">Cheque Deposit</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                      UTR / Transaction Reference
                    </label>
                    <input
                      type="text"
                      value={paymentReference}
                      onChange={(e) => setPaymentReference(e.target.value)}
                      placeholder="e.g. UTR123456789"
                      className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs font-mono focus:border-[#C27842] focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Multi-PO Selection Box */}
              <div className="space-y-2 border-2 border-slate-200 p-3 bg-slate-50">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-700">
                    Select Purchase Orders to Fund ({selectedPoIds.length} selected) <span className="text-red-500">*</span>
                  </label>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const matching = posList
                          .filter((p) =>
                            !poFilterQuery ||
                            p.po_number?.toLowerCase().includes(poFilterQuery.toLowerCase()) ||
                            p.client_name?.toLowerCase().includes(poFilterQuery.toLowerCase())
                          )
                          .map((p) => p.id || p._id);
                        setSelectedPoIds(matching);
                      }}
                      className="text-[10px] text-blue-600 font-bold uppercase hover:underline"
                    >
                      Select All Filtered
                    </button>
                    <span>·</span>
                    <button
                      type="button"
                      onClick={() => setSelectedPoIds([])}
                      className="text-[10px] text-slate-500 font-bold uppercase hover:underline"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    value={poFilterQuery}
                    onChange={(e) => setPoFilterQuery(e.target.value)}
                    placeholder="Filter PO number or client..."
                    className="w-full pl-8 pr-3 py-1.5 border border-slate-300 bg-white text-xs font-mono focus:outline-none"
                  />
                </div>

                <div className="max-h-48 overflow-y-auto divide-y divide-slate-200 border border-slate-200 bg-white">
                  {posList
                    .filter((p) => {
                      if (!poFilterQuery) return true;
                      const q = poFilterQuery.toLowerCase();
                      return (
                        (p.po_number && p.po_number.toLowerCase().includes(q)) ||
                        (p.client_name && p.client_name.toLowerCase().includes(q))
                      );
                    })
                    .map((p) => {
                      const poId = p.id || p._id;
                      const isChecked = selectedPoIds.includes(poId);
                      return (
                        <label
                          key={poId}
                          className={`flex items-center justify-between p-2.5 hover:bg-slate-50 cursor-pointer ${
                            isChecked ? "bg-amber-50/70 font-bold" : ""
                          }`}
                        >
                          <div className="flex items-center gap-2.5">
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={(e) => {
                                e.stopPropagation();
                                if (e.target.checked) {
                                  setSelectedPoIds((prev) => [...prev.filter((id) => id !== poId), poId]);
                                } else {
                                  setSelectedPoIds((prev) => prev.filter((id) => id !== poId));
                                }
                              }}
                              className="w-4 h-4 border-2 border-slate-400 rounded text-[#0F172A] focus:ring-0 cursor-pointer"
                            />
                            <div>
                              <span className="font-mono text-slate-900">{p.po_number}</span>
                              <span className="text-slate-500 font-normal ml-2">
                                ({p.client_name || "Client"})
                              </span>
                            </div>
                          </div>
                          <div className="text-right font-mono text-slate-600 text-[11px]">
                            {(p.total_quantity || p.quantity || 0).toLocaleString("en-IN")} pairs
                          </div>
                        </label>
                      );
                    })}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                    Negotiated Margin Override / Pair (₹)
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    value={marginOverride}
                    onChange={(e) => setMarginOverride(e.target.value)}
                    placeholder="e.g. 12.0"
                    className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm font-mono focus:border-[#C27842] focus:outline-none"
                  />
                </div>

                <div className="p-3 bg-slate-50 border-2 border-slate-200">
                  <label className="flex items-center gap-2 cursor-pointer font-bold text-slate-800">
                    <input
                      type="checkbox"
                      checked={includeOpex}
                      onChange={(e) => setIncludeOpex(e.target.checked)}
                      className="w-4 h-4 border-2 border-slate-400 rounded text-[#0F172A] focus:ring-0"
                    />
                    <span>Include Investor Opex Templates Once</span>
                  </label>
                  <p className="text-[10px] text-slate-500 mt-1 pl-6">
                    Applied once across the batch. Never multiplied.
                  </p>
                </div>
              </div>

              {/* LIVE BATCH COMPUTATION PREVIEW BOX */}
              {selectedPoIds.length > 0 && (
                <div className="p-3.5 bg-slate-100 border-2 border-slate-300 space-y-2.5">
                  <div className="text-[10px] uppercase font-bold text-slate-600 flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-[#C27842]" />
                      Multi-PO Capital Calculation Preview
                    </span>
                    {loadingPreview && <Loader2 className="w-3 h-3 animate-spin text-slate-500" />}
                  </div>

                  {batchPreview ? (
                    <div className="space-y-2">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                        <div className="bg-white p-2 border border-slate-200">
                          <span className="text-slate-500 block text-[9px] uppercase font-bold">Total POs</span>
                          <span className="font-mono font-bold text-slate-900">{batchPreview.count}</span>
                        </div>
                        <div className="bg-white p-2 border border-slate-200">
                          <span className="text-slate-500 block text-[9px] uppercase font-bold">Total Pairs</span>
                          <span className="font-mono font-bold text-slate-900">
                            {batchPreview.total_pairs?.toLocaleString("en-IN")}
                          </span>
                        </div>
                        <div className="bg-white p-2 border border-slate-200 col-span-2">
                          <span className="text-slate-500 block text-[9px] uppercase font-bold">
                            Total Capital to Fund
                          </span>
                          <span className="font-mono font-black text-slate-950 text-sm">
                            {inr(batchPreview.total_funding_required)}
                          </span>
                        </div>
                      </div>

                      {/* Itemized per-PO list */}
                      <div className="max-h-32 overflow-y-auto border border-slate-200 bg-white text-[11px] divide-y divide-slate-100">
                        {batchPreview.items?.map((item) => (
                          <div key={item.po_id} className="p-2 flex justify-between items-center">
                            <div>
                              <span className="font-bold text-slate-900 font-mono">{item.po_number}</span>
                              <span className="text-slate-500 ml-2">({item.pairs} prs)</span>
                            </div>
                            <div className="font-mono font-bold text-slate-900">
                              {inr(item.funding_required)}
                            </div>
                          </div>
                        ))}
                      </div>

                      <div className="bg-slate-900 text-white p-3 flex justify-between items-center">
                        <div>
                          <span className="text-[9px] uppercase tracking-wider text-slate-300 block font-bold">
                            Combined Advance Total
                          </span>
                          <span className="font-mono text-base font-black">
                            {inr(batchPreview.total_funding_required)}
                          </span>
                        </div>
                        <div className="text-right">
                          <span className="text-[9px] uppercase tracking-wider text-emerald-400 block font-bold">
                            Combined Yield @ ₹{marginOverride || 10}/pr
                          </span>
                          <span className="font-mono text-sm font-bold text-emerald-400">
                            {inr((batchPreview.total_pairs || 0) * (parseFloat(marginOverride) || 10.0))}
                          </span>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-slate-500 text-center py-2 text-[11px]">
                      {loadingPreview ? "Computing combined funding requirement..." : "Selecting POs..."}
                    </div>
                  )}
                </div>
              )}

              <div>
                <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                  Batch Deal Notes / Audit Remarks
                </label>
                <input
                  type="text"
                  value={advanceNotes}
                  onChange={(e) => setAdvanceNotes(e.target.value)}
                  placeholder="Optional syndicate reference"
                  className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#C27842] focus:outline-none"
                />
              </div>

              <div className="pt-2 flex justify-end gap-2 border-t border-slate-200 flex-shrink-0">
                <BtnSecondary type="button" onClick={() => setShowCreateAdvanceModal(false)}>
                  Cancel
                </BtnSecondary>
                <BtnPrimary
                  type="submit"
                  disabled={submittingAdvance || selectedPoIds.length === 0 || !selectedInvestorId}
                >
                  {submittingAdvance
                    ? "Executing Batch Advance..."
                    : `Fund ${selectedPoIds.length} Purchase Order${selectedPoIds.length > 1 ? "s" : ""}`}
                </BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 4: SETTLE ADVANCES (Supports Single or Multiple POs settled at once) */}
      {showRepayModal && advancesToSettle.length > 0 && (
        <div className="fixed inset-0 z-[100] grid place-items-center bg-black/50 p-4 overflow-y-auto">
          <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-xl my-auto flex flex-col max-h-[92vh]">
            <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between bg-slate-50 flex-shrink-0">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">
                  {advancesToSettle.length > 1 ? "Batch Settlement Action" : "Settlement Action"}
                </div>
                <div className="font-black text-base mt-0.5">
                  Settle {advancesToSettle.length} Purchase Order Advance{advancesToSettle.length > 1 ? "s" : ""}
                </div>
              </div>
              <button
                onClick={() => {
                  setShowRepayModal(false);
                  setAdvancesToSettle([]);
                }}
                className="p-1 text-slate-400 hover:text-slate-900 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleExecuteRepay} className="p-5 space-y-4 text-xs overflow-y-auto">
              {/* Advances being settled */}
              <div className="border border-slate-200 bg-slate-50 p-3 space-y-2">
                <div className="text-[10px] uppercase font-bold text-slate-600 flex justify-between">
                  <span>Target Advances ({advancesToSettle.length})</span>
                  <span>Principal / Margin</span>
                </div>
                <div className="max-h-36 overflow-y-auto divide-y divide-slate-200 bg-white border border-slate-200">
                  {advancesToSettle.map((adv) => (
                    <div key={adv._id} className="p-2 flex justify-between items-center">
                      <div>
                        <span className="font-bold text-slate-900 font-mono">{adv.po_number || "PO"}</span>
                        <span className="text-slate-500 ml-2">({adv.investor_name})</span>
                      </div>
                      <div className="text-right font-mono">
                        <span className="font-bold text-slate-900">{inr(adv.amount)}</span>
                        <span className="text-emerald-700 font-medium ml-2">
                          + {inr((adv.pairs || 0) * (adv.margin_per_pair || 10.0))}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Action Selection Tabs */}
              <div className="grid grid-cols-2 gap-2 border-2 border-slate-200 p-1 bg-slate-100">
                <button
                  type="button"
                  onClick={() => setRepayActionType("repay_in_full")}
                  className={`py-2 text-[10px] font-bold uppercase tracking-wider transition ${
                    repayActionType === "repay_in_full"
                      ? "bg-[#0F172A] text-white shadow-sm"
                      : "text-slate-700 hover:text-slate-900"
                  }`}
                >
                  Action 1: Repay in Full
                </button>
                <button
                  type="button"
                  onClick={() => setRepayActionType("reinvest")}
                  className={`py-2 text-[10px] font-bold uppercase tracking-wider transition ${
                    repayActionType === "reinvest"
                      ? "bg-[#0F172A] text-white shadow-sm"
                      : "text-slate-700 hover:text-slate-900"
                  }`}
                >
                  Action 2: Pay Margin & Reinvest
                </button>
              </div>

              {repayActionType === "repay_in_full" ? (
                <div className="p-4 bg-emerald-50 border-2 border-emerald-300 text-emerald-950 space-y-2">
                  <div className="font-bold uppercase tracking-wider text-[11px] text-emerald-900">
                    Full Cash Repayment (Real Cash Out for {advancesToSettle.length} POs)
                  </div>
                  <div className="flex justify-between py-1 border-b border-emerald-200">
                    <span>Total Principal (Debit Investor Advances Payable 2020):</span>
                    <span className="font-mono font-bold">
                      {inr(advancesToSettle.reduce((s, a) => s + (a.amount || 0), 0))}
                    </span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-emerald-200">
                    <span>Total Margin (Debit Investor Margin / Finance Cost 5030):</span>
                    <span className="font-mono font-bold">
                      {inr(
                        advancesToSettle.reduce(
                          (s, a) =>
                            s +
                            (a.pairs || 0) *
                              (repayMarginOverride ? parseFloat(repayMarginOverride) : a.margin_per_pair || 10.0),
                          0
                        )
                      )}
                    </span>
                  </div>
                  <div className="flex justify-between py-1 font-bold text-slate-950 text-sm">
                    <span>Total Cash Disbursed via Bank/Cash:</span>
                    <span className="font-mono">
                      {inr(
                        advancesToSettle.reduce(
                          (s, a) =>
                            s +
                            (a.amount || 0) +
                            (a.pairs || 0) *
                              (repayMarginOverride ? parseFloat(repayMarginOverride) : a.margin_per_pair || 10.0),
                          0
                        )
                      )}
                    </span>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="p-3 bg-blue-50 border-2 border-blue-200 text-blue-950 space-y-1">
                    <div className="font-bold uppercase tracking-wider text-[11px] text-blue-900">
                      Two-Leg Batch Reinvestment Structure
                    </div>
                    <div>1. <strong>Cash Out:</strong> Combined margin ({inr(
                      advancesToSettle.reduce(
                        (s, a) =>
                          s +
                          (a.pairs || 0) *
                            (repayMarginOverride ? parseFloat(repayMarginOverride) : a.margin_per_pair || 10.0),
                        0
                      )
                    )}) is disbursed immediately via Bank/Cash.</div>
                    <div>2. <strong>Non-Cash Rollover:</strong> Combined principal ({inr(
                      advancesToSettle.reduce((s, a) => s + (a.amount || 0), 0)
                    )}) rolls forward into the selected target PO advance with zero net cash movement.</div>
                  </div>

                  <div>
                    <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                      Target PO to Reinvest Into <span className="text-red-500">*</span>
                    </label>
                    <select
                      required
                      value={targetPoId}
                      onChange={(e) => setTargetPoId(e.target.value)}
                      className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs font-mono focus:border-[#C27842] focus:outline-none"
                    >
                      <option value="">-- Choose Target PO --</option>
                      {posList
                        .filter((p) => !advancesToSettle.some((a) => String(a.po_id) === String(p.id || p._id)))
                        .map((p) => {
                          const poId = p.id || p._id;
                          return (
                            <option key={poId} value={poId}>
                              {p.po_number} ({p.total_quantity || p.quantity || 0} pairs) - {p.client_name || "Client"}
                            </option>
                          );
                        })}
                    </select>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                    Margin Rate Override (₹/pr)
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    value={repayMarginOverride}
                    onChange={(e) => setRepayMarginOverride(e.target.value)}
                    placeholder="Leave blank for agreed rates"
                    className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs font-mono focus:border-[#C27842] focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                    Disbursement Mode
                  </label>
                  <select
                    value={repayMode}
                    onChange={(e) => setRepayMode(e.target.value)}
                    className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs focus:border-[#C27842] focus:outline-none"
                  >
                    <option value="Bank Transfer">Bank Transfer (RTGS/NEFT)</option>
                    <option value="Cash">Factory Petty Cash</option>
                    <option value="Cheque">Company Cheque</option>
                  </select>
                </div>
              </div>

              {repayMode !== "Cash" && (
                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">
                    Disbursing Bank Account <span className="text-red-500">*</span>
                  </label>
                  <select
                    required
                    value={repayBankAccountId}
                    onChange={(e) => setRepayBankAccountId(e.target.value)}
                    className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs focus:border-[#C27842] focus:outline-none"
                  >
                    <option value="">-- Choose Company Bank Account --</option>
                    {bankAccounts.map((acc) => (
                      <option key={acc._id || acc.id} value={acc._id || acc.id}>
                        {acc.bank_name || acc.account_name} {acc.account_number ? `(••${acc.account_number.slice(-4)})` : ""} · Bal: {inr(acc.current_balance || 0)}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div className="pt-2 flex justify-end gap-2 border-t border-slate-200 flex-shrink-0">
                <BtnSecondary
                  type="button"
                  onClick={() => {
                    setShowRepayModal(false);
                    setAdvancesToSettle([]);
                  }}
                >
                  Cancel
                </BtnSecondary>
                <BtnPrimary type="submit" disabled={submittingRepay}>
                  {submittingRepay
                    ? "Executing Settlement..."
                    : `Confirm Settlement for ${advancesToSettle.length} Advance${advancesToSettle.length > 1 ? "s" : ""}`}
                </BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 5: ADVANCE DETAILS INSPECTOR */}
      {selectedAdvanceDetails && (
        <div className="fixed inset-0 z-[100] grid place-items-center bg-black/50 p-4 overflow-y-auto">
          <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-lg my-auto flex flex-col">
            <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between bg-slate-50">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">Advance Inspection</div>
                <div className="font-black text-base mt-0.5">
                  {selectedAdvanceDetails.po_number || "PO Reference"}
                </div>
              </div>
              <button
                onClick={() => setSelectedAdvanceDetails(null)}
                className="p-1 text-slate-400 hover:text-slate-900 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 border border-slate-200">
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">Investor Partner</span>
                  <span className="font-bold text-slate-900 text-sm">{selectedAdvanceDetails.investor_name}</span>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">Status</span>
                  <div className="mt-0.5">{getStatusBadge(selectedAdvanceDetails.status)}</div>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">Advance Date</span>
                  <span className="font-mono text-slate-700">{selectedAdvanceDetails.advance_date}</span>
                </div>
                <div>
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">PO Production Pairs</span>
                  <span className="font-mono font-bold text-slate-900">
                    {selectedAdvanceDetails.pairs?.toLocaleString("en-IN") || 0}
                  </span>
                </div>
                {selectedAdvanceDetails.bank_name && (
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-500 block">Receiving Company Bank</span>
                    <span className="font-bold text-slate-900 flex items-center gap-1 mt-0.5">
                      <Landmark className="w-3.5 h-3.5 text-slate-500" />
                      {selectedAdvanceDetails.bank_name}
                    </span>
                  </div>
                )}
                {selectedAdvanceDetails.payment_mode && (
                  <div>
                    <span className="text-[10px] uppercase font-bold text-slate-500 block">Payment Mode & Ref</span>
                    <span className="font-mono text-slate-700">
                      {selectedAdvanceDetails.payment_mode}
                      {selectedAdvanceDetails.reference ? ` (${selectedAdvanceDetails.reference})` : ""}
                    </span>
                  </div>
                )}
              </div>

              {/* Breakdown */}
              <div className="border-2 border-slate-200 p-3 space-y-2">
                <div className="text-[10px] uppercase font-bold text-slate-600 flex items-center justify-between border-b pb-1">
                  <span>Funding Calculation Breakdown</span>
                  <span className="font-mono">
                    {selectedAdvanceDetails.breakdown?.opex_included ? "Includes Opex" : "Direct Manufacturing Only"}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-100">
                  <span className="text-slate-600">BOM Materials Cost:</span>
                  <span className="font-mono font-bold">{inr(selectedAdvanceDetails.breakdown?.bom_cost || 0)}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-100">
                  <span className="text-slate-600">Production Labor Cost:</span>
                  <span className="font-mono font-bold">{inr(selectedAdvanceDetails.breakdown?.labour_cost || 0)}</span>
                </div>
                {selectedAdvanceDetails.breakdown?.opex_included && (
                  <div className="flex justify-between py-1 border-b border-slate-100">
                    <span className="text-slate-600">Investor Recurring Opex:</span>
                    <span className="font-mono font-bold text-blue-700">
                      {inr(selectedAdvanceDetails.breakdown?.opex_cost || 0)}
                    </span>
                  </div>
                )}
                <div className="flex justify-between py-1 font-bold text-slate-950 text-sm pt-1">
                  <span>Total Capital Funded:</span>
                  <span className="font-mono">{inr(selectedAdvanceDetails.amount)}</span>
                </div>
              </div>

              {/* Margin & Yield */}
              <div className="p-3 bg-emerald-50 border border-emerald-200 space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-600">Agreed Margin / Pair:</span>
                  <span className="font-mono font-bold text-emerald-800">
                    ₹{selectedAdvanceDetails.margin_per_pair || 10.0}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-600">Expected Total Margin Return:</span>
                  <span className="font-mono font-bold text-emerald-800">
                    {inr((selectedAdvanceDetails.pairs || 0) * (selectedAdvanceDetails.margin_per_pair || 10.0))}
                  </span>
                </div>
              </div>

              {/* Batch link if exists */}
              {selectedAdvanceDetails.batch_id && (
                <div className="p-2.5 bg-slate-50 border border-slate-200 flex justify-between items-center text-[11px]">
                  <span className="text-slate-500 font-bold uppercase text-[10px]">Syndicate Batch Ref</span>
                  <span className="font-mono font-bold text-slate-900">{selectedAdvanceDetails.batch_id}</span>
                </div>
              )}

              {/* GL Mirroring info */}
              <div className="p-3 bg-slate-100 border border-slate-200 text-slate-600 text-[11px] space-y-1">
                <div className="font-bold text-slate-800 uppercase tracking-wider text-[10px] flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-blue-600" />
                  Supabase GL Ledger Integration
                </div>
                <div>Principal maps to <strong>Account 2020 (Investor Advances Payable)</strong></div>
                <div>Margin maps to <strong>Account 5030 (Investor Margin / Finance Cost)</strong></div>
              </div>

              <div className="pt-2 flex justify-end">
                <BtnSecondary onClick={() => setSelectedAdvanceDetails(null)}>
                  Close
                </BtnSecondary>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
