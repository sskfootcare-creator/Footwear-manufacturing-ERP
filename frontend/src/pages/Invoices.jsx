import { useEffect, useState } from "react";
import { http, inr } from "../lib/api";
import { PageHeader, Card, Badge, BtnPrimary, BtnSecondary } from "../components/ui-kit";
import { FileText, FileDown, Eye, X, Receipt, ClipboardCheck, IndianRupee, AlertCircle, Trash2 } from "lucide-react";

const STATUS_COLOR = { paid: "green", partial: "blue", overdue: "red", pending: "yellow" };
const PAYMENT_MODES = ["Bank Transfer", "RTGS", "NEFT", "Cheque", "UPI", "Cash", "Adjustment"];

export default function Invoices() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [view, setView] = useState(null);
  const [grnFor, setGrnFor] = useState(null);
  const [paymentFor, setPaymentFor] = useState(null);
  const [deleteFor, setDeleteFor] = useState(null);

  const load = async () => {
    const { data } = await http.get("/invoices");
    setRows(data || []);
  };
  useEffect(() => { load(); }, []);

  const filtered = rows.filter(r => {
    if (filter !== "all" && r.status !== filter) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!`${r.invoice_no} ${r.client_name} ${r.po_number}`.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  const overdue = rows.filter(r => r.status === "overdue");
  const partial = rows.filter(r => r.status === "partial");
  const paid = rows.filter(r => r.status === "paid");
  const pending = rows.filter(r => r.status === "pending");
  const totalOutstanding = rows.reduce((s, r) => s + (r.outstanding || 0), 0);

  const openInvoice = async (id) => {
    const { data } = await http.get(`/invoices/${id}`);
    setView(data);
  };

  return (
    <div>
      <PageHeader title="Invoices" subtitle="Accounts / Receivables" testId="invoices-header" />
      <div className="p-8 space-y-5">
        {overdue.length > 0 && (
          <Card className="bg-red-50 border-2 border-red-300 px-4 py-3 flex items-center justify-between" data-testid="overdue-banner">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-red-600" />
              <div>
                <div className="font-bold text-red-700 text-sm">
                  {overdue.length} invoice{overdue.length > 1 ? "s" : ""} overdue · {inr(overdue.reduce((s, r) => s + r.outstanding, 0))} pending
                </div>
                <div className="text-xs text-red-600">Payment terms exceeded — chase up with client.</div>
              </div>
            </div>
            <button onClick={() => setFilter("overdue")} className="text-xs uppercase tracking-wider font-bold text-red-700 hover:underline">View overdue →</button>
          </Card>
        )}

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Tile label="Total" value={rows.length} sub={inr(rows.reduce((s, r) => s + (r.net_amount || 0), 0))} active={filter === "all"} onClick={() => setFilter("all")} testId="tile-all" />
          <Tile label="Pending" value={pending.length} sub={inr(pending.reduce((s, r) => s + r.outstanding, 0))} accent="#F59E0B" active={filter === "pending"} onClick={() => setFilter("pending")} testId="tile-pending" />
          <Tile label="Partial" value={partial.length} sub={inr(partial.reduce((s, r) => s + r.outstanding, 0))} accent="#2563EB" active={filter === "partial"} onClick={() => setFilter("partial")} testId="tile-partial" />
          <Tile label="Overdue" value={overdue.length} sub={inr(overdue.reduce((s, r) => s + r.outstanding, 0))} accent="#DC2626" active={filter === "overdue"} onClick={() => setFilter("overdue")} testId="tile-overdue" />
          <Tile label="Paid" value={paid.length} sub={inr(paid.reduce((s, r) => s + (r.net_amount || 0), 0))} accent="#16A34A" active={filter === "paid"} onClick={() => setFilter("paid")} testId="tile-paid" />
        </div>

        <Card className="overflow-hidden" data-testid="invoices-card">
          <div className="px-5 py-3 border-b-2 border-slate-200 flex items-baseline justify-between gap-4">
            <h2 className="text-sm font-bold uppercase tracking-wider flex items-center gap-2">
              <FileText className="w-4 h-4 text-[#C27842]" />
              {filter === "all" ? "All invoices" : `${filter.charAt(0).toUpperCase() + filter.slice(1)} invoices`}
              <span className="text-slate-500 font-mono ml-1">({filtered.length})</span>
            </h2>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search invoice / PO / client"
              data-testid="invoices-search"
              className="border-2 border-slate-300 px-3 py-1.5 text-sm focus:border-[#C27842] outline-none w-72" />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="invoices-table">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-4 py-2 font-bold">Invoice #</th>
                  <th className="px-4 py-2 font-bold">Date</th>
                  <th className="px-4 py-2 font-bold">Client</th>
                  <th className="px-4 py-2 font-bold">PO #</th>
                  <th className="px-4 py-2 font-bold text-right">Amount</th>
                  <th className="px-4 py-2 font-bold text-right">Received</th>
                  <th className="px-4 py-2 font-bold text-right">Outstanding</th>
                  <th className="px-4 py-2 font-bold">Due</th>
                  <th className="px-4 py-2 font-bold">Status</th>
                  <th className="px-4 py-2 font-bold text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr><td colSpan="10" className="text-center text-slate-400 py-12 text-sm">No invoices match.</td></tr>
                ) : filtered.map(r => (
                  <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`invoice-row-${r.invoice_no}`}>
                    <td className="px-4 py-2 font-mono font-bold">{r.invoice_no}</td>
                    <td className="px-4 py-2 font-mono text-xs">{r.invoice_date}</td>
                    <td className="px-4 py-2 text-xs">{r.client_name}</td>
                    <td className="px-4 py-2 font-mono text-xs">{r.po_number || (r.po_numbers || []).join(", ")}</td>
                    <td className="px-4 py-2 text-right font-mono">{inr(r.net_amount || r.grand_total || 0)}</td>
                    <td className="px-4 py-2 text-right font-mono text-[#16A34A]">{inr(r.received_amount || 0)}</td>
                    <td className="px-4 py-2 text-right font-mono font-bold">{inr(r.outstanding || 0)}</td>
                    <td className="px-4 py-2 text-xs">
                      <span className={r.status === "overdue" ? "text-red-600 font-bold" : "text-slate-600"}>
                        {r.due_date || "—"}
                      </span>
                      {r.status !== "paid" && r.days_to_due != null && (
                        <div className={`text-[10px] ${r.days_to_due < 0 ? "text-red-600 font-bold" : r.days_to_due < 7 ? "text-amber-600" : "text-slate-500"}`}>
                          {r.days_to_due < 0 ? `${-r.days_to_due}d overdue` : `${r.days_to_due}d to go`}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2"><Badge color={STATUS_COLOR[r.status] || "yellow"}>{r.status}</Badge></td>
                    <td className="px-4 py-2 text-right whitespace-nowrap">
                      <button onClick={() => openInvoice(r.id)} className="text-slate-600 hover:text-[#2563EB] p-1.5" title="View" data-testid={`inv-view-${r.invoice_no}`}><Eye className="w-4 h-4" /></button>
                      <a href={`${process.env.REACT_APP_BACKEND_URL}/api/invoices/${r.id}/file`} target="_blank" rel="noreferrer" className="text-slate-600 hover:text-[#C27842] p-1.5 inline-block" title="Download PDF" data-testid={`inv-download-${r.invoice_no}`}><FileDown className="w-4 h-4" /></a>
                      {r.status !== "paid" && (
                        <>
                          <button onClick={() => setGrnFor(r)} className="text-slate-600 hover:text-[#7C3AED] p-1.5" title="Record GRN" data-testid={`inv-grn-${r.invoice_no}`}><ClipboardCheck className="w-4 h-4" /></button>
                          <button onClick={() => setPaymentFor(r)} className="text-slate-600 hover:text-[#16A34A] p-1.5" title="Record Payment" data-testid={`inv-payment-${r.invoice_no}`}><IndianRupee className="w-4 h-4" /></button>
                        </>
                      )}
                      <button onClick={() => setDeleteFor(r)} className="text-slate-600 hover:text-red-600 p-1.5" title="Delete Invoice" data-testid={`inv-delete-${r.invoice_no}`}><Trash2 className="w-4 h-4" /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
              {filtered.length > 0 && (
                <tfoot className="bg-slate-900 text-white">
                  <tr>
                    <td colSpan="4" className="px-4 py-2.5 text-[10px] uppercase tracking-wider font-bold text-[#C27842]">Filter totals</td>
                    <td className="px-4 py-2.5 text-right font-mono font-bold">{inr(filtered.reduce((s, r) => s + (r.net_amount || 0), 0))}</td>
                    <td className="px-4 py-2.5 text-right font-mono font-bold text-[#16A34A]">{inr(filtered.reduce((s, r) => s + (r.received_amount || 0), 0))}</td>
                    <td className="px-4 py-2.5 text-right font-mono font-bold text-[#C27842]">{inr(filtered.reduce((s, r) => s + (r.outstanding || 0), 0))}</td>
                    <td colSpan="3" className="px-4 py-2.5 text-right font-mono text-xs text-slate-300">Grand Total Outstanding · <b className="text-white">{inr(totalOutstanding)}</b></td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </Card>
      </div>

      {view && <InvoiceDetailModal inv={view} onClose={() => setView(null)} />}
      {grnFor && <GRNDialog invoiceMeta={grnFor} onClose={() => setGrnFor(null)} onSaved={() => { setGrnFor(null); load(); }} />}
      {paymentFor && <PaymentDialog invoiceMeta={paymentFor} onClose={() => setPaymentFor(null)} onSaved={() => { setPaymentFor(null); load(); }} />}
      {deleteFor && <DeleteConfirmDialog invoice={deleteFor} onClose={() => setDeleteFor(null)} onDeleted={() => { setDeleteFor(null); load(); }} />}
    </div>
  );
}

function Tile({ label, value, sub, accent = "#0F172A", active, onClick, testId }) {
  return (
    <button onClick={onClick} data-testid={testId}
      className={`text-left p-4 border-2 transition-colors ${active ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200 hover:border-slate-900"}`}>
      <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-80" style={!active ? { color: accent } : {}}>{label}</div>
      <div className="font-mono text-2xl font-bold mt-1">{value}</div>
      <div className={`text-xs font-mono mt-1 ${active ? "text-slate-300" : "text-slate-500"}`}>{sub}</div>
    </button>
  );
}

/* ------------------- INVOICE DETAIL MODAL ------------------- */
function InvoiceDetailModal({ inv, onClose }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4" data-testid="invoice-modal">
      <div className="bg-white w-full max-w-5xl max-h-[92vh] overflow-y-auto border-2 border-slate-200 shadow-2xl">
        <div className="bg-[#0F172A] text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold">Tax Invoice</div>
            <div className="text-xl font-bold">{inv.invoice_no} · {inv.client_name}</div>
          </div>
          <button onClick={onClose} className="hover:bg-white/10 p-1"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <DLPair label="Invoice Date" value={inv.invoice_date} />
            <DLPair label="Due Date" value={inv.due_date} highlight={inv.status === "overdue"} />
            <DLPair label="Payment Terms" value={`${inv.payment_terms_days || 45} days`} />
            <DLPair label="PO #" value={inv.po_number || (inv.po_numbers || []).join(" + ")} />
            <DLPair label="Subtotal" value={inr(inv.subtotal || 0)} />
            <DLPair label="IGST" value={inr(inv.igst_amount || 0)} />
            <DLPair label="Grand Total" value={inr(inv.grand_total || 0)} />
            <DLPair label="Status" value={inv.status?.toUpperCase()} highlight={inv.status === "overdue"} />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <BalanceTile label="Gross" value={inr(inv.grand_total || 0)} />
            <BalanceTile label="Short / Adjusted" value={`- ${inr(inv.grn_adjustment || 0)}`} accent="#DC2626" />
            <BalanceTile label="Outstanding" value={inr(inv.outstanding || 0)} accent="#C27842" big />
          </div>

          <Section title="Line items">
            <table className="w-full text-xs border-2 border-slate-200">
              <thead className="bg-slate-50">
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-2 font-bold">Style</th>
                  <th className="px-3 py-2 font-bold">Color</th>
                  <th className="px-3 py-2 font-bold">Size</th>
                  <th className="px-3 py-2 font-bold text-right">Qty</th>
                  <th className="px-3 py-2 font-bold text-right">Rate</th>
                  <th className="px-3 py-2 font-bold text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {(inv.line_items_snapshot || []).map((li, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="px-3 py-1.5 font-mono">{li.style_code}</td>
                    <td className="px-3 py-1.5">{li.color}</td>
                    <td className="px-3 py-1.5 font-mono">{li.size}</td>
                    <td className="px-3 py-1.5 text-right font-mono">{li.quantity}</td>
                    <td className="px-3 py-1.5 text-right font-mono">{inr(li.unit_price || 0)}</td>
                    <td className="px-3 py-1.5 text-right font-mono font-bold">{inr(li.amount || 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          {(inv.grns || []).length > 0 && (
            <Section title={`Goods Receipts (${inv.grns.length})`}>
              {inv.grns.map((g, i) => (
                <Card key={i} className="p-3 mb-2">
                  <div className="flex items-baseline justify-between text-xs">
                    <div>
                      <div className="font-bold font-mono">{g.grn_no} · {g.grn_date}</div>
                      <div className="text-slate-500 text-[10px]">Ref: {g.client_reference || "—"}</div>
                    </div>
                    <div className="text-right font-mono">
                      <div>Dispatched {g.total_dispatched} → Accepted {g.total_accepted} {g.total_rejected > 0 && <span className="text-red-600">(Rej {g.total_rejected})</span>}</div>
                    </div>
                  </div>
                  {g.notes && <div className="text-xs text-slate-600 mt-1 italic">{g.notes}</div>}
                </Card>
              ))}
            </Section>
          )}

          {(inv.payments || []).length > 0 && (
            <Section title={`Payments received (${inv.payments.length})`}>
              <table className="w-full text-xs">
                <thead className="bg-slate-50">
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600 border-b border-slate-200">
                    <th className="px-3 py-2 font-bold">Receipt #</th>
                    <th className="px-3 py-2 font-bold">Date</th>
                    <th className="px-3 py-2 font-bold">Mode</th>
                    <th className="px-3 py-2 font-bold">Reference</th>
                    <th className="px-3 py-2 font-bold text-right">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {inv.payments.map((p, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="px-3 py-1.5 font-mono font-bold">{p.payment_no}</td>
                      <td className="px-3 py-1.5 font-mono">{p.payment_date}</td>
                      <td className="px-3 py-1.5">{p.mode}</td>
                      <td className="px-3 py-1.5 font-mono text-slate-600">{p.reference || "—"}</td>
                      <td className="px-3 py-1.5 text-right font-mono font-bold text-[#16A34A]">{inr(p.allocations?.[inv.id] || p.amount || 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}

function DLPair({ label, value, highlight = false }) {
  return (
    <div className="border-b border-dashed border-slate-200 pb-2">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{label}</div>
      <div className={`font-mono font-bold ${highlight ? "text-red-600" : ""}`}>{value || "—"}</div>
    </div>
  );
}

function BalanceTile({ label, value, accent = "#0F172A", big = false }) {
  return (
    <div className="border-2 border-slate-200 px-4 py-3 relative">
      <div className="text-[10px] uppercase tracking-wider font-bold" style={{ color: accent }}>{label}</div>
      <div className={`font-mono font-bold ${big ? "text-2xl" : "text-lg"}`}>{value}</div>
      <div className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: accent }} />
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-[0.2em] font-bold text-[#C27842] mb-2 border-b border-slate-200 pb-1">{title}</h3>
      {children}
    </div>
  );
}

/* ------------------- GRN DIALOG ------------------- */
function GRNDialog({ invoiceMeta, onClose, onSaved }) {
  const [inv, setInv] = useState(null);
  const [form, setForm] = useState({
    grn_date: new Date().toISOString().slice(0, 10),
    client_reference: "",
    notes: "",
    lines: [],
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    http.get(`/invoices/${invoiceMeta.id}`).then(({ data }) => {
      setInv(data);
      setForm(f => ({
        ...f,
        lines: (data.line_items_snapshot || []).map(li => ({
          style_code: li.style_code, description: li.description || "", color: li.color, size: li.size,
          dispatched_qty: li.quantity, received_qty: li.quantity, accepted_qty: li.quantity,
          rejected_qty: 0, rejection_reason: "",
        })),
      }));
    });
  }, [invoiceMeta.id]);

  const updLine = (i, k, v) => setForm(f => {
    const lines = [...f.lines];
    lines[i] = { ...lines[i], [k]: v };
    if (k === "received_qty" || k === "rejected_qty") {
      const recv = Number(lines[i].received_qty || 0), rej = Number(lines[i].rejected_qty || 0);
      lines[i].accepted_qty = Math.max(0, recv - rej);
    }
    return { ...f, lines };
  });

  const submit = async () => {
    setSaving(true);
    try {
      await http.post("/grns", {
        invoice_id: invoiceMeta.id,
        grn_date: form.grn_date,
        client_reference: form.client_reference,
        notes: form.notes,
        line_items: form.lines.map(l => ({
          ...l,
          dispatched_qty: Number(l.dispatched_qty || 0),
          received_qty: Number(l.received_qty || 0),
          accepted_qty: Number(l.accepted_qty || 0),
          rejected_qty: Number(l.rejected_qty || 0),
        })),
      });
      onSaved();
    } catch (e) {
      alert("GRN failed: " + (e.response?.data?.detail || e.message));
    } finally { setSaving(false); }
  };

  if (!inv) return null;
  const tot = form.lines.reduce((s, l) => s + Number(l.accepted_qty || 0), 0);
  const totDisp = form.lines.reduce((s, l) => s + Number(l.dispatched_qty || 0), 0);
  const totRej = form.lines.reduce((s, l) => s + Number(l.rejected_qty || 0), 0);

  return (
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4" data-testid="grn-dialog">
      <div className="bg-white w-full max-w-5xl max-h-[92vh] overflow-y-auto border-2 border-slate-200 shadow-2xl">
        <div className="bg-[#7C3AED] text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-90">Goods Receipt Note</div>
            <div className="text-xl font-bold">{invoiceMeta.invoice_no} · {invoiceMeta.client_name}</div>
          </div>
          <button onClick={onClose} className="hover:bg-white/20 p-1"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 space-y-4">
          <div className="bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-slate-700">
            Update the <b>Received qty</b> and <b>Rejected qty</b> per line as per the client's confirmation email. <b>Accepted = Received − Rejected</b>. Short / rejected pcs auto-reduce the receivable in the ledger.
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">GRN Date</div>
              <input type="date" value={form.grn_date} onChange={(e) => setForm(f => ({ ...f, grn_date: e.target.value }))} data-testid="grn-date" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#7C3AED] outline-none" />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">Client reference / email</div>
              <input value={form.client_reference} onChange={(e) => setForm(f => ({ ...f, client_reference: e.target.value }))} placeholder="SIYARAM/GRN/2026/123" data-testid="grn-ref" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#7C3AED] outline-none" />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">Notes</div>
              <input value={form.notes} onChange={(e) => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Optional notes" data-testid="grn-notes" className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#7C3AED] outline-none" />
            </div>
          </div>

          <table className="w-full text-xs border-2 border-slate-200">
            <thead className="bg-slate-50">
              <tr className="text-left text-[10px] uppercase tracking-wider text-slate-600">
                <th className="px-2 py-2 font-bold">Style</th>
                <th className="px-2 py-2 font-bold">Color</th>
                <th className="px-2 py-2 font-bold">Size</th>
                <th className="px-2 py-2 font-bold text-right">Dispatched</th>
                <th className="px-2 py-2 font-bold text-right">Received</th>
                <th className="px-2 py-2 font-bold text-right">Rejected</th>
                <th className="px-2 py-2 font-bold text-right">Accepted</th>
                <th className="px-2 py-2 font-bold">Rejection reason</th>
              </tr>
            </thead>
            <tbody>
              {form.lines.map((l, i) => (
                <tr key={i} className="border-t border-slate-100" data-testid={`grn-line-${i}`}>
                  <td className="px-2 py-1.5 font-mono">{l.style_code}</td>
                  <td className="px-2 py-1.5">{l.color}</td>
                  <td className="px-2 py-1.5 font-mono">{l.size}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{l.dispatched_qty}</td>
                  <td className="px-2 py-1"><input type="number" min="0" value={l.received_qty} onChange={(e) => updLine(i, "received_qty", e.target.value)} data-testid={`grn-recv-${i}`} className="w-20 border border-slate-300 px-2 py-1 font-mono text-right focus:border-[#7C3AED] outline-none" /></td>
                  <td className="px-2 py-1"><input type="number" min="0" value={l.rejected_qty} onChange={(e) => updLine(i, "rejected_qty", e.target.value)} data-testid={`grn-rej-${i}`} className="w-20 border border-slate-300 px-2 py-1 font-mono text-right focus:border-[#7C3AED] outline-none" /></td>
                  <td className="px-2 py-1.5 text-right font-mono font-bold text-[#16A34A]">{l.accepted_qty}</td>
                  <td className="px-2 py-1"><input value={l.rejection_reason} onChange={(e) => updLine(i, "rejection_reason", e.target.value)} data-testid={`grn-reason-${i}`} placeholder={l.rejected_qty > 0 ? "Reason required" : ""} className="w-full border border-slate-300 px-2 py-1 text-xs focus:border-[#7C3AED] outline-none" /></td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-slate-900 text-white">
              <tr>
                <td colSpan="3" className="px-2 py-2 font-bold text-[#C27842] uppercase tracking-wider text-[10px]">Totals</td>
                <td className="px-2 py-2 text-right font-mono">{totDisp}</td>
                <td className="px-2 py-2 text-right font-mono">{form.lines.reduce((s, l) => s + Number(l.received_qty || 0), 0)}</td>
                <td className="px-2 py-2 text-right font-mono text-red-300">{totRej}</td>
                <td className="px-2 py-2 text-right font-mono font-bold">{tot}</td>
                <td className="px-2 py-2 text-right text-[10px] uppercase tracking-wider text-slate-300">Short: <b className="text-red-300">{totDisp - tot}</b></td>
              </tr>
            </tfoot>
          </table>

          <div className="flex gap-2 pt-3 border-t border-slate-200">
            <BtnPrimary onClick={submit} disabled={saving} data-testid="grn-submit" className="bg-[#7C3AED] border-[#7C3AED] hover:bg-[#5B21B6]">
              {saving ? "Saving…" : "Save GRN"}
            </BtnPrimary>
            <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------- PAYMENT DIALOG ------------------- */
function PaymentDialog({ invoiceMeta, onClose, onSaved }) {
  const [form, setForm] = useState({
    amount: invoiceMeta.outstanding || 0,
    payment_date: new Date().toISOString().slice(0, 10),
    mode: "NEFT",
    reference: "",
    bank: "",
    notes: "",
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!Number(form.amount)) return alert("Amount must be > 0");
    setSaving(true);
    try {
      await http.post("/payments", {
        invoice_ids: [invoiceMeta.id],
        amount: Number(form.amount),
        payment_date: form.payment_date,
        mode: form.mode,
        reference: form.reference,
        bank: form.bank,
        notes: form.notes,
      });
      onSaved();
    } catch (e) {
      alert("Payment failed: " + (e.response?.data?.detail || e.message));
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4" data-testid="payment-dialog">
      <div className="bg-white w-full max-w-2xl border-2 border-slate-200 shadow-2xl">
        <div className="bg-[#16A34A] text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-90">Record Payment</div>
            <div className="text-xl font-bold">{invoiceMeta.invoice_no} · {invoiceMeta.client_name}</div>
          </div>
          <button onClick={onClose} className="hover:bg-white/20 p-1"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <BalanceTile label="Invoice Total" value={inr(invoiceMeta.net_amount || 0)} />
            <BalanceTile label="Outstanding" value={inr(invoiceMeta.outstanding || 0)} accent="#C27842" big />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Amount received">
              <input type="number" min="0" step="0.01" value={form.amount} onChange={(e) => set("amount", e.target.value)} data-testid="pay-amount" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-lg focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Payment date">
              <input type="date" value={form.payment_date} onChange={(e) => set("payment_date", e.target.value)} data-testid="pay-date" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Mode">
              <select value={form.mode} onChange={(e) => set("mode", e.target.value)} data-testid="pay-mode" className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none">
                {PAYMENT_MODES.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </Field>
            <Field label="Reference (UTR / Cheque #)">
              <input value={form.reference} onChange={(e) => set("reference", e.target.value)} data-testid="pay-ref" placeholder="NEFT-UTR-XXXXXXXX" className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Bank">
              <input value={form.bank} onChange={(e) => set("bank", e.target.value)} data-testid="pay-bank" placeholder="HDFC / ICICI / SBI" className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none" />
            </Field>
            <Field label="Notes">
              <input value={form.notes} onChange={(e) => set("notes", e.target.value)} data-testid="pay-notes" className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none" />
            </Field>
          </div>

          <div className="flex gap-2 pt-3 border-t border-slate-200">
            <BtnPrimary onClick={submit} disabled={saving} data-testid="pay-submit" className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36]">
              {saving ? "Saving…" : "Save payment"}
            </BtnPrimary>
            <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1">{label}</div>
      {children}
    </div>
  );
}

function DeleteConfirmDialog({ invoice, onClose, onDeleted }) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await http.delete(`/invoices/${invoice.id}`);
      onDeleted();
    } catch (err) {
      alert("Failed to delete invoice: " + (err.response?.data?.detail || err.message));
      setDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4" data-testid="delete-dialog">
      <div className="bg-white w-full max-w-md border-2 border-red-200 shadow-2xl">
        <div className="bg-red-600 text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-90">Confirm Delete</div>
            <div className="text-xl font-bold">{invoice.invoice_no}</div>
          </div>
          <button onClick={onClose} className="hover:bg-white/20 p-1"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 space-y-4">
          <p className="text-sm text-slate-700">
            Are you sure you want to delete invoice <b>{invoice.invoice_no}</b>? 
            This action cannot be undone.
          </p>
          <div className="bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-slate-700">
            <b>Note:</b> This will also delete any associated payments and revert the original production jobs back to the "Dispatched" state.
          </div>
          <div className="flex gap-2 pt-4 border-t border-slate-200">
            <BtnPrimary onClick={handleDelete} disabled={deleting} className="bg-red-600 border-red-600 hover:bg-red-700">
              {deleting ? "Deleting…" : "Yes, Delete"}
            </BtnPrimary>
            <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          </div>
        </div>
      </div>
    </div>
  );
}
