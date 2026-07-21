import { useState, useEffect, useCallback } from "react";
import { http, inr } from "../lib/api";
import { PageHeader, Card, Badge, BtnPrimary, BtnSecondary } from "../components/ui-kit";
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
  FileText,
  PieChart as PieChartIcon,
  Loader2,
  ArrowUpRight,
  ArrowDownRight,
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
  // Main data state
  const [expenses, setExpenses] = useState([]);
  const [pnl, setPnl] = useState({
    revenue: 0,
    invoices_revenue: 0,
    settlements_revenue: 0,
    material_cost: 0,
    labor_cost: 0,
    expenses: 0,
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

  // Drawer / Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  // Form state
  const [form, setForm] = useState({
    category: EXPENSE_CATEGORIES[0],
    customCategory: "",
    amount: "",
    date: TODAY,
    payee: "",
    notes: "",
    receipt: null,
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (categoryFilter !== "all") params.category = categoryFilter;
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      if (search) params.search = search;

      const [expRes, pnlRes] = await Promise.all([
        http.get("/expenses", { params }),
        http.get("/reports/pnl", { params: { from_date: fromDate, to_date: toDate } }),
      ]);

      setExpenses(expRes.data || []);
      if (pnlRes.data) {
        setPnl(pnlRes.data);
      }
    } catch (err) {
      console.error("Failed to load expenses/P&L:", err);
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, fromDate, toDate, search]);

  useEffect(() => {
    loadData();
  }, [loadData]);

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
    });
    setModalOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.amount || parseFloat(form.amount) <= 0 || !form.payee.trim()) {
      alert("Please enter a valid amount and payee name.");
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

  const handleDelete = async (id) => {
    try {
      await http.delete(`/expenses/${id}`);
      setDeleteConfirm(null);
      loadData();
    } catch (err) {
      alert(err?.response?.data?.detail || "Failed to delete expense");
    }
  };

  // Compute total expenses from current list
  const listTotalExpenses = expenses.reduce((sum, item) => sum + (item.amount || 0), 0);

  // Group by category for current view
  const categorySummary = expenses.reduce((acc, item) => {
    const cat = item.category || "Uncategorized";
    acc[cat] = (acc[cat] || 0) + (item.amount || 0);
    return acc;
  }, {});

  // Group by month for current view
  const monthlyExpensesSummary = expenses.reduce((acc, item) => {
    const m = (item.date || "").substring(0, 7) || "Other";
    acc[m] = (acc[m] || 0) + (item.amount || 0);
    return acc;
  }, {});

  return (
    <div>
      <PageHeader
        title="Expenses & Simple P&L"
        subtitle="Financial Expense Logging, Category Filtering & Profit & Loss Statement"
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

          {/* Card 3: Operating Expenses */}
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
              <span>{expenses.length} Records</span>
              <span>Filter Total: {inr(listTotalExpenses)}</span>
            </div>
          </Card>

          {/* Card 4: Net P&L (Revenue - Costs - Expenses) */}
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

        {/* ── MONTHLY P&L TREND VISUALIZATION CHART ───────────────────────────── */}
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
                      if (absV >= 1000) {
                        return `${sign}₹${(absV / 1000).toFixed(0)}k`;
                      }
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

        {/* ── ACTION BAR & FILTERS ────────────────────────────────────────────── */}
        <div className="bg-white p-4 border border-slate-200 shadow-sm flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
          <div className="flex flex-wrap gap-2 items-center flex-1">
            {/* Search Input */}
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

            {/* Category Filter */}
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

            {/* Date Filters */}
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

          <BtnPrimary onClick={openNewModal} data-testid="add-expense-btn" className="flex items-center gap-2">
            <Plus className="w-4 h-4" /> Add Expense
          </BtnPrimary>
        </div>

        {/* ── EXPENSE CATEGORY & MONTHLY SUMMARY GRID ─────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Expenses Table (Takes 2 Columns) */}
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
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse" data-testid="expenses-table">
                    <thead>
                      <tr className="bg-slate-100 border-b border-slate-200 text-slate-600 uppercase tracking-wider text-[10px] font-bold">
                        <th className="p-3">Receipt</th>
                        <th className="p-3">Date</th>
                        <th className="p-3">Payee</th>
                        <th className="p-3">Category</th>
                        <th className="p-3">Notes</th>
                        <th className="p-3 text-right">Amount</th>
                        <th className="p-3 text-center">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {expenses.map((item) => (
                        <tr key={item.id} className="hover:bg-slate-50 transition-colors" data-testid={`expense-row-${item.id}`}>
                          <td className="p-3">
                            <ImageThumb image={item.receipt} size={36} alt="Receipt" clickable testId={`receipt-thumb-${item.id}`} />
                          </td>
                          <td className="p-3 font-semibold text-slate-800 whitespace-nowrap">{item.date}</td>
                          <td className="p-3 font-bold text-slate-900">{item.payee}</td>
                          <td className="p-3 whitespace-nowrap">
                            <span className="inline-block px-2 py-0.5 bg-slate-100 border border-slate-300 font-semibold text-[11px] text-slate-700 rounded-sm">
                              {item.category}
                            </span>
                          </td>
                          <td className="p-3 text-slate-500 max-w-[200px] truncate" title={item.notes}>
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
              )}
            </Card>
          </div>

          {/* Side Column: Category & Monthly Breakdown (1 Column) */}
          <div className="space-y-6">
            {/* Category Breakdown Card */}
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

            {/* Monthly Expense Totals */}
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

      {/* ── ADD / EDIT EXPENSE MODAL ────────────────────────────────────────── */}
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
              {/* Category */}
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

              {/* Amount & Date */}
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

              {/* Payee */}
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

              {/* Notes */}
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

              {/* Receipt Upload using ImageUploader component */}
              <div className="border-t border-slate-200 pt-3">
                <ImageUploader
                  label="Receipt Document / Image"
                  value={form.receipt}
                  onChange={(imgObj) => setForm({ ...form, receipt: imgObj })}
                  maxSizeMB={8}
                  testIdPrefix="expense-receipt"
                />
              </div>

              {/* Actions */}
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
    </div>
  );
}
