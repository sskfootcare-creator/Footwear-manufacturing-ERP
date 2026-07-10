import { useEffect, useState } from "react";
import { http, friendlyAxiosError } from "../lib/api";
import { BtnPrimary, BtnSecondary } from "./ui-kit";
import { SafeImage } from "./ImageUploader";
import { X, Loader2, Wrench, Package, AlertTriangle, CheckCircle2 } from "lucide-react";

/* ────────────────────────────────────────────────────────────
   AdHocProduceDrawer — color × size matrix. Operators can produce
   many (color, size) combinations for one style in a single pass —
   mirroring the Production Card + Pending List layout. Each non-zero
   cell → one POST /production/produce-cell call. Result summary
   surfaces per-cell success/error.
   ──────────────────────────────────────────────────────────────── */
export default function AdHocProduceDrawer({ style, hasBom, onClose, onEditBom, onDone }) {
  const [colors, setColors]     = useState([]);
  const [sizes, setSizes]       = useState([]);
  const [qty, setQty]           = useState({});         // key `${c}||${s}` → number
  const [newColor, setNewColor] = useState("");
  const [newSize, setNewSize]   = useState("");
  const [useComponents, setUseComp] = useState(hasBom);
  const [busy, setBusy]         = useState(false);
  const [err, setErr]           = useState("");
  const [results, setResults]   = useState(null);
  const [feasibility, setFeasibility] = useState(null); // {feasible, components, missing_bom, pairs}
  const [shortageConfirm, setShortageConfirm] = useState(null); // { shortages, onConfirm }

  // Prefill the matrix from any variants this style has been produced/stored in.
  useEffect(() => {
    (async () => {
      try {
        const r = await http.get(`/production/style-variants/${style.id}`);
        setColors(r.data?.colors?.length ? r.data.colors : []);
        setSizes(r.data?.sizes?.length   ? r.data.sizes   : []);
      } catch {
        setColors([]); setSizes([]);
      }
    })();
  }, [style.id]);

  const cellKey = (c, s) => `${c}||${s}`;
  const setCell = (c, s, v) =>
    setQty((prev) => ({ ...prev, [cellKey(c, s)]: Math.max(0, Number(v) || 0) }));
  const cellVal = (c, s) => Number(qty[cellKey(c, s)] || 0);

  const rowTotal = (c) => sizes.reduce((sum, s) => sum + cellVal(c, s), 0);
  const colTotal = (s) => colors.reduce((sum, c) => sum + cellVal(c, s), 0);
  const grandTotal = colors.reduce((sum, c) => sum + rowTotal(c), 0);

  // Live BOM feasibility preview — recomputes whenever grand total changes.
  useEffect(() => {
    if (!useComponents || grandTotal <= 0) { setFeasibility(null); return; }
    const controller = new AbortController();
    (async () => {
      try {
        const r = await http.get(`/production/bom-feasibility/${style.id}?pairs=${grandTotal}`, {
          signal: controller.signal,
        });
        setFeasibility(r.data);
      } catch (e) {
        if (e.name !== "CanceledError") setFeasibility(null);
      }
    })();
    return () => controller.abort();
  }, [style.id, useComponents, grandTotal]);

  const addColor = () => {
    const v = newColor.trim();
    if (!v || colors.includes(v)) return;
    setColors((p) => [...p, v]);
    setNewColor("");
  };
  const addSize = () => {
    const v = newSize.trim();
    if (!v || sizes.includes(v)) return;
    setSizes((p) => [...p, v]);
    setNewSize("");
  };
  const removeColor = (c) => {
    setColors((p) => p.filter((x) => x !== c));
    setQty((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((k) => k.startsWith(`${c}||`) && delete next[k]);
      return next;
    });
  };
  const removeSize = (s) => {
    setSizes((p) => p.filter((x) => x !== s));
    setQty((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((k) => k.endsWith(`||${s}`) && delete next[k]);
      return next;
    });
  };

  const runProduction = async (force) => {
    setErr(""); setResults(null); setBusy(true);
    // Build the list of non-zero cells
    const cells = [];
    for (const c of colors) for (const s of sizes) {
      const v = cellVal(c, s);
      if (v > 0) cells.push({ color: c, size: String(s), qty: v });
    }
    const ok = [], errors = [];
    let pendingShortage = null;
    for (const cell of cells) {
      try {
        const { data } = await http.post("/production/produce-cell", {
          style_id:              style.id,
          color:                 cell.color,
          size:                  cell.size,
          produced_qty:          cell.qty,
          use_components:        useComponents,
          channel_filter:        "online_channel",
          force_negative_stock:  !!force,
        });
        ok.push({ ...cell, ...data });
      } catch (e) {
        const d = e.response?.data?.detail;
        if (d && typeof d === "object" && d.code === "component_shortage" && !force) {
          // Aggregate the shortage — one confirm covers the rest of the batch.
          pendingShortage = { cell, shortages: d.shortages || [] };
          break;
        }
        const msg = (d && typeof d === "object" && d.message) ? d.message : friendlyAxiosError(e);
        errors.push({ ...cell, error: msg });
      }
    }
    setBusy(false);
    if (pendingShortage) {
      setShortageConfirm({
        shortages: pendingShortage.shortages,
        onConfirm: () => { setShortageConfirm(null); runProduction(true); },
        onCancel:  () => { setShortageConfirm(null); setResults({ ok, errors }); },
      });
      return;
    }
    setResults({ ok, errors });
  };

  const submit = () => {
    const cells = colors.flatMap((c) => sizes.map((s) => cellVal(c, s))).filter((v) => v > 0);
    if (cells.length === 0) { setErr("Enter at least one non-zero cell to produce."); return; }
    runProduction(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-2 sm:p-4 overflow-y-auto" onClick={onClose}>
      <div
        className="bg-white w-full max-w-4xl border-2 border-slate-900 shadow-ind-lg my-4"
        onClick={(e) => e.stopPropagation()}
        data-testid="adhoc-produce-drawer"
      >
        <div className="px-5 py-4 border-b-2 border-slate-900 bg-slate-50 flex items-center justify-between gap-3 sticky top-0 z-10">
          <div className="flex items-center gap-3 min-w-0">
            <SafeImage
              image={{ url: style.image_url, display_url: style.image_display_url, thumbnail_url: style.image_thumbnail_url }}
              alt={style.code}
              aspectRatio="1/1"
              className="w-12 h-12 flex-shrink-0"
            />
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Ad-hoc Production — Color × Size Matrix</div>
              <div className="font-mono font-black">{style.code}</div>
              <div className="text-xs text-slate-500 truncate">{style.name}</div>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-900" data-testid="adhoc-close"><X className="w-5 h-5" /></button>
        </div>

        {results ? (
          <div className="p-5 space-y-3">
            {results.ok.length > 0 && (
              <div className="p-3 border-2 border-emerald-500 bg-emerald-50 text-emerald-900 text-xs">
                <div className="font-bold mb-1">Produced {results.ok.reduce((s, r) => s + r.qty, 0)} pairs across {results.ok.length} cell(s):</div>
                <ul className="space-y-0.5">
                  {results.ok.map((r, i) => (
                    <li key={i}>
                      <span className="font-mono">{r.color} · Size {r.size}</span> — {r.qty} pairs
                      {r.excess_placed_at && <> · placed at <span className="font-mono">{r.excess_placed_at}</span></>}
                      {r.bom_components_used?.length > 0 && (
                        <> · deducted: {r.bom_components_used.map(c => `${c.component_code} (−${c.deducted})`).join(", ")}</>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {results.errors.length > 0 && (
              <div className="p-3 border-2 border-red-400 bg-red-50 text-red-900 text-xs">
                <div className="font-bold mb-1">{results.errors.length} cell(s) failed:</div>
                <ul className="space-y-0.5">
                  {results.errors.map((r, i) => (
                    <li key={i}><span className="font-mono">{r.color} · Size {r.size}</span> — {r.error}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex justify-end gap-2">
              <BtnSecondary onClick={() => { setResults(null); setQty({}); }}>Produce more</BtnSecondary>
              <BtnPrimary onClick={onDone} data-testid="adhoc-done">Done</BtnPrimary>
            </div>
          </div>
        ) : (
          <div className="p-5 space-y-4">
            {(colors.length === 0 || sizes.length === 0) && (
              <div className="p-2 border-2 border-amber-300 bg-amber-50 text-amber-900 text-xs">
                Add at least one color and one size below to build the matrix.
              </div>
            )}

            {/* Matrix table */}
            {colors.length > 0 && sizes.length > 0 && (
              <div className="overflow-x-auto">
                <table className="text-xs border-collapse">
                  <thead>
                    <tr>
                      <th className="border border-slate-300 bg-slate-100 px-2 py-1 sticky left-0 z-10">Color \ Size</th>
                      {sizes.map((s) => (
                        <th key={s} className="border border-slate-300 bg-slate-50 px-1 py-1 font-mono min-w-[3.5rem]">
                          {s}
                          <button onClick={() => removeSize(s)} className="ml-1 text-slate-400 hover:text-red-600 align-super" title={`Remove size ${s}`}>×</button>
                        </th>
                      ))}
                      <th className="border border-slate-300 bg-slate-200 px-2 py-1">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {colors.map((c) => (
                      <tr key={c}>
                        <th className="border border-slate-300 bg-slate-50 px-2 py-1 text-left sticky left-0 z-10 font-mono">
                          {c}
                          <button onClick={() => removeColor(c)} className="ml-1 text-slate-400 hover:text-red-600 align-super" title={`Remove color ${c}`}>×</button>
                        </th>
                        {sizes.map((s) => (
                          <td key={s} className="border border-slate-300 p-0">
                            <input
                              type="number"
                              min="0"
                              value={qty[cellKey(c, s)] || ""}
                              onChange={(e) => setCell(c, s, e.target.value)}
                              className={`w-16 text-center font-mono py-1.5 focus:outline-none focus:bg-emerald-50 ${cellVal(c, s) > 0 ? "bg-emerald-50 font-bold" : "bg-white"}`}
                              data-testid={`matrix-cell-${c}-${s}`}
                            />
                          </td>
                        ))}
                        <td className="border border-slate-300 bg-slate-100 px-2 py-1.5 text-center font-mono font-bold">{rowTotal(c) || "·"}</td>
                      </tr>
                    ))}
                    <tr>
                      <th className="border border-slate-300 bg-slate-200 px-2 py-1 text-left sticky left-0 z-10 uppercase text-[10px]">Total</th>
                      {sizes.map((s) => (
                        <td key={s} className="border border-slate-300 bg-slate-100 px-1 py-1.5 text-center font-mono font-bold">{colTotal(s) || "·"}</td>
                      ))}
                      <td className="border border-slate-300 bg-slate-900 text-white px-2 py-1.5 text-center font-mono font-black text-base" data-testid="matrix-grand-total">{grandTotal}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            {/* Add color / size chips */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Add color</label>
                <div className="flex gap-1 mt-0.5">
                  <input
                    value={newColor}
                    onChange={(e) => setNewColor(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && addColor()}
                    placeholder="e.g. Tan"
                    className="flex-1 border-2 border-slate-300 px-2 py-1.5 text-sm"
                    data-testid="adhoc-new-color"
                  />
                  <BtnSecondary onClick={addColor} data-testid="adhoc-add-color">Add</BtnSecondary>
                </div>
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Add size</label>
                <div className="flex gap-1 mt-0.5">
                  <input
                    value={newSize}
                    onChange={(e) => setNewSize(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && addSize()}
                    placeholder="e.g. 7"
                    className="flex-1 border-2 border-slate-300 px-2 py-1.5 text-sm font-mono"
                    data-testid="adhoc-new-size"
                  />
                  <BtnSecondary onClick={addSize} data-testid="adhoc-add-size">Add</BtnSecondary>
                </div>
              </div>
            </div>

            <label className="flex items-start gap-2 cursor-pointer text-xs pt-1">
              <input type="checkbox" checked={useComponents} onChange={(e) => setUseComp(e.target.checked)} className="mt-0.5" data-testid="adhoc-use-components" />
              <span className="flex-1">
                <span className="font-bold uppercase tracking-wider">Deduct from Component Inventory</span><br />
                <span className="text-slate-500">
                  Uncheck to produce directly from raw material without a BOM.
                  {!hasBom && (<> This style currently has <strong>no Production Card</strong>. </>)}
                </span>
              </span>
            </label>

            {/* Live feasibility indicator */}
            {useComponents && grandTotal > 0 && feasibility && (
              <div
                className={`p-2 border-2 text-xs ${
                  feasibility.missing_bom
                    ? "border-amber-400 bg-amber-50 text-amber-900"
                    : feasibility.feasible
                    ? "border-emerald-400 bg-emerald-50 text-emerald-900"
                    : "border-red-400 bg-red-50 text-red-900"
                }`}
                data-testid="adhoc-feasibility"
              >
                {feasibility.missing_bom ? (
                  <>
                    <AlertTriangle className="w-3.5 h-3.5 inline mr-1" />
                    No production card mapped. Click <strong>Edit Production Card</strong> or turn off the toggle above.
                  </>
                ) : feasibility.feasible ? (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5 inline mr-1" />
                    BOM feasible for {grandTotal} pairs — all components have enough stock.
                  </>
                ) : (
                  <>
                    <AlertTriangle className="w-3.5 h-3.5 inline mr-1" />
                    <strong>Shortage:</strong>{" "}
                    {feasibility.components.filter((c) => c.shortfall > 0)
                      .map((c) => `${c.component_code} (need ${c.needed}, have ${c.available}, short ${c.shortfall})`)
                      .join(" · ")}
                    <div className="mt-0.5 text-[10px]">You&apos;ll be asked to confirm before stock goes below zero.</div>
                  </>
                )}
              </div>
            )}

            {err && (
              <div className="p-2 border-2 border-red-300 bg-red-50 text-red-900 text-xs" data-testid="adhoc-error">{err}</div>
            )}

            <div className="flex gap-2 pt-1">
              <BtnSecondary onClick={onEditBom} className="flex-1"><Wrench className="w-3.5 h-3.5 inline mr-1" />Edit Production Card</BtnSecondary>
              <BtnPrimary onClick={submit} disabled={busy || grandTotal <= 0} className="flex-1" data-testid="adhoc-submit">
                {busy && <Loader2 className="w-3.5 h-3.5 inline mr-1 animate-spin" />}
                <Package className="w-3.5 h-3.5 inline mr-1" />
                Produce {grandTotal > 0 ? `${grandTotal} pairs` : ""}
              </BtnPrimary>
            </div>
          </div>
        )}
      </div>

      {shortageConfirm && (
        <div
          className="fixed inset-0 z-[60] bg-black/70 flex items-center justify-center p-4"
          onClick={shortageConfirm.onCancel}
          data-testid="shortage-confirm-modal"
        >
          <div
            className="bg-white w-full max-w-md border-2 border-red-500 shadow-ind-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 py-3 border-b-2 border-red-500 bg-red-50 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-700" />
              <div className="font-black text-red-900">Component shortage — proceed anyway?</div>
            </div>
            <div className="p-5 space-y-3 text-sm">
              <p className="text-slate-700">
                This production run will drive the following components below zero:
              </p>
              <div className="border-2 border-red-200 divide-y divide-red-200">
                {shortageConfirm.shortages.map((s, i) => (
                  <div key={i} className="px-3 py-2 flex items-baseline justify-between gap-2 text-xs">
                    <div>
                      <div className="font-mono font-bold">{s.component_code}</div>
                      <div className="text-slate-500">{s.component_name}</div>
                    </div>
                    <div className="text-right font-mono">
                      <div>need <strong>{s.needed}</strong></div>
                      <div>have <strong>{s.available}</strong></div>
                      <div className="text-red-700">→ short {s.shortfall}</div>
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-[11px] text-slate-500">
                If you proceed, component stock will go negative and a warning will remain in the ledger until inventory is topped up.
              </p>
              <div className="flex gap-2">
                <BtnSecondary onClick={shortageConfirm.onCancel} className="flex-1" data-testid="shortage-cancel">Cancel</BtnSecondary>
                <BtnPrimary onClick={shortageConfirm.onConfirm} className="flex-1 !bg-red-700 !border-red-700 hover:!bg-red-800" data-testid="shortage-proceed">
                  Proceed anyway
                </BtnPrimary>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
