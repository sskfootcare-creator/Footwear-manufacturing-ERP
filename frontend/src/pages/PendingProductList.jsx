import { useEffect, useMemo, useState } from "react";
import { http, friendlyAxiosError } from "../lib/api";
import { PageHeader, Card, BtnPrimary, BtnSecondary, Badge, Input } from "../components/ui-kit";
import { SafeImage } from "../components/ImageUploader";
import { Printer, RefreshCw, AlertTriangle, CheckCircle2, X, Wrench, Loader2 } from "lucide-react";

/**
 * Groups pending production jobs into a (style_code, color) matrix so that
 * the same style ordered by many buyers on many sizes shows as ONE row with
 * quantities laid out across sizes — matching the Production Card / Picklist
 * layout for consistency and print-readability.
 */
function useMatrix(rows) {
  return useMemo(() => {
    if (!rows || rows.length === 0) return { groups: [], allSizes: [] };
    const map = {};
    for (const r of rows) {
      const key = `${r.style_code || "—"}||${r.color || "—"}`;
      if (!map[key]) {
        map[key] = {
          style_id:             r.style_id || "",
          style_code:           r.style_code || "—",
          style_name:           r.style_name || "",
          color:                r.color || "—",
          image_url:            r.image_url || "",
          image_display_url:    r.image_display_url || "",
          image_thumbnail_url:  r.image_thumbnail_url || "",
          sizes:                {},         // size → { qty, jobs: [], components_available }
          total:                0,
          any_shortage:         false,
          shortages:            [],
          orders:               new Set(), // distinct PO/order numbers
        };
      }
      const g = map[key];
      const sz = String(r.size || "—");
      // Show the REMAINING pending count (raw quantity - completed_qty), not
      // the original qty — otherwise cells appear "still open" after produce.
      const pending = Math.max(0, Number(r.quantity || 0) - Number(r.completed_qty || 0));
      if (pending <= 0) continue;
      if (!g.sizes[sz]) g.sizes[sz] = { qty: 0, jobs: 0, ready: true };
      g.sizes[sz].qty  += pending;
      g.sizes[sz].jobs += 1;
      if (!r.components_available) {
        g.sizes[sz].ready = false;
        g.any_shortage     = true;
        (r.component_shortages || []).forEach((s) => {
          const k = `${s.component_code}||${s.component_name}`;
          if (!g.shortages.some((x) => `${x.component_code}||${x.component_name}` === k)) {
            g.shortages.push(s);
          }
        });
      }
      g.total += pending;
      if (r.po_number) g.orders.add(r.po_number);
    }
    const groups = Object.values(map)
      .filter((g) => g.total > 0)                          // hide fully-produced groups
      .map((g) => ({ ...g, orders: [...g.orders] }))
      .sort((a, b) => {
        // Rows with any shortage bubble to the top for attention
        if (a.any_shortage !== b.any_shortage) return a.any_shortage ? -1 : 1;
        return (a.style_code || "").localeCompare(b.style_code || "");
      });
    const allSizesSet = new Set();
    groups.forEach((g) => Object.keys(g.sizes).forEach((s) => allSizesSet.add(s)));
    const allSizes = [...allSizesSet].sort((a, b) => {
      const na = parseFloat(a), nb = parseFloat(b);
      if (!isNaN(na) && !isNaN(nb)) return na - nb;
      return String(a).localeCompare(String(b));
    });
    return { groups, allSizes };
  }, [rows]);
}

