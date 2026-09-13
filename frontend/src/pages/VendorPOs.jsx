import { useEffect, useState, Fragment } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { http, inr } from "../lib/api";
import {
  PageHeader,
  Card,
  Badge,
  BtnPrimary,
  BtnSecondary,
} from "../components/ui-kit";
import {
  FileText,
  Plus,
  Pencil,
  Trash2,
  X,
  AlertCircle,
  Calendar,
  FilePlus,
  CreditCard,
  BookOpen,
  ArrowUpRight,
  ArrowDownLeft,
  Clock,
  CheckCircle2,
  Wallet,
  Filter,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { useAuth } from "../lib/auth";

const STATUS_COLOR = {
  draft: "slate",
  sent: "blue",
  partially_received: "yellow",
  received: "green",
  cancelled: "red",
};

const PAYMENT_STATUS_COLOR = {
  paid: "green",
  partially_paid: "yellow",
  unpaid: "slate",
};

const EMPTY_LINE = { material_id: "", quantity: 0, rate: 0, amount: 0 };

export default function VendorPOs() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const canWrite = ["admin", "manager"].includes(user?.role);

  // Active Top-Level View: "pos" (Purchase Orders) | "ledgers" (Vendor Ledgers & Ageing)
  const [activeTab, setActiveTab] = useState("pos");

  const [pos, setPos] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [cashAccounts, setCashAccounts] = useState([]);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("all");
  const [filterPaymentStatus, setFilterPaymentStatus] = useState("all");

  // Drawer for Add / Edit PO
  const [drawer, setDrawer] = useState(null); // null | { mode: "add" | "edit", po?: {} }
  const [form, setForm] = useState({
    vendor_id: "",
    status: "draft",
    expected_delivery_date: "",
    notes: "",
    line_items: [],
  });

  // Modal for Receiving Materials
  const [receiveModal, setReceiveModal] = useState(null); // null | po
  const [receiveForm, setReceiveForm] = useState({ receipt_id: "", items: [] });

  // Expandable PO Table Rows for Material Delivery Breakdown
  const [expandedRows, setExpandedRows] = useState({});
  const toggleRowExpand = (poId) => {
    setExpandedRows((prev) => ({
      ...prev,
      [poId]: !prev[poId],
    }));
  };

  // Modal for Recording Payment
  const [paymentModal, setPaymentModal] = useState(null); // null | { po?: {}, vendor_id: string, vendor_name: string, balance_due?: number, total_amount?: number }
  const [paymentForm, setPaymentForm] = useState({
    amount: "",
    payment_date: new Date().toISOString().slice(0, 10),
    mode: "NEFT",
    account_type: "bank",
    bank_account_id: "",
    cash_account_id: "",
    reference: "",
    bank: "",
    notes: "",
  });

  // Drawer for Vendor Ledger
  const [ledgerDrawer, setLedgerDrawer] = useState(null); // null | { vendor_id: string, vendor_name: string }
  const [ledgerData, setLedgerData] = useState(null);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [ledgerFilter, setLedgerFilter] = useState("all"); // "all" | "receive" | "payment"

  // Ageing Data for "Vendor Ledgers & Ageing" Tab
  const [ageingData, setAgeingData] = useState(null);
  const [ageingLoading, setAgeingLoading] = useState(false);
  const [ageingSearch, setAgeingSearch] = useState("");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [poRes, vendorRes, matRes, bankRes, cashRes] = await Promise.all([
        http.get("/vendor-pos"),
        http.get("/vendors?include_inactive=true"),
        http.get("/materials"),
        http.get("/banking/accounts", { params: { active: true } }).catch(() => ({ data: [] })),
        http.get("/banking/cash-accounts").catch(() => ({ data: [] })),
      ]);
      setPos(poRes.data || []);
      setVendors(vendorRes.data || []);
      setMaterials(matRes.data || []);
      const bList = Array.isArray(bankRes?.data)
        ? bankRes.data
        : Array.isArray(bankRes?.data?.items)
        ? bankRes.data.items
        : [];
      setBankAccounts(bList);
      const cList = Array.isArray(cashRes?.data?.cash_accounts)
        ? cashRes.data.cash_accounts
        : Array.isArray(cashRes?.data?.items)
        ? cashRes.data.items
        : Array.isArray(cashRes?.data)
        ? cashRes.data
        : [];
      setCashAccounts(cList);
    } catch (e) {
      console.error("Failed to load PO and banking data", e);
    }
  };

  const loadAgeing = async () => {
    setAgeingLoading(true);
    try {
      const res = await http.get("/vendors/ageing");
      setAgeingData(res.data || null);
    } catch (e) {
      console.error("Failed to load vendor ageing", e);
    } finally {
      setAgeingLoading(false);
    }
  };

  const loadLedger = async (vid) => {
    setLedgerLoading(true);
    try {
      const res = await http.get(`/vendors/${vid}/ledger`);
      setLedgerData(res.data);
    } catch (e) {
      console.error("Failed to load ledger", e);
    } finally {
      setLedgerLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (activeTab === "ledgers") {
      loadAgeing();
    }
  }, [activeTab]);

  // Handle prefilled data from shortage redirect
  useEffect(() => {
    if (
      location.state &&
      location.state.prefill &&
      vendors.length > 0 &&
      materials.length > 0
    ) {
      const { vendor_id, items } = location.state.prefill;

      // Clear location state to prevent triggering on page refreshes
      navigate(location.pathname, { replace: true, state: {} });

      const mappedLines = items.map((it) => {
        const mat = materials.find(
          (m) => m.id === it.material_id || m.code === it.code,
        );
        return {
          material_id: mat ? mat.id : "",
          quantity: it.shortage || 0,
          rate: mat ? mat.rate : 0,
          amount: (it.shortage || 0) * (mat ? mat.rate : 0),
        };
      });

      setForm({
        vendor_id: vendor_id || "",
        status: "draft",
        expected_delivery_date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
          .toISOString()
          .split("T")[0],
        notes: "Raised automatically from stock shortage check.",
        line_items: mappedLines,
      });
      setError("");
      setDrawer({ mode: "add" });
    }
  }, [location.state, vendors, materials, navigate, location.pathname]);

  useEffect(() => {
    if (location.state && location.state.search) {
      setSearch(location.state.search);
    }
  }, [location.state]);

  const filtered = pos.filter((po) => {
    const vName = po.vendor_name || "";
    const poNo = po.po_number || "";
    const custPo = po.customer_po_number || "";
    const styleCode = po.style_code || "";
    const matchesSearch = `${poNo} ${vName} ${custPo} ${styleCode}`
      .toLowerCase()
      .includes(search.toLowerCase());
    const matchesStatus = filterStatus === "all" || po.status === filterStatus;
    const matchesPayment =
      filterPaymentStatus === "all" || po.payment_status === filterPaymentStatus;
    return matchesSearch && matchesStatus && matchesPayment;
  });

  // Calculate totals
  const totalCount = pos.length;
  const draftCount = pos.filter((p) => p.status === "draft").length;
  const sentCount = pos.filter(
    (p) => p.status === "sent" || p.status === "partially_received",
  ).length;
  const receivedCount = pos.filter((p) => p.status === "received").length;

  // Financial aggregates for POs
  const totalPOValue = pos.reduce((s, p) => s + (p.total_amount || 0), 0);
  const totalPOPaid = pos.reduce((s, p) => s + (p.paid_amount || 0), 0);
  const totalPOBalanceDue = pos.reduce((s, p) => s + (p.balance_due || 0), 0);

  const openAdd = () => {
    setForm({
      vendor_id: vendors[0]?.id || "",
      status: "draft",
      expected_delivery_date: "",
      notes: "",
      line_items: [{ ...EMPTY_LINE }],
    });
    setError("");
    setDrawer({ mode: "add" });
  };

  const openEdit = (po) => {
    setForm({
      vendor_id: po.vendor_id || "",
      status: po.status || "draft",
      expected_delivery_date: po.expected_delivery_date || "",
      notes: po.notes || "",
      line_items: (po.line_items || []).map((li) => ({
        material_id: li.material_id || "",
        quantity: li.quantity || 0,
        rate: li.rate || 0,
        amount: li.amount || 0,
        received_quantity: li.received_quantity || 0,
      })),
    });
    setError("");
    setDrawer({ mode: "edit", po });
  };

  const openReceive = (po) => {
    const rId =
      "rcpt_" +
      Date.now().toString(36) +
      Math.random().toString(36).substring(2, 7);
    setReceiveForm({
      receipt_id: rId,
      items: (po.line_items || []).map((li) => {
        const mat = materials.find((m) => m.id === li.material_id);
        const ordered = Number(li.quantity || 0);
        const received = Number(li.received_quantity || 0);
        const remaining = Math.max(
          0,
          Math.round((ordered - received) * 10000) / 10000
        );
        return {
          material_id: li.material_id,
          quantity: 0,
          material_code:
            mat?.code || li.material_code || "",
          material_name:
            mat?.name || li.material_name || "",
          ordered,
          received,
          remaining,
        };
      }),
    });
    setReceiveModal(po);
    setError("");
  };

  const handleReceive = async () => {
    for (const item of receiveForm.items) {
      const remaining = Math.max(
        0,
        Math.round((Number(item.ordered) - Number(item.received)) * 10000) / 10000
      );
      const qty = Number(item.quantity || 0);
      if (qty > remaining) {
        setError(
          `Cannot receive ${qty} for '${item.material_name || item.material_code}'. Maximum receivable is ${remaining}.`
        );
        return;
      }
    }

    const validItems = receiveForm.items.filter(
      (item) => Number(item.quantity) > 0,
    );
    if (validItems.length === 0) {
      setError(
        "Please enter a positive quantity to receive for at least one item.",
      );
      return;
    }

    setSaving(true);
    setError("");
    try {
      const payload = {
        receipt_id: receiveForm.receipt_id,
        items: validItems.map((item) => ({
          material_id: item.material_id,
          quantity: Number(item.quantity),
        })),
      };
      await http.post(`/vendor-pos/${receiveModal.id}/receive`, payload);
      await load();
      setReceiveModal(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  // Payment Handlers
  const openPayModal = (poOrVendor) => {
    const isPO = !!poOrVendor.po_number;
    const balance = isPO
      ? poOrVendor.balance_due ?? poOrVendor.total_amount ?? 0
      : poOrVendor.outstanding_balance ?? 0;

    const defaultBank = bankAccounts && bankAccounts.length > 0 ? bankAccounts[0] : null;
    const defaultBankId = defaultBank ? (defaultBank.id || defaultBank._id || "") : "";
    const defaultBankName = defaultBank
      ? `${defaultBank.name} (${defaultBank.bank_name || "Bank"}${defaultBank.account_number_last4 ? ` ••${defaultBank.account_number_last4}` : ""})`
      : "";

    setPaymentModal({
      po: isPO ? poOrVendor : null,
      vendor_id: poOrVendor.vendor_id || poOrVendor.id,
      vendor_name: poOrVendor.vendor_name || poOrVendor.name,
      total_amount: isPO ? poOrVendor.total_amount : undefined,
      paid_amount: isPO ? poOrVendor.paid_amount : undefined,
      balance_due: balance,
    });
    setPaymentForm({
      amount: balance > 0 ? String(balance) : "",
      payment_date: new Date().toISOString().slice(0, 10),
      mode: "NEFT",
      account_type: "bank",
      bank_account_id: defaultBankId,
      cash_account_id: "",
      reference: "",
      bank: defaultBankName,
      notes: isPO ? `Payment for PO ${poOrVendor.po_number}` : "",
    });
    setError("");
  };

  const handleAccountChange = (val) => {
    if (!val) {
      setPaymentForm((f) => ({
        ...f,
        bank_account_id: "",
        cash_account_id: "",
        account_type: "bank",
        bank: "",
      }));
      return;
    }
    if (val.startsWith("cash_")) {
      const cid = val.replace("cash_", "");
      const ca = cashAccounts.find((c) => (c.id || c._id) === cid);
      setPaymentForm((f) => ({
        ...f,
        cash_account_id: cid,
        bank_account_id: "",
        account_type: "cash",
        bank: ca?.name || "Cash Account",
        mode: "Cash",
      }));
    } else if (val === "custom") {
      setPaymentForm((f) => ({
        ...f,
        bank_account_id: "",
        cash_account_id: "",
        account_type: "bank",
        bank: "",
      }));
    } else {
      const ba = bankAccounts.find((b) => (b.id || b._id) === val);
      const bName = ba
        ? `${ba.name} (${ba.bank_name || "Bank"}${ba.account_number_last4 ? ` ••${ba.account_number_last4}` : ""})`
        : "";
      setPaymentForm((f) => ({
        ...f,
        bank_account_id: val,
        cash_account_id: "",
        account_type: "bank",
        bank: bName,
        mode: f.mode === "Cash" ? "NEFT" : f.mode,
      }));
    }
  };

  const handlePaymentModeChange = (newMode) => {
    if (newMode === "Cash") {
      if (cashAccounts.length > 0) {
        const ca = cashAccounts[0];
        const cid = ca.id || ca._id;
        setPaymentForm((f) => ({
          ...f,
          mode: newMode,
          account_type: "cash",
          cash_account_id: cid,
          bank_account_id: "",
          bank: ca.name || "Cash Account",
        }));
        return;
      }
    } else if (paymentForm.account_type === "cash") {
      const ba = bankAccounts.length > 0 ? bankAccounts[0] : null;
      const bid = ba ? (ba.id || ba._id || "") : "";
      const bName = ba ? `${ba.name} (${ba.bank_name || "Bank"}${ba.account_number_last4 ? ` ••${ba.account_number_last4}` : ""})` : "";
      setPaymentForm((f) => ({
        ...f,
        mode: newMode,
        account_type: "bank",
        bank_account_id: bid,
        cash_account_id: "",
        bank: bName,
      }));
      return;
    }
    setPaymentForm((f) => ({ ...f, mode: newMode }));
  };

  useEffect(() => {
    if (
      paymentModal &&
      !paymentForm.bank_account_id &&
      !paymentForm.cash_account_id &&
      !paymentForm.bank &&
      bankAccounts.length > 0
    ) {
      const b = bankAccounts[0];
      const bid = b.id || b._id || "";
      const bName = `${b.name} (${b.bank_name || "Bank"}${b.account_number_last4 ? ` ••${b.account_number_last4}` : ""})`;
      setPaymentForm((f) => ({
        ...f,
        bank_account_id: bid,
        bank: bName,
        account_type: "bank",
      }));
    }
  }, [paymentModal, bankAccounts]);

  const handleRecordPayment = async (e) => {
    e?.preventDefault();
    const amt = parseFloat(paymentForm.amount);
    if (isNaN(amt) || amt <= 0) {
      setError("Please enter a valid payment amount greater than zero.");
      return;
    }

    setSaving(true);
    setError("");
    try {
      const payload = {
        amount: amt,
        payment_date: paymentForm.payment_date,
        mode: paymentForm.mode,
        reference: paymentForm.reference,
        bank: paymentForm.bank,
        bank_account_id: paymentForm.bank_account_id || undefined,
        account_type: paymentForm.account_type || undefined,
        cash_account_id: paymentForm.cash_account_id || undefined,
        notes: paymentForm.notes,
      };

      if (paymentModal.po?.id) {
        // Record against specific PO
        await http.post(`/vendor-pos/${paymentModal.po.id}/payments`, payload);
      } else {
        // Record directly against vendor
        await http.post(`/vendors/${paymentModal.vendor_id}/payments`, payload);
      }

      // Refresh POs & Ageing
      await load();
      if (activeTab === "ledgers") {
        await loadAgeing();
      }
      // If ledger drawer is currently open for this vendor, refresh ledger data
      if (ledgerDrawer && ledgerDrawer.vendor_id === paymentModal.vendor_id) {
        await loadLedger(paymentModal.vendor_id);
      }

      setPaymentModal(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  // Ledger Drawer Handlers
  const openVendorLedger = (vendorId, vendorName) => {
    setLedgerDrawer({ vendor_id: vendorId, vendor_name: vendorName });
    setLedgerFilter("all");
    loadLedger(vendorId);
  };

  const closeDrawer = () => setDrawer(null);

  const addLine = () => {
    setForm((f) => ({
      ...f,
      line_items: [...f.line_items, { ...EMPTY_LINE }],
    }));
  };

  const removeLine = (idx) => {
    setForm((f) => ({
      ...f,
      line_items: f.line_items.filter((_, i) => i !== idx),
    }));
  };

  const handleLineChange = (idx, key, val) => {
    setForm((f) => {
      const nextLines = [...f.line_items];
      const line = { ...nextLines[idx] };
      line[key] = val;

      if (key === "material_id") {
        const mat = materials.find((m) => m.id === val);
        if (mat) {
          line.rate = mat.rate;
        }
      }

      const q = Number(line.quantity || 0);
      const r = Number(line.rate || 0);
      line.amount = roundTo2(q * r);

      nextLines[idx] = line;
      return { ...f, line_items: nextLines };
    });
  };

  const handleSave = async () => {
    if (!form.vendor_id) {
      setError("Please select a vendor.");
      return;
    }
    const validLines = form.line_items.filter(
      (li) => li.material_id && Number(li.quantity) > 0,
    );
    if (validLines.length === 0) {
      setError(
        "PO must contain at least one line item with a material and positive quantity.",
      );
      return;
    }

    setSaving(true);
    setError("");
    try {
      const payload = {
        vendor_id: form.vendor_id,
        status: form.status,
        expected_delivery_date: form.expected_delivery_date || "",
        notes: form.notes || "",
        line_items: validLines.map((li) => ({
          material_id: li.material_id,
          quantity: Number(li.quantity),
          rate: Number(li.rate),
          amount: Number(li.amount),
          received_quantity: Number(li.received_quantity || 0),
        })),
      };

      if (drawer.mode === "add") {
        await http.post("/vendor-pos", payload);
      } else {
        await http.patch(`/vendor-pos/${drawer.po.id}`, payload);
      }
      await load();
      closeDrawer();
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (po) => {
    if (!window.confirm(`Are you sure you want to delete ${po.po_number}?`))
      return;
    try {
      await http.delete(`/vendor-pos/${po.id}`);
      await load();
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  };

  const formGrandTotal = form.line_items.reduce(
    (s, li) => s + (li.amount || 0),
    0,
  );

  const roundTo2 = (num) => Math.round((num + Number.EPSILON) * 100) / 100;

  // Filtered transactions in Vendor Ledger Drawer
  const filteredTransactions = (ledgerData?.transactions || []).filter((tx) => {
    if (ledgerFilter === "all") return true;
    return tx.type === ledgerFilter;
  });

  // Filtered vendors for Ageing View
  const filteredAgeingVendors = (ageingData?.vendors || []).filter((v) => {
    if (!ageingSearch) return true;
    return v.vendor_name.toLowerCase().includes(ageingSearch.toLowerCase());
  });

  return (
    <div>
      <PageHeader
        title="Vendor Purchase Orders & Ledgers"
        subtitle="Accounts Payable / Material Procurements, PO Payments & Vendor Ledgers"
        testId="vendor-pos-header"
        action={
          canWrite && (
            <BtnPrimary onClick={openAdd} data-testid="add-vendor-po-btn" className="px-3 sm:px-5">
              <FilePlus className="w-3.5 h-3.5 inline" />
              <span className="hidden sm:inline ml-1">Raise PO</span>
            </BtnPrimary>
          )
        }
      />

      {/* Top View Selector Tabs */}
      <div className="px-4 sm:px-8 pt-4">
        <div className="flex items-center gap-2 border-b-2 border-slate-200">
          <button
            onClick={() => setActiveTab("pos")}
            data-testid="tab-vendor-pos"
            className={`px-4 py-2.5 text-xs sm:text-sm font-bold uppercase tracking-wider flex items-center gap-2 transition-all border-b-2 -mb-[2px] ${
              activeTab === "pos"
                ? "border-[#C27842] text-[#C27842] bg-white"
                : "border-transparent text-slate-500 hover:text-slate-900"
            }`}
          >
            <FileText className="w-4 h-4" />
            Purchase Orders
            <span className="font-mono text-xs px-1.5 py-0.2 rounded bg-slate-100 text-slate-700">
              {pos.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab("ledgers")}
            data-testid="tab-vendor-ledgers"
            className={`px-4 py-2.5 text-xs sm:text-sm font-bold uppercase tracking-wider flex items-center gap-2 transition-all border-b-2 -mb-[2px] ${
              activeTab === "ledgers"
                ? "border-[#C27842] text-[#C27842] bg-white"
                : "border-transparent text-slate-500 hover:text-slate-900"
            }`}
          >
            <BookOpen className="w-4 h-4" />
            Vendor Ledgers & Ageing
            {ageingData?.summary?.total_outstanding > 0 && (
              <span className="font-mono text-xs px-1.5 py-0.2 rounded bg-amber-100 text-amber-900 font-bold">
                {inr(ageingData.summary.total_outstanding)}
              </span>
            )}
          </button>
        </div>
      </div>

      {activeTab === "pos" ? (
        /* ================= TAB 1: PURCHASE ORDERS ================= */
        <div className="p-4 sm:p-8 space-y-5">
          {/* Enhanced KPI Metrics */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
            <Tile label="Total Raised" value={totalCount} accent="#0F172A" />
            <Tile label="Total PO Value" value={inr(totalPOValue)} accent="#2563EB" />
            <Tile label="Total Paid" value={inr(totalPOPaid)} accent="#16A34A" />
            <Tile label="Balance Due" value={inr(totalPOBalanceDue)} accent="#EA580C" />
            <Tile label="Open / Pending" value={sentCount} accent="#0284C7" />
            <Tile label="Fully Received" value={receivedCount} accent="#059669" />
          </div>

          {/* List Card */}
          <Card className="overflow-hidden" data-testid="vendor-pos-card">
            <div className="px-5 py-3 border-b-2 border-slate-200 flex items-center justify-between gap-4 flex-wrap">
              <h2 className="text-sm font-bold uppercase tracking-wider flex items-center gap-2">
                <FileText className="w-4 h-4 text-[#C27842]" />
                Purchase Orders List
                <span className="text-slate-500 font-mono ml-1">
                  ({filtered.length})
                </span>
              </h2>
              <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto mt-2 sm:mt-0">
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search PO / Vendor / Style..."
                  className="border-2 border-slate-300 px-3 py-1.5 text-sm focus:border-[#C27842] outline-none w-full sm:w-60 font-mono"
                />
                <select
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value)}
                  className="border-2 border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-[#C27842] outline-none w-full sm:w-auto"
                >
                  <option value="all">All Delivery Status</option>
                  <option value="draft">Draft</option>
                  <option value="sent">Sent</option>
                  <option value="partially_received">Partially Received</option>
                  <option value="received">Received</option>
                  <option value="cancelled">Cancelled</option>
                </select>
                <select
                  value={filterPaymentStatus}
                  onChange={(e) => setFilterPaymentStatus(e.target.value)}
                  className="border-2 border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-[#C27842] outline-none w-full sm:w-auto"
                >
                  <option value="all">All Payment Status</option>
                  <option value="unpaid">Unpaid</option>
                  <option value="partially_paid">Partially Paid</option>
                  <option value="paid">Fully Paid</option>
                </select>
              </div>
            </div>

            {filtered.length === 0 ? (
              <div
                className="p-16 text-center text-slate-400 text-sm"
                data-testid="vendor-pos-empty"
              >
                <FileText className="w-10 h-10 mx-auto mb-3 opacity-20" />
                No vendor purchase orders found.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="vendor-pos-table">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                      <th className="px-4 py-2 font-bold">PO Number</th>
                      <th className="px-4 py-2 font-bold">Vendor</th>
                      <th className="px-4 py-2 font-bold">Items</th>
                      <th className="px-4 py-2 font-bold text-right">Grand Total</th>
                      <th className="px-4 py-2 font-bold text-right">Paid</th>
                      <th className="px-4 py-2 font-bold text-right">Balance Due</th>
                      <th className="px-4 py-2 font-bold text-center">Payment</th>
                      <th className="px-4 py-2 font-bold">Expected</th>
                      <th className="px-4 py-2 font-bold text-center">Status</th>
                      <th className="px-4 py-2 font-bold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((po) => {
                      const totalOrdered = (po.line_items || []).reduce(
                        (sum, li) => sum + Number(li.quantity || 0),
                        0
                      );
                      const totalReceived = (po.line_items || []).reduce(
                        (sum, li) => sum + Number(li.received_quantity || 0),
                        0
                      );
                      const deliveryPct =
                        totalOrdered > 0
                          ? Math.min(100, Math.round((totalReceived / totalOrdered) * 100))
                          : 0;
                      const hasPendingItems = (po.line_items || []).some(
                        (li) => Number(li.quantity || 0) - Number(li.received_quantity || 0) > 0
                      );
                      const isExpanded = !!expandedRows[po.id];

                      return (
                        <Fragment key={po.id}>
                          <tr
                            data-testid={`vendor-po-row-${po.id}`}
                            className="border-b border-slate-100 hover:bg-slate-50 transition-colors"
                          >
                            <td className="px-4 py-3">
                              <div className="font-mono font-bold">{po.po_number}</div>
                              {po.customer_po_number && (
                                <div
                                  className="text-[10px] text-violet-700 font-semibold flex items-center gap-1 mt-0.5"
                                  data-testid={`vpo-cust-po-${po.id}`}
                                >
                                  <span>Order: {po.customer_po_number}</span>
                                  {po.style_code && (
                                    <span className="text-slate-500">· {po.style_code}</span>
                                  )}
                                </div>
                              )}
                            </td>
                            <td className="px-4 py-3">
                              <div className="font-bold text-slate-800">{po.vendor_name}</div>
                              <button
                                onClick={() => openVendorLedger(po.vendor_id, po.vendor_name)}
                                className="text-[11px] text-[#C27842] hover:underline flex items-center gap-0.5 mt-0.5 font-medium"
                                title="View Vendor Ledger"
                              >
                                <BookOpen className="w-3 h-3" /> View Ledger
                              </button>
                            </td>
                            <td className="px-4 py-3">
                              <div
                                className="flex items-center gap-2 cursor-pointer select-none group"
                                onClick={() => toggleRowExpand(po.id)}
                                data-testid={`toggle-expand-${po.id}`}
                                title={isExpanded ? "Collapse item breakdown" : "Expand item breakdown"}
                              >
                                <span className="p-0.5 text-slate-400 group-hover:text-slate-700 rounded transition-colors">
                                  {isExpanded ? (
                                    <ChevronDown className="w-4 h-4 text-slate-700" />
                                  ) : (
                                    <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-slate-700" />
                                  )}
                                </span>
                                <div>
                                  <div className="font-mono text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                                    <span>{(po.line_items || []).length} lines</span>
                                    <span className="text-[10px] text-slate-500 font-normal">
                                      ({totalReceived}/{totalOrdered})
                                    </span>
                                  </div>
                                  <div className="w-24 bg-slate-200 h-1.5 rounded-full overflow-hidden mt-1">
                                    <div
                                      className={`h-full transition-all ${
                                        deliveryPct >= 100
                                          ? "bg-emerald-500"
                                          : deliveryPct > 0
                                          ? "bg-amber-500"
                                          : "bg-slate-300"
                                      }`}
                                      style={{ width: `${deliveryPct}%` }}
                                    />
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3 text-right font-mono font-bold text-slate-900">
                              {inr(po.total_amount || 0)}
                            </td>
                            <td className="px-4 py-3 text-right font-mono text-green-700 font-semibold">
                              {inr(po.paid_amount || 0)}
                            </td>
                            <td className="px-4 py-3 text-right font-mono font-bold text-red-700">
                              {inr(po.balance_due ?? po.total_amount ?? 0)}
                            </td>
                            <td className="px-4 py-3 text-center">
                              <Badge color={PAYMENT_STATUS_COLOR[po.payment_status || "unpaid"]}>
                                {(po.payment_status || "unpaid").replace("_", " ")}
                              </Badge>
                            </td>
                            <td className="px-4 py-3 font-mono text-slate-600 text-xs">
                              {po.expected_delivery_date ? (
                                <span className="flex items-center gap-1">
                                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                                  {po.expected_delivery_date}
                                </span>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className="px-4 py-3 text-center">
                              <Badge color={STATUS_COLOR[po.status]}>
                                {po.status.replace("_", " ")}
                              </Badge>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <div className="flex items-center gap-1.5 justify-end">
                                {/* Pay PO button */}
                                {canWrite && (
                                  <button
                                    onClick={() => openPayModal(po)}
                                    data-testid={`pay-po-btn-${po.id}`}
                                    className={`px-2.5 py-1 text-xs font-bold uppercase tracking-wider transition-colors flex items-center gap-1 rounded ${
                                      po.payment_status === "paid"
                                        ? "bg-slate-100 text-slate-400 hover:bg-slate-200"
                                        : "bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm"
                                    }`}
                                    title="Record Outgoing Payment for this PO"
                                  >
                                    <CreditCard className="w-3 h-3" />
                                    <span>Pay</span>
                                  </button>
                                )}

                                {/* Receive materials button */}
                                {canWrite &&
                                  ["draft", "sent", "partially_received"].includes(po.status) &&
                                  hasPendingItems && (
                                    <button
                                      onClick={() => openReceive(po)}
                                      className="text-[#16A34A] border border-[#16A34A] px-2 py-1 text-xs font-bold uppercase tracking-wider hover:bg-[#16A34A] hover:text-white transition-colors flex items-center gap-1 rounded"
                                      data-testid={`receive-po-btn-${po.id}`}
                                      title="Receive Materials against PO"
                                    >
                                      <Plus className="w-3 h-3" />
                                      <span>Receive</span>
                                    </button>
                                  )}

                                {/* Edit PO */}
                                {canWrite && (
                                  <button
                                    onClick={() => openEdit(po)}
                                    className="text-[#2563EB] border border-[#2563EB] px-2 py-1 text-xs font-bold uppercase tracking-wider hover:bg-[#2563EB] hover:text-white transition-colors flex items-center gap-1 rounded"
                                    title="Edit PO"
                                  >
                                    <Pencil className="w-3 h-3" />
                                  </button>
                                )}

                                {/* Delete PO */}
                                {canWrite && (
                                  <button
                                    onClick={() => handleDelete(po)}
                                    className="text-red-600 border border-red-300 px-2 py-1 text-xs font-bold uppercase tracking-wider hover:bg-red-600 hover:text-white hover:border-red-600 transition-colors flex items-center gap-1 rounded"
                                    title="Delete PO"
                                  >
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>

                          {/* Expanded Line Items Detail Row */}
                          {isExpanded && (
                            <tr
                              className="bg-slate-50/90 border-b border-slate-200"
                              data-testid={`expanded-row-${po.id}`}
                            >
                              <td colSpan={10} className="px-6 py-3">
                                <div className="bg-white border border-slate-200 rounded p-3 shadow-sm">
                                  <div className="text-[11px] font-bold text-slate-700 uppercase tracking-wider mb-2 flex items-center justify-between">
                                    <span>Material Delivery Breakdown</span>
                                    <span className="text-slate-500 font-mono text-[10px]">
                                      {deliveryPct}% fulfilled ({totalReceived} of {totalOrdered})
                                    </span>
                                  </div>
                                  <table className="w-full text-xs">
                                    <thead>
                                      <tr className="text-slate-500 border-b border-slate-100 text-left font-medium">
                                        <th className="pb-1.5 font-bold">Material Code & Name</th>
                                        <th className="pb-1.5 text-right font-bold">Ordered</th>
                                        <th className="pb-1.5 text-right font-bold">Received</th>
                                        <th className="pb-1.5 text-right font-bold">Remaining</th>
                                        <th className="pb-1.5 text-center font-bold">Progress</th>
                                        <th className="pb-1.5 text-center font-bold">Status</th>
                                      </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100">
                                      {(po.line_items || []).map((li, idx) => {
                                        const mat = materials.find((m) => m.id === li.material_id);
                                        const matCode = mat?.code || li.material_code || "—";
                                        const matName = mat?.name || li.material_name || "Unknown Material";
                                        const ord = Number(li.quantity || 0);
                                        const rec = Number(li.received_quantity || 0);
                                        const rem = Math.max(0, Math.round((ord - rec) * 10000) / 10000);
                                        const linePct =
                                          ord > 0 ? Math.min(100, Math.round((rec / ord) * 100)) : 0;
                                        const statusColor =
                                          rem === 0 ? "green" : rec > 0 ? "yellow" : "slate";
                                        const statusLabel =
                                          rem === 0 ? "Completed" : rec > 0 ? "Partial" : "Pending";

                                        return (
                                          <tr key={idx} className="hover:bg-slate-50/50">
                                            <td className="py-1.5 pr-2">
                                              <span className="font-mono font-bold text-slate-700">
                                                [{matCode}]
                                              </span>{" "}
                                              <span className="text-slate-800">{matName}</span>
                                            </td>
                                            <td className="py-1.5 text-right font-mono">{ord}</td>
                                            <td className="py-1.5 text-right font-mono font-semibold text-emerald-700">
                                              {rec}
                                            </td>
                                            <td className="py-1.5 text-right font-mono font-bold text-amber-700">
                                              {rem}
                                            </td>
                                            <td className="py-1.5 px-4">
                                              <div className="flex items-center gap-1.5">
                                                <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden">
                                                  <div
                                                    className={`h-full transition-all ${
                                                      linePct >= 100
                                                        ? "bg-emerald-500"
                                                        : linePct > 0
                                                        ? "bg-amber-500"
                                                        : "bg-slate-300"
                                                    }`}
                                                    style={{ width: `${linePct}%` }}
                                                  />
                                                </div>
                                                <span className="text-[10px] font-mono text-slate-500 shrink-0">
                                                  {linePct}%
                                                </span>
                                              </div>
                                            </td>
                                            <td className="py-1.5 text-center">
                                              <Badge color={statusColor}>{statusLabel}</Badge>
                                            </td>
                                          </tr>
                                        );
                                      })}
                                    </tbody>
                                  </table>
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      ) : (
        /* ================= TAB 2: VENDOR LEDGERS & AGEING ================= */
        <div className="p-4 sm:p-8 space-y-5" data-testid="vendor-ageing-view">
          {/* AP Ageing Summary KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <Tile
              label="Vendors Count"
              value={ageingData?.summary?.total_vendors ?? "—"}
              accent="#0F172A"
            />
            <Tile
              label="Total AP Payable"
              value={inr(ageingData?.summary?.total_outstanding ?? 0)}
              accent="#B91C1C"
            />
            <Tile
              label="Current (0d)"
              value={inr(ageingData?.summary?.total_current ?? 0)}
              accent="#16A34A"
            />
            <Tile
              label="1 - 30 Days"
              value={inr(ageingData?.summary?.total_days_1_30 ?? 0)}
              accent="#2563EB"
            />
            <Tile
              label="31 - 60 Days"
              value={inr(ageingData?.summary?.total_days_31_60 ?? 0)}
              accent="#D97706"
            />
            <Tile
              label="60+ Days"
              value={inr(ageingData?.summary?.total_days_60_plus ?? 0)}
              accent="#DC2626"
            />
          </div>

          <Card className="overflow-hidden" data-testid="vendor-ageing-card">
            <div className="px-5 py-3 border-b-2 border-slate-200 flex items-center justify-between gap-4 flex-wrap">
              <div>
                <h2 className="text-sm font-bold uppercase tracking-wider flex items-center gap-2">
                  <BookOpen className="w-4 h-4 text-[#C27842]" />
                  Accounts Payable & Vendor Ageing Analysis
                </h2>
                <div className="text-xs text-slate-500 mt-0.5">
                  Chronological balances based on material receipts and payment allocations.
                </div>
              </div>
              <div className="w-full sm:w-auto">
                <input
                  value={ageingSearch}
                  onChange={(e) => setAgeingSearch(e.target.value)}
                  placeholder="Filter by vendor name..."
                  className="border-2 border-slate-300 px-3 py-1.5 text-sm focus:border-[#C27842] outline-none w-full sm:w-64 font-sans"
                />
              </div>
            </div>

            {ageingLoading ? (
              <div className="p-12 text-center text-slate-400 text-sm">
                Loading vendor ledgers and accounts payable ageing...
              </div>
            ) : filteredAgeingVendors.length === 0 ? (
              <div className="p-12 text-center text-slate-400 text-sm">
                No vendor records found.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="vendor-ageing-table">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                      <th className="px-4 py-2 font-bold">Vendor Name</th>
                      <th className="px-4 py-2 font-bold text-center">Credit Terms</th>
                      <th className="px-4 py-2 font-bold text-right">Outstanding</th>
                      <th className="px-4 py-2 font-bold text-right text-emerald-700">Current</th>
                      <th className="px-4 py-2 font-bold text-right text-blue-700">1 - 30 Days</th>
                      <th className="px-4 py-2 font-bold text-right text-amber-700">31 - 60 Days</th>
                      <th className="px-4 py-2 font-bold text-right text-red-700">60+ Days</th>
                      <th className="px-4 py-2 font-bold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAgeingVendors.map((v) => (
                      <tr
                        key={v.vendor_id}
                        className="border-b border-slate-100 hover:bg-slate-50 transition-colors"
                      >
                        <td className="px-4 py-3">
                          <div className="font-bold text-slate-900">{v.vendor_name}</div>
                        </td>
                        <td className="px-4 py-3 text-center font-mono text-xs text-slate-600">
                          {v.payment_terms_days} days
                        </td>
                        <td className="px-4 py-3 text-right font-mono font-bold text-slate-900">
                          <span
                            className={
                              v.outstanding_balance > 0
                                ? "text-red-700 font-bold"
                                : "text-emerald-700"
                            }
                          >
                            {inr(v.outstanding_balance)}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-emerald-700">
                          {inr(v.current)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-blue-700">
                          {inr(v.days_1_30)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-amber-700">
                          {inr(v.days_31_60)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-red-700 font-bold">
                          {inr(v.days_60_plus)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center gap-2 justify-end">
                            <button
                              onClick={() => openVendorLedger(v.vendor_id, v.vendor_name)}
                              className="text-[#C27842] border border-[#C27842] px-2.5 py-1 text-xs font-bold uppercase tracking-wider hover:bg-[#C27842] hover:text-white transition-colors flex items-center gap-1 rounded"
                            >
                              <BookOpen className="w-3 h-3" /> Ledger
                            </button>
                            {canWrite && (
                              <button
                                onClick={() => openPayModal(v)}
                                className="bg-emerald-600 hover:bg-emerald-700 text-white px-2.5 py-1 text-xs font-bold uppercase tracking-wider transition-colors flex items-center gap-1 rounded"
                              >
                                <CreditCard className="w-3 h-3" /> Pay
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* ================= MODAL: RECORD PAYMENT ================= */}
      {paymentModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
          data-testid="vendor-payment-modal"
        >
          <div className="bg-white max-w-lg w-full rounded-lg shadow-2xl border border-slate-200 overflow-hidden flex flex-col">
            {/* Header */}
            <div className="bg-[#0F172A] text-white px-6 py-4 flex items-center justify-between shrink-0">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-emerald-400 flex items-center gap-1">
                  <CreditCard className="w-3 h-3" /> Outgoing Vendor Payment
                </div>
                <div className="text-base font-bold text-white mt-0.5">
                  {paymentModal.po
                    ? `Payment for PO: ${paymentModal.po.po_number}`
                    : `Pay Vendor: ${paymentModal.vendor_name}`}
                </div>
              </div>
              <button
                onClick={() => setPaymentModal(null)}
                className="hover:bg-white/10 p-1 rounded transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content Form */}
            <form onSubmit={handleRecordPayment} className="p-6 space-y-4">
              {error && (
                <div className="bg-red-50 border-2 border-red-200 px-4 py-3 flex items-start gap-2 text-sm text-red-700 rounded">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {/* Financial Context Tile */}
              <div className="bg-slate-50 border border-slate-200 p-3 rounded grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-slate-500 uppercase tracking-wider text-[10px] block font-bold">
                    Vendor
                  </span>
                  <span className="font-bold text-slate-800 text-sm">
                    {paymentModal.vendor_name}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-slate-500 uppercase tracking-wider text-[10px] block font-bold">
                    Outstanding Balance
                  </span>
                  <span className="font-mono font-bold text-red-700 text-sm">
                    {inr(paymentModal.balance_due || 0)}
                  </span>
                </div>
              </div>

              {/* Payment Amount */}
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700">
                    Payment Amount (₹) *
                  </label>
                  {paymentModal.balance_due > 0 && (
                    <div className="flex items-center gap-1.5 text-[11px]">
                      <button
                        type="button"
                        onClick={() =>
                          setPaymentForm((f) => ({
                            ...f,
                            amount: String(paymentModal.balance_due),
                          }))
                        }
                        className="text-emerald-700 hover:underline font-bold"
                      >
                        Full ({inr(paymentModal.balance_due)})
                      </button>
                      <span className="text-slate-300">·</span>
                      <button
                        type="button"
                        onClick={() =>
                          setPaymentForm((f) => ({
                            ...f,
                            amount: String(roundTo2(paymentModal.balance_due / 2)),
                          }))
                        }
                        className="text-blue-700 hover:underline font-bold"
                      >
                        50%
                      </button>
                    </div>
                  )}
                </div>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  required
                  placeholder="0.00"
                  value={paymentForm.amount}
                  onChange={(e) =>
                    setPaymentForm((f) => ({ ...f, amount: e.target.value }))
                  }
                  className="w-full border-2 border-slate-300 px-3 py-2 text-base font-mono font-bold focus:border-emerald-600 outline-none rounded"
                />
              </div>

              {/* Date & Mode */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700">
                    Payment Date *
                  </label>
                  <input
                    type="date"
                    required
                    value={paymentForm.payment_date}
                    onChange={(e) =>
                      setPaymentForm((f) => ({ ...f, payment_date: e.target.value }))
                    }
                    className="w-full border-2 border-slate-300 px-3 py-2 text-sm font-mono focus:border-emerald-600 outline-none rounded"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700">
                    Payment Mode *
                  </label>
                  <select
                    value={paymentForm.mode}
                    onChange={(e) => handlePaymentModeChange(e.target.value)}
                    className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-emerald-600 outline-none rounded font-medium"
                  >
                    <option value="NEFT">NEFT</option>
                    <option value="RTGS">RTGS</option>
                    <option value="Bank Transfer">Bank Transfer</option>
                    <option value="UPI">UPI</option>
                    <option value="Cheque">Cheque</option>
                    <option value="Cash">Cash</option>
                  </select>
                </div>
              </div>

              {/* Reference / UTR & Bank */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700">
                    Reference / UTR / Cheque #
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. UTR89123490"
                    value={paymentForm.reference}
                    onChange={(e) =>
                      setPaymentForm((f) => ({ ...f, reference: e.target.value }))
                    }
                    className="w-full border-2 border-slate-300 px-3 py-2 text-sm font-mono focus:border-emerald-600 outline-none rounded"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700 flex items-center justify-between">
                    <span>Paying Bank / Account *</span>
                    {bankAccounts.length > 0 && (
                      <span className="text-[9px] text-emerald-700 font-semibold bg-emerald-50 px-1 py-0.2 rounded border border-emerald-200">
                        {bankAccounts.length} ERP accounts
                      </span>
                    )}
                  </label>
                  <select
                    data-testid="pay-bank-account-select"
                    value={
                      paymentForm.account_type === "cash" && paymentForm.cash_account_id
                        ? `cash_${paymentForm.cash_account_id}`
                        : paymentForm.bank_account_id
                        ? paymentForm.bank_account_id
                        : paymentForm.bank && !bankAccounts.some((b) => (b.id || b._id) === paymentForm.bank_account_id)
                        ? "custom"
                        : bankAccounts[0] ? (bankAccounts[0].id || bankAccounts[0]._id) : ""
                    }
                    onChange={(e) => handleAccountChange(e.target.value)}
                    className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-emerald-600 outline-none rounded font-medium"
                    required
                  >
                    <option value="">-- Select Bank Account --</option>
                    {bankAccounts.length > 0 && (
                      <optgroup label="🏦 ERP Bank Accounts">
                        {bankAccounts.map((acc) => {
                          const id = acc.id || acc._id;
                          const bal = acc.current_balance ?? acc.balance;
                          const balStr = bal !== undefined && bal !== null ? ` (₹${Number(bal).toLocaleString("en-IN")})` : "";
                          const label = `${acc.name} (${acc.bank_name || "Bank"}${acc.account_number_last4 ? ` ••${acc.account_number_last4}` : ""})${balStr}`;
                          return (
                            <option key={`bank_${id}`} value={id}>
                              {label}
                            </option>
                          );
                        })}
                      </optgroup>
                    )}
                    {cashAccounts.length > 0 && (
                      <optgroup label="💵 ERP Cash Accounts">
                        {cashAccounts.map((ca) => {
                          const id = ca.id || ca._id;
                          const bal = ca.current_balance;
                          const balStr = bal !== undefined && bal !== null ? ` (₹${Number(bal).toLocaleString("en-IN")})` : "";
                          const label = `${ca.name || "Cash Account"}${balStr}`;
                          return (
                            <option key={`cash_${id}`} value={`cash_${id}`}>
                              {label}
                            </option>
                          );
                        })}
                      </optgroup>
                    )}
                    <option value="custom">✍️ Other / Enter Custom Bank Name</option>
                  </select>
                </div>
              </div>

              {/* If Custom Bank selected or no ERP accounts loaded, show manual input field */}
              {(!paymentForm.bank_account_id && !paymentForm.cash_account_id) && (
                <div className="space-y-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700">
                    Custom Bank / Account Name *
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. HDFC Bank - 1234"
                    value={paymentForm.bank}
                    onChange={(e) =>
                      setPaymentForm((f) => ({ ...f, bank: e.target.value }))
                    }
                    className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-emerald-600 outline-none rounded"
                    required
                  />
                </div>
              )}

              {/* Notes */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-700">
                  Notes / Remarks
                </label>
                <input
                  type="text"
                  placeholder="Optional remarks"
                  value={paymentForm.notes}
                  onChange={(e) =>
                    setPaymentForm((f) => ({ ...f, notes: e.target.value }))
                  }
                  className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-emerald-600 outline-none rounded"
                />
              </div>

              {/* Footer */}
              <div className="pt-2 flex items-center justify-between border-t border-slate-200">
                <BtnSecondary type="button" onClick={() => setPaymentModal(null)}>
                  Cancel
                </BtnSecondary>
                <button
                  type="submit"
                  disabled={saving}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-5 py-2 text-sm uppercase tracking-wider rounded transition-colors disabled:opacity-50 flex items-center gap-1.5 shadow-sm"
                >
                  <CreditCard className="w-4 h-4" />
                  {saving ? "Recording…" : "Confirm Payment"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ================= DRAWER: VENDOR LEDGER ================= */}
      {ledgerDrawer && (
        <div
          className="fixed inset-0 z-50 flex justify-end"
          data-testid="vendor-ledger-drawer"
        >
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setLedgerDrawer(null)}
          />
          <div className="relative bg-white w-full max-w-3xl h-full flex flex-col shadow-2xl border-l-2 border-slate-200 overflow-hidden font-sans">
            {/* Header */}
            <div className="bg-[#0F172A] text-white px-6 py-4 flex items-center justify-between shrink-0">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-[#C27842] flex items-center gap-1">
                  <BookOpen className="w-3.5 h-3.5" /> Vendor Financial Ledger
                </div>
                <div className="text-xl font-bold mt-0.5">
                  {ledgerDrawer.vendor_name}
                </div>
              </div>
              <div className="flex items-center gap-3">
                {canWrite && (
                  <button
                    onClick={() =>
                      openPayModal({
                        id: ledgerDrawer.vendor_id,
                        vendor_id: ledgerDrawer.vendor_id,
                        vendor_name: ledgerDrawer.vendor_name,
                        outstanding_balance: ledgerData?.current_balance || 0,
                      })
                    }
                    className="bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 text-xs font-bold uppercase tracking-wider rounded transition-colors flex items-center gap-1 shadow-sm"
                  >
                    <CreditCard className="w-3.5 h-3.5" /> Pay Vendor
                  </button>
                )}
                <button
                  onClick={() => setLedgerDrawer(null)}
                  className="hover:bg-white/10 p-1 rounded"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              {ledgerLoading ? (
                <div className="p-16 text-center text-slate-400 text-sm">
                  Loading vendor transactions and ledger balance...
                </div>
              ) : !ledgerData ? (
                <div className="p-16 text-center text-slate-400 text-sm">
                  Failed to load ledger data.
                </div>
              ) : (
                <>
                  {/* Financial Summary KPIs */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="bg-slate-50 border border-slate-200 p-3 rounded">
                      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">
                        Total Invoiced / Received
                      </div>
                      <div className="text-lg font-mono font-bold text-slate-800 mt-1">
                        {inr(ledgerData.total_received || 0)}
                      </div>
                    </div>

                    <div className="bg-emerald-50 border border-emerald-200 p-3 rounded">
                      <div className="text-[10px] uppercase tracking-wider font-bold text-emerald-700">
                        Total Paid Out
                      </div>
                      <div className="text-lg font-mono font-bold text-emerald-800 mt-1">
                        {inr(ledgerData.total_paid || 0)}
                      </div>
                    </div>

                    <div
                      className={`p-3 rounded border ${
                        ledgerData.current_balance > 0
                          ? "bg-red-50 border-red-200"
                          : "bg-slate-50 border-slate-200"
                      }`}
                    >
                      <div
                        className={`text-[10px] uppercase tracking-wider font-bold ${
                          ledgerData.current_balance > 0
                            ? "text-red-700"
                            : "text-slate-500"
                        }`}
                      >
                        Net Payable Balance
                      </div>
                      <div
                        className={`text-lg font-mono font-bold mt-1 ${
                          ledgerData.current_balance > 0
                            ? "text-red-700"
                            : "text-slate-800"
                        }`}
                      >
                        {inr(ledgerData.current_balance || 0)}
                      </div>
                    </div>
                  </div>

                  {/* Transaction Filter Header */}
                  <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                      <Filter className="w-3.5 h-3.5 text-[#C27842]" /> Chronological Transactions
                    </h3>
                    <div className="flex items-center gap-1">
                      {["all", "receive", "payment"].map((type) => (
                        <button
                          key={type}
                          onClick={() => setLedgerFilter(type)}
                          className={`px-2.5 py-1 text-xs font-bold uppercase tracking-wider rounded transition-colors ${
                            ledgerFilter === type
                              ? "bg-slate-800 text-white"
                              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                          }`}
                        >
                          {type === "all"
                            ? "All"
                            : type === "receive"
                              ? "Receipts (Credit)"
                              : "Payments (Debit)"}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Transactions Table */}
                  {filteredTransactions.length === 0 ? (
                    <div className="p-12 text-center text-slate-400 text-xs">
                      No matching transactions found for this vendor.
                    </div>
                  ) : (
                    <div className="overflow-x-auto border border-slate-200 rounded">
                      <table className="w-full text-xs font-sans">
                        <thead className="bg-slate-100 border-b border-slate-200">
                          <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                            <th className="px-3 py-2 font-bold">Date</th>
                            <th className="px-3 py-2 font-bold text-center">Type</th>
                            <th className="px-3 py-2 font-bold">Ref / PO #</th>
                            <th className="px-3 py-2 font-bold">Description</th>
                            <th className="px-3 py-2 font-bold text-right text-emerald-700">
                              Debit (Paid)
                            </th>
                            <th className="px-3 py-2 font-bold text-right text-blue-700">
                              Credit (Bill)
                            </th>
                            <th className="px-3 py-2 font-bold text-right">Balance</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredTransactions.map((tx, idx) => (
                            <tr
                              key={idx}
                              className="border-b border-slate-100 hover:bg-slate-50 transition-colors"
                            >
                              <td className="px-3 py-2.5 font-mono text-slate-600 whitespace-nowrap">
                                {tx.date}
                              </td>
                              <td className="px-3 py-2.5 text-center whitespace-nowrap">
                                {tx.type === "receive" ? (
                                  <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-800">
                                    <ArrowDownLeft className="w-3 h-3 text-blue-600" /> Receipt
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">
                                    <ArrowUpRight className="w-3 h-3 text-emerald-600" /> Payment
                                  </span>
                                )}
                              </td>
                              <td className="px-3 py-2.5 font-mono font-semibold text-slate-700">
                                <div>{tx.reference || tx.po_number || "—"}</div>
                                {tx.po_number && tx.po_number !== tx.reference && (
                                  <div className="text-[10px] text-slate-500 font-normal">{tx.po_number}</div>
                                )}
                              </td>
                              <td className="px-3 py-2.5 text-slate-600 max-w-xs truncate" title={tx.description}>
                                {tx.description}
                                {tx.mode && (
                                  <span className="ml-1 text-[10px] font-mono text-slate-400">
                                    ({tx.mode})
                                  </span>
                                )}
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono font-semibold text-emerald-700">
                                {tx.debit > 0 ? inr(tx.debit) : "—"}
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono font-semibold text-blue-700">
                                {tx.credit > 0 ? inr(tx.credit) : "—"}
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono font-bold text-slate-900">
                                {inr(tx.running_balance)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ================= DRAWER: ADD / EDIT PO ================= */}
      {drawer && (
        <div
          className="fixed inset-0 z-50 flex justify-end"
          data-testid="vendor-po-drawer"
        >
          <div className="absolute inset-0 bg-black/40" onClick={closeDrawer} />
          <div className="relative bg-white w-full max-w-2xl h-full flex flex-col shadow-2xl border-l-2 border-slate-200 overflow-y-auto">
            {/* Header */}
            <div className="bg-[#0F172A] text-white px-6 py-4 flex items-center justify-between shrink-0">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-[#C27842]">
                  Accounts Payable
                </div>
                <div className="text-lg font-bold">
                  {drawer.mode === "add"
                    ? "Raise New Purchase Order"
                    : `Edit PO: ${drawer.po?.po_number}`}
                </div>
              </div>
              <button onClick={closeDrawer} className="hover:bg-white/10 p-1">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Form Fields */}
            <div className="flex-1 p-6 space-y-4">
              {drawer.po?.customer_po_number && (
                <div
                  className="bg-violet-50 border border-violet-200 p-2.5 rounded text-xs text-violet-900 flex items-center justify-between"
                  data-testid="vpo-drawer-linked-order"
                >
                  <div>
                    <span className="text-[10px] uppercase tracking-wider font-bold text-violet-700 block">
                      Linked Production Order
                    </span>
                    <span className="font-bold">
                      Customer PO: {drawer.po.customer_po_number}
                    </span>
                    {drawer.po.style_code && (
                      <span className="ml-2">
                        · Style: <span className="font-mono">{drawer.po.style_code}</span>
                      </span>
                    )}
                  </div>
                  {drawer.po.production_job_ids?.length > 0 && (
                    <span className="text-[10px] bg-white border border-violet-300 px-2 py-0.5 rounded font-mono text-violet-800">
                      {drawer.po.production_job_ids.length} job(s)
                    </span>
                  )}
                </div>
              )}

              {error && (
                <div className="bg-red-50 border-2 border-red-200 px-4 py-3 flex items-start gap-2 text-sm text-red-700">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                    Vendor *
                  </label>
                  <select
                    value={form.vendor_id}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, vendor_id: e.target.value }))
                    }
                    className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#C27842] outline-none font-bold"
                  >
                    <option value="">-- Choose Vendor --</option>
                    {vendors.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                    Expected Delivery
                  </label>
                  <input
                    type="date"
                    value={form.expected_delivery_date}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        expected_delivery_date: e.target.value,
                      }))
                    }
                    className="w-full border-2 border-slate-300 px-3 py-2 text-sm font-mono focus:border-[#C27842] outline-none"
                  />
                </div>
              </div>

              {/* Status Selection */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                  PO Status
                </label>
                <select
                  value={form.status}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, status: e.target.value }))
                  }
                  className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-[#C27842] outline-none font-bold"
                >
                  <option value="draft">Draft</option>
                  <option value="sent">Sent</option>
                  <option value="partially_received">Partially Received</option>
                  <option value="received">Fully Received</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>

              {/* Line items editor */}
              <div className="space-y-2 pt-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs uppercase tracking-wider font-bold text-slate-700">
                    BOM Line Items
                  </label>
                  <button
                    type="button"
                    onClick={addLine}
                    className="text-xs text-[#C27842] font-bold flex items-center gap-1 hover:underline"
                  >
                    <Plus className="w-3.5 h-3.5" /> Add Material
                  </button>
                </div>

                <div className="border border-slate-200 rounded overflow-hidden">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200 text-slate-500">
                      <tr>
                        <th className="px-3 py-2 text-left">Material</th>
                        <th className="px-3 py-2 text-right w-24">Qty</th>
                        <th className="px-3 py-2 text-right w-24">Rate (₹)</th>
                        <th className="px-3 py-2 text-right w-28">Amount (₹)</th>
                        <th className="w-10"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {form.line_items.map((line, idx) => (
                        <tr key={idx} className="border-b border-slate-100">
                          <td className="p-2">
                            <select
                              value={line.material_id}
                              onChange={(e) =>
                                handleLineChange(idx, "material_id", e.target.value)
                              }
                              className="w-full border border-slate-300 p-1 text-xs focus:border-[#C27842] outline-none"
                            >
                              <option value="">-- Choose Material --</option>
                              {materials.map((m) => (
                                <option key={m.id} value={m.id}>
                                  [{m.code}] {m.name} ({m.unit})
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="p-2">
                            <input
                              type="number"
                              min="0"
                              value={line.quantity}
                              onChange={(e) =>
                                handleLineChange(idx, "quantity", e.target.value)
                              }
                              className="w-full border border-slate-300 p-1 text-xs text-right font-mono focus:border-[#C27842] outline-none"
                            />
                          </td>
                          <td className="p-2">
                            <input
                              type="number"
                              min="0"
                              value={line.rate}
                              onChange={(e) =>
                                handleLineChange(idx, "rate", e.target.value)
                              }
                              className="w-full border border-slate-300 p-1 text-xs text-right font-mono focus:border-[#C27842] outline-none"
                            />
                          </td>
                          <td className="p-2 text-right font-mono font-bold text-slate-700">
                            {inr(line.amount)}
                          </td>
                          <td className="p-2 text-center">
                            {form.line_items.length > 1 && (
                              <button
                                type="button"
                                onClick={() => removeLine(idx)}
                                className="text-red-500 hover:text-red-700"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="bg-slate-50 font-bold border-t border-slate-200">
                      <tr>
                        <td colSpan="3" className="px-3 py-2 text-right">
                          Grand Total:
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-slate-900">
                          {inr(formGrandTotal)}
                        </td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>

              {/* Notes */}
              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                  Notes
                </label>
                <textarea
                  rows="3"
                  value={form.notes}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, notes: e.target.value }))
                  }
                  className="w-full border-2 border-slate-300 p-2 text-sm focus:border-[#C27842] outline-none"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="border-t border-slate-200 px-6 py-4 flex items-center justify-between bg-slate-50">
              <BtnSecondary onClick={closeDrawer}>Cancel</BtnSecondary>
              <BtnPrimary onClick={handleSave} disabled={saving}>
                {saving ? "Saving…" : "Save Purchase Order"}
              </BtnPrimary>
            </div>
          </div>
        </div>
      )}

      {/* ================= MODAL: RECEIVE MATERIALS ================= */}
      {receiveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="bg-white max-w-xl w-full rounded shadow-2xl border border-slate-200 overflow-hidden flex flex-col">
            {/* Header */}
            <div className="bg-[#0F172A] text-white px-6 py-4 flex items-center justify-between shrink-0">
              <div>
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-[#16A34A]">
                  GRN Material Inward
                </div>
                <div className="text-base font-bold text-white mt-0.5">
                  {`Receive Against: ${receiveModal.po_number}`}
                </div>
              </div>
              <button
                onClick={() => setReceiveModal(null)}
                className="hover:bg-white/10 p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="p-6 space-y-4 flex-1 overflow-y-auto max-h-[400px]">
              {error && (
                <div className="bg-red-50 border-2 border-red-200 px-4 py-3 flex items-start gap-2 text-sm text-red-700">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div className="text-xs text-slate-500 mb-2">
                Specify quantities received in this shipment. A stock-in record will be created.
              </div>

              <div className="space-y-3">
                {receiveForm.items.map((item, idx) => {
                  const rem = Math.max(
                    0,
                    Math.round((Number(item.ordered) - Number(item.received)) * 10000) / 10000
                  );
                  const enteredQty = Number(item.quantity || 0);
                  const isOver = enteredQty > rem;
                  const isComplete = rem === 0;
                  const isPartial = Number(item.received) > 0 && rem > 0;

                  return (
                    <div
                      key={item.material_id}
                      className={`p-3 border rounded flex flex-col gap-2 font-sans transition-colors ${
                        isOver
                          ? "bg-red-50/70 border-red-300"
                          : isComplete
                          ? "bg-emerald-50/40 border-emerald-200"
                          : "bg-slate-50 border-slate-200"
                      }`}
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="font-bold text-sm text-slate-800">
                            [{item.material_code}] {item.material_name}
                          </div>
                          <div className="text-xs text-slate-500 mt-0.5">
                            Ordered: <span className="font-mono font-medium text-slate-700">{item.ordered}</span> ·
                            Received So Far:{" "}
                            <span className="font-mono font-bold text-emerald-700">
                              {item.received}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Badge color={isComplete ? "green" : isPartial ? "yellow" : "slate"}>
                            {isComplete ? "Completed" : isPartial ? "Partial" : "Pending"}
                          </Badge>
                          <div className="text-xs font-mono font-bold text-amber-800 bg-amber-100 px-2 py-0.5 rounded">
                            {`Remaining: ${rem}`}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 mt-1">
                        <label className="text-xs font-bold text-slate-600 shrink-0">
                          Receive Now:
                        </label>
                        <div className="flex items-center gap-2 flex-1">
                          <input
                            type="number"
                            min="0"
                            max={rem}
                            step="any"
                            disabled={rem === 0}
                            placeholder={rem === 0 ? "Fully received" : `Max ${rem}`}
                            value={item.quantity === 0 && !item.hasTyped ? "" : item.quantity}
                            onChange={(e) => {
                              const val = e.target.value === "" ? 0 : Number(e.target.value);
                              setReceiveForm((f) => {
                                const nextItems = [...f.items];
                                nextItems[idx] = {
                                  ...nextItems[idx],
                                  quantity: val,
                                  hasTyped: true,
                                };
                                return { ...f, items: nextItems };
                              });
                            }}
                            className={`w-full border px-3 py-1 text-sm font-mono outline-none rounded transition-colors ${
                              isOver
                                ? "border-red-500 focus:border-red-600 bg-red-50 text-red-700"
                                : "border-slate-300 focus:border-[#16A34A]"
                            } disabled:bg-slate-100 disabled:text-slate-400`}
                          />
                          {rem > 0 && (
                            <button
                              type="button"
                              onClick={() => {
                                setReceiveForm((f) => {
                                  const nextItems = [...f.items];
                                  nextItems[idx] = {
                                    ...nextItems[idx],
                                    quantity: rem,
                                    hasTyped: true,
                                  };
                                  return { ...f, items: nextItems };
                                });
                              }}
                              className="text-[11px] font-bold text-slate-600 hover:text-[#16A34A] border border-slate-300 hover:border-[#16A34A] px-2 py-1 rounded shrink-0 bg-white transition-colors"
                              title="Auto-fill remaining quantity"
                            >
                              Fill Remaining
                            </button>
                          )}
                        </div>
                      </div>
                      {isOver && (
                        <div className="text-[11px] text-red-600 font-semibold flex items-center gap-1">
                          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                          <span>{`Cannot receive more than remaining balance (${rem}).`}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Footer */}
            <div className="shrink-0 border-t border-slate-200 px-6 py-4 flex items-center justify-between bg-slate-50 font-sans">
              <BtnSecondary onClick={() => setReceiveModal(null)}>
                Cancel
              </BtnSecondary>
              {(() => {
                const hasOverReceipt = receiveForm.items.some((item) => {
                  const rem = Math.max(
                    0,
                    Math.round((Number(item.ordered) - Number(item.received)) * 10000) / 10000
                  );
                  return Number(item.quantity || 0) > rem;
                });
                const totalReceiving = receiveForm.items.reduce(
                  (sum, item) => sum + Number(item.quantity || 0),
                  0
                );
                return (
                  <button
                    onClick={handleReceive}
                    disabled={saving || hasOverReceipt || totalReceiving <= 0}
                    className="bg-[#16A34A] hover:bg-[#15803d] text-white font-bold px-5 py-2 text-sm uppercase tracking-wider rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {saving ? "Saving…" : "Post Receipt"}
                  </button>
                );
              })()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Tile({ label, value, accent }) {
  return (
    <Card className="p-3 sm:p-5 relative overflow-hidden">
      <div
        className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 truncate"
        style={{ color: accent }}
      >
        {label}
      </div>
      <div
        className="font-mono text-lg sm:text-2xl font-bold mt-1 truncate"
        title={String(value)}
      >
        {value}
      </div>
      <div
        className="absolute left-0 top-0 bottom-0 w-1.5"
        style={{ background: accent }}
      />
    </Card>
  );
}
