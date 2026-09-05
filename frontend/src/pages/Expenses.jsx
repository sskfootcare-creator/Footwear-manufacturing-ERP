import { useState, useEffect, useCallback } from "react";
import { http, inr } from "../lib/api";
import { PageHeader, Card, Badge, BtnPrimary, BtnSecondary, PaginationControls, usePagination } from "../components/ui-kit";
import ImageUploader, { ImageThumb } from "../components/ImageUploader";
import {
  Plus,
  Search,
  Filter,
  Calendar,
  IndianRupee,
  TrendingUp,
  TrendingDown,
  Receipt,
  Trash2,
  Edit3,
  X,
  Check,
  PieChart as PieChartIcon,
  Loader2,
  ArrowUpRight,
  RefreshCw,
  Clock,
  AlertTriangle,
  CheckCircle2,
  PauseCircle,
  PlayCircle,
  Coins,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";

const EXPENSE_CATEGORIES = [
  "wages",
  "Rent",
  "Electricity",
  "Salary",
  "EMI",
  "Rent & Utilities",
  "Raw Materials",
  "Machinery & Maintenance",
  "Labor & Wages",
  "Transport & Logistics",
  "Packaging & Printing",
  "Office & Administrative",
  "Marketing & Sales",
  "Tax & Professional Fees",
  "Other Expenses",
];

const TODAY = new Date().toISOString().split("T")[0];

export default function Expenses() {
  // Navigation tab
  const [activeTab, setActiveTab] = useState("expenses"); // "expenses" | "due_queue" | "recurring"

  // Main data state
  const [expenses, setExpenses] = useState([]);

  const {
    paginatedItems: paginatedExpenses,
    paginationProps: expensePaginationProps,
  } = usePagination(expenses, {
    initialPageSize: 25,
    pageSizeOptions: [10, 25, 50, 100],
    testIdPrefix: "expenses-pagination",
  });
  const [dueQueue, setDueQueue] = useState([]);
  const [recurringTemplates, setRecurringTemplates] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [cashLedgerEntries, setCashLedgerEntries] = useState([]);
  const [pnl, setPnl] = useState({
    revenue: 0,
    invoices_revenue: 0,
    settlements_revenue: 0,
    material_cost: 0,
    labor_cost: 0,
    expenses: 0,
    recurring_expenses: 0,
    variable_expenses: 0,
    gross_profit: 0,
    net_profit: 0,
    category_totals: {},
    monthly_breakdown: [],
  });
  const [loading, setLoading] = useState(true);

  // Filters state
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [search, setSearch] = useState("");

  // Modals state
  const [modalOpen, setModalOpen] = useState(false);
  const [showCashWithdrawalModal, setShowCashWithdrawalModal] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  // Confirm due expense modal
  const [confirmModalItem, setConfirmModalItem] = useState(null);
  const [confirmForm, setConfirmForm] = useState({
    amount: "",
    payee: "",
    date: TODAY,
    notes: "",
    receipt: null,
    paid_via: "bank",
    cash_ledger_id: "",
    bank_account_id: "",
  });

  // Recurring template modal
  const [recurringModalOpen, setRecurringModalOpen] = useState(false);
  const [editingRecurring, setEditingRecurring] = useState(null);
  const [recurringForm, setRecurringForm] = useState({
    category: "Rent",
    payee: "",
    amount: "",
    frequency: "monthly",
    start_date: TODAY,
    due_day: "1",
    end_date: "",
    bank_account_id: "",
    active: true,
    notes: "",
  });

  // One-time / Manual Expense form state
  const [form, setForm] = useState({
    category: EXPENSE_CATEGORIES[0],
    customCategory: "",
    amount: "",
    date: TODAY,
    payee: "",
    notes: "",
    receipt: null,
    paid_via: "bank",
    cash_ledger_id: "",
    bank_account_id: "",
    is_recurring: false,
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (categoryFilter !== "all") params.category = categoryFilter;
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      if (search) params.search = search;

      const [expRes, pnlRes, dueRes, recRes, bankRes, cashRes] = await Promise.all([
        http.get("/expenses", { params }),
        http.get("/reports/pnl", { params: { from_date: fromDate, to_date: toDate } }),
        http.get("/expenses/due-queue"),
        http.get("/expenses/recurring"),
        http.get("/banking/accounts", { params: { active: true } }).catch(() => ({ data: [] })),
        http.get("/banking/cash-ledger").catch(() => ({ data: [] })),
      ]);

      setExpenses(expRes.data || []);
      if (pnlRes.data) setPnl(pnlRes.data);
      setDueQueue(dueRes.data || []);
      setRecurringTemplates(recRes.data || []);
      setBankAccounts(Array.isArray(bankRes?.data) ? bankRes.data : bankRes?.data?.items || []);
      const clItems = cashRes?.data?.items || (Array.isArray(cashRes?.data) ? cashRes.data : []);
      setCashLedgerEntries(clItems);
    } catch (err) {
      console.error("Failed to load expenses data:", err);
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, fromDate, toDate, search]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Modal Handlers
  const openNewModal = () => {
    setEditingItem(null);
    setForm({
      category: EXPENSE_CATEGORIES[0],
      customCategory: "",
      amount: "",
      date: TODAY,
      payee: "",
      notes: "",
      receipt: null,
      paid_via: "bank",
      cash_ledger_id: "",
      bank_account_id: "",
      is_recurring: false,
    });
    setModalOpen(true);
  };

  const openEditModal = (item) => {
    setEditingItem(item);
    const isCustom = !EXPENSE_CATEGORIES.includes(item.category);
    setForm({
      category: isCustom ? "Other" : item.category,
      customCategory: isCustom ? item.category : "",
      amount: item.amount || "",
      date: item.date || TODAY,
      payee: item.payee || "",
      notes: item.notes || "",
      receipt: item.receipt || null,
      paid_via: item.paid_via || (item.cash_ledger_id ? "cash" : "bank"),
      cash_ledger_id: item.cash_ledger_id || "",
      bank_account_id: item.bank_account_id || "",
      is_recurring: !!item.is_recurring,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.amount || parseFloat(form.amount) <= 0 || !form.payee.trim()) {
      alert("Please enter a valid amount and payee name.");
      return;
    }

    if (form.paid_via === "cash" && !form.cash_ledger_id) {
      alert("Please select a Cash Withdrawal ledger entry for cash payment.");
      return;
    }

    const finalCategory =
      form.category === "Other" && form.customCategory.trim()
        ? form.customCategory.trim()
        : form.category;

    const payload = {
      category: finalCategory,
      amount: parseFloat(form.amount),
      date: form.date || TODAY,
      payee: form.payee.trim(),
      notes: form.notes ? form.notes.trim() : "",
      receipt: form.receipt,
      paid_via: form.paid_via || "bank",
      cash_ledger_id: form.paid_via === "cash" ? form.cash_ledger_id : null,
      bank_account_id: form.paid_via === "bank" ? (form.bank_account_id || null) : null,
      is_recurring: form.is_recurring,
      status: "confirmed",
    };

    setSubmitting(true);
    try {
      if (editingItem) {
        await http.put(`/expenses/${editingItem.id}`, payload);
      } else {
        await http.post("/expenses", payload);
      }
      setModalOpen(false);
      loadData();
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to save expense");
    } finally {
      setSubmitting(false);
    }
  };

  // Confirm Auto-generated Due Expense
  const openConfirmModal = (item) => {
    setConfirmModalItem(item);
    setConfirmForm({
      amount: item.amount || "",
      payee: item.payee || "",
      date: item.date || TODAY,
      notes: item.notes || "",
      receipt: item.receipt || null,
      bank_account_id: item.bank_account_id || "",
    });
  };

  const handleConfirmSubmit = async (e) => {
    e.preventDefault();
    if (!confirmModalItem) return;
    setSubmitting(true);
    try {
      await http.post(`/expenses/${confirmModalItem.id}/confirm`, {
        amount: parseFloat(confirmForm.amount),
        payee: confirmForm.payee,
        date: confirmForm.date,
        notes: confirmForm.notes,
        receipt: confirmForm.receipt,
        bank_account_id: confirmForm.bank_account_id || null,
      });
      setConfirmModalItem(null);
      loadData();
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to confirm expense");
    } finally {
      setSubmitting(false);
    }
  };

  // Recurring Template Handlers
  const openNewRecurringModal = () => {
    setEditingRecurring(null);
    setRecurringForm({
      category: "Rent",
      payee: "",
      amount: "",
      frequency: "monthly",
      start_date: TODAY,
      due_day: "1",
      end_date: "",
      bank_account_id: "",
      active: true,
      notes: "",
    });
    setRecurringModalOpen(true);
  };

  const handleRecurringSubmit = async (e) => {
    e.preventDefault();
    if (!recurringForm.amount || parseFloat(recurringForm.amount) <= 0 || !recurringForm.payee.trim()) {
      alert("Please enter a valid base amount and payee.");
      return;
    }
    const payload = {
      category: recurringForm.category,
      payee: recurringForm.payee.trim(),
      amount: parseFloat(recurringForm.amount),
      frequency: recurringForm.frequency,
      start_date: recurringForm.start_date,
      due_day: parseInt(recurringForm.due_day, 10),
      end_date: recurringForm.end_date || null,
      bank_account_id: recurringForm.bank_account_id || null,
      active: recurringForm.active,
      notes: recurringForm.notes || "",
    };

    setSubmitting(true);
    try {
      if (editingRecurring) {
        await http.patch(`/expenses/recurring/${editingRecurring.id}`, payload);
      } else {
        await http.post("/expenses/recurring", payload);
      }
      setRecurringModalOpen(false);
      loadData();
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to save recurring template");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleRecurringActive = async (template) => {
    try {
      await http.patch(`/expenses/recurring/${template.id}`, { active: !template.active });
      loadData();
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to toggle status");
    }
  };

  const handleDeleteRecurring = async (id) => {
    if (!window.confirm("Are you sure you want to delete this recurring expense template?")) return;
    try {
      await http.delete(`/expenses/recurring/${id}`);
      loadData();
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to delete recurring template");
    }
  };

  const handleDelete = async (id) => {
    try {
      await http.delete(`/expenses/${id}`);
      setDeleteConfirm(null);
      loadData();
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to delete expense");
    }
  };

  const listTotalExpenses = expenses.reduce((sum, item) => sum + (item.amount || 0), 0);

  const categorySummary = expenses.reduce((acc, item) => {
    const cat = item.category || "Uncategorized";
    acc[cat] = (acc[cat] || 0) + (item.amount || 0);
    return acc;
  }, {});

  const monthlyExpensesSummary = expenses.reduce((acc, item) => {
    const m = (item.date || "").substring(0, 7) || "Other";
    acc[m] = (acc[m] || 0) + (item.amount || 0);
    return acc;
  }, {});

  return (
    <div>
      <PageHeader
        title="Expenses & Simple P&L"
        subtitle="Financial Expense Logging, Recurring Expenses, Auto-generation & Profit & Loss Statement"
        testId="expenses-header"
      />

      <div className="p-2 sm:p-4 lg:p-8 space-y-6">
        {/* ── SIMPLE P&L SUMMARY DASHBOARD ────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="pnl-summary-cards">
          {/* Card 1: Total Revenue */}
          <Card className="p-5 border-l-4 border-l-emerald-600 bg-gradient-to-br from-white to-emerald-50/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs uppercase tracking-wider font-bold text-slate-500">Total Revenue</span>
              <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 grid place-items-center">
                <ArrowUpRight className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-black text-slate-900" data-testid="pnl-revenue-value">
              {inr(pnl.revenue)}
            </div>
            <div className="mt-2 text-[11px] text-slate-500 font-medium flex flex-wrap justify-between gap-x-2 gap-y-1 border-t pt-2">
              <span>Invoices: {inr(pnl.invoices_revenue)}</span>
              <span>Settlements: {inr(pnl.settlements_revenue)}</span>
            </div>
          </Card>

          {/* Card 2: Material & Labor Costs */}
          <Card className="p-5 border-l-4 border-l-amber-500 bg-gradient-to-br from-white to-amber-50/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs uppercase tracking-wider font-bold text-slate-500">Material & Labor Cost</span>
              <div className="w-8 h-8 rounded-full bg-amber-100 text-amber-700 grid place-items-center">
                <IndianRupee className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-black text-slate-900" data-testid="pnl-cogs-value">
              {inr(pnl.material_cost + pnl.labor_cost)}
            </div>
            <div className="mt-2 text-[11px] text-slate-500 font-medium flex flex-wrap justify-between gap-x-2 gap-y-1 border-t pt-2">
              <span>Material: {inr(pnl.material_cost)}</span>
              <span>Labor: {inr(pnl.labor_cost)}</span>
            </div>
          </Card>

          {/* Card 3: Operating Expenses (Split Recurring vs Variable) */}
          <Card className="p-5 border-l-4 border-l-blue-600 bg-gradient-to-br from-white to-blue-50/30">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs uppercase tracking-wider font-bold text-slate-500">Operating Expenses</span>
              <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 grid place-items-center">
                <Receipt className="w-4 h-4" />
              </div>
            </div>
            <div className="text-2xl font-black text-slate-900" data-testid="pnl-expenses-value">
              {inr(pnl.expenses)}
            </div>
            <div className="mt-2 text-[11px] text-slate-500 font-medium flex flex-wrap justify-between gap-x-2 gap-y-1 border-t pt-2">
              <span title="Recurring fixed expenses">Recurring: {inr(pnl.recurring_expenses || 0)}</span>
              <span title="Variable one-time expenses">Variable: {inr(pnl.variable_expenses || 0)}</span>
            </div>
          </Card>

          {/* Card 4: Net P&L */}
          <Card
            className={`p-5 border-l-4 ${
              pnl.net_profit >= 0
                ? "border-l-emerald-500 bg-gradient-to-br from-emerald-900 to-slate-900 text-white"
                : "border-l-red-500 bg-gradient-to-br from-red-950 to-slate-900 text-white"
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs uppercase tracking-wider font-bold text-slate-300">Simple P&L Net</span>
              <Badge variant={pnl.net_profit >= 0 ? "green" : "red"}>
                {pnl.net_profit >= 0 ? "PROFIT" : "LOSS"}
              </Badge>
            </div>
            <div className="text-2xl font-black" data-testid="pnl-net-profit-value">
              {inr(pnl.net_profit)}
            </div>
            <div className="mt-2 text-[11px] text-slate-300 font-medium border-t border-slate-700/60 pt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
              {pnl.net_profit >= 0 ? (
                <span className="flex items-center gap-1">
                  <TrendingUp className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  <span>Revenue − Costs − Expenses</span>
                </span>
              ) : (
                <span className="flex items-center gap-1">
                  <TrendingDown className="w-3.5 h-3.5 text-red-400 shrink-0" />
                  <span>Expenses & Costs exceed Revenue</span>
                </span>
              )}
            </div>
          </Card>
        </div>

        {/* ── NAVIGATION TABS BAR ────────────────────────────────────────────── */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 py-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab("expenses")}
              className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 ${
                activeTab === "expenses"
                  ? "border-[#C27842] text-[#C27842]"
                  : "border-transparent text-slate-500 hover:text-slate-900"
              }`}
              data-testid="tab-all-expenses"
            >
              <Receipt className="w-4 h-4 inline mr-1.5" />
              Main Expenses List
            </button>
            <button
              onClick={() => setActiveTab("due_queue")}
              className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 flex items-center gap-1.5 ${
                activeTab === "due_queue"
                  ? "border-[#C27842] text-[#C27842]"
                  : "border-transparent text-slate-500 hover:text-slate-900"
              }`}
              data-testid="tab-due-queue"
            >
              <Clock className="w-4 h-4" />
              Due This Month
              {dueQueue.length > 0 && (
                <span className="px-1.5 py-0.5 text-[10px] bg-amber-500 text-white rounded-full font-black">
                  {dueQueue.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab("recurring")}
              className={`px-4 py-2 text-xs font-bold uppercase tracking-wider transition-colors border-b-2 ${
                activeTab === "recurring"
                  ? "border-[#C27842] text-[#C27842]"
                  : "border-transparent text-slate-500 hover:text-slate-900"
              }`}
              data-testid="tab-recurring"
            >
              <RefreshCw className="w-4 h-4 inline mr-1.5" />
              Recurring Templates ({recurringTemplates.length})
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowCashWithdrawalModal(true)}
              className="flex items-center gap-1.5 bg-amber-600 hover:bg-amber-700 text-white font-bold uppercase tracking-wider text-xs px-3.5 py-2 border-2 border-amber-600 shadow-sm transition-colors"
              data-testid="record-cash-withdrawal-btn"
            >
              <Coins className="w-3.5 h-3.5" /> Record Cash Withdrawal
            </button>
            {activeTab === "recurring" ? (
              <BtnPrimary onClick={openNewRecurringModal} data-testid="add-recurring-btn" className="flex items-center gap-2">
                <Plus className="w-4 h-4" /> New Recurring Template
              </BtnPrimary>
            ) : (
              <BtnPrimary onClick={openNewModal} data-testid="add-expense-btn" className="flex items-center gap-2">
                <Plus className="w-4 h-4" /> Add Expense
              </BtnPrimary>
            )}
          </div>
        </div>

        {/* ── TAB 1: MAIN EXPENSES LIST & CHART ───────────────────────────────── */}
        {activeTab === "expenses" && (
          <div className="space-y-6">
            {/* Monthly Trend Chart */}
            {pnl.monthly_breakdown && pnl.monthly_breakdown.length > 0 && (
              <Card className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="font-bold text-slate-900 text-sm uppercase tracking-wider flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-[#C27842]" /> Monthly Financial Breakdown (P&L Trend)
                    </h3>
                    <p className="text-xs text-slate-500">Revenue vs Material/Labor & Expenses per month</p>
                  </div>
                </div>
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={pnl.monthly_breakdown} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                      <YAxis
                        tick={{ fontSize: 11 }}
                        tickFormatter={(v) => {
                          if (v === 0) return "0";
                          const absV = Math.abs(v);
                          const sign = v < 0 ? "-" : "";
                          if (absV >= 1000) return `${sign}₹${(absV / 1000).toFixed(0)}k`;
                          return `${sign}₹${absV}`;
                        }}
                      />
                      <Tooltip formatter={(value) => [inr(value)]} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="revenue" name="Revenue" fill="#16A34A" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="material_cost" name="Material Cost" fill="#F59E0B" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="expenses" name="Expenses" fill="#2563EB" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="net_profit" name="Net Profit" fill="#0EA5E9" radius={[4, 4, 0, 0]}>
                        {pnl.monthly_breakdown.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.net_profit >= 0 ? "#0EA5E9" : "#EF4444"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            )}

            {/* Action Bar Filters */}
            <div className="bg-white p-4 border border-slate-200 shadow-sm flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
              <div className="flex flex-wrap gap-2 items-center flex-1">
                <div className="relative min-w-[200px] flex-1 sm:flex-initial">
                  <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search payee, notes..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 text-xs border border-slate-300 focus:outline-none focus:border-slate-800"
                    data-testid="expense-search-input"
                  />
                </div>

                <div className="flex items-center gap-1.5 min-w-[180px]">
                  <Filter className="w-3.5 h-3.5 text-slate-400 hidden sm:block" />
                  <select
                    value={categoryFilter}
                    onChange={(e) => setCategoryFilter(e.target.value)}
                    className="w-full px-2.5 py-2 text-xs border border-slate-300 bg-white font-medium focus:outline-none focus:border-slate-800"
                    data-testid="expense-category-filter"
                  >
                    <option value="all">All Categories</option>
                    {EXPENSE_CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="date"
                    value={fromDate}
                    onChange={(e) => setFromDate(e.target.value)}
                    className="px-2 py-1.5 text-xs border border-slate-300 bg-white focus:outline-none"
                    data-testid="expense-from-date"
                  />
                  <span className="text-xs text-slate-400">to</span>
                  <input
                    type="date"
                    value={toDate}
                    onChange={(e) => setToDate(e.target.value)}
                    className="px-2 py-1.5 text-xs border border-slate-300 bg-white focus:outline-none"
                    data-testid="expense-to-date"
                  />
                  {(fromDate || toDate || categoryFilter !== "all" || search) && (
                    <button
                      onClick={() => {
                        setFromDate("");
                        setToDate("");
                        setCategoryFilter("all");
                        setSearch("");
                      }}
                      className="text-xs text-red-600 font-bold uppercase tracking-wider hover:underline ml-1"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Expenses Table & Side Column */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 space-y-4">
                <Card className="overflow-hidden">
                  <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
                    <div className="font-bold text-xs uppercase tracking-wider text-slate-800 flex items-center gap-2">
                      <Receipt className="w-4 h-4 text-[#C27842]" /> Expense Records ({expenses.length})
                    </div>
                    <div className="font-black text-sm text-slate-900">Total: {inr(listTotalExpenses)}</div>
                  </div>

                  {loading ? (
                    <div className="p-12 text-center text-slate-400 flex flex-col items-center gap-2">
                      <Loader2 className="w-6 h-6 animate-spin text-[#C27842]" />
                      <span className="text-xs font-semibold">Loading expense data...</span>
                    </div>
                  ) : expenses.length === 0 ? (
                    <div className="p-12 text-center text-slate-400 space-y-2">
                      <div className="text-4xl">🧾</div>
                      <div className="font-bold text-slate-700 text-sm">No expenses found</div>
                      <p className="text-xs text-slate-400">Click "Add Expense" to record a new business expense.</p>
                    </div>
                  ) : (
                    <>
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs border-collapse" data-testid="expenses-table">
                          <thead>
                            <tr className="bg-slate-100 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[10px] font-bold">
                              <th className="p-3">Receipt</th>
                              <th className="p-3">Type</th>
                              <th className="p-3">Date</th>
                              <th className="p-3">Payee</th>
                              <th className="p-3">Category</th>
                              <th className="p-3">Notes</th>
                              <th className="p-3 text-right">Amount</th>
                              <th className="p-3 text-center">Actions</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-200">
                            {paginatedExpenses.map((item) => (
                              <tr key={item.id} className="hover:bg-slate-50 transition-colors" data-testid={`expense-row-${item.id}`}>
                                <td className="p-3">
                                  <ImageThumb image={item.receipt} size={36} alt="Receipt" clickable testId={`receipt-thumb-${item.id}`} />
                                </td>
                                <td className="p-3 whitespace-nowrap">
                                  {item.linked_wage_payment_id ? (
                                    <a
                                      href="/payroll"
                                      className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 hover:bg-blue-100 hover:text-blue-900 border border-blue-200 text-[10px] font-bold rounded-full transition-colors cursor-pointer"
                                      title={`Linked to Wage Payment ${item.linked_wage_payment_id} - Click to view in Payroll`}
                                      data-testid={`linked-wage-badge-${item.id}`}
                                    >
                                      <Coins className="w-3 h-3" /> Wage Payout
                                    </a>
                                  ) : item.is_recurring || item.recurring_expense_id ? (
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-50 text-purple-700 border border-purple-200 text-[10px] font-bold rounded-full">
                                      <RefreshCw className="w-3 h-3" /> Recurring
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-100 text-slate-600 border border-slate-200 text-[10px] font-medium rounded-full">
                                      One-Time
                                    </span>
                                  )}
                                </td>
                                <td className="p-3 font-semibold text-slate-800 whitespace-nowrap">{item.date}</td>
                                <td className="p-3 font-bold text-slate-900">
                                  {item.payee}
                                  {item.linked_wage_payment_id && (
                                    <span className="block text-[10px] font-normal text-blue-600">
                                      Karigar Wage
                                    </span>
                                  )}
                                </td>
                                <td className="p-3 whitespace-nowrap">
                                  <span className="inline-block px-2 py-0.5 bg-slate-100 border border-slate-300 font-semibold text-[11px] text-slate-700 rounded-sm">
                                    {item.category}
                                  </span>
                                  {item.bank_account_id && bankAccounts.length > 0 && (
                                    <span
                                      className="block text-[10px] text-slate-500 truncate max-w-[140px]"
                                      title={bankAccounts.find((b) => (b.id || b._id) === item.bank_account_id)?.name || "Bank Account"}
                                      data-testid={`expense-bank-attr-${item.id}`}
                                    >
                                      🏛️ {bankAccounts.find((b) => (b.id || b._id) === item.bank_account_id)?.name || "Bank Account"}
                                    </span>
                                  )}
                                </td>
                                <td className="p-3 text-slate-500 max-w-[180px] truncate" title={item.notes}>
                                  {item.notes || "—"}
                                </td>
                                <td className="p-3 text-right font-black text-slate-900 whitespace-nowrap">{inr(item.amount)}</td>
                                <td className="p-3 text-center whitespace-nowrap">
                                  <div className="flex items-center justify-center gap-1">
                                    <button
                                      onClick={() => openEditModal(item)}
                                      className="p-1.5 text-slate-500 hover:text-slate-900 transition-colors"
                                      title="Edit Expense"
                                      data-testid={`edit-expense-${item.id}`}
                                    >
                                      <Edit3 className="w-3.5 h-3.5" />
                                    </button>
                                    <button
                                      onClick={() => setDeleteConfirm(item)}
                                      className="p-1.5 text-slate-400 hover:text-red-600 transition-colors"
                                      title="Delete Expense"
                                      data-testid={`delete-expense-${item.id}`}
                                    >
                                      <Trash2 className="w-3.5 h-3.5" />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div className="px-5 py-3 bg-white border-t border-slate-200">
                        <PaginationControls {...expensePaginationProps} />
                      </div>
                    </>
                  )}
                </Card>
              </div>

              {/* Side Breakdown Column */}
              <div className="space-y-6">
                <Card className="p-5">
                  <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900 mb-3 flex items-center gap-2 border-b pb-2">
                    <PieChartIcon className="w-4 h-4 text-[#C27842]" /> Expenses by Category
                  </h4>
                  <div className="space-y-3">
                    {Object.keys(categorySummary).length === 0 ? (
                      <div className="text-xs text-slate-400 text-center py-4">No categories recorded</div>
                    ) : (
                      Object.entries(categorySummary)
                        .sort((a, b) => b[1] - a[1])
                        .map(([cat, amt]) => {
                          const pct = listTotalExpenses > 0 ? (amt / listTotalExpenses) * 100 : 0;
                          return (
                            <div key={cat} className="space-y-1">
                              <div className="flex justify-between text-xs font-semibold">
                                <span className="text-slate-700">{cat}</span>
                                <span className="text-slate-900 font-bold">{inr(amt)}</span>
                              </div>
                              <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                                <div className="bg-[#C27842] h-full rounded-full" style={{ width: `${Math.min(pct, 100)}%` }} />
                              </div>
                            </div>
                          );
                        })
                    )}
                  </div>
                </Card>

                <Card className="p-5">
                  <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900 mb-3 flex items-center gap-2 border-b pb-2">
                    <Calendar className="w-4 h-4 text-[#C27842]" /> Monthly Totals
                  </h4>
                  <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                    {Object.keys(monthlyExpensesSummary).length === 0 ? (
                      <div className="text-xs text-slate-400 text-center py-4">No monthly totals</div>
                    ) : (
                      Object.entries(monthlyExpensesSummary)
                        .sort((a, b) => b[0].localeCompare(a[0]))
                        .map(([month, amt]) => (
                          <div key={month} className="flex justify-between items-center py-1.5 px-2 bg-slate-50 border border-slate-200 text-xs">
                            <span className="font-mono font-semibold text-slate-700">{month}</span>
                            <span className="font-black text-slate-900">{inr(amt)}</span>
                          </div>
                        ))
                    )}
                  </div>
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 2: DUE THIS MONTH QUEUE ─────────────────────────────────────── */}
        {activeTab === "due_queue" && (
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-200">
              <div>
                <h3 className="font-bold text-slate-900 text-sm uppercase tracking-wider flex items-center gap-2">
                  <Clock className="w-4 h-4 text-amber-600" /> Due This Month Queue
                </h3>
                <p className="text-xs text-slate-500">
                  Auto-generated recurring expenses pending verification/edit & confirmation.
                </p>
              </div>
              <button
                onClick={loadData}
                className="text-xs font-bold text-slate-700 hover:text-slate-900 flex items-center gap-1 border px-2.5 py-1.5 rounded-sm"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Check Daily Schedule
              </button>
            </div>

            {dueQueue.length === 0 ? (
              <div className="p-12 text-center text-slate-400 space-y-2">
                <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-500" />
                <div className="font-bold text-slate-700 text-sm">All caught up!</div>
                <p className="text-xs text-slate-400">No pending auto-generated recurring expenses for this cycle.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse" data-testid="due-queue-table">
                  <thead>
                    <tr className="bg-slate-100 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[10px] font-bold">
                      <th className="p-3">Status</th>
                      <th className="p-3">Category</th>
                      <th className="p-3">Payee</th>
                      <th className="p-3">Due Date</th>
                      <th className="p-3 text-right">Base / Suggested Amount</th>
                      <th className="p-3">Notes</th>
                      <th className="p-3 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {dueQueue.map((item) => (
                      <tr key={item.id} className="hover:bg-slate-50 transition-colors" data-testid={`due-item-${item.id}`}>
                        <td className="p-3 whitespace-nowrap">
                          {item.status === "overdue" ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-red-100 text-red-700 font-bold text-[10px] uppercase rounded-full">
                              <AlertTriangle className="w-3 h-3" /> Overdue
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-amber-100 text-amber-800 font-bold text-[10px] uppercase rounded-full">
                              <Clock className="w-3 h-3" /> Due Soon
                            </span>
                          )}
                        </td>
                        <td className="p-3 font-bold text-slate-900">{item.category}</td>
                        <td className="p-3 font-semibold text-slate-800">{item.payee}</td>
                        <td className="p-3 font-mono font-semibold text-slate-700 whitespace-nowrap">{item.date}</td>
                        <td className="p-3 text-right font-black text-slate-900 whitespace-nowrap">{inr(item.amount)}</td>
                        <td className="p-3 text-slate-500 max-w-[200px] truncate" title={item.notes}>
                          {item.notes || "—"}
                        </td>
                        <td className="p-3 text-center whitespace-nowrap">
                          <BtnPrimary
                            onClick={() => openConfirmModal(item)}
                            className="text-xs px-3 py-1 bg-emerald-600 hover:bg-emerald-700 border-none"
                            data-testid={`confirm-btn-${item.id}`}
                          >
                            <Check className="w-3.5 h-3.5 inline mr-1" /> Edit & Confirm
                          </BtnPrimary>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}

        {/* ── TAB 3: RECURRING EXPENSE TEMPLATES ─────────────────────────────── */}
        {activeTab === "recurring" && (
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-200">
              <div>
                <h3 className="font-bold text-slate-900 text-sm uppercase tracking-wider flex items-center gap-2">
                  <RefreshCw className="w-4 h-4 text-purple-600" /> Active Recurring Expense Templates
                </h3>
                <p className="text-xs text-slate-500">
                  Configure rent, electricity, salaries, EMIs to auto-generate entries each cycle.
                </p>
              </div>
              <BtnPrimary onClick={openNewRecurringModal} data-testid="add-recurring-template-btn">
                <Plus className="w-4 h-4 inline mr-1" /> New Template
              </BtnPrimary>
            </div>

            {recurringTemplates.length === 0 ? (
              <div className="p-12 text-center text-slate-400 space-y-2">
                <RefreshCw className="w-10 h-10 mx-auto text-slate-300" />
                <div className="font-bold text-slate-700 text-sm">No recurring templates set up</div>
                <p className="text-xs text-slate-400">Click "New Template" to add fixed or variable recurring expenses.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse" data-testid="recurring-templates-table">
                  <thead>
                    <tr className="bg-slate-100 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[10px] font-bold">
                      <th className="p-3">Status</th>
                      <th className="p-3">Category</th>
                      <th className="p-3">Payee</th>
                      <th className="p-3 text-right">Base Amount</th>
                      <th className="p-3">Frequency</th>
                      <th className="p-3 text-center">Due Day</th>
                      <th className="p-3">Start Date</th>
                      <th className="p-3 text-center">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {recurringTemplates.map((item) => (
                      <tr key={item.id} className="hover:bg-slate-50 transition-colors" data-testid={`rec-tmpl-row-${item.id}`}>
                        <td className="p-3 whitespace-nowrap">
                          {item.active ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-emerald-100 text-emerald-800 font-bold text-[10px] uppercase rounded-full">
                              <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-slate-200 text-slate-700 font-bold text-[10px] uppercase rounded-full">
                              <PauseCircle className="w-3 h-3 text-slate-500" /> Paused
                            </span>
                          )}
                        </td>
                        <td className="p-3 font-bold text-slate-900">{item.category}</td>
                        <td className="p-3 font-semibold text-slate-800">{item.payee}</td>
                        <td className="p-3 text-right font-black text-slate-900 whitespace-nowrap">{inr(item.amount)}</td>
                        <td className="p-3 font-medium text-slate-600 uppercase text-[11px] whitespace-nowrap">{item.frequency}</td>
                        <td className="p-3 text-center font-bold text-slate-800">Day {item.due_day}</td>
                        <td className="p-3 font-mono text-slate-600 whitespace-nowrap">{item.start_date}</td>
                        <td className="p-3 text-center whitespace-nowrap">
                          <div className="flex items-center justify-center gap-2">
                            <button
                              onClick={() => toggleRecurringActive(item)}
                              className={`p-1.5 rounded transition-colors ${
                                item.active ? "text-amber-600 hover:bg-amber-50" : "text-emerald-600 hover:bg-emerald-50"
                              }`}
                              title={item.active ? "Pause Template" : "Activate Template"}
                              data-testid={`toggle-rec-${item.id}`}
                            >
                              {item.active ? <PauseCircle className="w-4 h-4" /> : <PlayCircle className="w-4 h-4" />}
                            </button>
                            <button
                              onClick={() => handleDeleteRecurring(item.id)}
                              className="p-1.5 text-slate-400 hover:text-red-600 transition-colors"
                              title="Delete Template"
                              data-testid={`delete-rec-${item.id}`}
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}
      </div>

      {/* ── CONFIRM DUE EXPENSE MODAL ────────────────────────────────────────── */}
      {confirmModalItem && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4" role="dialog">
          <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-md overflow-hidden flex flex-col">
            <div className="bg-[#0F172A] text-white px-5 py-3.5 flex items-center justify-between">
              <div className="font-bold text-sm uppercase tracking-wider flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Confirm Recurring Expense
              </div>
              <button onClick={() => setConfirmModalItem(null)} className="text-slate-400 hover:text-white transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleConfirmSubmit} className="p-5 space-y-4">
              <div className="bg-slate-50 p-3 border border-slate-200 rounded space-y-1 text-xs">
                <div className="font-bold text-slate-900">{confirmModalItem.category} for {confirmModalItem.payee}</div>
                <div className="text-slate-500">Auto-generated due date: <span className="font-mono">{confirmModalItem.date}</span></div>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Actual Amount Paid (₹) *
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={confirmForm.amount}
                  onChange={(e) => setConfirmForm({ ...confirmForm, amount: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-black text-slate-900 outline-none focus:border-slate-800"
                  required
                  data-testid="confirm-form-amount"
                />
                <p className="text-[10px] text-slate-400 mt-1">Pre-filled with base amount. Adjust for variable bill (e.g. electricity).</p>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Payee Name</label>
                <input
                  type="text"
                  value={confirmForm.payee}
                  onChange={(e) => setConfirmForm({ ...confirmForm, payee: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                  required
                  data-testid="confirm-form-payee"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Payment Date</label>
                <input
                  type="date"
                  value={confirmForm.date}
                  onChange={(e) => setConfirmForm({ ...confirmForm, date: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                  required
                  data-testid="confirm-form-date"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Bank Account (Optional)
                </label>
                <select
                  value={confirmForm.bank_account_id || ""}
                  onChange={(e) => setConfirmForm({ ...confirmForm, bank_account_id: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                  data-testid="confirm-form-bank-account"
                >
                  <option value="">-- No Bank Account / Unassigned --</option>
                  {bankAccounts.map((acc) => (
                    <option key={acc.id || acc._id} value={acc.id || acc._id}>
                      {`${acc.name} (${acc.bank_name || "Bank"}${acc.account_number_last4 ? ` - ••${acc.account_number_last4}` : ""})`}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Notes / Invoice Ref</label>
                <textarea
                  rows={2}
                  value={confirmForm.notes}
                  onChange={(e) => setConfirmForm({ ...confirmForm, notes: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-medium outline-none focus:border-slate-800"
                  data-testid="confirm-form-notes"
                />
              </div>

              <div className="border-t border-slate-200 pt-3">
                <ImageUploader
                  label="Receipt / Bill Copy"
                  value={confirmForm.receipt}
                  onChange={(imgObj) => setConfirmForm({ ...confirmForm, receipt: imgObj })}
                  maxSizeMB={8}
                  testIdPrefix="confirm-receipt"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
                <BtnSecondary type="button" onClick={() => setConfirmModalItem(null)}>
                  Cancel
                </BtnSecondary>
                <BtnPrimary type="submit" disabled={submitting} className="bg-emerald-600 hover:bg-emerald-700 border-none" data-testid="submit-confirm-btn">
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> : <Check className="w-4 h-4 inline mr-1" />}
                  Confirm Expense
                </BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── ADD / EDIT RECURRING TEMPLATE MODAL ─────────────────────────────── */}
      {recurringModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4" role="dialog">
          <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-lg overflow-hidden flex flex-col">
            <div className="bg-[#0F172A] text-white px-5 py-3.5 flex items-center justify-between">
              <div className="font-bold text-sm uppercase tracking-wider flex items-center gap-2">
                <RefreshCw className="w-4 h-4 text-purple-400" /> New Recurring Expense Template
              </div>
              <button onClick={() => setRecurringModalOpen(false)} className="text-slate-400 hover:text-white transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleRecurringSubmit} className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Category *</label>
                  <select
                    value={recurringForm.category}
                    onChange={(e) => setRecurringForm({ ...recurringForm, category: e.target.value })}
                    className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                    data-testid="rec-form-category"
                  >
                    <option value="Rent">Rent</option>
                    <option value="Electricity">Electricity</option>
                    <option value="Salary">Salary</option>
                    <option value="EMI">EMI</option>
                    <option value="Other Expenses">Other Expenses</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Frequency *</label>
                  <select
                    value={recurringForm.frequency}
                    onChange={(e) => setRecurringForm({ ...recurringForm, frequency: e.target.value })}
                    className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                    data-testid="rec-form-frequency"
                  >
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                    <option value="yearly">Yearly</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Payee / Recipient *</label>
                <input
                  type="text"
                  placeholder="e.g. Landlord, State Power Corp, Bank Name"
                  value={recurringForm.payee}
                  onChange={(e) => setRecurringForm({ ...recurringForm, payee: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                  required
                  data-testid="rec-form-payee"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Base Amount (₹) *</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    placeholder="50000.00"
                    value={recurringForm.amount}
                    onChange={(e) => setRecurringForm({ ...recurringForm, amount: e.target.value })}
                    className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-bold outline-none focus:border-slate-800"
                    required
                    data-testid="rec-form-amount"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Due Day of Month (1-31) *</label>
                  <input
                    type="number"
                    min="1"
                    max="31"
                    value={recurringForm.due_day}
                    onChange={(e) => setRecurringForm({ ...recurringForm, due_day: e.target.value })}
                    className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-bold outline-none focus:border-slate-800"
                    required
                    data-testid="rec-form-due-day"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Start Date *</label>
                  <input
                    type="date"
                    value={recurringForm.start_date}
                    onChange={(e) => setRecurringForm({ ...recurringForm, start_date: e.target.value })}
                    className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                    required
                    data-testid="rec-form-start-date"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">End Date (Optional)</label>
                  <input
                    type="date"
                    value={recurringForm.end_date}
                    onChange={(e) => setRecurringForm({ ...recurringForm, end_date: e.target.value })}
                    className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                    data-testid="rec-form-end-date"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Bank Account (Optional)
                </label>
                <select
                  value={recurringForm.bank_account_id || ""}
                  onChange={(e) => setRecurringForm({ ...recurringForm, bank_account_id: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                  data-testid="rec-form-bank-account"
                >
                  <option value="">-- No Bank Account / Unassigned --</option>
                  {bankAccounts.map((acc) => (
                    <option key={acc.id || acc._id} value={acc.id || acc._id}>
                      {`${acc.name} (${acc.bank_name || "Bank"}${acc.account_number_last4 ? ` - ••${acc.account_number_last4}` : ""})`}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Notes</label>
                <textarea
                  rows={2}
                  placeholder="Template remarks..."
                  value={recurringForm.notes}
                  onChange={(e) => setRecurringForm({ ...recurringForm, notes: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-medium outline-none focus:border-slate-800"
                  data-testid="rec-form-notes"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
                <BtnSecondary type="button" onClick={() => setRecurringModalOpen(false)}>
                  Cancel
                </BtnSecondary>
                <BtnPrimary type="submit" disabled={submitting} data-testid="save-rec-template-btn">
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> : <Check className="w-4 h-4 inline mr-1" />}
                  Save Template
                </BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── ADD / EDIT ONE-TIME EXPENSE MODAL ────────────────────────────────── */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4" role="dialog">
          <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-lg overflow-hidden flex flex-col max-h-[90vh]">
            <div className="bg-[#0F172A] text-white px-5 py-3.5 flex items-center justify-between flex-shrink-0">
              <div className="font-bold text-sm uppercase tracking-wider flex items-center gap-2">
                <Receipt className="w-4 h-4 text-[#C27842]" /> {editingItem ? "Edit Expense Record" : "Add New Expense Record"}
              </div>
              <button onClick={() => setModalOpen(false)} className="text-slate-400 hover:text-white transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-5 space-y-4 overflow-y-auto flex-1">
              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Category *</label>
                <select
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                  data-testid="expense-form-category"
                >
                  {EXPENSE_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                  <option value="Other">Other Category (Custom)</option>
                </select>
                {form.category === "Other" && (
                  <input
                    type="text"
                    placeholder="Enter custom category name"
                    value={form.customCategory}
                    onChange={(e) => setForm({ ...form, customCategory: e.target.value })}
                    className="w-full mt-2 border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                    data-testid="expense-form-custom-category"
                  />
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Amount (₹) *</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    placeholder="0.00"
                    value={form.amount}
                    onChange={(e) => setForm({ ...form, amount: e.target.value })}
                    className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-bold outline-none focus:border-slate-800"
                    required
                    data-testid="expense-form-amount"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Date *</label>
                  <input
                    type="date"
                    value={form.date}
                    onChange={(e) => setForm({ ...form, date: e.target.value })}
                    className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                    required
                    data-testid="expense-form-date"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Payee / Recipient *</label>
                <input
                  type="text"
                  placeholder="e.g. Electric Board, Landlord, Vendor Name"
                  value={form.payee}
                  onChange={(e) => setForm({ ...form, payee: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                  required
                  data-testid="expense-form-payee"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                  Payment Method *
                </label>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, paid_via: "bank", cash_ledger_id: "" })}
                    className={`px-3 py-2 text-xs font-bold uppercase tracking-wider border-2 flex items-center justify-center gap-1.5 transition-all ${
                      form.paid_via === "bank"
                        ? "bg-[#0F172A] text-white border-[#0F172A] shadow-sm"
                        : "bg-slate-50 text-slate-700 border-slate-300 hover:bg-slate-100"
                    }`}
                    data-testid="expense-pay-via-bank"
                  >
                    <span>🏦 Bank Account</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, paid_via: "cash", bank_account_id: "" })}
                    className={`px-3 py-2 text-xs font-bold uppercase tracking-wider border-2 flex items-center justify-center gap-1.5 transition-all ${
                      form.paid_via === "cash"
                        ? "bg-amber-700 text-white border-amber-700 shadow-sm"
                        : "bg-slate-50 text-slate-700 border-slate-300 hover:bg-slate-100"
                    }`}
                    data-testid="expense-pay-via-cash"
                  >
                    <span>💵 Paid via Cash</span>
                  </button>
                </div>

                {form.paid_via === "bank" ? (
                  <div>
                    <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                      Bank Account (Optional)
                    </label>
                    <select
                      value={form.bank_account_id || ""}
                      onChange={(e) => setForm({ ...form, bank_account_id: e.target.value })}
                      className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-semibold outline-none focus:border-slate-800"
                      data-testid="expense-form-bank-account"
                    >
                      <option value="">-- No Bank Account / Unassigned --</option>
                      {bankAccounts.map((acc) => (
                        <option key={acc.id || acc._id} value={acc.id || acc._id}>
                          {`${acc.name} (${acc.bank_name || "Bank"}${acc.account_number_last4 ? ` - ••${acc.account_number_last4}` : ""})`}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-[10px] font-bold uppercase tracking-wider text-amber-900">
                        Cash in Hand Withdrawal Pool *
                      </label>
                      <button
                        type="button"
                        onClick={() => setShowCashWithdrawalModal(true)}
                        className="text-[10px] font-bold text-amber-800 hover:text-amber-950 underline flex items-center gap-1"
                        data-testid="expense-add-cash-pool-btn"
                      >
                        <Plus className="w-3 h-3" /> New Cash Withdrawal
                      </button>
                    </div>
                    <select
                      value={form.cash_ledger_id || ""}
                      onChange={(e) => setForm({ ...form, cash_ledger_id: e.target.value })}
                      className="w-full border-2 border-amber-400 bg-amber-50/40 px-3 py-2 text-xs font-bold text-amber-950 outline-none focus:border-amber-700"
                      required
                      data-testid="expense-form-cash-ledger"
                    >
                      <option value="">-- Select Cash Withdrawal to Draw From --</option>
                      {cashLedgerEntries.map((cl) => {
                        const cid = String(cl.id || cl._id);
                        const rem = Number(cl.remaining_balance ?? cl.amount ?? 0);
                        return (
                          <option key={cid} value={cid}>
                            {`Withdrawal #${cid.slice(-6)} • ${cl.date || "Date"} • ₹${inr(rem)} remaining${cl.notes ? ` (${cl.notes})` : ""}`}
                          </option>
                        );
                      })}
                    </select>
                    <p className="text-[10px] text-amber-800 mt-1 font-medium">
                      Payment will draw down this withdrawal's remaining cash pool.
                    </p>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-700 mb-1">Notes / Remarks</label>
                <textarea
                  rows={2}
                  placeholder="Bill details, invoice ref, payment notes..."
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-xs font-medium outline-none focus:border-slate-800"
                  data-testid="expense-form-notes"
                />
              </div>

              <div className="border-t border-slate-200 pt-3">
                <ImageUploader
                  label="Receipt Document / Image"
                  value={form.receipt}
                  onChange={(imgObj) => setForm({ ...form, receipt: imgObj })}
                  maxSizeMB={8}
                  testIdPrefix="expense-receipt"
                />
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-slate-200">
                <BtnSecondary type="button" onClick={() => setModalOpen(false)}>
                  Cancel
                </BtnSecondary>
                <BtnPrimary type="submit" disabled={submitting} data-testid="save-expense-btn">
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin inline mr-1" /> : <Check className="w-4 h-4 inline mr-1" />}
                  {editingItem ? "Update Expense" : "Save Expense"}
                </BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── DELETE CONFIRMATION MODAL ───────────────────────────────────────── */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4" role="dialog">
          <div className="bg-white border-2 border-red-600 p-6 max-w-sm w-full space-y-4">
            <h3 className="font-black text-red-700 text-base uppercase tracking-tight flex items-center gap-2">
              <Trash2 className="w-5 h-5" /> Delete Expense Record?
            </h3>
            <p className="text-xs text-slate-600">
              Are you sure you want to delete the expense of <strong className="text-slate-900">{inr(deleteConfirm.amount)}</strong> for{" "}
              <strong>{deleteConfirm.payee}</strong>? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <BtnSecondary onClick={() => setDeleteConfirm(null)}>Cancel</BtnSecondary>
              <button
                onClick={() => handleDelete(deleteConfirm.id)}
                className="bg-red-600 hover:bg-red-700 text-white font-bold uppercase tracking-wider text-xs px-4 py-2"
                data-testid="confirm-delete-expense"
              >
                Delete Record
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── RECORD DIRECT CASH WITHDRAWAL MODAL ─────────────────────────────── */}
      {showCashWithdrawalModal && (
        <RecordCashWithdrawalModal
          bankAccounts={bankAccounts}
          onClose={() => setShowCashWithdrawalModal(false)}
          onSuccess={(newEntry) => {
            setShowCashWithdrawalModal(false);
            loadData();
            if (newEntry && (newEntry.id || newEntry._id)) {
              const newId = String(newEntry.id || newEntry._id);
              if (modalOpen) {
                setForm((prev) => ({ ...prev, paid_via: "cash", cash_ledger_id: newId }));
              }
            }
          }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-Modal: Record Direct Cash Withdrawal Modal in Expenses
// ─────────────────────────────────────────────────────────────────────────────
function RecordCashWithdrawalModal({ bankAccounts, onClose, onSuccess }) {
  const [formData, setFormData] = useState({
    bank_account_id: bankAccounts[0]?.id || bankAccounts[0]?._id || "",
    amount: "",
    date: TODAY,
    notes: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.bank_account_id) {
      setError("Please select a bank account.");
      return;
    }
    const amt = parseFloat(formData.amount);
    if (!amt || amt <= 0) {
      setError("Please enter a valid cash amount > 0.");
      return;
    }
    if (!formData.date) {
      setError("Please select a withdrawal date.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await http.post("/banking/cash-ledger", {
        ...formData,
        amount: amt,
      });
      onSuccess(res.data?.cash_ledger || res.data);
    } catch (err) {
      setError(err.message || "Failed to record cash withdrawal");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 backdrop-blur-sm p-4">
      <div className="bg-white border-2 border-slate-900 shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95">
        <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between bg-amber-50/50">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-amber-800 font-bold">Finance / Cash In-Hand</div>
            <h3 className="font-bold text-base text-slate-900 mt-0.5 flex items-center gap-2">
              <Coins className="w-4 h-4 text-amber-600" /> Record Cash Withdrawal
            </h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div className="p-3 bg-amber-50 border border-amber-200 text-xs text-amber-900 space-y-1">
            <p className="font-bold">Record Physical Cash Withdrawal</p>
            <p className="text-[11px] text-amber-800">
              Creates a Cash in Hand entry immediately usable for cash expenses and wage payments without waiting for bank statement import.
            </p>
          </div>

          {error && (
            <div className="p-3 bg-red-50 border-2 border-red-300 text-red-800 text-xs font-medium">
              {error}
            </div>
          )}

          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Bank Account *</div>
            <select
              value={formData.bank_account_id}
              onChange={(e) => setFormData({ ...formData, bank_account_id: e.target.value })}
              className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs font-semibold focus:border-slate-800 focus:outline-none"
              required
              data-testid="record-cash-account-select"
            >
              <option value="">-- Select Bank Account --</option>
              {bankAccounts.map((acc) => {
                const accId = acc.id || acc._id;
                return (
                  <option key={accId} value={accId}>
                    {`${acc.name} (${acc.bank_name || "Bank"}${acc.account_number_last4 ? ` - ••${acc.account_number_last4}` : ""})`}
                  </option>
                );
              })}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Amount (₹) *</div>
              <input
                type="number"
                step="0.01"
                min="0.01"
                placeholder="e.g. 25000"
                value={formData.amount}
                onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs font-mono font-bold focus:border-slate-800 focus:outline-none"
                required
                data-testid="record-cash-amount-input"
              />
            </div>
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Withdrawal Date *</div>
              <input
                type="date"
                value={formData.date}
                onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs font-mono focus:border-slate-800 focus:outline-none"
                required
                data-testid="record-cash-date-input"
              />
            </div>
          </div>

          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Purpose / Notes (Optional)</div>
            <input
              type="text"
              placeholder="e.g. for worker wages this week"
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-xs focus:border-slate-800 focus:outline-none"
              data-testid="record-cash-notes-input"
            />
          </div>

          <div className="pt-3 flex items-center justify-end gap-2 border-t-2 border-slate-200">
            <BtnSecondary onClick={onClose} type="button">Cancel</BtnSecondary>
            <button
              type="submit"
              disabled={loading}
              className="bg-amber-600 hover:bg-amber-700 text-white font-bold uppercase tracking-wider text-xs px-4 py-2 border-2 border-amber-600 shadow-ind flex items-center gap-1.5 disabled:opacity-50 transition-colors"
              data-testid="record-cash-submit-btn"
            >
              {loading ? "Recording..." : "Record Cash Withdrawal"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
