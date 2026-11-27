import { useState, useEffect, useCallback } from "react";
import { http, inr } from "../lib/api";
import { Card, BtnPrimary, BtnSecondary, Badge, Input } from "./ui-kit";
import {
  Calendar,
  Plus,
  Trash2,
  IndianRupee,
  Users,
  BookOpen,
  Check,
  X,
  FileDown,
  Clock,
  Sparkles,
  Edit3,
} from "lucide-react";

const ATT_STATUSES = [
  { key: "present", short: "P", label: "Present", cls: "bg-emerald-100 text-emerald-800 border-emerald-300" },
  { key: "half_day", short: "HD", label: "Half Day", cls: "bg-amber-100 text-amber-800 border-amber-300" },
  { key: "paid_leave", short: "PL", label: "Paid Leave", cls: "bg-blue-100 text-blue-800 border-blue-300" },
  { key: "absent", short: "A", label: "Absent (LOP)", cls: "bg-rose-100 text-rose-800 border-rose-300" },
  { key: "holiday", short: "H", label: "Holiday", cls: "bg-purple-100 text-purple-800 border-purple-300" },
  { key: "week_off", short: "WO", label: "Week Off", cls: "bg-slate-100 text-slate-600 border-slate-300" },
];

export default function MonthlyStaffPayroll() {
  const today = new Date();
  const [subTab, setSubTab] = useState("salary"); // salary | attendance | holidays | staff
  const [month, setMonth] = useState(
    `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`
  );
  const [summary, setSummary] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [holidays, setHolidays] = useState([]);
  const [attendance, setAttendance] = useState([]);
  const [loading, setLoading] = useState(false);

  // Modals / Forms
  const [empForm, setEmpForm] = useState(null);
  const [holidayForm, setHolidayForm] = useState({ holiday_date: "", name: "", holiday_type: "Public Holiday" });
  const [payModal, setPayModal] = useState(null);
  const [ledgerModal, setLedgerModal] = useState(null);
  const [relieveModal, setRelieveModal] = useState(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const year = month.slice(0, 4);
      const [sumRes, empRes, holRes, attRes] = await Promise.all([
        http.get(`/staff-payroll/monthly-summary?month=${month}`),
        http.get("/staff-payroll/employees"),
        http.get(`/staff-payroll/holidays?year=${year}`),
        http.get(`/staff-payroll/attendance?month=${month}`),
      ]);
      setSummary(sumRes.data);
      setEmployees(empRes.data || []);
      setHolidays(holRes.data || []);
      setAttendance(attRes.data || []);
    } catch (e) {
      console.error("Failed to load monthly staff payroll:", e);
    } finally {
      setLoading(false);
    }
  }, [month]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // Attendance lookup map: `${staffId}_${date}` -> record
  const attMap = {};
  attendance.forEach((a) => {
    attMap[`${a.staff_id}_${a.date}`] = a;
  });
  const holidaySet = new Set(holidays.map((h) => h.holiday_date));

  const [yrNum, moNum] = month.split("-").map(Number);
  const daysInMonth = yrNum && moNum ? new Date(yrNum, moNum, 0).getDate() : 30;
  const daysArray = Array.from({ length: daysInMonth }, (_, i) => {
    const d = i + 1;
    const dStr = `${month}-${String(d).padStart(2, "0")}`;
    const isSunday = new Date(yrNum, moNum - 1, d).getDay() === 0;
    return { day: d, dateStr: dStr, isSunday, isHoliday: holidaySet.has(dStr) };
  });

  const cycleAttendance = async (staffId, dateStr, currentStatus) => {
    const order = ["present", "half_day", "paid_leave", "absent", "holiday", "week_off"];
    const nextIdx = (order.indexOf(currentStatus) + 1) % order.length;
    const nextStatus = order[nextIdx];
    try {
      await http.post("/staff-payroll/attendance", {
        staff_id: staffId,
        date: dateStr,
        status: nextStatus,
      });
      loadAll();
    } catch (e) {
      alert(e.response?.data?.detail || "Failed to update attendance");
    }
  };

  const markBulkToday = async (status) => {
    const targetDate = today.toISOString().slice(0, 10);
    try {
      await http.post("/staff-payroll/attendance/bulk", { date: targetDate, status });
      loadAll();
    } catch (e) {
      alert(e.response?.data?.detail || "Failed to mark bulk attendance");
    }
  };

  const saveEmployee = async (e) => {
    e.preventDefault();
    if (!empForm?.name?.trim()) return;
    try {
      const payload = {
        ...empForm,
        role: empForm.role || "Staff",
        department: empForm.department || "Operations",
        monthly_salary: Number(empForm.monthly_salary || 0),
        phone: empForm.phone || "",
        joining_date: empForm.joining_date || "",
        relieving_date: empForm.relieving_date || "",
        is_active: empForm.relieving_date ? false : empForm.is_active !== false,
      };
      if (empForm.id) {
        await http.put(`/staff-payroll/employees/${empForm.id}`, payload);
      } else {
        await http.post("/staff-payroll/employees", payload);
      }
      setEmpForm(null);
      loadAll();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to save employee");
    }
  };

  const deleteEmployee = async (id) => {
    if (!window.confirm("Remove this salaried staff member?")) return;
    await http.delete(`/staff-payroll/employees/${id}`);
    loadAll();
  };

  const addHoliday = async (e) => {
    e.preventDefault();
    if (!holidayForm.holiday_date || !holidayForm.name.trim()) return;
    try {
      await http.post("/staff-payroll/holidays", holidayForm);
      setHolidayForm({ holiday_date: "", name: "", holiday_type: "Public Holiday" });
      loadAll();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to add holiday");
    }
  };

  const deleteHoliday = async (id) => {
    await http.delete(`/staff-payroll/holidays/${id}`);
    loadAll();
  };

  const submitPayment = async (e) => {
    e.preventDefault();
    if (!payModal) return;
    try {
      await http.post("/staff-payroll/pay", {
        staff_id: payModal.staff_id,
        month,
        amount: Number(payModal.amount || 0),
        bonus: Number(payModal.bonus || 0),
        advance_deduction: Number(payModal.advance_deduction || 0),
        payment_mode: payModal.payment_mode || "bank",
        reference_no: payModal.reference_no || "",
        notes: payModal.notes || "",
      });
      setPayModal(null);
      loadAll();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to record salary payment");
    }
  };

  const openLedger = async (staffId) => {
    try {
      const res = await http.get(`/staff-payroll/employees/${staffId}/ledger`);
      setLedgerModal(res.data);
    } catch (err) {
      alert("Failed to load staff ledger");
    }
  };

  const submitRelieve = async (e) => {
    e.preventDefault();
    if (!relieveModal?.relieving_date) return;
    try {
      await http.put(`/staff-payroll/employees/${relieveModal.id}`, {
        name: relieveModal.name,
        role: relieveModal.role || "Staff",
        department: relieveModal.department || "Operations",
        monthly_salary: Number(relieveModal.monthly_salary || 0),
        phone: relieveModal.phone || "",
        joining_date: relieveModal.joining_date || "",
        relieving_date: relieveModal.relieving_date,
        is_active: false,
      });
      setRelieveModal(null);
      loadAll();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to relieve staff member");
    }
  };

  const exportCsv = () => {
    if (!summary?.rows?.length) return;
    const headers = [
      "Name", "Role", "Department", "Monthly Salary", "Days in Month",
      "Present", "Half Day", "Paid Leave", "Holiday", "Week Off", "Absent (LOP)",
      "LOP Deduction", "Overtime Pay", "Bonus", "Advance Deduction", "Net Payable", "Paid", "Balance Due",
    ];
    const lines = [headers.join(",")];
    summary.rows.forEach((r) => {
      lines.push([
        `"${r.name || ""}"`, `"${r.role || ""}"`, `"${r.department || ""}"`,
        r.monthly_salary, r.days_in_month, r.present_days, r.half_days,
        r.paid_leave_days, r.holiday_days, r.week_off_days, r.absent_days,
        r.lop_deduction, r.overtime_pay, r.bonus, r.advance_deduction,
        r.net_payable, r.paid_amount, r.balance_due,
      ].join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `monthly_staff_salary_${month}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const rows = summary?.rows || [];
  const totals = summary?.totals || {};

  return (
    <div className="space-y-5">
      {/* Top Controls & Sub-tabs */}
      <Card className="p-4 flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {[
            { id: "salary", label: "Salary Sheet & Ledger", icon: IndianRupee },
            { id: "attendance", label: "Attendance Register", icon: Calendar },
            { id: "holidays", label: `Holiday List (${holidays.length})`, icon: Sparkles },
            { id: "staff", label: `Salaried Staff (${employees.length})`, icon: Users },
          ].map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                onClick={() => setSubTab(t.id)}
                className={`px-3 py-1.5 text-xs font-bold uppercase tracking-wider border-2 flex items-center gap-1.5 transition ${
                  subTab === t.id
                    ? "bg-slate-900 text-white border-slate-900"
                    : "bg-white text-slate-700 border-slate-300 hover:border-slate-900"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{t.label}</span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2">
          <label className="text-[10px] uppercase font-bold text-slate-500">Month:</label>
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="border-2 border-slate-300 px-2.5 py-1 text-xs font-mono font-bold bg-white"
          />
          <BtnSecondary onClick={exportCsv} className="text-xs py-1 px-2.5">
            <FileDown className="w-3.5 h-3.5 inline mr-1" />
            Export CSV
          </BtnSecondary>
          <BtnPrimary
            onClick={() =>
              setEmpForm({
                name: "",
                role: "Supervisor",
                department: "Production",
                monthly_salary: "",
                phone: "",
                joining_date: today.toISOString().slice(0, 10),
                is_active: true,
              })
            }
            className="text-xs py-1 px-3"
          >
            <Plus className="w-3.5 h-3.5 inline mr-1" />
            Add Staff
          </BtnPrimary>
        </div>
      </Card>

      {/* Summary Metric Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <Card className="p-3 border-l-4 border-l-slate-900">
          <div className="text-[10px] uppercase font-bold text-slate-500">Monthly Gross</div>
          <div className="text-lg font-mono font-black text-slate-900 mt-0.5">{inr(totals.total_gross || 0)}</div>
        </Card>
        <Card className="p-3 border-l-4 border-l-rose-600">
          <div className="text-[10px] uppercase font-bold text-slate-500">LOP &amp; Deductions</div>
          <div className="text-lg font-mono font-black text-rose-700 mt-0.5">{inr(totals.total_deductions || 0)}</div>
        </Card>
        <Card className="p-3 border-l-4 border-l-[#C27842]">
          <div className="text-[10px] uppercase font-bold text-slate-500">Net Payable</div>
          <div className="text-lg font-mono font-black text-[#C27842] mt-0.5">{inr(totals.total_net_payable || 0)}</div>
        </Card>
        <Card className="p-3 border-l-4 border-l-emerald-600">
          <div className="text-[10px] uppercase font-bold text-slate-500">Paid This Month</div>
          <div className="text-lg font-mono font-black text-emerald-700 mt-0.5">{inr(totals.total_paid || 0)}</div>
        </Card>
        <Card className="p-3 border-l-4 border-l-amber-500">
          <div className="text-[10px] uppercase font-bold text-slate-500">Balance Due</div>
          <div className="text-lg font-mono font-black text-amber-700 mt-0.5">{inr(totals.total_balance_due || 0)}</div>
        </Card>
      </div>

      {/* SUB-TAB 1: SALARY SHEET & LEDGER */}
      {subTab === "salary" && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead className="bg-slate-900 text-white uppercase text-[10px] font-mono">
                <tr>
                  <th className="px-3 py-2.5">Staff Member</th>
                  <th className="px-3 py-2.5 text-right">Base Salary</th>
                  <th className="px-3 py-2.5 text-center">Present</th>
                  <th className="px-3 py-2.5 text-center">Half Day</th>
                  <th className="px-3 py-2.5 text-center">Paid Leave</th>
                  <th className="px-3 py-2.5 text-center">Holiday/WO</th>
                  <th className="px-3 py-2.5 text-center">Absent (LOP)</th>
                  <th className="px-3 py-2.5 text-right">LOP Ded.</th>
                  <th className="px-3 py-2.5 text-right">Net Payable</th>
                  <th className="px-3 py-2.5 text-right">Paid</th>
                  <th className="px-3 py-2.5 text-right">Due</th>
                  <th className="px-3 py-2.5 text-center">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white">
                {loading ? (
                  <tr>
                    <td colSpan={12} className="p-6 text-center text-slate-500 font-mono">Loading monthly salary sheet...</td>
                  </tr>
                ) : rows.length === 0 ? (
                  <tr>
                    <td colSpan={12} className="p-8 text-center text-slate-500">
                      No monthly salaried staff added yet. Click <strong>+ Add Staff</strong> to add your first employee.
                    </td>
                  </tr>
                ) : (
                  rows.map((r) => (
                    <tr key={r.staff_id} className="hover:bg-slate-50">
                      <td className="px-3 py-2.5">
                        <div className="font-bold text-slate-900">{r.name}</div>
                        <div className="text-[10px] text-slate-500 font-mono">
                          {r.role} · {r.department}
                          {r.employed_days < r.days_in_month && (
                            <span className="ml-1.5 text-[#C27842] font-bold">
                              ({r.employed_days}/{r.days_in_month}d pro-rata)
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono font-bold">
                        <div>{inr(r.pro_rata_salary ?? r.monthly_salary)}</div>
                        {r.employed_days < r.days_in_month && (
                          <div className="text-[10px] text-slate-400 line-through">{inr(r.monthly_salary)}</div>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-center font-mono text-emerald-700 font-bold">{r.present_days}</td>
                      <td className="px-3 py-2.5 text-center font-mono text-amber-700">{r.half_days}</td>
                      <td className="px-3 py-2.5 text-center font-mono text-blue-700">{r.paid_leave_days}</td>
                      <td className="px-3 py-2.5 text-center font-mono text-purple-700">{r.holiday_days + r.week_off_days}</td>
                      <td className="px-3 py-2.5 text-center font-mono text-rose-700 font-bold">{r.absent_days}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-rose-700">{inr(r.lop_deduction)}</td>
                      <td className="px-3 py-2.5 text-right font-mono font-black text-slate-900">{inr(r.net_payable)}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-emerald-700">{inr(r.paid_amount)}</td>
                      <td className="px-3 py-2.5 text-right font-mono font-bold text-[#C27842]">{inr(r.balance_due)}</td>
                      <td className="px-3 py-2.5 text-center whitespace-nowrap space-x-1">
                        <button
                          onClick={() => openLedger(r.staff_id)}
                          className="px-2 py-1 text-[10px] font-bold uppercase border border-slate-300 hover:border-slate-900 bg-white"
                          title="View Staff Ledger"
                        >
                          <BookOpen className="w-3 h-3 inline mr-0.5" /> Ledger
                        </button>
                        {r.balance_due > 0 && (
                          <button
                            onClick={() =>
                              setPayModal({
                                staff_id: r.staff_id,
                                name: r.name,
                                amount: r.balance_due,
                                bonus: 0,
                                advance_deduction: 0,
                                payment_mode: "bank",
                                reference_no: "",
                                notes: "",
                              })
                            }
                            className="px-2 py-1 text-[10px] font-bold uppercase bg-emerald-700 text-white hover:bg-emerald-800"
                          >
                            Pay
                          </button>
                        )}
                        {!r.relieving_date && (
                          <button
                            onClick={() => {
                              const emp = employees.find((x) => x.id === r.staff_id);
                              setRelieveModal({
                                ...(emp || {
                                  id: r.staff_id,
                                  name: r.name,
                                  role: r.role,
                                  department: r.department,
                                  monthly_salary: r.monthly_salary,
                                  phone: r.phone,
                                  joining_date: r.joining_date,
                                }),
                                relieving_date: new Date().toISOString().slice(0, 10),
                              });
                            }}
                            className="px-2 py-1 text-[10px] font-bold uppercase border border-rose-300 text-rose-700 hover:bg-rose-50"
                            title="Relieve Staff Member"
                          >
                            Relieve
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* SUB-TAB 2: ATTENDANCE CALENDAR */}
      {subTab === "attendance" && (
        <Card className="p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-2">
            <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono">
              <span className="font-bold uppercase text-slate-700">Click cell to cycle:</span>
              {ATT_STATUSES.map((s) => (
                <span key={s.key} className={`px-1.5 py-0.5 border font-bold ${s.cls}`}>
                  {s.short} = {s.label}
                </span>
              ))}
            </div>
            <BtnSecondary onClick={() => markBulkToday("present")} className="text-xs py-1 px-2.5">
              <Check className="w-3.5 h-3.5 inline mr-1 text-emerald-700" />
              Mark Today All Present
            </BtnSecondary>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[10px] font-mono border-collapse">
              <thead>
                <tr className="bg-slate-100 border-b border-slate-300">
                  <th className="px-2 py-1.5 text-left sticky left-0 bg-slate-100 z-10 min-w-[140px]">Employee</th>
                  {daysArray.map((d) => (
                    <th
                      key={d.day}
                      className={`px-1 py-1.5 text-center min-w-[26px] ${
                        d.isHoliday ? "bg-purple-100 text-purple-900" : d.isSunday ? "bg-slate-200 text-slate-600" : ""
                      }`}
                    >
                      {d.day}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {employees.filter((e) => e.is_active).map((emp) => (
                  <tr key={emp.id}>
                    <td className="px-2 py-1.5 font-bold text-slate-900 sticky left-0 bg-white border-r border-slate-200 truncate max-w-[140px]">
                      {emp.name}
                    </td>
                    {daysArray.map((d) => {
                      const rec = attMap[`${emp.id}_${d.dateStr}`];
                      const st = rec?.status || (d.isHoliday ? "holiday" : d.isSunday ? "week_off" : "");
                      const meta = ATT_STATUSES.find((s) => s.key === st);
                      return (
                        <td key={d.day} className="p-0.5 text-center">
                          <button
                            type="button"
                            onClick={() => cycleAttendance(emp.id, d.dateStr, st || "week_off")}
                            className={`w-6 h-6 text-[9px] font-bold border rounded transition ${
                              meta ? meta.cls : "bg-white text-slate-300 border-slate-200 hover:border-slate-500"
                            }`}
                            title={`${emp.name} (${d.dateStr}): ${meta?.label || "Unmarked"}`}
                          >
                            {meta ? meta.short : "·"}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* SUB-TAB 3: HOLIDAY LIST */}
      {subTab === "holidays" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <Card className="lg:col-span-4 p-4 space-y-3">
            <h3 className="font-bold text-xs uppercase tracking-wider text-slate-900 border-b border-slate-200 pb-2">
              Add Company / Public Holiday
            </h3>
            <form onSubmit={addHoliday} className="space-y-2.5 text-xs">
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Holiday Date *</label>
                <input
                  type="date"
                  required
                  value={holidayForm.holiday_date}
                  onChange={(e) => setHolidayForm((f) => ({ ...f, holiday_date: e.target.value }))}
                  className="w-full border-2 border-slate-300 px-2.5 py-1.5 font-mono"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Holiday Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Diwali, Republic Day"
                  value={holidayForm.name}
                  onChange={(e) => setHolidayForm((f) => ({ ...f, name: e.target.value }))}
                  className="w-full border-2 border-slate-300 px-2.5 py-1.5"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Type</label>
                <select
                  value={holidayForm.holiday_type}
                  onChange={(e) => setHolidayForm((f) => ({ ...f, holiday_type: e.target.value }))}
                  className="w-full border-2 border-slate-300 px-2.5 py-1.5 bg-white"
                >
                  <option value="Public Holiday">Public Holiday</option>
                  <option value="Festival">Festival Holiday</option>
                  <option value="Company Off">Company Off</option>
                </select>
              </div>
              <BtnPrimary type="submit" className="w-full py-2 text-xs">Add Holiday</BtnPrimary>
            </form>
          </Card>

          <Card className="lg:col-span-8 p-4">
            <h3 className="font-bold text-xs uppercase tracking-wider text-slate-900 border-b border-slate-200 pb-2 mb-3">
              Holiday Calendar ({month.slice(0, 4)})
            </h3>
            {holidays.length === 0 ? (
              <p className="text-xs text-slate-500 py-6 text-center">No holidays configured for this year.</p>
            ) : (
              <div className="divide-y divide-slate-200">
                {holidays.map((h) => (
                  <div key={h.id} className="py-2 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-3">
                      <span className="font-mono font-bold px-2 py-0.5 bg-purple-100 text-purple-900 border border-purple-300">
                        {h.holiday_date}
                      </span>
                      <span className="font-bold text-slate-900">{h.name}</span>
                      <Badge color="slate">{h.holiday_type}</Badge>
                    </div>
                    <button onClick={() => deleteHoliday(h.id)} className="text-slate-400 hover:text-rose-600 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {/* SUB-TAB 4: SALARIED STAFF MASTER */}
      {subTab === "staff" && (
        <Card className="overflow-hidden">
          <table className="w-full text-left border-collapse text-xs">
            <thead className="bg-slate-900 text-white uppercase text-[10px] font-mono">
              <tr>
                <th className="px-3 py-2.5">Name</th>
                <th className="px-3 py-2.5">Role / Designation</th>
                <th className="px-3 py-2.5">Department</th>
                <th className="px-3 py-2.5">Phone</th>
                <th className="px-3 py-2.5">DOJ / DOR</th>
                <th className="px-3 py-2.5 text-right">Monthly Salary</th>
                <th className="px-3 py-2.5 text-center">Status</th>
                <th className="px-3 py-2.5 text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 bg-white">
              {employees.map((emp) => (
                <tr key={emp.id} className="hover:bg-slate-50">
                  <td className="px-3 py-2.5 font-bold text-slate-900">{emp.name}</td>
                  <td className="px-3 py-2.5">{emp.role}</td>
                  <td className="px-3 py-2.5 font-mono">{emp.department}</td>
                  <td className="px-3 py-2.5 font-mono">{emp.phone || "—"}</td>
                  <td className="px-3 py-2.5 font-mono text-[11px]">
                    <div>DOJ: {emp.joining_date || "—"}</div>
                    {emp.relieving_date && <div className="text-rose-600">DOR: {emp.relieving_date}</div>}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono font-bold">{inr(emp.monthly_salary)}</td>
                  <td className="px-3 py-2.5 text-center">
                    <Badge color={emp.is_active ? "green" : "slate"}>{emp.is_active ? "Active" : "Inactive"}</Badge>
                  </td>
                  <td className="px-3 py-2.5 text-center space-x-2">
                    <button onClick={() => setEmpForm(emp)} className="text-slate-600 hover:text-blue-600" title="Edit Staff">
                      <Edit3 className="w-4 h-4 inline" />
                    </button>
                    {!emp.relieving_date && emp.is_active !== false && (
                      <button
                        onClick={() =>
                          setRelieveModal({
                            ...emp,
                            relieving_date: new Date().toISOString().slice(0, 10),
                          })
                        }
                        className="px-2 py-0.5 text-[10px] font-bold uppercase border border-rose-300 text-rose-700 hover:bg-rose-50"
                        title="Relieve Staff Member"
                      >
                        Relieve
                      </button>
                    )}
                    <button onClick={() => deleteEmployee(emp.id)} className="text-slate-600 hover:text-rose-600" title="Delete Staff">
                      <Trash2 className="w-4 h-4 inline" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* ADD / EDIT STAFF MODAL */}
      {empForm && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white border-2 border-slate-900 w-full max-w-md p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <h3 className="font-bold text-sm uppercase">{empForm.id ? "Edit Salaried Staff" : "Add Salaried Staff"}</h3>
              <button onClick={() => setEmpForm(null)}><X className="w-4 h-4" /></button>
            </div>
            <form onSubmit={saveEmployee} className="space-y-2.5 text-xs">
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Full Name *</label>
                <input required type="text" value={empForm.name} onChange={(e) => setEmpForm({ ...empForm, name: e.target.value })} className="w-full border-2 border-slate-300 px-2.5 py-1.5" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Role / Designation</label>
                  <input type="text" value={empForm.role} onChange={(e) => setEmpForm({ ...empForm, role: e.target.value })} className="w-full border-2 border-slate-300 px-2.5 py-1.5" />
                </div>
                <div>
                  <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Department</label>
                  <input type="text" value={empForm.department} onChange={(e) => setEmpForm({ ...empForm, department: e.target.value })} className="w-full border-2 border-slate-300 px-2.5 py-1.5" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Monthly Salary (₹) *</label>
                  <input required type="number" min="0" value={empForm.monthly_salary} onChange={(e) => setEmpForm({ ...empForm, monthly_salary: e.target.value })} className="w-full border-2 border-slate-300 px-2.5 py-1.5 font-mono" />
                </div>
                <div>
                  <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Phone</label>
                  <input type="text" value={empForm.phone || ""} onChange={(e) => setEmpForm({ ...empForm, phone: e.target.value })} className="w-full border-2 border-slate-300 px-2.5 py-1.5 font-mono" />
                </div>
              </div>
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Date of Joining *</label>
                <input required type="date" value={empForm.joining_date || ""} onChange={(e) => setEmpForm({ ...empForm, joining_date: e.target.value })} className="w-full border-2 border-slate-300 px-2.5 py-1.5 font-mono" />
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <BtnSecondary type="button" onClick={() => setEmpForm(null)}>Cancel</BtnSecondary>
                <BtnPrimary type="submit">Save Staff</BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* RELIEVE STAFF MODAL */}
      {relieveModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white border-2 border-slate-900 w-full max-w-sm p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <h3 className="font-bold text-sm uppercase">Relieve Staff · {relieveModal.name}</h3>
              <button onClick={() => setRelieveModal(null)}><X className="w-4 h-4" /></button>
            </div>
            <form onSubmit={submitRelieve} className="space-y-3 text-xs">
              <div className="text-[11px] text-slate-600">
                Date of Joining: <span className="font-mono font-bold">{relieveModal.joining_date || "—"}</span>
              </div>
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Date of Relieving *</label>
                <input
                  required
                  type="date"
                  min={relieveModal.joining_date || undefined}
                  value={relieveModal.relieving_date || ""}
                  onChange={(e) => setRelieveModal({ ...relieveModal, relieving_date: e.target.value })}
                  className="w-full border-2 border-slate-300 px-2.5 py-1.5 font-mono"
                />
              </div>
              <p className="text-[11px] text-slate-500">
                Salary for the relieving month will be automatically pro-rated up to this date.
              </p>
              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <BtnSecondary type="button" onClick={() => setRelieveModal(null)}>Cancel</BtnSecondary>
                <BtnPrimary type="submit">Confirm Relieve</BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* PAY SALARY MODAL */}
      {payModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white border-2 border-slate-900 w-full max-w-md p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <h3 className="font-bold text-sm uppercase">Pay Salary · {payModal.name} ({month})</h3>
              <button onClick={() => setPayModal(null)}><X className="w-4 h-4" /></button>
            </div>
            <form onSubmit={submitPayment} className="space-y-2.5 text-xs">
              <div>
                <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Amount to Pay (₹) *</label>
                <input required type="number" step="0.01" min="1" value={payModal.amount} onChange={(e) => setPayModal({ ...payModal, amount: e.target.value })} className="w-full border-2 border-slate-300 px-2.5 py-1.5 font-mono font-bold" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Bonus (₹)</label>
                  <input type="number" step="0.01" min="0" value={payModal.bonus} onChange={(e) => setPayModal({ ...payModal, bonus: e.target.value })} className="w-full border-2 border-slate-300 px-2.5 py-1.5 font-mono" />
                </div>
                <div>
                  <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Advance Ded. (₹)</label>
                  <input type="number" step="0.01" min="0" value={payModal.advance_deduction} onChange={(e) => setPayModal({ ...payModal, advance_deduction: e.target.value })} className="w-full border-2 border-slate-300 px-2.5 py-1.5 font-mono" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Payment Mode</label>
                  <select value={payModal.payment_mode} onChange={(e) => setPayModal({ ...payModal, payment_mode: e.target.value })} className="w-full border-2 border-slate-300 px-2.5 py-1.5 bg-white">
                    <option value="bank">Bank Transfer</option>
                    <option value="cash">Cash</option>
                    <option value="upi">UPI</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase font-bold text-slate-600 block mb-1">Ref / UTR</label>
                  <input type="text" value={payModal.reference_no} onChange={(e) => setPayModal({ ...payModal, reference_no: e.target.value })} className="w-full border-2 border-slate-300 px-2.5 py-1.5 font-mono" />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <BtnSecondary type="button" onClick={() => setPayModal(null)}>Cancel</BtnSecondary>
                <BtnPrimary type="submit">Confirm Salary Payment</BtnPrimary>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* STAFF LEDGER DRAWER */}
      {ledgerModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white border-2 border-slate-900 w-full max-w-xl p-5 space-y-3 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <div>
                <h3 className="font-bold text-sm uppercase">{ledgerModal.employee?.name} · Salary Ledger</h3>
                <p className="text-[11px] font-mono text-slate-500">
                  {ledgerModal.employee?.role} · Base: {inr(ledgerModal.employee?.monthly_salary || 0)}/mo · Total Paid: {inr(ledgerModal.total_paid || 0)}
                </p>
              </div>
              <button onClick={() => setLedgerModal(null)}><X className="w-4 h-4" /></button>
            </div>
            <div className="overflow-y-auto flex-1">
              {(ledgerModal.payments || []).length === 0 ? (
                <p className="text-xs text-slate-500 py-6 text-center">No salary payments recorded yet.</p>
              ) : (
                <table className="w-full text-xs text-left border-collapse">
                  <thead className="bg-slate-100 text-[10px] uppercase font-mono">
                    <tr>
                      <th className="px-2 py-1.5">Date</th>
                      <th className="px-2 py-1.5">Month</th>
                      <th className="px-2 py-1.5">Mode</th>
                      <th className="px-2 py-1.5">Ref</th>
                      <th className="px-2 py-1.5 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {ledgerModal.payments.map((p) => (
                      <tr key={p.id}>
                        <td className="px-2 py-1.5 font-mono">{String(p.paid_at || "").slice(0, 10)}</td>
                        <td className="px-2 py-1.5 font-mono font-bold">{p.month}</td>
                        <td className="px-2 py-1.5 uppercase">{p.payment_mode}</td>
                        <td className="px-2 py-1.5 font-mono">{p.reference_no || "—"}</td>
                        <td className="px-2 py-1.5 text-right font-mono font-bold text-emerald-700">{inr(p.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