export default function PendingProductList() {
  const [rows, setRows]     = useState([]);
  const [loading, setLoad]  = useState(false);
  const [err, setErr]       = useState("");
  const [filter, setFilter] = useState("all"); // all | available | shortage

  // Produce-cell drawer state (opened when operator taps a size cell)
  const [produceCtx, setProduceCtx] = useState(null); // {style_id, style_code, style_name, color, size, pending, image}

  async function load() {
    setLoad(true); setErr("");
    try {
      const r = await http.get("/production/pending-list");
      setRows(r.data);
    } catch (e) { setErr(friendlyAxiosError(e)); }
    finally { setLoad(false); }
  }
  useEffect(() => { load(); }, []);

  const filtered = rows.filter((r) => {
    if (filter === "available") return r.components_available;
    if (filter === "shortage")  return !r.components_available;
    return true;
  });

  const totals = {
    total:     rows.length,
    available: rows.filter((r) => r.components_available).length,
    shortage:  rows.filter((r) => !r.components_available).length,
    pairs:     rows.reduce((s, r) => s + (r.quantity || 0), 0),
  };

  const { groups, allSizes } = useMatrix(filtered);

  return (
    <div data-testid="page-pending-list" className="print:bg-white">
      {/* Screen header (hidden on print) */}
      <div className="print:hidden">
        <PageHeader
          title="Pending Product List"
          subtitle="Production / Online orders awaiting manufacture"
          testId="pending-list-header"
          action={
            <div className="flex gap-2">
              <BtnSecondary onClick={load} disabled={loading} data-testid="pending-refresh-btn">
                <RefreshCw className={`w-3.5 h-3.5 inline mr-1 ${loading ? "animate-spin" : ""}`} />Refresh
              </BtnSecondary>
              <BtnSecondary onClick={() => window.print()} data-testid="pending-print-btn">
                <Printer className="w-3.5 h-3.5 inline mr-1" />Print
              </BtnSecondary>
            </div>
          }
        />
      </div>

      {/* Print header */}
      <div className="hidden print:block px-6 py-4 border-b-2 border-slate-900">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs uppercase tracking-widest text-slate-500">SSK Footcare · Production</div>
            <h1 className="text-2xl font-black">Pending Product List</h1>
          </div>
          <div className="text-right text-xs text-slate-600">
            <div>Generated: <strong>{new Date().toLocaleString()}</strong></div>
            <div>Total groups: <strong>{groups.length}</strong> · Total pairs: <strong>{totals.pairs.toLocaleString()}</strong></div>
          </div>
        </div>
      </div>

      <div className="p-4 sm:p-6 space-y-4 print:p-6 print:space-y-3">
        {err && <div className="p-3 bg-red-50 border-2 border-red-300 text-red-800 text-sm print:hidden">{err}</div>}

        {/* Summary tiles (screen only) */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 print:hidden">
          <Card className="p-4">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Total Pending</div>
            <div className="text-3xl font-black mt-1">{totals.total}</div>
            <div className="text-xs text-slate-500 mt-1">jobs</div>
          </Card>
          <Card className="p-4 border-green-300">
            <div className="text-[10px] uppercase tracking-wider font-bold text-green-700">Ready to Produce</div>
            <div className="text-3xl font-black mt-1 text-green-800">{totals.available}</div>
            <div className="text-xs text-slate-500 mt-1">components available</div>
          </Card>
          <Card className="p-4 border-red-300">
            <div className="text-[10px] uppercase tracking-wider font-bold text-red-700">Awaiting Components</div>
            <div className="text-3xl font-black mt-1 text-red-800">{totals.shortage}</div>
            <div className="text-xs text-slate-500 mt-1">component shortage</div>
          </Card>
          <Card className="p-4">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">Total Pairs</div>
            <div className="text-3xl font-black mt-1">{totals.pairs.toLocaleString()}</div>
            <div className="text-xs text-slate-500 mt-1">to manufacture</div>
          </Card>
        </div>

        {/* Filter tabs (screen only) */}
        <div className="flex gap-2 print:hidden">
          <BtnSecondary onClick={() => setFilter("all")}       className={filter === "all"       ? "bg-slate-900 text-white border-slate-900" : ""} data-testid="filter-all">All ({totals.total})</BtnSecondary>
          <BtnSecondary onClick={() => setFilter("available")} className={filter === "available" ? "bg-green-700 text-white border-green-700" : ""} data-testid="filter-available">Ready ({totals.available})</BtnSecondary>
          <BtnSecondary onClick={() => setFilter("shortage")}  className={filter === "shortage"  ? "bg-red-700 text-white border-red-700"    : ""} data-testid="filter-shortage">Shortage ({totals.shortage})</BtnSecondary>
        </div>

        {groups.length === 0 && (
          <div className="text-center text-slate-500 py-12">
            <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-green-500" />
            No pending production jobs.
          </div>
        )}

        {/* Matrix cards — same layout on screen AND print, print-friendly by default */}
        <div className="space-y-3">
          {groups.map((g, gi) => (
            <div
              key={gi}
              className={`border-2 break-inside-avoid print:shadow-none ${
                g.any_shortage ? "border-red-500" : "border-slate-900"
              } bg-white`}
              data-testid={`pending-group-${g.style_code}-${g.color}`}
            >
              <div className="flex items-stretch">
                {/* Product image */}
                <div className="w-28 flex-shrink-0 border-r-2 border-slate-900 bg-slate-50 flex items-center justify-center print:w-24">
                  <SafeImage
                    image={{
                      url: g.image_url,
                      display_url: g.image_display_url,
                      thumbnail_url: g.image_thumbnail_url,
                    }}
                    alt={g.style_code}
                    aspectRatio="1/1"
                    className="w-full"
                  />
                </div>
                {/* Header + matrix */}
                <div className="flex-1 min-w-0">
                  <div className="px-3 py-2 border-b-2 border-slate-900 bg-slate-100 flex items-baseline justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-mono font-black text-base truncate">{g.style_code}</div>
                      {g.style_name && <div className="text-[10px] text-slate-600 truncate">{g.style_name}</div>}
                      <div className="text-[11px] font-bold uppercase tracking-wider">Color: <span className="font-mono">{g.color}</span></div>
                      {g.orders.length > 0 && (
                        <div className="text-[9px] text-slate-500 truncate">
                          Orders: {g.orders.slice(0, 4).join(", ")}
                          {g.orders.length > 4 ? ` +${g.orders.length - 4} more` : ""}
                        </div>
                      )}
                    </div>
                    <div className="text-right flex-shrink-0">
                      <div className="text-[9px] uppercase text-slate-500">Group Total</div>
                      <div className="text-2xl font-black font-mono">{g.total}</div>
                      <div className="text-[9px] uppercase text-slate-500">pairs</div>
                      {g.any_shortage ? (
                        <Badge color="red" className="print:border print:bg-white print:text-red-700">
                          <AlertTriangle className="w-3 h-3 inline mr-0.5" /> Shortage
                        </Badge>
                      ) : (
                        <Badge color="green" className="print:border print:bg-white print:text-green-800">Ready</Badge>
                      )}
                    </div>
                  </div>
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr className="bg-slate-50">
                        <th className="border border-slate-400 px-2 py-1 text-left w-16">Size</th>
                        {allSizes.map((sz) => (
                          <th key={sz} className="border border-slate-400 px-1 py-1 text-center font-mono">{sz}</th>
                        ))}
                        <th className="border border-slate-400 px-2 py-1 text-center bg-slate-200 w-16">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td className="border border-slate-400 px-2 py-1 font-bold uppercase text-[10px]">Qty</td>
                        {allSizes.map((sz) => {
                          const cell = g.sizes[sz];
                          return (
                            <td
                              key={sz}
                              className={`border border-slate-400 px-1 py-1 text-center font-mono font-bold ${
                                cell
                                  ? cell.ready
                                    ? "bg-white text-slate-900"
                                    : "bg-red-50 text-red-800"
                                  : "bg-slate-50 text-slate-300"
                              }`}
                            >
                              {cell ? cell.qty : "·"}
                            </td>
                          );
                        })}
                        <td className="border border-slate-400 px-2 py-1 text-center bg-slate-100 font-black font-mono text-base">{g.total}</td>
                      </tr>
                      <tr>
                        <td className="border border-slate-400 px-2 py-1 font-bold uppercase text-[10px]">Made</td>
                        {allSizes.map((sz) => {
                          const cell = g.sizes[sz];
                          return (
                            <td key={sz} className="border border-slate-400 px-1 py-1 text-center">
                              {cell ? (
                                <button
                                  type="button"
                                  data-testid={`made-cell-${g.style_code}-${g.color}-${sz}`}
                                  onClick={() => setProduceCtx({
                                    style_id:   g.style_id,
                                    style_code: g.style_code,
                                    style_name: g.style_name,
                                    color:      g.color,
                                    size:       sz,
                                    pending:    cell.qty,
                                    image:      {
                                      url: g.image_url,
                                      display_url: g.image_display_url,
                                      thumbnail_url: g.image_thumbnail_url,
                                    },
                                  })}
                                  className="border-2 border-slate-500 w-6 h-6 hover:bg-emerald-100 hover:border-emerald-600 active:bg-emerald-200 transition-colors mx-auto flex items-center justify-center print:cursor-default print:hover:bg-transparent"
                                  title={`Record production for ${g.style_code} · ${g.color} · Size ${sz}`}
                                />
                              ) : (
                                <div className="border border-slate-200 w-5 h-5 mx-auto" />
                              )}
                            </td>
                          );
                        })}
                        <td className="border border-slate-400 px-2 py-1 text-center">
                          <div className="border-2 border-slate-900 w-6 h-6 mx-auto" title="All done" />
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  {g.any_shortage && g.shortages.length > 0 && (
                    <div className="px-3 py-1.5 bg-red-50 border-t-2 border-red-500 text-[10px] text-red-800">
                      <span className="font-bold uppercase tracking-wider">Missing components:</span>{" "}
                      {g.shortages.slice(0, 4).map((s, i) => (
                        <span key={i} className="mr-2">
                          {s.component_code} · {s.component_name} (avail {s.available})
                          {i < Math.min(3, g.shortages.length - 1) ? "," : ""}
                        </span>
                      ))}
                      {g.shortages.length > 4 && <span>+{g.shortages.length - 4} more…</span>}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Print footer */}
        <div className="hidden print:flex justify-between text-xs text-slate-500 border-t border-slate-300 pt-2 mt-6">
          <span>Prepared by: __________________________</span>
          <span>Verified by: __________________________</span>
          <span>Date: __________</span>
        </div>
      </div>

      {produceCtx && (
        <ProduceCellDrawer
          ctx={produceCtx}
          onClose={() => setProduceCtx(null)}
          onDone={() => { setProduceCtx(null); load(); }}
        />
      )}
    </div>
  );
}


/* ────────────────────────────────────────────────────────────────
   ProduceCellDrawer — opens when the operator clicks a Made cell.
   Handles: produced-all / short (reason mandatory) / over (excess auto-
   lands in the style's allotted rack), and prompts to create a production
   card (BOM) if the style has none mapped yet.
   ──────────────────────────────────────────────────────────────── */
function ProduceCellDrawer({ ctx, onClose, onDone }) {
  const [producedQty, setProducedQty] = useState(ctx.pending);
  const [reason, setReason]           = useState("");
  const [useComponents, setUseComp]   = useState(true);
  const [busy, setBusy]               = useState(false);
  const [err, setErr]                 = useState("");
  const [result, setResult]           = useState(null);
  const [needCard, setNeedCard]       = useState(false);

  const isShort = producedQty < ctx.pending;
  const isOver  = producedQty > ctx.pending;

  const submit = async (force = false) => {
    setErr(""); setBusy(true); setResult(null);
    try {
      if (isShort && !reason.trim()) {
        setErr("Short production must include a reason.");
        setBusy(false);
        return;
      }
      const { data } = await http.post("/production/produce-cell", {
        style_id:              ctx.style_id,
        color:                 ctx.color,
        size:                  ctx.size,
        produced_qty:          Number(producedQty),
        reason:                reason.trim(),
        use_components:        useComponents,
        channel_filter:        "online_channel",
        force_negative_stock:  force,
      });
      setResult(data);
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.code === "no_production_card") {
        setNeedCard(true);
      } else if (detail && typeof detail === "object" && detail.code === "component_shortage") {
        // Ask the operator to explicitly opt into negative stock.
        const parts = (detail.shortages || []).map(
          (s) => `${s.component_code} (need ${s.needed}, have ${s.available}, short ${s.shortfall})`
        ).join("\n");
        if (window.confirm(
          "Component shortage — the following will go below zero:\n\n" + parts +
          "\n\nProceed anyway? Stock will go negative and remain flagged in the ledger."
        )) {
          submit(true);
          return;
        }
      } else {
        setErr(friendlyAxiosError(e));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-0 sm:p-4" onClick={onClose}>
      <div
        className="bg-white w-full sm:max-w-lg border-2 border-slate-900 shadow-ind-lg print:hidden"
        onClick={(e) => e.stopPropagation()}
        data-testid="produce-cell-drawer"
      >
        <div className="px-5 py-4 border-b-2 border-slate-900 bg-slate-50 flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <SafeImage image={ctx.image} alt={ctx.style_code} aspectRatio="1/1" className="w-14 h-14 flex-shrink-0" />
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Record Production</div>
              <div className="font-mono font-black text-lg truncate">{ctx.style_code}</div>
              <div className="text-xs text-slate-600 truncate">
                {ctx.style_name && <>{ctx.style_name} · </>}
                Color <span className="font-mono font-bold">{ctx.color}</span> ·
                Size <span className="font-mono font-bold">{ctx.size}</span> ·
                Pending <span className="font-mono font-bold">{ctx.pending}</span>
              </div>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-900 text-xl font-bold" data-testid="produce-close">
            <X className="w-5 h-5" />
          </button>
        </div>

        {result ? (
          <div className="p-5 space-y-3" data-testid="produce-result">
            <div className="p-3 border-2 border-emerald-500 bg-emerald-50 text-emerald-900">
              <div className="font-bold flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4" /> Recorded
              </div>
              <div className="text-xs mt-1 space-y-0.5">
                <div>Produced <strong>{result.produced}</strong> of pending <strong>{result.pending_before}</strong> pairs.</div>
                {result.shortfall > 0 && <div className="text-red-800">Shortfall: <strong>{result.shortfall}</strong> pairs · logged with reason.</div>}
                {result.excess > 0 && <div className="text-blue-800">Excess: <strong>{result.excess}</strong> pairs placed at <strong className="font-mono">{result.excess_placed_at}</strong>.</div>}
                {result.bom_components_used?.length > 0 && (
                  <div>Components deducted: {result.bom_components_used.map(c => `${c.component_code} (-${c.deducted}, ${c.new_stock} left)`).join(", ")}</div>
                )}
                <div>Production jobs updated: <strong>{result.jobs_updated}</strong></div>
              </div>
            </div>
            <div className="flex justify-end">
              <BtnPrimary onClick={onDone} data-testid="produce-done">Done</BtnPrimary>
            </div>
          </div>
        ) : needCard ? (
          <NoProductionCardPrompt
            styleId={ctx.style_id}
            styleCode={ctx.style_code}
            onCancel={() => setNeedCard(false)}
            onCreated={() => { setNeedCard(false); submit(); }}
            onSkipComponents={() => { setNeedCard(false); setUseComp(false); }}
          />
        ) : (
          <div className="p-5 space-y-4">
            {/* Big produced-qty stepper */}
            <div className="text-center">
              <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-1">Pairs produced</div>
              <div className="flex items-center justify-center gap-2">
                <button onClick={() => setProducedQty(Math.max(1, Number(producedQty) - 1))}
                        className="w-10 h-10 border-2 border-slate-300 hover:border-slate-900 text-lg font-bold"
                        data-testid="produce-minus">−</button>
                <input
                  type="number"
                  value={producedQty}
                  onChange={(e) => setProducedQty(Math.max(0, Number(e.target.value)))}
                  className="w-24 border-2 border-slate-300 px-2 py-2 text-center font-mono font-black text-2xl"
                  data-testid="produce-qty-input"
                />
                <button onClick={() => setProducedQty(Number(producedQty) + 1)}
                        className="w-10 h-10 border-2 border-slate-300 hover:border-slate-900 text-lg font-bold"
                        data-testid="produce-plus">+</button>
              </div>
              <div className="mt-2 flex justify-center gap-2 flex-wrap">
                <button onClick={() => setProducedQty(ctx.pending)}
                        className="text-[10px] uppercase tracking-wider font-bold px-2 py-1 border border-slate-300 hover:border-slate-900"
                        data-testid="produce-preset-all">Produced all ({ctx.pending})</button>
                <button onClick={() => setProducedQty(Math.max(1, Math.floor(ctx.pending / 2)))}
                        className="text-[10px] uppercase tracking-wider font-bold px-2 py-1 border border-slate-300 hover:border-slate-900">Half</button>
              </div>
            </div>

            {/* Delta hint */}
            {(isShort || isOver) && (
              <div className={`p-2 border-2 text-xs ${isShort ? "border-red-300 bg-red-50 text-red-900" : "border-blue-300 bg-blue-50 text-blue-900"}`}>
                {isShort
                  ? <>Short by <strong>{ctx.pending - producedQty}</strong> pairs — this shortfall stays on the pending list. Reason required below.</>
                  : <>Excess of <strong>{producedQty - ctx.pending}</strong> pairs → auto-added to this style&apos;s allotted rack (or first empty cell if none).</>}
              </div>
            )}

            {isShort && (
              <div>
                <label className="text-xs uppercase tracking-wider font-bold text-slate-600">Reason for short production *</label>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={2}
                  placeholder="e.g. Sole supplier delay; Karigar leave; Rework batch"
                  className="w-full mt-1 border-2 border-slate-300 px-3 py-2 text-sm focus:border-red-500 focus:outline-none"
                  data-testid="produce-reason"
                />
              </div>
            )}

            {/* Component consumption toggle */}
            <label className="flex items-start gap-2 cursor-pointer text-xs">
              <input
                type="checkbox"
                checked={useComponents}
                onChange={(e) => setUseComp(e.target.checked)}
                className="mt-0.5"
                data-testid="produce-use-components"
              />
              <span>
                <span className="font-bold uppercase tracking-wider">Deduct from Component Inventory</span>
                <br />
                <span className="text-slate-500">Uncheck if this batch is produced directly from raw material without pre-made components. When checked, the style must have a production card (BOM).</span>
              </span>
            </label>

            {err && (
              <div className="p-2 border-2 border-red-300 bg-red-50 text-red-900 text-xs" data-testid="produce-error">{err}</div>
            )}

            <div className="flex gap-2 pt-1">
              <BtnSecondary onClick={onClose} className="flex-1">Cancel</BtnSecondary>
              <BtnPrimary onClick={submit} disabled={busy || producedQty <= 0} className="flex-1" data-testid="produce-submit">
                {busy && <Loader2 className="w-3.5 h-3.5 inline mr-1 animate-spin" />}
                Confirm Production
              </BtnPrimary>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


/* Sub-drawer shown when the style has no BOM yet. Loads components list,
   lets the operator pick which ones this style consumes + qty-per-pair, and
   POSTs a new production card. */
function NoProductionCardPrompt({ styleId, styleCode, onCancel, onCreated, onSkipComponents }) {
  const [components, setComponents] = useState([]);
  const [picks, setPicks]           = useState([{ component_id: "", quantity_per_pair: 1, wastage_percent: 5 }]);
  const [busy, setBusy]             = useState(false);
  const [err, setErr]               = useState("");

  useEffect(() => {
    (async () => {
      try {
        const r = await http.get("/components");
        setComponents(r.data);
      } catch (e) {
        setErr(friendlyAxiosError(e));
      }
    })();
  }, []);

  const updatePick = (i, k, v) => setPicks(prev => prev.map((p, idx) => idx === i ? { ...p, [k]: v } : p));
  const addPick    = () => setPicks(prev => [...prev, { component_id: "", quantity_per_pair: 1, wastage_percent: 5 }]);
  const removePick = (i) => setPicks(prev => prev.filter((_, idx) => idx !== i));

  const save = async () => {
    setErr(""); setBusy(true);
    try {
      const cleaned = picks.filter(p => p.component_id).map(p => ({
        component_id:      p.component_id,
        quantity_per_pair: Number(p.quantity_per_pair) || 1,
        wastage_percent:   Number(p.wastage_percent)   || 0,
      }));
      if (cleaned.length === 0) {
        setErr("Add at least one component or skip components below.");
        setBusy(false);
        return;
      }
      await http.post("/production/production-card", { style_id: styleId, components: cleaned });
      onCreated();
    } catch (e) {
      setErr(friendlyAxiosError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-5 space-y-4" data-testid="production-card-prompt">
      <div className="p-3 border-2 border-amber-300 bg-amber-50 text-amber-900 text-xs">
        <div className="font-bold uppercase tracking-wider flex items-center gap-1">
          <Wrench className="w-3.5 h-3.5" /> No production card for {styleCode}
        </div>
        <div className="mt-1">
          Map the components this style consumes per pair. We&apos;ll remember these picks and auto-deduct them from Component Inventory on every future production for {styleCode}.
        </div>
      </div>

      {picks.map((p, i) => (
        <div key={i} className="grid grid-cols-12 gap-2 items-end" data-testid={`bom-row-${i}`}>
          <div className="col-span-6">
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Component</label>
            <select
              value={p.component_id}
              onChange={(e) => updatePick(i, "component_id", e.target.value)}
              className="w-full mt-0.5 border-2 border-slate-300 px-2 py-1.5 text-xs font-mono"
              data-testid={`bom-row-${i}-component`}
            >
              <option value="">— pick component —</option>
              {components.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.component_code} · {c.component_name}{c.color ? ` (${c.color})` : ""} · stock {c.current_stock}
                </option>
              ))}
            </select>
          </div>
          <div className="col-span-3">
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Qty / pair</label>
            <input
              type="number"
              step="0.01"
              value={p.quantity_per_pair}
              onChange={(e) => updatePick(i, "quantity_per_pair", e.target.value)}
              className="w-full mt-0.5 border-2 border-slate-300 px-2 py-1.5 text-xs font-mono text-right"
            />
          </div>
          <div className="col-span-2">
            <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Waste %</label>
            <input
              type="number"
              step="0.1"
              value={p.wastage_percent}
              onChange={(e) => updatePick(i, "wastage_percent", e.target.value)}
              className="w-full mt-0.5 border-2 border-slate-300 px-2 py-1.5 text-xs font-mono text-right"
            />
          </div>
          <div className="col-span-1 flex items-end justify-center">
            {picks.length > 1 && (
              <button onClick={() => removePick(i)} className="text-slate-500 hover:text-red-600 h-8" title="Remove">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      ))}
      <button onClick={addPick} className="text-xs font-bold uppercase tracking-wider text-[#2563EB]">+ Add component</button>

      {err && (<div className="p-2 border-2 border-red-300 bg-red-50 text-red-900 text-xs">{err}</div>)}

      <div className="flex gap-2 pt-1">
        <BtnSecondary onClick={onCancel} className="flex-1">Back</BtnSecondary>
        <BtnSecondary onClick={onSkipComponents} className="flex-1" data-testid="bom-skip">Skip · Use raw material</BtnSecondary>
        <BtnPrimary onClick={save} disabled={busy} className="flex-1" data-testid="bom-save">
          {busy ? "Saving…" : "Save & Produce"}
        </BtnPrimary>
      </div>
    </div>
  );
}
