import React, { useState, useEffect, useMemo, useCallback } from "react";
import { http, inr, friendlyAxiosError } from "../lib/api";
import {
  PageHeader,
  Card,
  StatTile,
  Badge,
  BtnPrimary,
  BtnSecondary,
  Input,
  Select,
} from "../components/ui-kit";
import {
  Mail,
  MailCheck,
  RefreshCw,
  Sliders,
  Sparkles,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ClipboardCheck,
  IndianRupee,
  FileText,
  Search,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Paperclip,
  Check,
  X,
  Building2,
  Calendar,
  Layers,
  HelpCircle,
  ShieldCheck,
  Tag,
  ArrowRight,
  Info,
} from "lucide-react";

export default function GmailInbox() {
  const [items, setItems] = useState([]);
  const [statusInfo, setStatusInfo] = useState(null);
  const [rules, setRules] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [filterTab, setFilterTab] = useState("pending"); // pending, grn, payment, recorded, dismissed, all
  const [search, setSearch] = useState("");
  const [toast, setToast] = useState(null);

  // Modals state
  const [showRulesModal, setShowRulesModal] = useState(false);
  const [showTestModal, setShowTestModal] = useState(false);
  const [editItem, setEditItem] = useState(null); // Item being edited for approval
  const [editForm, setEditForm] = useState({});

  // Test parser state
  const [testForm, setTestForm] = useState({
    subject: "",
    sender: "stores@clientcorp.com",
    body_text: "",
  });
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  const showToast = (message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 5000);
  };

  const loadAllData = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, itemsRes, rulesRes, invRes, bankRes] = await Promise.all([
        http.get("/gmail-inbox/status").catch(() => ({ data: null })),
        http.get("/gmail-inbox/items?limit=100").catch(() => ({ data: { items: [], total: 0 } })),
        http.get("/gmail-inbox/rules").catch(() => ({ data: null })),
        http.get("/invoices").catch(() => ({ data: [] })),
        http.get("/banking/accounts", { params: { active: true } }).catch(() => ({ data: [] })),
      ]);

      if (statusRes?.data) setStatusInfo(statusRes.data);
      if (itemsRes?.data?.items) setItems(itemsRes.data.items);
      if (rulesRes?.data) setRules(rulesRes.data);
      if (Array.isArray(invRes?.data)) setInvoices(invRes.data);
      if (Array.isArray(bankRes?.data)) setBankAccounts(bankRes.data);
    } catch (err) {
      showToast(friendlyAxiosError(err), "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAllData();
  }, [loadAllData]);

  // Sync Gmail Now
  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await http.post("/gmail-inbox/sync", { days_back: 7, max_emails: 50 });
      const { scanned, created, auto_recorded, errors } = res.data;
      showToast(
        `Sync complete! Scanned ${scanned} emails · Found ${created} actionable items · Auto-recorded ${auto_recorded}.`,
        errors?.length ? "warning" : "success"
      );
      loadAllData();
    } catch (err) {
      showToast(friendlyAxiosError(err), "error");
    } finally {
      setSyncing(false);
    }
  };

  // One-click Approve & Record
  const handleApprove = async (item) => {
    // If no matched invoice/bank account, open edit modal instead so user can select
    if (item.category === "grn" && !item.matched_invoice_id) {
      openEditModal(item);
      return;
    }
    if (item.category === "payment" && (!item.matched_bank_account_id || !item.matched_invoice_id)) {
      openEditModal(item);
      return;
    }

    setActionLoading(true);
    try {
      const payload = {};
      if (item.category === "payment") {
        payload.override_amount = item.extracted_data?.amount;
        payload.override_payment_date = item.extracted_data?.payment_date;
        payload.override_utr = item.extracted_data?.utr_number;
      } else if (item.category === "grn") {
        payload.override_accepted_qty = item.extracted_data?.accepted_pairs;
        payload.override_rejected_qty = item.extracted_data?.rejected_pairs;
      }

      const res = await http.post(`/gmail-inbox/items/${item.id}/approve`, payload);
      showToast(res.data.message || "Successfully recorded into ERP database!");
      loadAllData();
    } catch (err) {
      showToast(friendlyAxiosError(err), "error");
    } finally {
      setActionLoading(false);
    }
  };

  // Open Edit & Approve Modal
  const openEditModal = (item) => {
    setEditItem(item);
    if (item.category === "grn") {
      setEditForm({
        override_invoice_id: item.matched_invoice_id || "",
        override_accepted_qty: item.extracted_data?.accepted_pairs || item.extracted_data?.total_pairs || 0,
        override_rejected_qty: item.extracted_data?.rejected_pairs || 0,
        remarks: item.extracted_data?.rejection_reason || `Extracted from email: ${item.subject}`,
      });
    } else {
      setEditForm({
        override_bank_account_id: item.matched_bank_account_id || (bankAccounts[0]?.id || ""),
        override_invoice_id: item.matched_invoice_id || "",
        override_amount: item.extracted_data?.amount || 0,
        override_payment_date: item.extracted_data?.payment_date || new Date().toISOString().slice(0, 10),
        override_utr: item.extracted_data?.utr_number || "",
        payment_mode: item.extracted_data?.payment_mode || "Bank Transfer",
        remarks: `Email payment remittance: ${item.subject}`,
      });
    }
  };

  // Save Edit & Approve
  const handleSaveEdit = async () => {
    if (!editItem) return;
    setActionLoading(true);
    try {
      const res = await http.post(`/gmail-inbox/items/${editItem.id}/approve`, editForm);
      showToast(res.data.message || "Successfully approved and recorded into ERP!");
      setEditItem(null);
      loadAllData();
    } catch (err) {
      showToast(friendlyAxiosError(err), "error");
    } finally {
      setActionLoading(false);
    }
  };

  // Dismiss Item
  const handleDismiss = async (item) => {
    const reason = window.prompt("Reason for dismissing this email item (e.g., Duplicate, Internal test, Not relevant):", "Not relevant to ERP");
    if (reason === null) return;
    try {
      await http.post(`/gmail-inbox/items/${item.id}/dismiss`, { reason });
      showToast("Item dismissed.");
      loadAllData();
    } catch (err) {
      showToast(friendlyAxiosError(err), "error");
    }
  };

  // Save Rules
  const handleSaveRules = async (e) => {
    e.preventDefault();
    try {
      await http.put("/gmail-inbox/rules", rules);
      showToast("Auto-posting configuration saved successfully!");
      setShowRulesModal(false);
      loadAllData();
    } catch (err) {
      showToast(friendlyAxiosError(err), "error");
    }
  };

  // Run Test Parser
  const handleRunTest = async (e) => {
    e.preventDefault();
    if (!testForm.subject.trim() && !testForm.body_text.trim()) {
      showToast("Please enter an email subject or body text to test.", "warning");
      return;
    }
    setTesting(true);
    try {
      const res = await http.post("/gmail-inbox/test-parse", testForm);
      setTestResult(res.data);
    } catch (err) {
      showToast(friendlyAxiosError(err), "error");
    } finally {
      setTesting(false);
    }
  };

  // Filter helper functions
  const isPending = (item) => item.status === "pending" || item.status === "pending_review";
  const isRecorded = (item) => item.status === "recorded" || item.status === "processed" || item.status === "auto_recorded";
  const isDismissed = (item) => item.status === "dismissed";
  const isGrn = (item) => item.category?.toLowerCase() === "grn";
  const isPayment = (item) => item.category?.toLowerCase() === "payment";

  // Filtered Items
  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      // Status & Category Tabs
      if (filterTab === "pending" && !isPending(item)) return false;
      if (filterTab === "recorded" && !isRecorded(item)) return false;
      if (filterTab === "dismissed" && !isDismissed(item)) return false;
      if (filterTab === "grn" && !isGrn(item)) return false;
      if (filterTab === "payment" && !isPayment(item)) return false;

      // Text search
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchesSubject = item.subject?.toLowerCase().includes(q);
        const matchesSender = item.sender?.toLowerCase().includes(q) || item.from_header?.toLowerCase().includes(q) || item.from_email?.toLowerCase().includes(q);
        const matchesInv = (item.extracted_data?.invoice_no || item.matched_invoice_no || "")
          .toLowerCase()
          .includes(q);
        const matchesUtr = (item.extracted_data?.utr_number || item.extracted_data?.reference || "").toLowerCase().includes(q);
        const matchesClient = (item.extracted_data?.client_name || "").toLowerCase().includes(q);
        if (!matchesSubject && !matchesSender && !matchesInv && !matchesUtr && !matchesClient) {
          return false;
        }
      }
      return true;
    });
  }, [items, filterTab, search]);

  // Counts for stat tiles
  const pendingCount = items.filter(isPending).length;
  const pendingGrnCount = items.filter((i) => isPending(i) && isGrn(i)).length;
  const pendingPaymentCount = items.filter((i) => isPending(i) && isPayment(i)).length;
  const autoRecordedCount = items.filter((i) => i.auto_recorded || i.status === "auto_recorded").length;
  const totalRecordedCount = items.filter(isRecorded).length;

  return (
    <div className="space-y-6 pb-12">
      {/* Toast Alert */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-3 border-2 shadow-lg flex items-center gap-3 transition-all ${
            toast.type === "error"
              ? "bg-red-50 border-red-500 text-red-900"
              : toast.type === "warning"
              ? "bg-amber-50 border-amber-500 text-amber-900"
              : "bg-emerald-50 border-emerald-500 text-emerald-900"
          }`}
        >
          {toast.type === "error" ? (
            <XCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
          ) : toast.type === "warning" ? (
            <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
          ) : (
            <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
          )}
          <span className="text-sm font-semibold">{toast.message}</span>
          <button onClick={() => setToast(null)} className="ml-2 text-slate-500 hover:text-slate-800">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Page Header */}
      <PageHeader
        title="Gmail Automation"
        subtitle="Automated GRN & Client Payment Recording"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <BtnSecondary
              onClick={() => setShowTestModal(true)}
              className="flex items-center gap-2"
              title="Test Email Parser with custom text or delivery challan"
            >
              <Sparkles className="w-3.5 h-3.5 text-purple-600" />
              <span>Test Parser</span>
            </BtnSecondary>
            <BtnSecondary
              onClick={() => setShowRulesModal(true)}
              className="flex items-center gap-2"
              title="Configure auto-posting rules and confidence thresholds"
            >
              <Sliders className="w-3.5 h-3.5 text-[#C27842]" />
              <span>Auto-Post Rules</span>
            </BtnSecondary>
            <BtnPrimary
              onClick={handleSync}
              disabled={syncing}
              className="flex items-center gap-2 bg-[#0F172A] border-[#0F172A]"
              title="Fetch recent emails from Gmail and process GRNs & Payments"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin text-amber-400" : ""}`} />
              <span>{syncing ? "Scanning Inbox..." : "Sync Gmail Now"}</span>
            </BtnPrimary>
          </div>
        }
      />

      <div className="px-4 sm:px-8 space-y-6">
        {/* Connection & Configuration Info Banner */}
        <div className="bg-slate-900 text-white border-2 border-slate-900 p-4 sm:p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start sm:items-center gap-3">
            <div className="p-2.5 bg-slate-800 rounded border border-slate-700">
              <MailCheck className="w-6 h-6 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-sm tracking-wide">
                  {statusInfo?.connected ? "Gmail Connected & Listening" : "Gmail Connection State"}
                </span>
                <span
                  className={`px-2 py-0.5 text-[10px] font-bold uppercase rounded ${
                    statusInfo?.connected ? "bg-emerald-950 text-emerald-300 border border-emerald-700" : "bg-amber-950 text-amber-300 border border-amber-700"
                  }`}
                >
                  {statusInfo?.connected ? "Active" : "Offline / Unconfigured"}
                </span>
              </div>
              <p className="text-xs text-slate-300 mt-0.5">
                Target Account: <span className="font-mono text-emerald-300">{statusInfo?.email_address || "GMAIL_SENDER / OAuth"}</span> · Last Sync:{" "}
                <span className="text-slate-200">{statusInfo?.last_sync ? new Date(statusInfo.last_sync).toLocaleString("en-IN") : "Pending initial sync"}</span>
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <div className="bg-slate-800 px-3 py-1.5 rounded border border-slate-700 flex items-center gap-2">
              <span className="text-slate-400">Auto-Post GRN:</span>
              <span className={`font-bold font-mono ${rules?.auto_record_grn ? "text-emerald-400" : "text-slate-400"}`}>
                {rules?.auto_record_grn ? `ON (≥${Math.round((rules.min_confidence_grn || 0.85) * 100)}%)` : "OFF"}
              </span>
            </div>
            <div className="bg-slate-800 px-3 py-1.5 rounded border border-slate-700 flex items-center gap-2">
              <span className="text-slate-400">Auto-Post Payment:</span>
              <span className={`font-bold font-mono ${rules?.auto_record_payment ? "text-emerald-400" : "text-slate-400"}`}>
                {rules?.auto_record_payment ? `ON (≥${Math.round((rules.min_confidence_payment || 0.85) * 100)}%)` : "OFF"}
              </span>
            </div>
          </div>
        </div>

        {/* Stat Tiles */}
        <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
          <StatTile
            label="Pending Review"
            value={pendingCount}
            sub={`${pendingGrnCount} GRNs · ${pendingPaymentCount} Payments`}
            accent="#C27842"
          />
          <StatTile
            label="Awaiting GRN Post"
            value={pendingGrnCount}
            sub="Dispatched goods receipts"
            accent="#7C3AED"
          />
          <StatTile
            label="Awaiting Payment Post"
            value={pendingPaymentCount}
            sub="Bank remittance & receipts"
            accent="#059669"
          />
          <StatTile
            label="Total Auto-Recorded"
            value={autoRecordedCount}
            sub={`${totalRecordedCount} total recorded in ERP`}
            accent="#2563EB"
          />
        </div>

        {/* Filter Tabs & Search Card */}
        <Card className="overflow-hidden">
          <div className="p-3 sm:p-4 border-b-2 border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-3 bg-slate-50">
            {/* Tabs */}
            <div className="flex flex-wrap items-center gap-1.5">
              {[
                { id: "pending", label: "Pending Review", count: pendingCount, color: "bg-amber-600 text-white" },
                { id: "grn", label: "GRN Receipts", count: items.filter((i) => i.category === "grn").length, color: "bg-purple-700 text-white" },
                { id: "payment", label: "Client Payments", count: items.filter((i) => i.category === "payment").length, color: "bg-emerald-700 text-white" },
                { id: "recorded", label: "Recorded", count: totalRecordedCount, color: "bg-blue-600 text-white" },
                { id: "dismissed", label: "Dismissed", count: items.filter((i) => i.status === "dismissed").length, color: "bg-slate-700 text-white" },
                { id: "all", label: "All Items", count: items.length, color: "bg-slate-900 text-white" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setFilterTab(tab.id)}
                  className={`px-3 py-1.5 text-xs font-bold uppercase tracking-wider rounded transition-colors flex items-center gap-1.5 ${
                    filterTab === tab.id
                      ? tab.color
                      : "bg-white text-slate-700 border border-slate-300 hover:bg-slate-100"
                  }`}
                >
                  <span>{tab.label}</span>
                  <span className="text-[10px] px-1 py-0.2 bg-black/10 rounded font-mono">
                    {tab.count}
                  </span>
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div className="relative w-full md:w-80">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search subject, invoice #, UTR, sender..."
                className="w-full pl-9 pr-3 py-1.5 text-xs border-2 border-slate-300 focus:border-[#C27842] focus:outline-none font-mono"
              />
              {search && (
                <button
                  onClick={() => setSearch("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Items Feed */}
          {loading ? (
            <div className="p-12 text-center text-slate-500">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-slate-400" />
              <div className="text-sm font-semibold">Loading inbox feed...</div>
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              <Mail className="w-10 h-10 mx-auto mb-3 text-slate-300" />
              <div className="text-base font-bold text-slate-800">No email items match current filter</div>
              <p className="text-xs text-slate-500 max-w-md mx-auto mt-1">
                {items.length === 0
                  ? "Your Gmail inbox hasn't processed any GRN or Payment emails yet. Click 'Sync Gmail Now' to check for recent messages or test with 'Test Parser'."
                  : "Try clearing your search query or selecting a different filter tab above."}
              </p>
              {items.length === 0 && (
                <div className="mt-4 flex justify-center gap-3">
                  <BtnPrimary onClick={handleSync} disabled={syncing}>
                    Sync Gmail Now
                  </BtnPrimary>
                  <BtnSecondary onClick={() => setShowTestModal(true)}>
                    Test With Sample Email
                  </BtnSecondary>
                </div>
              )}
            </div>
          ) : (
            <div className="divide-y-2 divide-slate-100">
              {filteredItems.map((item) => (
                <div
                  key={item.id}
                  className={`p-4 sm:p-5 transition-colors ${
                    item.status === "pending"
                      ? "bg-white hover:bg-slate-50/80"
                      : item.status === "recorded"
                      ? "bg-slate-50/50"
                      : "bg-slate-100/50 opacity-75"
                  }`}
                >
                  <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
                    {/* Left: Classification Badges & Email Details */}
                    <div className="space-y-2.5 flex-1">
                      {/* Badge row */}
                      <div className="flex flex-wrap items-center gap-2">
                        {item.category === "grn" ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-black uppercase tracking-wider rounded bg-purple-100 text-purple-900 border border-purple-300">
                            <ClipboardCheck className="w-3.5 h-3.5 text-purple-700" />
                            Goods Receipt (GRN)
                          </span>
                        ) : item.category === "payment" ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-black uppercase tracking-wider rounded bg-emerald-100 text-emerald-900 border border-emerald-300">
                            <IndianRupee className="w-3.5 h-3.5 text-emerald-700" />
                            Client Payment
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-bold uppercase tracking-wider rounded bg-slate-200 text-slate-800">
                            <Mail className="w-3.5 h-3.5" />
                            General Email
                          </span>
                        )}

                        {/* Confidence score */}
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded font-mono border ${
                            item.confidence >= 0.8
                              ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                              : item.confidence >= 0.5
                              ? "bg-amber-50 text-amber-800 border-amber-300"
                              : "bg-red-50 text-red-800 border-red-300"
                          }`}
                          title={`Confidence score based on keyword matches and structured pattern extraction.`}
                        >
                          {Math.round(item.confidence * 100)}% Confidence
                        </span>

                        {/* Auto-recorded vs Manual vs Dismissed */}
                        {item.auto_recorded ? (
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-100 text-blue-900 border border-blue-300 flex items-center gap-1">
                            <Sparkles className="w-3 h-3 text-blue-600" />
                            Auto-Posted by Rules
                          </span>
                        ) : item.status === "recorded" ? (
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-100 text-emerald-900 border border-emerald-300 flex items-center gap-1">
                            <Check className="w-3 h-3 text-emerald-600" />
                            Approved & Recorded
                          </span>
                        ) : item.status === "dismissed" ? (
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-200 text-slate-700">
                            Dismissed: {item.dismissed_reason || "Ignored"}
                          </span>
                        ) : null}

                        {item.has_attachments && (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-300 flex items-center gap-1">
                            <Paperclip className="w-3 h-3 text-slate-500" />
                            {item.attachments?.length || 1} Attachment(s)
                          </span>
                        )}

                        <span className="text-xs text-slate-500 ml-auto font-mono">
                          {item.date ? new Date(item.date).toLocaleString("en-IN") : ""}
                        </span>
                      </div>

                      {/* Email Subject & Sender */}
                      <div>
                        <h3 className="text-sm sm:text-base font-bold text-slate-900 leading-snug">
                          {item.subject || "(No Subject)"}
                        </h3>
                        <div className="text-xs text-slate-500 mt-0.5 flex flex-wrap items-center gap-2">
                          <span>From: <strong className="text-slate-700">{item.sender}</strong></span>
                        </div>
                      </div>

                      {/* Extracted Structured Data Card */}
                      <div className="p-3 bg-slate-50 rounded border border-slate-200 text-xs">
                        {item.category === "grn" ? (
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            <div>
                              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Invoice #</div>
                              <div className="font-mono font-bold text-slate-900 text-sm mt-0.5">
                                {item.extracted_data?.invoice_no || (
                                  <span className="text-amber-600 italic">Not detected</span>
                                )}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">PO / Client</div>
                              <div className="font-semibold text-slate-800 mt-0.5">
                                {item.extracted_data?.po_number || item.extracted_data?.client_name || "—"}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Accepted Pairs</div>
                              <div className="font-mono font-bold text-emerald-700 text-sm mt-0.5">
                                {item.extracted_data?.accepted_pairs != null
                                  ? `${item.extracted_data.accepted_pairs} pairs`
                                  : `${item.extracted_data?.total_pairs || 0} pairs`}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Rejected Pairs</div>
                              <div className="font-mono font-bold text-red-600 text-sm mt-0.5">
                                {item.extracted_data?.rejected_pairs != null
                                  ? `${item.extracted_data.rejected_pairs} pairs`
                                  : "0 pairs"}
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            <div>
                              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Amount Received</div>
                              <div className="font-mono font-bold text-emerald-700 text-base mt-0.5">
                                {item.extracted_data?.amount ? inr(item.extracted_data.amount) : "—"}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Payment Date</div>
                              <div className="font-mono font-bold text-slate-900 mt-0.5">
                                {item.extracted_data?.payment_date || "—"}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">UTR / Ref #</div>
                              <div className="font-mono font-bold text-slate-800 mt-0.5 truncate" title={item.extracted_data?.utr_number}>
                                {item.extracted_data?.utr_number || "—"}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Mode / Client</div>
                              <div className="font-semibold text-slate-800 mt-0.5 truncate">
                                {item.extracted_data?.payment_mode || "NEFT/RTGS"} {item.extracted_data?.client_name ? `· ${item.extracted_data.client_name}` : ""}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Line items or rejection reason */}
                        {item.extracted_data?.rejection_reason && (
                          <div className="mt-2 pt-2 border-t border-slate-200 text-red-700 font-semibold text-[11px]">
                            Rejection Note: {item.extracted_data.rejection_reason}
                          </div>
                        )}
                      </div>

                      {/* Matching Diagnostics & Reasons */}
                      <div className="flex flex-wrap items-center gap-2 pt-1">
                        {item.matched_invoice_no ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                            Matched Invoice: {item.matched_invoice_no}
                          </span>
                        ) : item.category === "grn" ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-800 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                            <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                            No exact invoice auto-matched (Select via Edit & Record)
                          </span>
                        ) : null}

                        {item.matched_bank_name && (
                          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-blue-800 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                            <Building2 className="w-3.5 h-3.5 text-blue-600" />
                            Target Bank: {item.matched_bank_name}
                          </span>
                        )}

                        {/* Classification reasons tags */}
                        {item.classification_reasons?.map((reason, idx) => (
                          <span key={idx} className="text-[10px] text-slate-600 bg-slate-200/80 px-2 py-0.5 rounded">
                            {reason}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Right: Actions */}
                    <div className="lg:w-48 flex-shrink-0 flex flex-col justify-start gap-2 pt-2 lg:pt-0 lg:border-l-2 lg:border-slate-100 lg:pl-4">
                      {item.status === "pending" ? (
                        <>
                          <button
                            onClick={() => handleApprove(item)}
                            disabled={actionLoading}
                            className="w-full bg-[#16A34A] hover:bg-[#0F7A36] text-white text-xs font-bold uppercase tracking-wider py-2 px-3 rounded shadow-sm flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                            title="Directly approve and record this item into the ERP core database"
                          >
                            <Check className="w-4 h-4" />
                            <span>Approve & Record</span>
                          </button>
                          <button
                            onClick={() => openEditModal(item)}
                            disabled={actionLoading}
                            className="w-full bg-white hover:bg-slate-100 text-slate-800 border-2 border-slate-300 text-xs font-bold uppercase tracking-wider py-1.5 px-3 rounded transition-colors"
                            title="Modify invoice allocation, quantities, or bank account before recording"
                          >
                            Edit & Record
                          </button>
                          <button
                            onClick={() => handleDismiss(item)}
                            disabled={actionLoading}
                            className="w-full text-slate-500 hover:text-red-700 text-xs font-semibold py-1 px-3 text-center transition-colors"
                          >
                            Dismiss
                          </button>
                        </>
                      ) : item.status === "recorded" ? (
                        <div className="text-center p-2 bg-emerald-50 border border-emerald-200 rounded">
                          <CheckCircle2 className="w-5 h-5 text-emerald-600 mx-auto mb-1" />
                          <div className="text-xs font-bold text-emerald-900">Recorded in ERP</div>
                          {item.recorded_record_id && (
                            <div className="font-mono text-[11px] font-bold text-emerald-700 mt-0.5">
                              ID: {item.recorded_record_id}
                            </div>
                          )}
                          <div className="text-[10px] text-emerald-600 mt-0.5">
                            {item.recorded_at ? new Date(item.recorded_at).toLocaleDateString() : ""}
                          </div>
                        </div>
                      ) : (
                        <div className="text-center p-2 bg-slate-100 border border-slate-200 rounded">
                          <XCircle className="w-5 h-5 text-slate-400 mx-auto mb-1" />
                          <div className="text-xs font-semibold text-slate-600">Dismissed</div>
                          <button
                            onClick={() => {
                              item.status = "pending";
                              setItems([...items]);
                            }}
                            className="text-[10px] text-blue-600 font-bold hover:underline mt-1"
                          >
                            Reopen
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* ─────────────────────────────────────────────────────────────
          MODAL: EDIT & RECORD MODAL
      ───────────────────────────────────────────────────────────── */}
      {editItem && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 overflow-y-auto">
          <Card className="max-w-xl w-full p-6 shadow-2xl relative">
            <button
              onClick={() => setEditItem(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-700"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-2 mb-4">
              {editItem.category === "grn" ? (
                <ClipboardCheck className="w-5 h-5 text-purple-700" />
              ) : (
                <IndianRupee className="w-5 h-5 text-emerald-700" />
              )}
              <h2 className="text-lg font-bold text-slate-900">
                {editItem.category === "grn" ? "Record Goods Receipt Note (GRN)" : "Record Client Payment"}
              </h2>
            </div>

            <p className="text-xs text-slate-500 mb-4">
              Review and adjust the extracted values from email: <strong className="text-slate-700">{editItem.subject}</strong>
            </p>

            <div className="space-y-4">
              {/* Common: Target Invoice Selection */}
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-600 tracking-wider block mb-1">
                  Target ERP Invoice <span className="text-red-500">*</span>
                </label>
                <select
                  value={editForm.override_invoice_id || ""}
                  onChange={(e) => setEditForm({ ...editForm, override_invoice_id: e.target.value })}
                  className="w-full border-2 border-slate-300 p-2 text-xs font-mono focus:border-[#C27842] focus:outline-none"
                >
                  <option value="">-- Select Matched Invoice --</option>
                  {invoices.map((inv) => (
                    <option key={inv.id} value={inv.id}>
                      {inv.invoice_no} · {inv.client_name} · Total: {inr(inv.net_amount || inv.total_amount)} · Outstanding: {inr(inv.outstanding || 0)} {inv.grn_recorded ? "(GRN Done)" : "(Awaiting GRN)"}
                    </option>
                  ))}
                </select>
              </div>

              {/* GRN specific fields */}
              {editItem.category === "grn" && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <Input
                      label="Accepted Quantity (Pairs)"
                      type="number"
                      value={editForm.override_accepted_qty}
                      onChange={(e) => setEditForm({ ...editForm, override_accepted_qty: parseInt(e.target.value, 10) || 0 })}
                    />
                    <Input
                      label="Rejected Quantity (Pairs)"
                      type="number"
                      value={editForm.override_rejected_qty}
                      onChange={(e) => setEditForm({ ...editForm, override_rejected_qty: parseInt(e.target.value, 10) || 0 })}
                    />
                  </div>
                  <div>
                    <label className="text-[10px] uppercase font-bold text-slate-600 tracking-wider block mb-1">
                      Inspection / Rejection Remarks
                    </label>
                    <textarea
                      value={editForm.remarks || ""}
                      onChange={(e) => setEditForm({ ...editForm, remarks: e.target.value })}
                      rows={2}
                      className="w-full border-2 border-slate-300 p-2 text-xs focus:border-[#C27842] focus:outline-none"
                      placeholder="Notes on rejection, box condition, or receiving details"
                    />
                  </div>
                </>
              )}

              {/* Payment specific fields */}
              {editItem.category === "payment" && (
                <>
                  <div>
                    <label className="text-[10px] uppercase font-bold text-slate-600 tracking-wider block mb-1">
                      Target Bank Account <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={editForm.override_bank_account_id || ""}
                      onChange={(e) => setEditForm({ ...editForm, override_bank_account_id: e.target.value })}
                      className="w-full border-2 border-slate-300 p-2 text-xs font-mono focus:border-[#C27842] focus:outline-none"
                    >
                      <option value="">-- Select Bank Account --</option>
                      {bankAccounts.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.bank_name || b.account_name} ({b.account_number}) · Bal: {inr(b.current_balance)}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <Input
                      label="Payment Amount (₹)"
                      type="number"
                      value={editForm.override_amount}
                      onChange={(e) => setEditForm({ ...editForm, override_amount: parseFloat(e.target.value) || 0 })}
                    />
                    <Input
                      label="Payment Date"
                      type="date"
                      value={editForm.override_payment_date}
                      onChange={(e) => setEditForm({ ...editForm, override_payment_date: e.target.value })}
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <Input
                      label="UTR / Reference Number"
                      value={editForm.override_utr}
                      onChange={(e) => setEditForm({ ...editForm, override_utr: e.target.value })}
                    />
                    <div>
                      <label className="text-[10px] uppercase font-bold text-slate-600 tracking-wider block mb-1">
                        Payment Mode
                      </label>
                      <select
                        value={editForm.payment_mode || "Bank Transfer"}
                        onChange={(e) => setEditForm({ ...editForm, payment_mode: e.target.value })}
                        className="w-full border-2 border-slate-300 p-2 text-xs focus:border-[#C27842] focus:outline-none"
                      >
                        <option value="Bank Transfer">Bank Transfer</option>
                        <option value="NEFT">NEFT</option>
                        <option value="RTGS">RTGS</option>
                        <option value="IMPS">IMPS</option>
                        <option value="UPI">UPI</option>
                        <option value="Cheque">Cheque</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="text-[10px] uppercase font-bold text-slate-600 tracking-wider block mb-1">
                      Remarks / Narration
                    </label>
                    <textarea
                      value={editForm.remarks || ""}
                      onChange={(e) => setEditForm({ ...editForm, remarks: e.target.value })}
                      rows={2}
                      className="w-full border-2 border-slate-300 p-2 text-xs focus:border-[#C27842] focus:outline-none"
                    />
                  </div>
                </>
              )}
            </div>

            <div className="mt-6 flex justify-end gap-3 pt-4 border-t-2 border-slate-100">
              <BtnSecondary onClick={() => setEditItem(null)}>Cancel</BtnSecondary>
              <BtnPrimary onClick={handleSaveEdit} disabled={actionLoading}>
                {actionLoading ? "Recording to ERP..." : "Confirm & Record into ERP"}
              </BtnPrimary>
            </div>
          </Card>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          MODAL: AUTO-POSTING RULES
      ───────────────────────────────────────────────────────────── */}
      {showRulesModal && rules && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 overflow-y-auto">
          <Card className="max-w-lg w-full p-6 shadow-2xl relative">
            <button
              onClick={() => setShowRulesModal(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-700"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-2 mb-2">
              <Sliders className="w-5 h-5 text-[#C27842]" />
              <h2 className="text-lg font-bold text-slate-900">Auto-Posting Rules</h2>
            </div>
            <p className="text-xs text-slate-500 mb-6">
              Configure autonomous recording into the ERP core database when emails match with high confidence.
            </p>

            <form onSubmit={handleSaveRules} className="space-y-5">
              {/* GRN Auto-post */}
              <div className="p-4 bg-purple-50/60 rounded border border-purple-200 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-bold text-purple-950">Auto-Record GRNs</div>
                    <div className="text-xs text-purple-700">
                      Directly record Goods Receipt Notes when email contains verified quantities.
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={rules.auto_record_grn || false}
                    onChange={(e) => setRules({ ...rules, auto_record_grn: e.target.checked })}
                    className="w-5 h-5 accent-purple-700 rounded cursor-pointer"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-xs font-semibold text-purple-900 mb-1">
                    <span>Minimum Confidence Threshold</span>
                    <span className="font-mono font-bold">
                      {Math.round((rules.min_confidence_grn || 0.85) * 100)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0.5"
                    max="1.0"
                    step="0.05"
                    value={rules.min_confidence_grn || 0.85}
                    onChange={(e) => setRules({ ...rules, min_confidence_grn: parseFloat(e.target.value) })}
                    className="w-full accent-purple-700 cursor-pointer"
                  />
                </div>
              </div>

              {/* Payment Auto-post */}
              <div className="p-4 bg-emerald-50/60 rounded border border-emerald-200 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-bold text-emerald-950">Auto-Record Client Payments</div>
                    <div className="text-xs text-emerald-700">
                      Directly credit bank ledger and invoice allocation upon verified bank alert/remittance.
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={rules.auto_record_payment || false}
                    onChange={(e) => setRules({ ...rules, auto_record_payment: e.target.checked })}
                    className="w-5 h-5 accent-emerald-700 rounded cursor-pointer"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-xs font-semibold text-emerald-900 mb-1">
                    <span>Minimum Confidence Threshold</span>
                    <span className="font-mono font-bold">
                      {Math.round((rules.min_confidence_payment || 0.85) * 100)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0.5"
                    max="1.0"
                    step="0.05"
                    value={rules.min_confidence_payment || 0.85}
                    onChange={(e) => setRules({ ...rules, min_confidence_payment: parseFloat(e.target.value) })}
                    className="w-full accent-emerald-700 cursor-pointer"
                  />
                </div>
              </div>

              {/* Require Exact Match */}
              <div className="p-4 bg-slate-50 rounded border border-slate-200 flex items-center justify-between">
                <div>
                  <div className="text-xs font-bold text-slate-800">Require Exact Invoice Match</div>
                  <div className="text-[11px] text-slate-500">
                    Only auto-record if the invoice number strictly matches an active ERP invoice.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={rules.require_exact_invoice_match !== false}
                  onChange={(e) => setRules({ ...rules, require_exact_invoice_match: e.target.checked })}
                  className="w-5 h-5 accent-slate-800 rounded cursor-pointer"
                />
              </div>

              <div className="flex justify-end gap-3 pt-3">
                <BtnSecondary type="button" onClick={() => setShowRulesModal(false)}>
                  Cancel
                </BtnSecondary>
                <BtnPrimary type="submit">Save Rules</BtnPrimary>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          MODAL: TEST EMAIL PARSER
      ───────────────────────────────────────────────────────────── */}
      {showTestModal && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 overflow-y-auto">
          <Card className="max-w-2xl w-full p-6 shadow-2xl relative">
            <button
              onClick={() => {
                setShowTestModal(false);
                setTestResult(null);
              }}
              className="absolute top-4 right-4 text-slate-400 hover:text-slate-700"
            >
              <X className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-5 h-5 text-purple-600" />
              <h2 className="text-lg font-bold text-slate-900">Test Email Parser</h2>
            </div>
            <p className="text-xs text-slate-500 mb-4">
              Paste email text or delivery challan information to test real-time classification, entity extraction, and ERP invoice matching.
            </p>

            {/* Quick templates */}
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <span className="text-[10px] font-bold text-slate-500 uppercase">Insert Sample:</span>
              <button
                type="button"
                onClick={() =>
                  setTestForm({
                    subject: "GRN Confirmation for INV-2026-001 / PO 4412",
                    sender: "receiving@bataindia.com",
                    body_text:
                      "Dear SSK Footwear,\n\nWe have received shipment against Invoice INV-2026-001.\nDispatched Qty: 600 pairs\nAccepted Qty: 580 pairs\nRejected Qty: 20 pairs due to sole pasting defect on size 8.\n\nPlease find the attached GRN delivery note.\n\nRegards,\nWarehouse Team",
                  })
                }
                className="text-[11px] font-bold text-purple-700 bg-purple-50 hover:bg-purple-100 border border-purple-200 px-2.5 py-1 rounded transition-colors"
              >
                + Sample GRN Email
              </button>
              <button
                type="button"
                onClick={() =>
                  setTestForm({
                    subject: "Payment Advice: NEFT / UTR UTIB202610240982 for INV-2026-001",
                    sender: "accounts@reliancefootprint.in",
                    body_text:
                      "Dear SSK Footwear,\n\nWe have credited INR 1,50,000 to your bank account via NEFT on 24-Oct-2026.\nUTR Number: UTIB202610240982\nAccount: SSK Footwear HDFC Operating A/c\nInvoice Reference: INV-2026-001\n\nKindly acknowledge receipt.\n\nAccounts Dept",
                  })
                }
                className="text-[11px] font-bold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 px-2.5 py-1 rounded transition-colors"
              >
                + Sample NEFT Payment
              </button>
            </div>

            <form onSubmit={handleRunTest} className="space-y-3">
              <Input
                label="Email Subject"
                value={testForm.subject}
                onChange={(e) => setTestForm({ ...testForm, subject: e.target.value })}
                placeholder="e.g. GRN for INV-2026-001"
              />
              <Input
                label="Sender Email Address"
                value={testForm.sender}
                onChange={(e) => setTestForm({ ...testForm, sender: e.target.value })}
                placeholder="e.g. stores@clientcorp.com"
              />
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-600 tracking-wider block mb-1">
                  Email Body Text
                </label>
                <textarea
                  value={testForm.body_text}
                  onChange={(e) => setTestForm({ ...testForm, body_text: e.target.value })}
                  rows={4}
                  className="w-full border-2 border-slate-300 p-2 text-xs font-mono focus:border-[#C27842] focus:outline-none"
                  placeholder="Paste raw email body, dispatch notice, or bank alert message..."
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <BtnSecondary
                  type="button"
                  onClick={() => {
                    setShowTestModal(false);
                    setTestResult(null);
                  }}
                >
                  Close
                </BtnSecondary>
                <BtnPrimary type="submit" disabled={testing}>
                  {testing ? "Analyzing..." : "Analyze & Parse"}
                </BtnPrimary>
              </div>
            </form>

            {/* Test Results View */}
            {testResult && (
              <div className="mt-5 pt-4 border-t-2 border-slate-200 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-600">Classification:</span>
                    <span
                      className={`text-xs font-black uppercase px-2.5 py-0.5 rounded font-mono ${
                        testResult.category?.toLowerCase() === "grn"
                          ? "bg-purple-100 text-purple-900 border border-purple-300"
                          : testResult.category?.toLowerCase() === "payment"
                          ? "bg-emerald-100 text-emerald-900 border border-emerald-300"
                          : "bg-slate-200 text-slate-800"
                      }`}
                    >
                      {testResult.category}
                    </span>
                    <span className="text-xs font-bold font-mono text-slate-700">
                      ({Math.round((testResult.confidence || 0) * 100)}% match)
                    </span>
                  </div>
                </div>

                <div className="p-3 bg-slate-50 border border-slate-200 rounded font-mono text-xs space-y-1">
                  <div className="font-bold text-slate-700 mb-1 font-sans uppercase text-[10px]">Extracted Entities:</div>
                  <pre className="text-[11px] text-slate-800 overflow-x-auto">
                    {JSON.stringify(testResult.extracted_data, null, 2)}
                  </pre>
                </div>

                <div className="flex flex-wrap gap-2 text-xs">
                  {(testResult.matched_invoice_no || testResult.erp_match?.matched_invoice?.invoice_no) ? (
                    <span className="inline-flex items-center gap-1 font-bold text-emerald-800 bg-emerald-50 px-2 py-1 rounded border border-emerald-300">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                      Matched Invoice in ERP: {testResult.matched_invoice_no || testResult.erp_match?.matched_invoice?.invoice_no}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 font-semibold text-amber-800 bg-amber-50 px-2 py-1 rounded border border-amber-300">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                      No existing invoice auto-matched
                    </span>
                  )}

                  {(testResult.matched_bank_name || testResult.erp_match?.matched_bank_account?.name || testResult.erp_match?.matched_bank_account?.bank_name) && (
                    <span className="inline-flex items-center gap-1 font-bold text-blue-800 bg-blue-50 px-2 py-1 rounded border border-blue-300">
                      <Building2 className="w-3.5 h-3.5 text-blue-600" />
                      Matched Bank Account: {testResult.matched_bank_name || testResult.erp_match?.matched_bank_account?.name || testResult.erp_match?.matched_bank_account?.bank_name}
                    </span>
                  )}
                </div>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
