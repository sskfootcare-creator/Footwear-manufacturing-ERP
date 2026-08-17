import { useEffect, useState } from "react";
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
  FileDown,
  Eye,
  X,
  Receipt,
  ClipboardCheck,
  IndianRupee,
  AlertCircle,
  Trash2,
  Calendar,
  TrendingUp,
  Clock,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  Sparkles,
  CheckCircle2,
  CalendarDays,
  Coins,
} from "lucide-react";

const STATUS_COLOR = {
  paid: "green",
  partial: "blue",
  overdue: "red",
  pending: "yellow",
};
const PAYMENT_MODES = [
  "Bank Transfer",
  "RTGS",
  "NEFT",
  "Cheque",
  "UPI",
  "Cash",
  "Adjustment",
];

export default function Invoices() {
  const [rows, setRows] = useState([]);
  const [forecast, setForecast] = useState(null);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [view, setView] = useState(null);
  const [grnFor, setGrnFor] = useState(null);
  const [paymentFor, setPaymentFor] = useState(null);
  const [deleteFor, setDeleteFor] = useState(null);
  const [showForecast, setShowForecast] = useState(true);

  const load = async () => {
    try {
      const [{ data: invData }, { data: forecastData }] = await Promise.all([
        http.get("/invoices"),
        http.get("/invoices/cash-forecast").catch(() => ({ data: null })),
      ]);
      setRows(invData || []);
      setForecast(forecastData || null);
    } catch (err) {
      console.error("Failed to load invoices or forecast", err);
    }
  };
  useEffect(() => {
    load();
  }, []);

  const filtered = rows.filter((r) => {
    if (filter === "grn_recorded") {
      if (!r.grn_recorded && !r.grn_date) return false;
    } else if (filter === "awaiting_grn") {
      if (r.grn_recorded || r.grn_date) return false;
    } else if (filter !== "all" && r.status !== filter) {
      return false;
    }
    if (search) {
      const q = search.toLowerCase();
      if (
        !`${r.invoice_no} ${r.client_name} ${r.po_number} ${r.grn_no || ""} ${r.grn_date || ""}`
          .toLowerCase()
          .includes(q)
      )
        return false;
    }
    return true;
  });

  const overdue = rows.filter((r) => r.status === "overdue");
  const partial = rows.filter((r) => r.status === "partial");
  const paid = rows.filter((r) => r.status === "paid");
  const pending = rows.filter((r) => r.status === "pending");
  const grnRecorded = rows.filter((r) => r.grn_recorded || r.grn_date);
  const awaitingGrn = rows.filter((r) => !r.grn_recorded && !r.grn_date);
  const totalOutstanding = rows.reduce((s, r) => s + (r.outstanding || 0), 0);

  const openInvoice = async (id) => {
    const { data } = await http.get(`/invoices/${id}`);
    setView(data);
  };

  return (
    <div>
      <PageHeader
        title="Invoices"
        subtitle="Accounts / Receivables"
        testId="invoices-header"
      />
      <div className="p-2 sm:p-4 lg:p-8 space-y-5">
        {overdue.length > 0 && (
          <Card
            className="bg-red-50 border-2 border-red-300 px-4 py-3 flex items-center justify-between"
            data-testid="overdue-banner"
          >
            <div className="flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-red-600" />
              <div>
                <div className="font-bold text-red-700 text-sm">
                  {overdue.length} invoice{overdue.length > 1 ? "s" : ""}{" "}
                  overdue ·{" "}
                  {inr(overdue.reduce((s, r) => s + r.outstanding, 0))} pending
                </div>
                <div className="text-xs text-red-600">
                  Payment terms exceeded — chase up with client.
                </div>
              </div>
            </div>
            <button
              onClick={() => setFilter("overdue")}
              className="text-xs uppercase tracking-wider font-bold text-red-700 hover:underline"
            >
              View overdue →
            </button>
          </Card>
        )}

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Tile
            label="Total"
            value={rows.length}
            sub={inr(rows.reduce((s, r) => s + (r.net_amount || 0), 0))}
            active={filter === "all"}
            onClick={() => setFilter("all")}
            testId="tile-all"
          />
          <Tile
            label="Pending"
            value={pending.length}
            sub={inr(pending.reduce((s, r) => s + r.outstanding, 0))}
            accent="#F59E0B"
            active={filter === "pending"}
            onClick={() => setFilter("pending")}
            testId="tile-pending"
          />
          <Tile
            label="Partial"
            value={partial.length}
            sub={inr(partial.reduce((s, r) => s + r.outstanding, 0))}
            accent="#2563EB"
            active={filter === "partial"}
            onClick={() => setFilter("partial")}
            testId="tile-partial"
          />
          <Tile
            label="Overdue"
            value={overdue.length}
            sub={inr(overdue.reduce((s, r) => s + r.outstanding, 0))}
            accent="#DC2626"
            active={filter === "overdue"}
            onClick={() => setFilter("overdue")}
            testId="tile-overdue"
          />
          <Tile
            label="Paid"
            value={paid.length}
            sub={inr(paid.reduce((s, r) => s + (r.net_amount || 0), 0))}
            accent="#16A34A"
            active={filter === "paid"}
            onClick={() => setFilter("paid")}
            testId="tile-paid"
          />
        </div>

        {/* Weekly Cash Inflow Forecast & Vendor Payment Schedule */}
        {forecast && (
          <WeeklyCashInflowForecast
            forecast={forecast}
            onSelectInvoice={(invId) => openInvoice(invId)}
            onRecordGRN={(invSummary) => {
              const fullRow = rows.find((r) => r.id === invSummary.id) || invSummary;
              setGrnFor(fullRow);
            }}
          />
        )}

        <Card className="overflow-hidden" data-testid="invoices-card">
          <div className="px-5 py-3 border-b-2 border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-bold uppercase tracking-wider flex items-center gap-2 mr-2">
                <FileText className="w-4 h-4 text-[#C27842]" />
                Invoices
                <span className="text-slate-500 font-mono ml-1">
                  ({filtered.length})
                </span>
              </h2>

              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <button
                  onClick={() => setFilter("all")}
                  className={`px-2.5 py-1 rounded font-semibold transition-colors ${
                    filter === "all"
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  All ({rows.length})
                </button>
                <button
                  onClick={() => setFilter("grn_recorded")}
                  className={`px-2.5 py-1 rounded font-semibold flex items-center gap-1 transition-colors ${
                    filter === "grn_recorded"
                      ? "bg-purple-700 text-white"
                      : "bg-purple-50 text-purple-800 border border-purple-200 hover:bg-purple-100"
                  }`}
                >
                  <ClipboardCheck className="w-3.5 h-3.5" />
                  GRN Recorded ({grnRecorded.length})
                </button>
                <button
                  onClick={() => setFilter("awaiting_grn")}
                  className={`px-2.5 py-1 rounded font-semibold flex items-center gap-1 transition-colors ${
                    filter === "awaiting_grn"
                      ? "bg-amber-600 text-white"
                      : "bg-amber-50 text-amber-800 border border-amber-200 hover:bg-amber-100"
                  }`}
                >
                  <Clock className="w-3.5 h-3.5" />
                  Awaiting GRN ({awaitingGrn.length})
                </button>
                <button
                  onClick={() => setFilter("overdue")}
                  className={`px-2.5 py-1 rounded font-semibold transition-colors ${
                    filter === "overdue"
                      ? "bg-red-600 text-white"
                      : "bg-red-50 text-red-700 border border-red-200 hover:bg-red-100"
                  }`}
                >
                  Overdue ({overdue.length})
                </button>
                <button
                  onClick={() => setFilter("paid")}
                  className={`px-2.5 py-1 rounded font-semibold transition-colors ${
                    filter === "paid"
                      ? "bg-green-600 text-white"
                      : "bg-green-50 text-green-700 border border-green-200 hover:bg-green-100"
                  }`}
                >
                  Paid ({paid.length})
                </button>
              </div>
            </div>

            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search invoice / PO / client / GRN"
              data-testid="invoices-search"
              className="border-2 border-slate-300 px-3 py-1.5 text-sm focus:border-[#C27842] outline-none w-full md:w-72"
            />
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
                  <th className="px-4 py-2 font-bold text-right">
                    Outstanding
                  </th>
                  <th className="px-4 py-2 font-bold">GRN Status</th>
                  <th className="px-4 py-2 font-bold">Due (45d)</th>
                  <th className="px-4 py-2 font-bold">Status</th>
                  <th className="px-4 py-2 font-bold text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td
                      colSpan="11"
                      className="text-center text-slate-400 py-12 text-sm"
                    >
                      No invoices match.
                    </td>
                  </tr>
                ) : (
                  filtered.map((r) => (
                    <tr
                      key={r.id}
                      className="border-b border-slate-100 hover:bg-slate-50"
                      data-testid={`invoice-row-${r.invoice_no}`}
                    >
                      <td className="px-4 py-2 font-mono font-bold">
                        {r.invoice_no}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs">
                        {r.invoice_date}
                      </td>
                      <td className="px-4 py-2 text-xs">{r.client_name}</td>
                      <td className="px-4 py-2 font-mono text-xs">
                        {r.po_number || (r.po_numbers || []).join(", ")}
                      </td>
                      <td className="px-4 py-2 text-right font-mono">
                        {inr(r.net_amount || r.grand_total || 0)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-[#16A34A]">
                        {inr(r.received_amount || 0)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono font-bold">
                        {inr(r.outstanding || 0)}
                      </td>
                      <td className="px-4 py-2 whitespace-nowrap">
                        {r.grn_recorded || r.grn_date ? (
                          <div>
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-900 border border-purple-300">
                              <ClipboardCheck className="w-3.5 h-3.5 text-purple-700" />
                              GRN Recorded
                            </span>
                            <div className="text-[10px] font-mono text-purple-700 mt-0.5">
                              {r.grn_date} {r.grn_no ? `· ${r.grn_no}` : ""}
                            </div>
                          </div>
                        ) : (
                          <div>
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                              <Clock className="w-3.5 h-3.5 text-amber-600" />
                              Awaiting GRN
                            </span>
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-2 text-xs whitespace-nowrap">
                        {r.due_date ? (
                          <>
                            <span
                              className={
                                r.status === "overdue"
                                  ? "text-red-600 font-bold font-mono"
                                  : "text-slate-800 font-bold font-mono"
                              }
                            >
                              {r.due_date}
                            </span>
                            <div className="flex flex-wrap items-center gap-1 mt-0.5">
                              {r.status !== "paid" && r.days_to_due != null && (
                                <span
                                  className={`text-[10px] font-semibold ${r.days_to_due < 0 ? "text-red-600 font-bold" : r.days_to_due < 7 ? "text-amber-600" : "text-slate-500"}`}
                                >
                                  {r.days_to_due < 0
                                    ? `${-r.days_to_due}d overdue`
                                    : `${r.days_to_due}d to go`}
                                </span>
                              )}
                            </div>
                          </>
                        ) : (
                          <div className="text-[10px] text-slate-400">
                            {r.payment_terms_days || 45}d from GRN
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        <Badge color={STATUS_COLOR[r.status] || "yellow"}>
                          {r.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-2 text-right whitespace-nowrap">
                        <button
                          onClick={() => openInvoice(r.id)}
                          className="text-slate-600 hover:text-[#2563EB] p-1.5"
                          title="View"
                          data-testid={`inv-view-${r.invoice_no}`}
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <a
                          href={`${process.env.REACT_APP_BACKEND_URL}/api/invoices/${r.id}/file`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-slate-600 hover:text-[#C27842] p-1.5 inline-block"
                          title="Download PDF"
                          data-testid={`inv-download-${r.invoice_no}`}
                        >
                          <FileDown className="w-4 h-4" />
                        </a>
                        {r.status !== "paid" && (
                          <>
                            <button
                              onClick={() => setGrnFor(r)}
                              className={`p-1.5 rounded inline-block ${
                                r.grn_recorded || r.grn_date
                                  ? "text-purple-700 bg-purple-50 hover:bg-purple-100 border border-purple-200"
                                  : "text-slate-600 hover:text-[#7C3AED]"
                              }`}
                              title={r.grn_recorded || r.grn_date ? "GRN Recorded: click to view or add details" : "Record GRN"}
                              data-testid={`inv-grn-${r.invoice_no}`}
                            >
                              <ClipboardCheck className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => setPaymentFor(r)}
                              className="text-slate-600 hover:text-[#16A34A] p-1.5"
                              title="Record Payment"
                              data-testid={`inv-payment-${r.invoice_no}`}
                            >
                              <IndianRupee className="w-4 h-4" />
                            </button>
                          </>
                        )}
                        <button
                          onClick={() => setDeleteFor(r)}
                          className="text-slate-600 hover:text-red-600 p-1.5"
                          title="Delete Invoice"
                          data-testid={`inv-delete-${r.invoice_no}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
              {filtered.length > 0 && (
                <tfoot className="bg-slate-900 text-white">
                  <tr>
                    <td
                      colSpan="4"
                      className="px-4 py-2.5 text-[10px] uppercase tracking-wider font-bold text-[#C27842]"
                    >
                      Filter totals
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono font-bold">
                      {inr(
                        filtered.reduce((s, r) => s + (r.net_amount || 0), 0),
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono font-bold text-[#16A34A]">
                      {inr(
                        filtered.reduce(
                          (s, r) => s + (r.received_amount || 0),
                          0,
                        ),
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono font-bold text-[#C27842]">
                      {inr(
                        filtered.reduce((s, r) => s + (r.outstanding || 0), 0),
                      )}
                    </td>
                    <td
                      colSpan="4"
                      className="px-4 py-2.5 text-right font-mono text-xs text-slate-300"
                    >
                      Grand Total Outstanding ·{" "}
                      <b className="text-white">{inr(totalOutstanding)}</b>
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </Card>
      </div>

      {view && <InvoiceDetailModal inv={view} onClose={() => setView(null)} />}
      {grnFor && (
        <GRNDialog
          invoiceMeta={grnFor}
          onClose={() => setGrnFor(null)}
          onSaved={() => {
            setGrnFor(null);
            load();
          }}
        />
      )}
      {paymentFor && (
        <PaymentDialog
          invoiceMeta={paymentFor}
          onClose={() => setPaymentFor(null)}
          onSaved={() => {
            setPaymentFor(null);
            load();
          }}
        />
      )}
      {deleteFor && (
        <DeleteConfirmDialog
          invoice={deleteFor}
          onClose={() => setDeleteFor(null)}
          onDeleted={() => {
            setDeleteFor(null);
            load();
          }}
        />
      )}
    </div>
  );
}

function Tile({
  label,
  value,
  sub,
  accent = "#0F172A",
  active,
  onClick,
  testId,
}) {
  return (
    <button
      onClick={onClick}
      data-testid={testId}
      className={`text-left p-3 sm:p-4 border-2 transition-colors ${active ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200 hover:border-slate-900"}`}
    >
      <div
        className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-80 truncate"
        style={!active ? { color: accent } : {}}
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
        className={`text-[10px] sm:text-xs font-mono mt-1 truncate ${active ? "text-slate-300" : "text-slate-500"}`}
        title={String(sub)}
      >
        {sub}
      </div>
    </button>
  );
}

/* ------------------- INVOICE DETAIL MODAL ------------------- */
function InvoiceDetailModal({ inv, onClose }) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4"
      data-testid="invoice-modal"
    >
      <div className="bg-white w-full max-w-5xl max-h-[92vh] overflow-y-auto border-2 border-slate-200 shadow-2xl">
        <div className="bg-[#0F172A] text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-[#C27842] font-bold">
              Tax Invoice
            </div>
            <div className="text-xl font-bold">
              {inv.invoice_no} · {inv.client_name}
            </div>
          </div>
          <button onClick={onClose} className="hover:bg-white/10 p-1">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6 space-y-5">
          {/* Prominent GRN Recording Status Banner */}
          {inv.grn_recorded || inv.grn_date ? (
            <div className="bg-purple-50 border-2 border-purple-300 p-3.5 rounded-lg flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-purple-600 text-white rounded-lg">
                  <ClipboardCheck className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-xs font-bold text-purple-950 flex items-center gap-2">
                    <span>GRN Recorded</span>
                    <span className="font-mono text-purple-700 bg-purple-200/70 px-2 py-0.5 rounded text-[11px]">
                      {inv.grn_no ? `${inv.grn_no} · ` : ""}Date: {inv.grn_date}
                    </span>
                  </div>
                  <div className="text-xs text-purple-800 mt-0.5">
                    Goods received & accepted. 45-day payment term ends on <b className="font-mono">{inv.due_date}</b>.
                  </div>
                </div>
              </div>
              <span className="text-[10px] uppercase font-bold tracking-wider bg-purple-200 text-purple-900 px-2.5 py-1 rounded">
                Clock Running
              </span>
            </div>
          ) : (
            <div className="bg-amber-50 border-2 border-amber-300 p-3.5 rounded-lg flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-amber-500 text-white rounded-lg">
                  <Clock className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-xs font-bold text-amber-950">
                    Awaiting Client GRN Confirmation
                  </div>
                  <div className="text-xs text-amber-800 mt-0.5">
                    Goods dispatched. The 45-day payment due date will be calculated as soon as the GRN date is recorded.
                  </div>
                </div>
              </div>
              <span className="text-[10px] uppercase font-bold tracking-wider bg-amber-200 text-amber-900 px-2.5 py-1 rounded">
                Awaiting GRN
              </span>
            </div>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <DLPair label="Invoice Date" value={inv.invoice_date} />
            <DLPair
              label="GRN Date"
              value={inv.grn_date || "Awaiting GRN"}
              highlight={!inv.grn_date}
            />
            <DLPair
              label="Due Date"
              value={inv.due_date || "Calculates 45d from GRN"}
              highlight={inv.status === "overdue"}
            />
            <DLPair
              label="Payment Terms"
              value={`${inv.payment_terms_days || 45} days from GRN`}
            />
            <DLPair
              label="PO #"
              value={inv.po_number || (inv.po_numbers || []).join(" + ")}
            />
            <DLPair label="Subtotal" value={inr(inv.subtotal || 0)} />
            <DLPair label="IGST" value={inr(inv.igst_amount || 0)} />
            <DLPair label="Grand Total" value={inr(inv.grand_total || 0)} />
            <DLPair
              label="Status"
              value={inv.status?.toUpperCase()}
              highlight={inv.status === "overdue"}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <BalanceTile label="Gross" value={inr(inv.grand_total || 0)} />
            <BalanceTile
              label="Short / Adjusted"
              value={`- ${inr(inv.grn_adjustment || 0)}`}
              accent="#DC2626"
            />
            <BalanceTile
              label="Outstanding"
              value={inr(inv.outstanding || 0)}
              accent="#C27842"
              big
            />
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
                    <td className="px-3 py-1.5 text-right font-mono">
                      {li.quantity}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono">
                      {inr(li.unit_price || 0)}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono font-bold">
                      {inr(li.amount || 0)}
                    </td>
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
                      <div className="font-bold font-mono">
                        {g.grn_no} · {g.grn_date}
                      </div>
                      <div className="text-slate-500 text-[10px]">
                        Ref: {g.client_reference || "—"}
                      </div>
                    </div>
                    <div className="text-right font-mono">
                      <div>
                        Dispatched {g.total_dispatched} → Accepted{" "}
                        {g.total_accepted}{" "}
                        {g.total_rejected > 0 && (
                          <span className="text-red-600">
                            (Rej {g.total_rejected})
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  {g.notes && (
                    <div className="text-xs text-slate-600 mt-1 italic">
                      {g.notes}
                    </div>
                  )}
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
                      <td className="px-3 py-1.5 font-mono font-bold">
                        {p.payment_no}
                      </td>
                      <td className="px-3 py-1.5 font-mono">
                        {p.payment_date}
                      </td>
                      <td className="px-3 py-1.5">{p.mode}</td>
                      <td className="px-3 py-1.5 font-mono text-slate-600">
                        {p.reference || "—"}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono font-bold text-[#16A34A]">
                        {inr(p.allocations?.[inv.id] || p.amount || 0)}
                      </td>
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
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
        {label}
      </div>
      <div className={`font-mono font-bold ${highlight ? "text-red-600" : ""}`}>
        {value || "—"}
      </div>
    </div>
  );
}

function BalanceTile({ label, value, accent = "#0F172A", big = false }) {
  return (
    <div className="border-2 border-slate-200 px-4 py-3 relative">
      <div
        className="text-[10px] uppercase tracking-wider font-bold"
        style={{ color: accent }}
      >
        {label}
      </div>
      <div className={`font-mono font-bold ${big ? "text-2xl" : "text-lg"}`}>
        {value}
      </div>
      <div
        className="absolute left-0 top-0 bottom-0 w-1.5"
        style={{ background: accent }}
      />
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-[0.2em] font-bold text-[#C27842] mb-2 border-b border-slate-200 pb-1">
        {title}
      </h3>
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
      setForm((f) => ({
        ...f,
        lines: (data.line_items_snapshot || []).map((li) => ({
          style_code: li.style_code,
          description: li.description || "",
          color: li.color,
          size: li.size,
          dispatched_qty: li.quantity,
          received_qty: li.quantity,
          accepted_qty: li.quantity,
          rejected_qty: 0,
          rejection_reason: "",
        })),
      }));
    });
  }, [invoiceMeta.id]);

  const updLine = (i, k, v) =>
    setForm((f) => {
      const lines = [...f.lines];
      lines[i] = { ...lines[i], [k]: v };
      if (k === "received_qty" || k === "rejected_qty") {
        const recv = Number(lines[i].received_qty || 0),
          rej = Number(lines[i].rejected_qty || 0);
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
        line_items: form.lines.map((l) => ({
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
    } finally {
      setSaving(false);
    }
  };

  if (!inv) return null;
  const tot = form.lines.reduce((s, l) => s + Number(l.accepted_qty || 0), 0);
  const totDisp = form.lines.reduce(
    (s, l) => s + Number(l.dispatched_qty || 0),
    0,
  );
  const totRej = form.lines.reduce(
    (s, l) => s + Number(l.rejected_qty || 0),
    0,
  );

  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4"
      data-testid="grn-dialog"
    >
      <div className="bg-white w-full max-w-5xl max-h-[92vh] overflow-y-auto border-2 border-slate-200 shadow-2xl">
        <div className="bg-[#7C3AED] text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-90">
              Goods Receipt Note
            </div>
            <div className="text-xl font-bold">
              {invoiceMeta.invoice_no} · {invoiceMeta.client_name}
            </div>
          </div>
          <button onClick={onClose} className="hover:bg-white/20 p-1">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6 space-y-4">
          <div className="bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-slate-700">
            Update the <b>Received qty</b> and <b>Rejected qty</b> per line as
            per the client's confirmation email.{" "}
            <b>Accepted = Received − Rejected</b>. Short / rejected pcs
            auto-reduce the receivable in the ledger.
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">
                GRN Date
              </div>
              <input
                type="date"
                value={form.grn_date}
                onChange={(e) =>
                  setForm((f) => ({ ...f, grn_date: e.target.value }))
                }
                data-testid="grn-date"
                className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#7C3AED] outline-none"
              />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">
                Client reference / email
              </div>
              <input
                value={form.client_reference}
                onChange={(e) =>
                  setForm((f) => ({ ...f, client_reference: e.target.value }))
                }
                placeholder="SIYARAM/GRN/2026/123"
                data-testid="grn-ref"
                className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#7C3AED] outline-none"
              />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">
                Notes
              </div>
              <input
                value={form.notes}
                onChange={(e) =>
                  setForm((f) => ({ ...f, notes: e.target.value }))
                }
                placeholder="Optional notes"
                data-testid="grn-notes"
                className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#7C3AED] outline-none"
              />
            </div>
          </div>

          {form.grn_date && (
            <div className="text-xs bg-purple-50 border border-purple-200 px-3 py-2 text-purple-900 rounded flex items-center justify-between font-mono">
              <span className="flex items-center gap-1.5">
                <span>🗓️</span>
                <span>
                  <b>Payment Due Date:</b>{" "}
                  {(() => {
                    try {
                      const d = new Date(form.grn_date);
                      d.setDate(d.getDate() + (invoiceMeta.payment_terms_days || 45));
                      return d.toISOString().slice(0, 10);
                    } catch {
                      return "—";
                    }
                  })()}{" "}
                  <span className="text-slate-600 font-sans text-[11px]">
                    ({invoiceMeta.payment_terms_days || 45} days credit from GRN Date)
                  </span>
                </span>
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wider bg-purple-200 text-purple-800 px-2 py-0.5 rounded font-sans">
                Payment Clock Starts
              </span>
            </div>
          )}

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
                <tr
                  key={i}
                  className="border-t border-slate-100"
                  data-testid={`grn-line-${i}`}
                >
                  <td className="px-2 py-1.5 font-mono">{l.style_code}</td>
                  <td className="px-2 py-1.5">{l.color}</td>
                  <td className="px-2 py-1.5 font-mono">{l.size}</td>
                  <td className="px-2 py-1.5 text-right font-mono">
                    {l.dispatched_qty}
                  </td>
                  <td className="px-2 py-1">
                    <input
                      type="number"
                      min="0"
                      value={l.received_qty}
                      onChange={(e) =>
                        updLine(i, "received_qty", e.target.value)
                      }
                      data-testid={`grn-recv-${i}`}
                      className="w-20 border border-slate-300 px-2 py-1 font-mono text-right focus:border-[#7C3AED] outline-none"
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      type="number"
                      min="0"
                      value={l.rejected_qty}
                      onChange={(e) =>
                        updLine(i, "rejected_qty", e.target.value)
                      }
                      data-testid={`grn-rej-${i}`}
                      className="w-20 border border-slate-300 px-2 py-1 font-mono text-right focus:border-[#7C3AED] outline-none"
                    />
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono font-bold text-[#16A34A]">
                    {l.accepted_qty}
                  </td>
                  <td className="px-2 py-1">
                    <input
                      value={l.rejection_reason}
                      onChange={(e) =>
                        updLine(i, "rejection_reason", e.target.value)
                      }
                      data-testid={`grn-reason-${i}`}
                      placeholder={l.rejected_qty > 0 ? "Reason required" : ""}
                      className="w-full border border-slate-300 px-2 py-1 text-xs focus:border-[#7C3AED] outline-none"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-slate-900 text-white">
              <tr>
                <td
                  colSpan="3"
                  className="px-2 py-2 font-bold text-[#C27842] uppercase tracking-wider text-[10px]"
                >
                  Totals
                </td>
                <td className="px-2 py-2 text-right font-mono">{totDisp}</td>
                <td className="px-2 py-2 text-right font-mono">
                  {form.lines.reduce(
                    (s, l) => s + Number(l.received_qty || 0),
                    0,
                  )}
                </td>
                <td className="px-2 py-2 text-right font-mono text-red-300">
                  {totRej}
                </td>
                <td className="px-2 py-2 text-right font-mono font-bold">
                  {tot}
                </td>
                <td className="px-2 py-2 text-right text-[10px] uppercase tracking-wider text-slate-300">
                  Short: <b className="text-red-300">{totDisp - tot}</b>
                </td>
              </tr>
            </tfoot>
          </table>

          <div className="flex gap-2 pt-3 border-t border-slate-200">
            <BtnPrimary
              onClick={submit}
              disabled={saving}
              data-testid="grn-submit"
              className="bg-[#7C3AED] border-[#7C3AED] hover:bg-[#5B21B6]"
            >
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
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

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
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4"
      data-testid="payment-dialog"
    >
      <div className="bg-white w-full max-w-2xl border-2 border-slate-200 shadow-2xl">
        <div className="bg-[#16A34A] text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-90">
              Record Payment
            </div>
            <div className="text-xl font-bold">
              {invoiceMeta.invoice_no} · {invoiceMeta.client_name}
            </div>
          </div>
          <button onClick={onClose} className="hover:bg-white/20 p-1">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <BalanceTile
              label="Invoice Total"
              value={inr(invoiceMeta.net_amount || 0)}
            />
            <BalanceTile
              label="Outstanding"
              value={inr(invoiceMeta.outstanding || 0)}
              accent="#C27842"
              big
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Amount received">
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.amount}
                onChange={(e) => set("amount", e.target.value)}
                data-testid="pay-amount"
                className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-lg focus:border-[#16A34A] outline-none"
              />
            </Field>
            <Field label="Payment date">
              <input
                type="date"
                value={form.payment_date}
                onChange={(e) => set("payment_date", e.target.value)}
                data-testid="pay-date"
                className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none"
              />
            </Field>
            <Field label="Mode">
              <select
                value={form.mode}
                onChange={(e) => set("mode", e.target.value)}
                data-testid="pay-mode"
                className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none"
              >
                {PAYMENT_MODES.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Reference (UTR / Cheque #)">
              <input
                value={form.reference}
                onChange={(e) => set("reference", e.target.value)}
                data-testid="pay-ref"
                placeholder="NEFT-UTR-XXXXXXXX"
                className="w-full border-2 border-slate-300 px-3 py-2 font-mono text-sm focus:border-[#16A34A] outline-none"
              />
            </Field>
            <Field label="Bank">
              <input
                value={form.bank}
                onChange={(e) => set("bank", e.target.value)}
                data-testid="pay-bank"
                placeholder="HDFC / ICICI / SBI"
                className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none"
              />
            </Field>
            <Field label="Notes">
              <input
                value={form.notes}
                onChange={(e) => set("notes", e.target.value)}
                data-testid="pay-notes"
                className="w-full border-2 border-slate-300 px-3 py-2 text-sm focus:border-[#16A34A] outline-none"
              />
            </Field>
          </div>

          <div className="flex gap-2 pt-3 border-t border-slate-200">
            <BtnPrimary
              onClick={submit}
              disabled={saving}
              data-testid="pay-submit"
              className="bg-[#16A34A] border-[#16A34A] hover:bg-[#0F7A36]"
            >
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
      <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 mb-1">
        {label}
      </div>
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
      alert(
        "Failed to delete invoice: " +
          (err.response?.data?.detail || err.message),
      );
      setDeleting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 grid place-items-center p-4"
      data-testid="delete-dialog"
    >
      <div className="bg-white w-full max-w-md border-2 border-red-200 shadow-2xl">
        <div className="bg-red-600 text-white px-6 py-4 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold opacity-90">
              Confirm Delete
            </div>
            <div className="text-xl font-bold">{invoice.invoice_no}</div>
          </div>
          <button onClick={onClose} className="hover:bg-white/20 p-1">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6 space-y-4">
          <p className="text-sm text-slate-700">
            Are you sure you want to delete invoice <b>{invoice.invoice_no}</b>?
            This action cannot be undone.
          </p>
          <div className="bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-slate-700">
            <b>Note:</b> This will also delete any associated payments and
            revert the original production jobs back to the "Dispatched" state.
          </div>
          <div className="flex gap-2 pt-4 border-t border-slate-200">
            <BtnPrimary
              onClick={handleDelete}
              disabled={deleting}
              className="bg-red-600 border-red-600 hover:bg-red-700"
            >
              {deleting ? "Deleting…" : "Yes, Delete"}
            </BtnPrimary>
            <BtnSecondary onClick={onClose}>Cancel</BtnSecondary>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------- WEEKLY CASH INFLOW FORECAST WIDGET ------------------- */
function WeeklyCashInflowForecast({ forecast, onSelectInvoice, onRecordGRN }) {
  const [viewMode, setViewMode] = useState("weekly"); // 'weekly' | 'date'
  const [selectedWeekIdx, setSelectedWeekIdx] = useState(() => {
    // default to first non-empty week if available
    const firstActive = (forecast.weeks || []).findIndex((w) => w.total_amount > 0);
    return firstActive !== -1 ? firstActive : 0;
  });
  const [isCollapsed, setIsCollapsed] = useState(false);

  const weeks = forecast.weeks || [];
  const selectedWeek = weeks[selectedWeekIdx] || weeks[0];
  const overdue = forecast.overdue || { total_amount: 0, invoices: [] };
  const awaitingGrn = forecast.awaiting_grn || { total_amount: 0, invoices: [] };
  const byDate = forecast.by_date || [];

  return (
    <Card className="overflow-hidden border-2 border-purple-300 shadow-md" data-testid="cash-inflow-forecast-card">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-purple-950 to-slate-900 text-white px-5 py-4 flex flex-col md:flex-row md:items-center md:justify-between gap-3 border-b border-purple-900/50">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-purple-600/30 border border-purple-400/40 rounded-lg text-purple-300">
            <CalendarDays className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-wide flex items-center gap-2">
                Cash Inflow & Vendor Payment Planning Schedule
              </h2>
              <span className="text-[10px] uppercase font-bold tracking-wider bg-purple-500/30 text-purple-200 border border-purple-400/30 px-2 py-0.5 rounded">
                GRN 45-Day Clock
              </span>
            </div>
            <p className="text-xs text-purple-200/80 mt-0.5">
              Exact weekly dates & expected client receivables so you know when cash arrives and can safely commit vendor payments.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 self-end md:self-auto">
          <div className="flex bg-slate-800/80 p-0.5 rounded border border-slate-700 text-xs">
            <button
              onClick={() => setViewMode("weekly")}
              className={`px-3 py-1 font-semibold rounded transition-colors ${
                viewMode === "weekly"
                  ? "bg-purple-600 text-white"
                  : "text-slate-300 hover:text-white"
              }`}
            >
              Weekly Forecast
            </button>
            <button
              onClick={() => setViewMode("date")}
              className={`px-3 py-1 font-semibold rounded transition-colors ${
                viewMode === "date"
                  ? "bg-purple-600 text-white"
                  : "text-slate-300 hover:text-white"
              }`}
            >
              Exact Date Timeline ({byDate.length})
            </button>
          </div>

          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-800"
            title={isCollapsed ? "Expand" : "Collapse"}
          >
            {isCollapsed ? <ChevronDown className="w-5 h-5" /> : <ChevronUp className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <div className="p-4 sm:p-5 space-y-5 bg-slate-50/50">
          {/* Summary Stats Row */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="bg-white border-2 border-slate-200 p-3 rounded-lg flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">
                  Total Scheduled Inflows
                </div>
                <div className="text-xl font-bold font-mono text-slate-900 mt-0.5">
                  {inr(forecast.total_scheduled || 0)}
                </div>
                <div className="text-[11px] text-[#16A34A] font-semibold mt-0.5 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  GRN verified & locked into 45-day cycle
                </div>
              </div>
              <div className="p-2.5 bg-green-50 rounded-full text-[#16A34A]">
                <IndianRupee className="w-5 h-5" />
              </div>
            </div>

            <div className="bg-white border-2 border-slate-200 p-3 rounded-lg flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">
                  Dispatched · Awaiting GRN
                </div>
                <div className="text-xl font-bold font-mono text-amber-600 mt-0.5">
                  {inr(awaitingGrn.total_amount || 0)}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  {awaitingGrn.invoice_count} invoice{awaitingGrn.invoice_count !== 1 ? "s" : ""} pending client receipt
                </div>
              </div>
              <div className="p-2.5 bg-amber-50 rounded-full text-amber-600">
                <Clock className="w-5 h-5" />
              </div>
            </div>

            <div className="bg-white border-2 border-slate-200 p-3 rounded-lg flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">
                  Total AR Pipeline
                </div>
                <div className="text-xl font-bold font-mono text-[#7C3AED] mt-0.5">
                  {inr(forecast.total_pipeline || 0)}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  Scheduled + Awaiting GRN
                </div>
              </div>
              <div className="p-2.5 bg-purple-50 rounded-full text-[#7C3AED]">
                <TrendingUp className="w-5 h-5" />
              </div>
            </div>
          </div>

          {/* VIEW MODE 1: WEEKLY FORECAST BUCKETS */}
          {viewMode === "weekly" && (
            <div className="space-y-4">
              {/* Weekly Tabs / Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
                {weeks.map((w, idx) => {
                  const isSelected = selectedWeekIdx === idx;
                  const hasAmount = w.total_amount > 0;
                  return (
                    <button
                      key={idx}
                      onClick={() => setSelectedWeekIdx(idx)}
                      className={`text-left p-3 rounded-lg border-2 transition-all flex flex-col justify-between relative ${
                        isSelected
                          ? "bg-purple-900 text-white border-purple-900 shadow-md ring-2 ring-purple-400/50"
                          : hasAmount
                          ? "bg-white border-purple-200 hover:border-purple-400 text-slate-800"
                          : "bg-slate-100/70 border-slate-200 text-slate-400 hover:border-slate-300"
                      }`}
                    >
                      <div>
                        <div className="flex items-center justify-between">
                          <span
                            className={`text-[10px] font-bold uppercase tracking-wider ${
                              isSelected ? "text-purple-200" : hasAmount ? "text-purple-700" : "text-slate-400"
                            }`}
                          >
                            {w.label}
                          </span>
                          {hasAmount && (
                            <span
                              className={`w-2 h-2 rounded-full ${
                                isSelected ? "bg-green-400" : "bg-purple-500"
                              }`}
                            />
                          )}
                        </div>
                        <div className={`text-[10px] font-mono mt-0.5 ${isSelected ? "text-purple-300" : "text-slate-500"}`}>
                          {w.display_range}
                        </div>
                      </div>

                      <div className="mt-3">
                        <div className="font-mono text-sm sm:text-base font-bold truncate">
                          {inr(w.total_amount)}
                        </div>
                        <div className={`text-[10px] ${isSelected ? "text-purple-200" : "text-slate-400"}`}>
                          {w.invoice_count} inv
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Selected Week Detailed Inflow Table & Vendor Promise Recommendation */}
              {selectedWeek && (
                <div className="bg-white border-2 border-purple-200 rounded-lg p-4 space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-200 gap-2">
                    <div>
                      <div className="text-xs uppercase tracking-wider font-bold text-purple-700">
                        {selectedWeek.label} · {selectedWeek.display_range}
                      </div>
                      <div className="text-lg font-bold text-slate-900 mt-0.5">
                        Expected Inflow: <span className="text-purple-700 font-mono">{inr(selectedWeek.total_amount)}</span>{" "}
                        <span className="text-xs font-normal text-slate-500">
                          ({selectedWeek.invoice_count} invoice{selectedWeek.invoice_count !== 1 ? "s" : ""} due)
                        </span>
                      </div>
                    </div>

                    {selectedWeek.total_amount > 0 && (
                      <div className="bg-purple-50 border border-purple-200 px-3 py-1.5 rounded-md text-xs text-purple-900 flex items-center gap-2">
                        <span>🤝</span>
                        <span>
                          <b>Vendor Promise Safe Amount:</b> You can promise up to{" "}
                          <b className="font-mono text-[#16A34A]">{inr(selectedWeek.total_amount)}</b> during this week.
                        </span>
                      </div>
                    )}
                  </div>

                  {selectedWeek.invoices.length === 0 ? (
                    <div className="text-center py-8 text-sm text-slate-400">
                      No client invoices are scheduled to mature during {selectedWeek.label} ({selectedWeek.display_range}).
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase text-[10px] tracking-wider">
                          <tr>
                            <th className="px-3 py-2 text-left font-bold">Expected Inflow Date</th>
                            <th className="px-3 py-2 text-left font-bold">Timeline</th>
                            <th className="px-3 py-2 text-left font-bold">Invoice #</th>
                            <th className="px-3 py-2 text-left font-bold">Client Name</th>
                            <th className="px-3 py-2 text-left font-bold">GRN Date</th>
                            <th className="px-3 py-2 text-right font-bold">Expected Cash Inflow</th>
                            <th className="px-3 py-2 text-left font-bold">Vendor Payment Recommendation</th>
                            <th className="px-3 py-2 text-right font-bold">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {selectedWeek.invoices.map((inv, i) => (
                            <tr key={i} className="hover:bg-purple-50/40">
                              <td className="px-3 py-2 font-mono font-bold text-slate-900">
                                {inv.due_date}
                              </td>
                              <td className="px-3 py-2">
                                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                                  inv.days_to_due < 0
                                    ? "bg-red-100 text-red-700"
                                    : inv.days_to_due <= 7
                                    ? "bg-amber-100 text-amber-800"
                                    : "bg-slate-100 text-slate-700"
                                }`}>
                                  {inv.days_to_due < 0
                                    ? `${-inv.days_to_due}d overdue`
                                    : `in ${inv.days_to_due} days`}
                                </span>
                              </td>
                              <td className="px-3 py-2 font-mono font-bold text-purple-700">
                                {inv.invoice_no}
                              </td>
                              <td className="px-3 py-2 font-medium text-slate-800">
                                {inv.client_name}
                              </td>
                              <td className="px-3 py-2 font-mono text-slate-600">
                                <span className="bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded border border-purple-200">
                                  {inv.grn_date} (+45d)
                                </span>
                              </td>
                              <td className="px-3 py-2 text-right font-mono font-bold text-[#16A34A] text-sm">
                                {inr(inv.outstanding)}
                              </td>
                              <td className="px-3 py-2 text-[11px] text-slate-600">
                                Safe to promise vendors on or after <b>{inv.due_date}</b>
                              </td>
                              <td className="px-3 py-2 text-right">
                                <button
                                  onClick={() => onSelectInvoice(inv.id)}
                                  className="text-slate-500 hover:text-purple-700 p-1"
                                  title="View Invoice"
                                >
                                  <Eye className="w-4 h-4" />
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                        <tfoot className="bg-purple-50/70 border-t border-purple-200 font-bold">
                          <tr>
                            <td colSpan="5" className="px-3 py-2 text-purple-900 uppercase text-[10px] tracking-wider">
                              Week Total Inflow
                            </td>
                            <td className="px-3 py-2 text-right font-mono text-purple-900 text-sm">
                              {inr(selectedWeek.total_amount)}
                            </td>
                            <td colSpan="2" className="px-3 py-2 text-[10px] text-purple-700">
                              Available for supplier payments
                            </td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* VIEW MODE 2: EXACT DATE TIMELINE */}
          {viewMode === "date" && (
            <div className="bg-white border-2 border-purple-200 rounded-lg p-4 space-y-4">
              <div className="text-xs uppercase tracking-wider font-bold text-purple-700 border-b border-slate-200 pb-2 flex items-center justify-between">
                <span>Exact Due Dates & Inflow Amounts</span>
                <span className="text-slate-500 font-normal">Sorted chronologically by GRN maturity date</span>
              </div>

              {byDate.length === 0 ? (
                <div className="text-center py-8 text-sm text-slate-400">
                  No scheduled due dates available. Record GRNs for pending invoices to populate the timeline.
                </div>
              ) : (
                <div className="space-y-3">
                  {byDate.map((group, idx) => (
                    <div key={idx} className="border-2 border-slate-200 rounded-lg overflow-hidden hover:border-purple-300 transition-colors">
                      <div className="bg-slate-50 px-4 py-2.5 flex items-center justify-between border-b border-slate-200">
                        <div className="flex items-center gap-3">
                          <div className="p-1.5 bg-purple-100 text-purple-700 rounded font-mono font-bold text-xs">
                            {group.date}
                          </div>
                          <div>
                            <span className="font-bold text-slate-900 text-sm">{group.formatted_date}</span>
                            <span className="text-xs text-slate-500 ml-2">
                              ({group.days_to_go < 0 ? `${-group.days_to_go} days overdue` : `in ${group.days_to_go} days`})
                            </span>
                          </div>
                        </div>

                        <div className="text-right">
                          <span className="text-[10px] uppercase font-bold text-slate-500 mr-2">Inflow On This Date:</span>
                          <span className="font-mono font-bold text-base text-[#16A34A]">
                            {inr(group.total_amount)}
                          </span>
                        </div>
                      </div>

                      <div className="p-3 bg-white">
                        <div className="text-[11px] text-slate-600 mb-2 flex items-center gap-1.5">
                          <Coins className="w-3.5 h-3.5 text-purple-600" />
                          <span>
                            <b>Vendor Payment Promise:</b> You will receive <b>{inr(group.total_amount)}</b> from{" "}
                            {group.invoices.map((i) => i.client_name).join(", ")}. You can promise vendors payment for{" "}
                            <b>{group.formatted_date}</b>.
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                          {group.invoices.map((inv, invIdx) => (
                            <div
                              key={invIdx}
                              onClick={() => onSelectInvoice(inv.id)}
                              className="p-2.5 rounded border border-slate-200 bg-slate-50/50 hover:bg-purple-50 hover:border-purple-300 cursor-pointer flex items-center justify-between"
                            >
                              <div>
                                <div className="font-mono font-bold text-purple-700 text-xs">{inv.invoice_no}</div>
                                <div className="text-[11px] text-slate-600 truncate max-w-[180px]">{inv.client_name}</div>
                                <div className="text-[10px] text-slate-400 font-mono">GRN: {inv.grn_date}</div>
                              </div>
                              <div className="text-right font-mono font-bold text-xs text-[#16A34A]">
                                {inr(inv.outstanding)}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* AWAITING GRN UNSCHEDULED SECTION */}
          {awaitingGrn.invoices.length > 0 && (
            <div className="bg-amber-50/80 border border-amber-200 rounded-lg p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div className="flex items-start gap-2.5">
                <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-bold text-amber-900">
                    {awaitingGrn.invoices.length} Dispatched Invoice{awaitingGrn.invoices.length !== 1 ? "s" : ""} ({inr(awaitingGrn.total_amount)}) Awaiting GRN
                  </div>
                  <div className="text-[11px] text-amber-800/80 mt-0.5">
                    As soon as you enter the GRN date from the client's confirmation email, their 45-day payment due date will automatically appear in the weekly schedule above.
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                {awaitingGrn.invoices.slice(0, 3).map((inv, idx) => (
                  <button
                    key={idx}
                    onClick={() => onRecordGRN(inv)}
                    className="px-2.5 py-1 text-[11px] bg-white border border-amber-300 hover:bg-amber-100 text-amber-900 rounded font-mono flex items-center gap-1"
                  >
                    <ClipboardCheck className="w-3.5 h-3.5 text-amber-700" />
                    Record GRN: {inv.invoice_no}
                  </button>
                ))}
                {awaitingGrn.invoices.length > 3 && (
                  <span className="text-[11px] text-amber-700 font-semibold px-1">
                    +{awaitingGrn.invoices.length - 3} more
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
