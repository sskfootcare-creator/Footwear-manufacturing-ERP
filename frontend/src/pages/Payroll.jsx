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
  Landmark,
  Smartphone,
  Banknote,
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
  const [bankAccounts, setBankAccounts] = useState([]);
  const [cashLedgers, setCashLedgers] = useState([]);

  const loadBankingData = async () => {
    try {
      const [b, c] = await Promise.all([
        http.get("/banking/accounts").catch(() => ({ data: [] })),
        http.get("/banking/cash-ledger").catch(() => ({ data: [] })),
      ]);
      setBankAccounts(b.data || []);
      const cItems = Array.isArray(c.data)
        ? c.data
        : c.data?.items || c.data?.cash_ledger || [];
      setCashLedgers(cItems);
    } catch (e) {
      console.error("Failed to load banking data for payroll", e);
    }
  };

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
    loadBankingData();
  };
  const loadAdvances = async () => {
    const { data } = await http.get("/advances");
    setAdvances(data);
    loadBankingData();
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

  const openNewTransactionModal = (initial = {}) => {
    loadBankingData();
    const defCash =
      cashLedgers.find((c) => (c.remaining_balance || 0) > 0) || cashLedgers[0];
    const defBank = bankAccounts[0];
    setAdvForm({
      worker_id: initial.worker_id || "",
      amount: initial.amount !== undefined ? initial.amount : "",
      date: initial.date || new Date().toISOString().slice(0, 10),
      notes: initial.notes || "",
      txn_type: initial.txn_type || "payment",
      paid_via: initial.paid_via || "cash",
      cash_ledger_id: initial.cash_ledger_id || defCash?.id || "",
      bank_account_id: initial.bank_account_id || defBank?.id || "",
      upi_reference: initial.upi_reference || "",
    });
  };

  const submitAdvance = async () => {
    try {
      const amt = Number(advForm.amount);
      if (!amt || amt <= 0) {
        alert("Please enter a valid amount greater than 0");
        return;
      }
      const ttype = advForm.txn_type || "advance";
      const payload = {
        worker_id: advForm.worker_id,
        amount: amt,
        date: advForm.date,
        notes: advForm.notes || "",
        txn_type: ttype,
      };

      if (["advance", "payment"].includes(ttype)) {
        const mode = advForm.paid_via || "cash";
        payload.paid_via = mode;
        if (mode === "cash") {
          if (!advForm.cash_ledger_id) {
            alert("Please select a Cash Pool withdrawal entry.");
            return;
          }
          payload.cash_ledger_id = advForm.cash_ledger_id;
        } else if (["bank_transfer", "upi"].includes(mode)) {
          if (!advForm.bank_account_id) {
            alert("Please select a Bank Account.");
            return;
          }
          payload.bank_account_id = advForm.bank_account_id;
          if (mode === "upi") {
            payload.upi_reference = advForm.upi_reference || "";
          }
        }
      }

      await http.post("/advances", payload);
      setAdvForm(null);
      await Promise.all([loadAdvances(), load()]);
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
                            openNewTransactionModal({
                              worker_id: r.worker_id,
                              amount: r.net_payable > 0 ? String(r.net_payable) : "",
                              notes: `Wage payment to ${r.name}`,
                              txn_type: "payment",
                              paid_via: "cash",
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
                onClick={() => openNewTransactionModal({ txn_type: "advance" })}
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
                  <th className="px-3 py-2 font-bold">Payment Source</th>
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
                      colSpan="8"
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
                        <td className="px-3 py-2">
                          {a.paid_via === "cash" && (
                            <span className="inline-flex items-center gap-1 text-[10px] bg-emerald-50 text-emerald-700 px-1.5 py-0.5 rounded border border-emerald-200 font-medium">
                              <Banknote className="w-3 h-3" />
                              Cash Pool {a.cash_ledger_notes ? `· ${a.cash_ledger_notes}` : ""}
                            </span>
                          )}
                          {a.paid_via === "bank_transfer" && (
                            <span className="inline-flex items-center gap-1 text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded border border-blue-200 font-medium">
                              <Landmark className="w-3 h-3" />
                              {a.bank_account_name || "Bank Transfer"}
                            </span>
                          )}
                          {a.paid_via === "upi" && (
                            <span className="inline-flex items-center gap-1 text-[10px] bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded border border-purple-200 font-medium">
                              <Smartphone className="w-3 h-3" />
                              UPI · {a.bank_account_name || "Bank"}
                              {a.upi_reference ? ` (${a.upi_reference})` : ""}
                            </span>
                          )}
                          {!a.paid_via && (
                            <span className="text-slate-400 text-xs">—</span>
                          )}
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
                  openNewTransactionModal({
                    worker_id: ledgerFor.row.worker_id,
                    amount:
                      ledgerFor.ledger.balance > 0
                        ? String(ledgerFor.ledger.balance)
                        : "",
                    date: new Date().toISOString().slice(0, 10),
                    notes: `Payment to ${ledgerFor.row.name}`,
                    txn_type: "payment",
                    paid_via: "cash",
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
        <div className="fixed inset-0 z-[60] grid place-items-center bg-black/50 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-white border-2 border-slate-300 shadow-2xl w-full max-w-lg my-8">
            <div className="px-6 py-4 bg-slate-50 border-b-2 border-slate-200 flex items-center justify-between">
              <div>
                <div className="font-bold text-slate-800 text-base">
                  {advForm.txn_type === "payment"
                    ? "Record Wage Payment"
                    : advForm.txn_type === "advance"
                      ? "Issue Karigar Advance"
                      : "New Karigar Transaction"}
                </div>
                <div className="text-[11px] text-slate-500">
                  Record payout, advance or adjustment with ERP accounting source
                </div>
              </div>
              <button
                onClick={() => setAdvForm(null)}
                className="p-1.5 rounded hover:bg-slate-200 text-slate-500"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-6 space-y-4 max-h-[80vh] overflow-y-auto">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">
                    Transaction Type
                  </label>
                  <select
                    value={advForm.txn_type || "payment"}
                    onChange={(e) =>
                      setAdvForm({ ...advForm, txn_type: e.target.value })
                    }
                    className="w-full border-2 border-slate-300 px-3 py-2 text-sm bg-white"
                    data-testid="adv-type"
                  >
                    <option value="payment">Payment (wages paid out)</option>
                    <option value="advance">
                      Advance (loan taken, will be deducted)
                    </option>
                    <option value="bonus">Bonus (manual credit)</option>
                    <option value="adjustment">Adjustment</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">
                    Date
                  </label>
                  <input
                    type="date"
                    value={advForm.date}
                    onChange={(e) =>
                      setAdvForm({ ...advForm, date: e.target.value })
                    }
                    className="w-full border-2 border-slate-300 px-3 py-2 text-sm bg-white"
                    data-testid="adv-date"
                  />
                </div>
              </div>

              <div>
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">
                  Karigar
                </label>
                <select
                  value={advForm.worker_id}
                  onChange={(e) => {
                    const wid = e.target.value;
                    const wRow = data?.rows?.find((r) => r.worker_id === wid);
                    setAdvForm({
                      ...advForm,
                      worker_id: wid,
                      amount:
                        advForm.txn_type === "payment" && wRow?.net_payable > 0
                          ? String(wRow.net_payable)
                          : advForm.amount,
                      notes:
                        advForm.txn_type === "payment" && wRow?.name
                          ? `Wage payment to ${wRow.name}`
                          : advForm.notes,
                    });
                  }}
                  className="w-full border-2 border-slate-300 px-3 py-2 text-sm bg-white"
                  data-testid="adv-worker"
                >
                  <option value="">— Select karigar —</option>
                  {workers.map((w) => {
                    const row = data?.rows?.find((r) => r.worker_id === w.id);
                    const bal = row ? ` · Due: ₹${row.net_payable}` : "";
                    return (
                      <option key={w.id} value={w.id}>
                        {`${w.name} (${w.skill})${bal}`}
                      </option>
                    );
                  })}
                </select>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                    Amount (₹)
                  </label>
                  {(() => {
                    const row = data?.rows?.find(
                      (r) => r.worker_id === advForm.worker_id,
                    );
                    if (row && row.net_payable > 0) {
                      return (
                        <button
                          type="button"
                          onClick={() =>
                            setAdvForm({
                              ...advForm,
                              amount: String(row.net_payable),
                            })
                          }
                          className="text-[11px] font-bold text-blue-600 hover:text-blue-800 underline flex items-center gap-1"
                        >
                          Net due: {inr(row.net_payable)} (Click to fill)
                        </button>
                      );
                    }
                    return null;
                  })()}
                </div>
                <Input
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  value={advForm.amount}
                  onChange={(e) =>
                    setAdvForm({ ...advForm, amount: e.target.value })
                  }
                  testId="adv-amount"
                  className="w-full font-mono text-base"
                />
              </div>

              {["advance", "payment"].includes(advForm.txn_type || "payment") && (
                <div className="space-y-3 pt-3 border-t border-slate-200">
                  <div>
                    <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1.5">
                      Mode of Payment
                    </label>
                    <div className="grid grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          const defCash =
                            cashLedgers.find(
                              (c) => (c.remaining_balance || 0) > 0,
                            ) || cashLedgers[0];
                          setAdvForm({
                            ...advForm,
                            paid_via: "cash",
                            cash_ledger_id: defCash?.id || "",
                          });
                        }}
                        className={`flex items-center justify-center gap-1.5 py-2 px-2 text-xs font-bold border-2 rounded transition-all ${
                          (advForm.paid_via || "cash") === "cash"
                            ? "border-[#16A34A] bg-green-50 text-[#16A34A] shadow-sm"
                            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                        }`}
                        data-testid="mode-cash"
                      >
                        <Banknote className="w-4 h-4" />
                        <span>Cash Pool</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setAdvForm({
                            ...advForm,
                            paid_via: "bank_transfer",
                            bank_account_id:
                              advForm.bank_account_id ||
                              bankAccounts[0]?.id ||
                              "",
                          });
                        }}
                        className={`flex items-center justify-center gap-1.5 py-2 px-2 text-xs font-bold border-2 rounded transition-all ${
                          advForm.paid_via === "bank_transfer"
                            ? "border-[#2563EB] bg-blue-50 text-[#2563EB] shadow-sm"
                            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                        }`}
                        data-testid="mode-bank"
                      >
                        <Landmark className="w-4 h-4" />
                        <span>Bank Transfer</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setAdvForm({
                            ...advForm,
                            paid_via: "upi",
                            bank_account_id:
                              advForm.bank_account_id ||
                              bankAccounts[0]?.id ||
                              "",
                          });
                        }}
                        className={`flex items-center justify-center gap-1.5 py-2 px-2 text-xs font-bold border-2 rounded transition-all ${
                          advForm.paid_via === "upi"
                            ? "border-[#7C3AED] bg-purple-50 text-[#7C3AED] shadow-sm"
                            : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                        }`}
                        data-testid="mode-upi"
                      >
                        <Smartphone className="w-4 h-4" />
                        <span>UPI</span>
                      </button>
                    </div>
                  </div>

                  {(advForm.paid_via || "cash") === "cash" && (
                    <div className="bg-slate-50 p-3.5 border border-slate-200 rounded space-y-2">
                      <div className="flex justify-between items-center">
                        <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                          Cash Withdrawal / Pool Entry
                        </label>
                        <span className="text-[10px] text-slate-500">
                          Debited from cash pool
                        </span>
                      </div>
                      {cashLedgers.length === 0 ? (
                        <div className="text-xs text-amber-800 bg-amber-50 p-2.5 border border-amber-200 rounded">
                          ⚠️ No cash withdrawal entries found. Please record a
                          cash withdrawal under Banking first, or pay via
                          Bank/UPI.
                        </div>
                      ) : (
                        <>
                          <select
                            value={advForm.cash_ledger_id || ""}
                            onChange={(e) =>
                              setAdvForm({
                                ...advForm,
                                cash_ledger_id: e.target.value,
                              })
                            }
                            className="w-full border-2 border-slate-300 px-3 py-2 text-xs bg-white font-medium"
                            data-testid="adv-cash-ledger"
                          >
                            <option value="">
                              — Select Cash Withdrawal Pool —
                            </option>
                            {cashLedgers.map((cl) => (
                              <option key={cl.id} value={cl.id}>
                                {`${cl.notes || "Cash Withdrawal"} · Avail: ₹${(cl.remaining_balance || 0).toLocaleString("en-IN")} (${cl.date})`}
                              </option>
                            ))}
                          </select>
                          {(() => {
                            const sel = cashLedgers.find(
                              (c) => c.id === advForm.cash_ledger_id,
                            );
                            if (!sel) return null;
                            const isOver =
                              Number(advForm.amount || 0) >
                              (sel.remaining_balance || 0);
                            return (
                              <div
                                className={`text-xs p-2 rounded flex justify-between items-center ${
                                  isOver
                                    ? "bg-red-50 text-red-700 border border-red-200"
                                    : "bg-emerald-50 text-emerald-800 border border-emerald-200"
                                }`}
                              >
                                <span>
                                  Available in Pool:{" "}
                                  <b>{inr(sel.remaining_balance || 0)}</b>
                                </span>
                                {isOver ? (
                                  <span className="font-bold text-red-600 text-[11px]">
                                    ⚠️ Exceeds pool balance
                                  </span>
                                ) : (
                                  <span className="text-emerald-700 text-[11px]">
                                    ✓ Sufficient funds
                                  </span>
                                )}
                              </div>
                            );
                          })()}
                        </>
                      )}
                    </div>
                  )}

                  {["bank_transfer", "upi"].includes(advForm.paid_via) && (
                    <div className="bg-slate-50 p-3.5 border border-slate-200 rounded space-y-3">
                      <div>
                        <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600 block mb-1">
                          Source Bank Account
                        </label>
                        <select
                          value={advForm.bank_account_id || ""}
                          onChange={(e) =>
                            setAdvForm({
                              ...advForm,
                              bank_account_id: e.target.value,
                            })
                          }
                          className="w-full border-2 border-slate-300 px-3 py-2 text-xs bg-white font-medium"
                          data-testid="adv-bank-account"
                        >
                          <option value="">— Select Bank Account —</option>
                          {bankAccounts.map((b) => (
                            <option key={b.id} value={b.id}>
                              {`${b.name} (${b.bank_name || "Bank"} ····${b.account_number_last4 || ""})`}
                            </option>
                          ))}
                        </select>
                        <p className="text-[10px] text-slate-500 mt-1">
                          ✓ Automatically recorded in this bank account's ERP
                          statement as a confirmed wage expense for
                          reconciliation.
                        </p>
                      </div>

                      {advForm.paid_via === "upi" && (
                        <div>
                          <Input
                            label="UPI Reference / UTR Number"
                            placeholder="e.g. UPI/429182390192 or UTR"
                            value={advForm.upi_reference || ""}
                            onChange={(e) =>
                              setAdvForm({
                                ...advForm,
                                upi_reference: e.target.value,
                              })
                            }
                            testId="adv-upi-ref"
                            className="text-xs"
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              <div>
                <Input
                  label="Notes / Remarks"
                  placeholder="Optional notes or remarks"
                  value={advForm.notes}
                  onChange={(e) =>
                    setAdvForm({ ...advForm, notes: e.target.value })
                  }
                />
              </div>

              <div className="flex gap-2 pt-4 border-t border-slate-200">
                <BtnPrimary
                  onClick={submitAdvance}
                  disabled={!advForm.worker_id || !advForm.amount}
                  data-testid="adv-save"
                  className="w-full justify-center py-2.5 text-sm"
                >
                  <Check className="w-4 h-4 inline -mt-0.5 mr-1" />
                  {advForm.txn_type === "payment"
                    ? "Record Payment"
                    : "Save Transaction"}
                </BtnPrimary>
                <BtnSecondary
                  onClick={() => setAdvForm(null)}
                  className="px-5 py-2.5 text-sm"
                >
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
