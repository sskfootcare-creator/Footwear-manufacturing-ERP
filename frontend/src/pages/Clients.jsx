import { useEffect, useState } from "react";
import { http, inr } from "../lib/api";
import { PageHeader, Card, Badge, BtnSecondary } from "../components/ui-kit";
import { Users, BookOpen, X, AlertCircle, Download } from "lucide-react";

const STATUS_COLOR = {
  paid: "green",
  partial: "blue",
  overdue: "red",
  pending: "yellow",
};
const VCH_COLOR = {
  Invoice: "#C27842",
  Payment: "#16A34A",
  "GR Adj": "#DC2626",
};

export default function Clients() {
  const [clients, setClients] = useState([]);
  const [open, setOpen] = useState(null); // {client_name, ...ledger}
  const [loadingLedger, setLoadingLedger] = useState(false);

  const load = async () => {
    const { data } = await http.get("/clients");
    setClients(data || []);
  };
  useEffect(() => {
    load();
  }, []);

  const openLedger = async (c) => {
    setLoadingLedger(true);
    try {
      const { data } = await http.get(
        `/clients/${encodeURIComponent(c.client_name)}/ledger`,
      );
      setOpen(data);
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally {
      setLoadingLedger(false);
    }
  };

  const totalOutstanding = clients.reduce(
    (s, c) => s + (c.outstanding || 0),
    0,
  );
  const totalOverdue = clients.reduce((s, c) => s + (c.overdue_amount || 0), 0);

  return (
    <div>
      <PageHeader
        title="Clients"
        subtitle="Accounts / Ledger"
        testId="clients-header"
      />
      <div className="p-2 sm:p-4 lg:p-8 space-y-5">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile label="Clients" value={clients.length} accent="#0F172A" />
          <Tile
            label="Total Receivable"
            value={inr(totalOutstanding)}
            accent="#C27842"
          />
          <Tile
            label="Overdue Amount"
            value={inr(totalOverdue)}
            accent="#DC2626"
          />
          <Tile
            label="YTD Sales"
            value={inr(
              clients.reduce((s, c) => s + (c.total_invoiced || 0), 0),
            )}
            accent="#16A34A"
          />
        </div>

        <Card className="overflow-hidden" data-testid="clients-card">
          <div className="px-5 py-3 border-b-2 border-slate-200">
            <h2 className="text-sm font-bold uppercase tracking-wider flex items-center gap-2">
              <Users className="w-4 h-4 text-[#C27842]" /> All clients (
              {clients.length})
            </h2>
          </div>
          {clients.length === 0 ? (
            <div
              className="p-12 text-center text-slate-400 text-sm"
              data-testid="clients-empty"
            >
              No invoiced clients yet. Generate your first invoice from the
              Production board to see your client ledger here.
            </div>
          ) : (
            <table className="w-full text-sm" data-testid="clients-table">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-4 py-2 font-bold">Client</th>
                  <th className="px-4 py-2 font-bold text-right">Invoices</th>
                  <th className="px-4 py-2 font-bold text-right">
                    Total Invoiced
                  </th>
                  <th className="px-4 py-2 font-bold text-right">Received</th>
                  <th className="px-4 py-2 font-bold text-right">
                    Outstanding
                  </th>
                  <th className="px-4 py-2 font-bold text-right">Overdue</th>
                  <th className="px-4 py-2 font-bold text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((c) => (
                  <tr
                    key={c.client_name}
                    className="border-b border-slate-100 hover:bg-slate-50"
                    data-testid={`client-row-${c.client_name}`}
                  >
                    <td className="px-4 py-3 font-bold">{c.client_name}</td>
                    <td className="px-4 py-3 text-right font-mono">
                      {c.invoice_count}
                    </td>
                    <td className="px-4 py-3 text-right font-mono">
                      {inr(c.total_invoiced)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-[#16A34A]">
                      {inr(c.total_received)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-bold">
                      {inr(c.outstanding)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {c.overdue_count > 0 ? (
                        <div>
                          <Badge color="red">{c.overdue_count} overdue</Badge>
                          <div className="text-xs font-mono text-red-600 mt-1">
                            {inr(c.overdue_amount)}
                          </div>
                        </div>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => openLedger(c)}
                        className="text-xs uppercase tracking-wider font-bold text-[#2563EB] hover:bg-[#2563EB] hover:text-white border border-[#2563EB] px-3 py-1.5 flex items-center gap-1 ml-auto"
                        data-testid={`open-ledger-${c.client_name}`}
                      >
                        <BookOpen className="w-3 h-3" /> Ledger
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-slate-900 text-white">
                <tr>
                  <td className="px-4 py-3 font-bold uppercase text-[10px] tracking-wider text-[#C27842]">
                    Grand Total
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    {clients.reduce((s, c) => s + c.invoice_count, 0)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    {inr(clients.reduce((s, c) => s + c.total_invoiced, 0))}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-[#86EFAC]">
                    {inr(clients.reduce((s, c) => s + c.total_received, 0))}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-bold">
                    {inr(totalOutstanding)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-bold text-red-300">
                    {inr(totalOverdue)}
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          )}
        </Card>

        {loadingLedger && (
          <div className="text-sm text-slate-500">Loading ledger…</div>
        )}
      </div>

      {open && <LedgerModal ledger={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

function Tile({ label, value, accent }) {
  return (
    <Card className="p-3 sm:p-5 relative overflow-hidden">
      <div
        className="text-[10px] uppercase tracking-[0.2em] font-bold truncate"
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

/* ------------------- LEDGER MODAL ------------------- */
function LedgerModal({ ledger, onClose }) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4"
      data-testid="ledger-modal"
    >
      <div className="bg-white w-full max-w-6xl max-h-[92vh] overflow-y-auto border-2 border-slate-200 shadow-2xl">
        <div className="bg-[#0F172A] text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-[#C27842]">
              Client Ledger
            </div>
            <div className="text-xl font-bold">{ledger.client_name}</div>
          </div>
          <button
            onClick={onClose}
            className="hover:bg-white/10 p-1"
            data-testid="ledger-close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6 space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Tile
              label="Total Invoiced"
              value={inr(ledger.totals.invoiced)}
              accent="#0F172A"
            />
            <Tile
              label="Received"
              value={inr(ledger.totals.received)}
              accent="#16A34A"
            />
            <Tile
              label="Closing Balance"
              value={`${inr(Math.abs(ledger.closing_balance))} ${ledger.closing_balance_type}`}
              accent="#C27842"
            />
            <Tile
              label="No. of Entries"
              value={ledger.entries.length}
              accent="#2563EB"
            />
          </div>

          {/* Aging */}
          <div>
            <h3 className="text-[11px] uppercase tracking-[0.2em] font-bold text-[#C27842] mb-2 border-b border-slate-200 pb-1">
              Aging analysis
            </h3>
            <div className="grid grid-cols-4 gap-3">
              {ledger.aging.map((a, i) => (
                <div
                  key={i}
                  className="border-2 border-slate-200 px-4 py-3"
                  data-testid={`aging-${a.bucket.replace("+", "plus")}`}
                >
                  <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">
                    {a.bucket} days
                  </div>
                  <div
                    className={`font-mono font-bold text-lg ${a.amount > 0 ? "text-red-600" : "text-slate-400"}`}
                  >
                    {inr(a.amount)}
                  </div>
                  <div className="text-[10px] text-slate-500 font-mono">
                    {a.count} invoice{a.count !== 1 ? "s" : ""}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Outstanding invoices */}
          {(ledger.invoices || []).some((i) => i.outstanding > 0) && (
            <div>
              <h3 className="text-[11px] uppercase tracking-[0.2em] font-bold text-[#C27842] mb-2 border-b border-slate-200 pb-1">
                Open invoices
              </h3>
              <table
                className="w-full text-xs border-2 border-slate-200"
                data-testid="ledger-open-invoices"
              >
                <thead className="bg-slate-50">
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                    <th className="px-3 py-2 font-bold">Invoice #</th>
                    <th className="px-3 py-2 font-bold">PO</th>
                    <th className="px-3 py-2 font-bold">Date</th>
                    <th className="px-3 py-2 font-bold">Due</th>
                    <th className="px-3 py-2 font-bold text-right">Amount</th>
                    <th className="px-3 py-2 font-bold text-right">Received</th>
                    <th className="px-3 py-2 font-bold text-right">
                      Outstanding
                    </th>
                    <th className="px-3 py-2 font-bold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {ledger.invoices
                    .filter((i) => i.outstanding > 0)
                    .map((i, idx) => (
                      <tr
                        key={idx}
                        className="border-t border-slate-100 hover:bg-slate-50"
                      >
                        <td className="px-3 py-2 font-mono font-bold">
                          {i.invoice_no}
                        </td>
                        <td className="px-3 py-2 font-mono text-slate-600">
                          {i.po_number || "—"}
                        </td>
                        <td className="px-3 py-2 font-mono text-slate-600">
                          {i.invoice_date}
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={
                              i.status === "overdue"
                                ? "text-red-600 font-bold"
                                : ""
                            }
                          >
                            {i.due_date}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right font-mono">
                          {inr(i.net_amount || 0)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-[#16A34A]">
                          {inr(i.received_amount || 0)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono font-bold">
                          {inr(i.outstanding)}
                        </td>
                        <td className="px-3 py-2">
                          <Badge color={STATUS_COLOR[i.status] || "yellow"}>
                            {i.status}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Tally-style ledger entries */}
          <div>
            <h3 className="text-[11px] uppercase tracking-[0.2em] font-bold text-[#C27842] mb-2 border-b border-slate-200 pb-1 flex items-center justify-between">
              <span>Ledger entries (Tally format)</span>
              <span className="text-slate-500 normal-case font-mono text-[10px]">
                {ledger.entries.length} entries
              </span>
            </h3>
            <table
              className="w-full text-xs border-2 border-slate-200"
              data-testid="ledger-entries"
            >
              <thead className="bg-slate-900 text-white">
                <tr className="text-left text-[10px] uppercase tracking-wider">
                  <th className="px-3 py-2 font-bold">Date</th>
                  <th className="px-3 py-2 font-bold">Vch. Type</th>
                  <th className="px-3 py-2 font-bold">Vch. No.</th>
                  <th className="px-3 py-2 font-bold">Particulars</th>
                  <th className="px-3 py-2 font-bold text-right">Debit (Dr)</th>
                  <th className="px-3 py-2 font-bold text-right">
                    Credit (Cr)
                  </th>
                  <th className="px-3 py-2 font-bold text-right">
                    Running Balance
                  </th>
                </tr>
              </thead>
              <tbody>
                {ledger.entries.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="text-center text-slate-400 py-8">
                      No entries.
                    </td>
                  </tr>
                ) : (
                  ledger.entries.map((e, i) => (
                    <tr
                      key={i}
                      className="border-t border-slate-100 hover:bg-slate-50"
                      data-testid={`ledger-entry-${i}`}
                    >
                      <td className="px-3 py-1.5 font-mono text-slate-600 whitespace-nowrap">
                        {e.date}
                      </td>
                      <td className="px-3 py-1.5">
                        <span
                          className="font-bold text-[10px] uppercase tracking-wider"
                          style={{ color: VCH_COLOR[e.vch_type] || "#0F172A" }}
                        >
                          {e.vch_type}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 font-mono font-bold">
                        {e.vch_no}
                      </td>
                      <td className="px-3 py-1.5 text-slate-700">
                        {e.particulars}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono">
                        {e.debit > 0 ? inr(e.debit) : ""}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono text-[#16A34A]">
                        {e.credit > 0 ? inr(e.credit) : ""}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono font-bold">
                        {inr(Math.abs(e.balance))}{" "}
                        <span className="text-slate-500 text-[10px]">
                          {e.balance_type}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
              <tfoot className="bg-slate-900 text-white">
                <tr>
                  <td
                    colSpan="4"
                    className="px-3 py-2 font-bold uppercase text-[10px] tracking-wider text-[#C27842]"
                  >
                    Closing Balance
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {inr(ledger.entries.reduce((s, e) => s + e.debit, 0))}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {inr(ledger.entries.reduce((s, e) => s + e.credit, 0))}
                  </td>
                  <td className="px-3 py-2 text-right font-mono font-bold text-base">
                    {inr(Math.abs(ledger.closing_balance))}{" "}
                    <span className="text-[#C27842]">
                      {ledger.closing_balance_type}
                    </span>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          {ledger.closing_balance > 0 && (
            <Card className="bg-amber-50 border-amber-200 p-4">
              <div className="text-xs text-slate-700 flex items-baseline gap-2">
                <AlertCircle className="w-4 h-4 text-amber-600 -mb-0.5" />
                <div>
                  <b>{inr(ledger.closing_balance)} Dr</b> still receivable from{" "}
                  {ledger.client_name}.
                  {ledger.aging.find((a) => a.bucket === "90+")?.amount > 0 && (
                    <span className="text-red-600 font-bold">
                      {" "}
                      ·{" "}
                      {inr(
                        ledger.aging.find((a) => a.bucket === "90+").amount,
                      )}{" "}
                      is more than 90 days overdue.
                    </span>
                  )}
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
