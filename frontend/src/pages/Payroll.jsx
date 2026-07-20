import { useEffect, useState } from "react";
import { http, API, inr } from "../lib/api";
import {
  PageHeader,
  Card,
  BtnPrimary,
  BtnSecondary,
  Input,
  Badge,
  ConfirmDialog,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import {
  Calendar,
  FileDown,
  IndianRupee,
  Plus,
  Trash2,
  Check,
  X,
  Users as UsersIcon,
  BookOpen,
  ArrowDownLeft,
  Sparkles,
} from "lucide-react";

const ROLE_LABEL = {
  cutting: "Cutting",
  upper: "Upper",
  bottom: "Bottom/Insole",
  stitching: "Stitching",
  lasting: "Lasting",
  sole_pasting: "Sole Pasting",
  finishing: "Finishing",
  qc_pack: "QC & Pack",
};

export default function Payroll() {
  const today = new Date();
  const monthStart = new Date(today.getFullYear(), today.getMonth(), 1)
    .toISOString()
    .slice(0, 10);
  const [fromDate, setFromDate] = useState(monthStart);
  const [toDate, setToDate] = useState(today.toISOString().slice(0, 10));
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [workers, setWorkers] = useState([]);
  const [showAdvances, setShowAdvances] = useState(false);
  const [advances, setAdvances] = useState([]);
  const [advForm, setAdvForm] = useState(null);
  const [ledgerFor, setLedgerFor] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const load = async () => {
    const params = new URLSearchParams();
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const [p, w] = await Promise.all([
      http.get(`/reports/payroll?${params.toString()}`),
      http.get("/workers"),
    ]);
    setData(p.data);
    setWorkers(w.data);
  };
  const loadAdvances = async () => {
    const { data } = await http.get("/advances");
    setAdvances(data);
  };
  useEffect(() => {
    load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const openAdvancesDrawer = async () => {
    await loadAdvances();
    setShowAdvances(true);
  };

  const dlPayrollPdf = () => {
    const url = `${API}/reports/payroll.pdf?from_date=${fromDate}&to_date=${toDate}`;
    window.open(url, "_blank");
  };
  const dlWageSlip = (wid, e) => {
    e.stopPropagation();
    const url = `${API}/reports/payroll/${wid}.pdf?from_date=${fromDate}&to_date=${toDate}`;
    window.open(url, "_blank");
  };

  const submitAdvance = async () => {
    try {
      await http.post("/advances", {
        worker_id: advForm.worker_id,
        amount: Number(advForm.amount),
        date: advForm.date,
        notes: advForm.notes,
        txn_type: advForm.txn_type || "advance",
      });
      setAdvForm(null);
      await loadAdvances();
      load();
      if (ledgerFor) openLedger(ledgerFor.row);
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    }
  };
  const toggleSettled = async (adv) => {
    await http.patch(`/advances/${adv.id}`, { settled: !adv.settled });
    await loadAdvances();
    load();
  };
  const delAdvance = (adv) => {
    setConfirm({
      title: "Delete Transaction",
      message: `Are you sure you want to delete this ${adv.txn_type} transaction of ₹${adv.amount}?`,
      onConfirm: async () => {
        await http.delete(`/advances/${adv.id}`);
        setConfirm(null);
        await loadAdvances();
        load();
        if (ledgerFor) openLedger(ledgerFor.row);
      },
    });
  };

  const openLedger = async (row) => {
    const params = new URLSearchParams();
    if (fromDate) params.set("from_date", fromDate);
    if (toDate) params.set("to_date", toDate);
    const { data } = await http.get(
      `/workers/${row.worker_id}/ledger?${params.toString()}`,
    );
    setLedgerFor({ row, ledger: data });
  };

  return (
    <div>
      <PageHeader
        title="Karigar Payroll"
        subtitle="Reports / Payroll"
        testId="payroll-header"
        action={
          <div className="flex gap-2">
            <BtnPrimary
              onClick={openAdvancesDrawer}
              data-testid="open-advances-btn"
              className="bg-[#2563EB] border-[#2563EB] hover:bg-[#1E40AF] px-3 sm:px-5"
            >
              <IndianRupee className="w-3.5 h-3.5 inline -mt-0.5" />
              <span className="hidden sm:inline ml-1">Transactions</span>
            </BtnPrimary>
            <BtnPrimary
              onClick={dlPayrollPdf}
              data-testid="payroll-pdf-btn"
              className="bg-[#C27842] border-[#C27842] hover:bg-[#A65D24] px-3 sm:px-5"
            >
              <FileDown className="w-3.5 h-3.5 inline -mt-0.5" />
              <span className="hidden sm:inline ml-1">PDF</span>
            </BtnPrimary>
          </div>
        }
      />

      <div className="p-2 sm:p-4 lg:p-8 space-y-4">
        <div className="flex flex-wrap gap-2 items-end bg-white p-4 border-2 border-slate-200">
          <div className="w-full sm:w-auto">
            <Input
              testId="payroll-from"
              label="From"
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="w-full"
            />
          </div>
          <div className="w-full sm:w-auto">
            <Input
              testId="payroll-to"
              label="To"
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="w-full"
            />
          </div>
          <BtnPrimary
            onClick={load}
            data-testid="payroll-run-btn"
            className="w-full sm:w-auto py-2"
          >
            <Calendar className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Run
          </BtnPrimary>
        </div>

        {!data ? (
          <Card className="p-12 text-center text-slate-400">Loading...</Card>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <KpiTile
                label="Karigars"
                value={data.worker_count}
                icon={<UsersIcon className="w-4 h-4" />}
              />
              <KpiTile
                label="Earnings"
                value={inr(data.grand_total)}
                accent="#C27842"
              />
              <KpiTile
                label="Bonus"
                value={inr(data.grand_bonus || 0)}
                accent="#7C3AED"
              />
              <KpiTile
                label="Paid Out + Advances"
                value={inr(
                  (data.grand_advances_open || 0) + (data.grand_payments || 0),
                )}
                accent="#DC2626"
              />
              <KpiTile
                label="Net Balance"
                value={inr(data.grand_net_payable)}
                accent="#16A34A"
              />
            </div>

            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="payroll-table">
                  <thead className="bg-slate-50 border-b-2 border-slate-200">
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                      <th className="px-4 py-3 font-bold">Karigar</th>
                      <th className="px-4 py-3 font-bold">Skill</th>
                      <th className="px-4 py-3 font-bold text-right">Pairs</th>
                      <th className="px-4 py-3 font-bold text-right">
                        Earnings
                      </th>
                      <th className="px-4 py-3 font-bold text-right">Bonus</th>
                      <th className="px-4 py-3 font-bold text-right">
                        Paid / Advance
                      </th>
                      <th className="px-4 py-3 font-bold text-right">
                        Net Balance
                      </th>
                      <th className="px-4 py-3" />
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.length === 0 ? (
                      <tr>
                        <td
                          colSpan="8"
                          className="px-6 py-10 text-center text-slate-400"
                        >
                          No payroll data in this period.
                        </td>
                      </tr>
                    ) : (
                      data.rows.map((r) => (
                        <ExpandableRow
                          key={r.worker_id}
                          r={r}
                          expanded={expanded === r.worker_id}
                          onToggle={() =>
                            setExpanded(
                              expanded === r.worker_id ? null : r.worker_id,
                            )
                          }
                          onSlip={(e) => dlWageSlip(r.worker_id, e)}
                          onLedger={(e) => {
                            e.stopPropagation();
                            openLedger(r);
                          }}
                          onPay={(e) => {
                            e.stopPropagation();
                            setAdvForm({
                              worker_id: r.worker_id,
                              amount: "",
                              date: new Date().toISOString().slice(0, 10),
                              notes: `Payment to ${r.name}`,
                              txn_type: "payment",
                            });
                          }}
                        />
                      ))
                    )}
                  </tbody>
                  {data.rows.length > 0 && (
                    <tfoot>
                      <tr className="bg-[#0F172A] text-white">
                        <td
                          colSpan="3"
                          className="px-4 py-3 text-right font-bold uppercase tracking-wider text-xs"
                        >
                          Total
                        </td>
                        <td className="px-4 py-3 text-right font-mono font-bold">
                          {inr(data.grand_total)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono">
                          {inr(data.grand_bonus || 0)}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-red-400">
                          {inr(
                            (data.grand_advances_open || 0) +
                              (data.grand_payments || 0),
                          )}
                        </td>
                        <td className="px-4 py-3 text-right font-mono font-black text-[#C27842] text-base">
                          {inr(data.grand_net_payable)}
                        </td>
                        <td />
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </Card>
          </>
        )}
      </div>

      {showAdvances && (
        <Drawer
          onClose={() => setShowAdvances(false)}
          title="Karigar Transactions"
          width="max-w-3xl"
        >
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <p className="text-xs text-slate-600">
                All payments, advances and manual entries. Earnings auto-credit
                from completed jobs.
              </p>
              <BtnPrimary
                onClick={() =>
                  setAdvForm({
                    worker_id: "",
                    amount: "",
                    date: new Date().toISOString().slice(0, 10),
                    notes: "",
                    txn_type: "advance",
                  })
                }
                data-testid="new-advance-btn"
              >
                <Plus className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> New
              </BtnPrimary>
            </div>
            <table className="w-full text-xs">
              <thead className="bg-slate-50 border-b-2 border-slate-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-2 font-bold">Date</th>
                  <th className="px-3 py-2 font-bold">Karigar</th>
                  <th className="px-3 py-2 font-bold">Type</th>
                  <th className="px-3 py-2 font-bold text-right">Amount</th>
                  <th className="px-3 py-2 font-bold">Notes</th>
                  <th className="px-3 py-2 font-bold">Status</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {advances.length === 0 ? (
                  <tr>
                    <td
                      colSpan="7"
                      className="px-3 py-8 text-center text-slate-400"
                    >
                      No transactions recorded.
                    </td>
                  </tr>
                ) : (
                  advances.map((a) => {
                    const ttype = a.txn_type || "advance";
                    const colorMap = {
                      advance: "yellow",
                      payment: "blue",
                      bonus: "green",
                      adjustment: "slate",
                    };
                    return (
                      <tr key={a.id} className="border-b border-slate-100">
                        <td className="px-3 py-2 font-mono">
                          {(a.date || "").slice(0, 10)}
                        </td>
                        <td className="px-3 py-2 font-bold">{a.worker_name}</td>
                        <td className="px-3 py-2">
                          <Badge color={colorMap[ttype]}>
                            {ttype.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="px-3 py-2 text-right font-mono font-bold">
                          {inr(a.amount)}
                        </td>
                        <td className="px-3 py-2 text-slate-600 max-w-xs truncate">
                          {a.notes || "—"}
                        </td>
                        <td className="px-3 py-2">
                          {ttype === "advance" && (
                            <button
                              onClick={() => toggleSettled(a)}
                              data-testid={`toggle-${a.id}`}
                            >
                              {a.settled ? (
                                <Badge color="green">Settled</Badge>
                              ) : (
                                <Badge color="red">Open</Badge>
                              )}
                            </button>
                          )}
                          {ttype !== "advance" && (
                            <span className="text-xs text-slate-400">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button
                            onClick={() => delAdvance(a)}
                            className="text-slate-500 hover:text-red-600 p-1"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Drawer>
      )}

      {ledgerFor && (
        <Drawer
          onClose={() => setLedgerFor(null)}
          title={`Ledger – ${ledgerFor.row.name}`}
          width="max-w-3xl"
        >
          <div className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="bg-orange-50 border-2 border-orange-300 p-3">
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-orange-700">
                  Total Earned
                </div>
                <div className="font-mono text-xl font-bold text-orange-900 mt-1">
                  {inr(ledgerFor.ledger.total_earned)}
                </div>
              </div>
              <div className="bg-red-50 border-2 border-red-300 p-3">
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-red-700">
                  Total Paid Out
                </div>
                <div className="font-mono text-xl font-bold text-red-900 mt-1">
                  {inr(ledgerFor.ledger.total_paid)}
                </div>
              </div>
              <div
                className={`border-2 p-3 ${ledgerFor.ledger.balance >= 0 ? "bg-green-50 border-green-300" : "bg-red-50 border-red-300"}`}
              >
                <div
                  className={`text-[10px] uppercase tracking-[0.2em] font-bold ${ledgerFor.ledger.balance >= 0 ? "text-green-700" : "text-red-700"}`}
                >
                  Net Balance Due
                </div>
                <div
                  className={`font-mono text-2xl font-bold mt-1 ${ledgerFor.ledger.balance >= 0 ? "text-green-900" : "text-red-900"}`}
                >
                  {inr(ledgerFor.ledger.balance)}
                </div>
              </div>
            </div>

            <div className="flex justify-end">
              <BtnPrimary
                onClick={() =>
                  setAdvForm({
                    worker_id: ledgerFor.row.worker_id,
                    amount: "",
                    date: new Date().toISOString().slice(0, 10),
                    notes: `Payment to ${ledgerFor.row.name}`,
                    txn_type: "payment",
                  })
                }
                data-testid="ledger-pay-btn"
                className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36]"
              >
                <ArrowDownLeft className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />{" "}
                Record Payment
              </BtnPrimary>
            </div>

            <table className="w-full text-xs" data-testid="ledger-table">
              <thead className="bg-slate-50 border-b-2 border-slate-200 sticky top-0">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-2 font-bold">Date</th>
                  <th className="px-3 py-2 font-bold">Type</th>
                  <th className="px-3 py-2 font-bold">Description</th>
                  <th className="px-3 py-2 font-bold text-right">Credit (+)</th>
                  <th className="px-3 py-2 font-bold text-right">Debit (−)</th>
                  <th className="px-3 py-2 font-bold text-right">Balance</th>
                </tr>
              </thead>
              <tbody>
                {ledgerFor.ledger.entries.length === 0 ? (
                  <tr>
                    <td
                      colSpan="6"
                      className="px-3 py-8 text-center text-slate-400"
                    >
                      No transactions yet.
                    </td>
                  </tr>
                ) : (
                  ledgerFor.ledger.entries.map((e, i) => {
                    const isCredit = e.amount > 0;
                    const colorMap = {
                      earning: "orange",
                      bonus: "purple",
                      advance: "yellow",
                      payment: "blue",
                      adjustment: "slate",
                    };
                    return (
                      <tr key={i} className="border-b border-slate-100">
                        <td className="px-3 py-2 font-mono">{e.date}</td>
                        <td className="px-3 py-2">
                          <Badge color={colorMap[e.txn_type] || "slate"}>
                            {e.txn_type.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="px-3 py-2 text-slate-600 max-w-md">
                          {e.description}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-green-700">
                          {isCredit ? inr(e.amount) : ""}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-red-700">
                          {!isCredit ? inr(-e.amount) : ""}
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-mono font-bold ${e.balance >= 0 ? "text-slate-900" : "text-red-700"}`}
                        >
                          {inr(e.balance)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </Drawer>
      )}

      {advForm && (
        <div className="fixed inset-0 z-[60] grid place-items-center bg-black/40 p-4">
          <div className="bg-white border-2 border-slate-200 shadow-2xl w-full max-w-md">
            <div className="px-5 py-4 border-b-2 border-slate-200 flex items-center justify-between">
              <div className="font-bold">New Transaction</div>
              <button
                onClick={() => setAdvForm(null)}
                className="p-1 hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                  Type
                </label>
                <select
                  value={advForm.txn_type || "advance"}
                  onChange={(e) =>
                    setAdvForm({ ...advForm, txn_type: e.target.value })
                  }
                  className="w-full border-2 border-slate-300 px-3 py-2 text-sm"
                  data-testid="adv-type"
                >
                  <option value="advance">
                    Advance (loan taken, will be deducted)
                  </option>
                  <option value="payment">Payment (wages paid out)</option>
                  <option value="bonus">Bonus (manual credit)</option>
                  <option value="adjustment">Adjustment</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                  Karigar
                </label>
                <select
                  value={advForm.worker_id}
                  onChange={(e) =>
                    setAdvForm({ ...advForm, worker_id: e.target.value })
                  }
                  className="w-full border-2 border-slate-300 px-3 py-2 text-sm"
                  data-testid="adv-worker"
                >
                  <option value="">— Select karigar —</option>
                  {workers.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name} ({w.skill})
                    </option>
                  ))}
                </select>
              </div>
              <Input
                label="Amount (₹)"
                type="number"
                step="0.01"
                value={advForm.amount}
                onChange={(e) =>
                  setAdvForm({ ...advForm, amount: e.target.value })
                }
                testId="adv-amount"
              />
              <Input
                label="Date"
                type="date"
                value={advForm.date}
                onChange={(e) =>
                  setAdvForm({ ...advForm, date: e.target.value })
                }
              />
              <Input
                label="Notes"
                value={advForm.notes}
                onChange={(e) =>
                  setAdvForm({ ...advForm, notes: e.target.value })
                }
              />
              <div className="flex gap-2 pt-3 border-t border-slate-200">
                <BtnPrimary
                  onClick={submitAdvance}
                  disabled={!advForm.worker_id || !advForm.amount}
                  data-testid="adv-save"
                >
                  <Check className="w-3.5 h-3.5 inline -mt-0.5 mr-1" /> Save
                </BtnPrimary>
                <BtnSecondary onClick={() => setAdvForm(null)}>
                  Cancel
                </BtnSecondary>
              </div>
            </div>
          </div>
        </div>
      )}
      <ConfirmDialog
        open={!!confirm}
        title={confirm?.title}
        message={confirm?.message}
        onConfirm={confirm?.onConfirm}
        onCancel={() => setConfirm(null)}
      />
    </div>
  );
}

function ExpandableRow({ r, expanded, onToggle, onSlip, onLedger, onPay }) {
  const debit = (r.advances_open || 0) + (r.payments_paid || 0);
  return (
    <>
      <tr
        className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer"
        onClick={onToggle}
        data-testid={`payroll-row-${r.worker_id}`}
      >
        <td className="px-4 py-3 font-bold">{r.name}</td>
        <td className="px-4 py-3">
          <Badge color="orange">{r.skill}</Badge>
        </td>
        <td className="px-4 py-3 text-right font-mono">{r.total_pairs}</td>
        <td className="px-4 py-3 text-right font-mono font-bold text-[#C27842]">
          {inr(r.total_earning)}
        </td>
        <td className="px-4 py-3 text-right font-mono text-purple-700">
          {inr(r.total_bonus || 0)}
        </td>
        <td className="px-4 py-3 text-right font-mono text-red-700">
          {inr(debit)}
        </td>
        <td
          className={`px-4 py-3 text-right font-mono font-bold ${r.net_payable >= 0 ? "text-green-700" : "text-red-700"}`}
        >
          {inr(r.net_payable)}
        </td>
        <td className="px-4 py-3 text-right whitespace-nowrap">
          <button
            onClick={onPay}
            className="text-slate-600 hover:text-[#16A34A] p-1.5"
            title="Record payment"
            data-testid={`pay-${r.worker_id}`}
          >
            <ArrowDownLeft className="w-4 h-4" />
          </button>
          <button
            onClick={onLedger}
            className="text-slate-600 hover:text-[#2563EB] p-1.5 ml-0.5"
            title="View ledger"
            data-testid={`ledger-${r.worker_id}`}
          >
            <BookOpen className="w-4 h-4" />
          </button>
          <button
            onClick={onSlip}
            className="text-slate-600 hover:text-[#C27842] p-1.5 ml-0.5"
            title="Wage slip PDF"
            data-testid={`wage-slip-${r.worker_id}`}
          >
            <FileDown className="w-4 h-4" />
          </button>
          <span className="text-xs text-slate-500 ml-1">
            {expanded ? "▼" : "▶"}
          </span>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan="8" className="bg-slate-50 px-8 py-5">
            <div className="space-y-3">
              {r.bonus_pct > 0 && r.target_cycle_days > 0 && (
                <div className="bg-purple-50 border border-purple-200 px-3 py-2 text-xs flex items-center gap-2">
                  <Sparkles className="w-3.5 h-3.5 text-purple-700" />
                  <span>
                    <b>Productivity bonus:</b> {r.bonus_pct}% extra if job
                    completes within {r.target_cycle_days} days of assignment.
                  </span>
                </div>
              )}
              <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500">
                Per-job earnings
              </div>
              <table className="w-full text-xs border border-slate-200">
                <thead className="bg-white">
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                    <th className="px-2 py-1.5 border-b">PO</th>
                    <th className="px-2 py-1.5 border-b">Style</th>
                    <th className="px-2 py-1.5 border-b">Color</th>
                    <th className="px-2 py-1.5 border-b">Size</th>
                    <th className="px-2 py-1.5 border-b">Role</th>
                    <th className="px-2 py-1.5 border-b text-right">Pairs</th>
                    <th className="px-2 py-1.5 border-b text-right">Rate</th>
                    <th className="px-2 py-1.5 border-b text-right">Earning</th>
                    <th className="px-2 py-1.5 border-b text-right">Bonus</th>
                  </tr>
                </thead>
                <tbody>
                  {r.jobs.map((j, i) => (
                    <tr key={i} className="border-b border-slate-200">
                      <td className="px-2 py-1.5 font-mono">{j.po_number}</td>
                      <td className="px-2 py-1.5 font-mono">{j.style_code}</td>
                      <td className="px-2 py-1.5">{j.color}</td>
                      <td className="px-2 py-1.5 font-mono">{j.size}</td>
                      <td className="px-2 py-1.5">
                        <Badge color="slate">
                          {(ROLE_LABEL[j.role] || j.role).toUpperCase()}
                        </Badge>
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono">
                        {j.pairs}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono">
                        {inr(j.rate)}/pr
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono font-bold">
                        {inr(j.earning)}
                      </td>
                      <td className="px-2 py-1.5 text-right font-mono text-purple-700">
                        {j.bonus ? inr(j.bonus) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function KpiTile({ label, value, accent = "#0F172A", icon }) {
  return (
    <Card className="p-5 relative overflow-hidden">
      <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-slate-500 flex items-center gap-1.5">
        {icon}
        {label}
      </div>
      <div className="font-mono text-2xl font-bold mt-2">{value}</div>
      <div
        className="absolute left-0 top-0 bottom-0 w-1.5"
        style={{ background: accent }}
      />
    </Card>
  );
}
