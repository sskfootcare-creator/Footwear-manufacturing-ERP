import { useState, useMemo, useEffect } from "react";
import { http, formatApiError } from "../lib/api";
import { Drawer } from "./Materials";
import {
  BtnPrimary, BtnSecondary, Input, Select,
} from "../components/ui-kit";
import {
  Save, X, AlertTriangle, CheckCircle2, Plus, Trash2, Package,
} from "lucide-react";

const CATEGORIES = [
  "Upper", "Sole", "Insole", "Sockliner", "Bottom",
  "Lace", "Box", "Tag", "Label", "Packaging", "Other",
];

/*
   Drawer for creating multiple component rows at once, in a Color x Size
   matrix (mirrors the AddStockDrawer in Ready Stock).
   Two modes:
     • "new"    — creating a brand-new component_code with a full matrix
     • "extend" — adding new (color, size) rows to an existing code
                  (colors/sizes present in the master are pre-filled, opening 0)
*/
export default function ComponentBulkDrawer({ prefill, existingCodes, onClose, onDone }) {
  const isExtend = !!prefill?.component_code;
  const [meta, setMeta] = useState({
    component_code:     prefill?.component_code     || "",
    component_name:     prefill?.component_name     || "",
    component_category: prefill?.component_category || "Insole",
    vendor:             prefill?.vendor             || "",
    unit:               prefill?.unit               || "pair",
    reorder_level:      0,
    minimum_stock:      0,
    lead_time_days:     0,
  });
  const [colorInput, setColorInput] = useState("");
  const [sizeInput,  setSizeInput]  = useState("");
  const [colors, setColors] = useState([]);
  const [sizes,  setSizes]  = useState([]);
  const [qtyMatrix, setQtyMatrix] = useState({});   // "color|size" → int
  // Existing (color|size) → current_stock map (populated in extend mode)
  // so the drawer can show "was 12 → +5 → will be 17" per cell.
  const [existingStock, setExistingStock] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState("");
  const [result, setResult] = useState(null);

  // When extend mode, prefill sizes/colors from existing rows
  useEffect(() => {
    if (!isExtend) return;
    (async () => {
      try {
        const r = await http.get(`/components?code=${encodeURIComponent(prefill.component_code)}`);
        const rows = r.data || [];
        const cSet = new Set(), sSet = new Set();
        const stockMap = {};
        for (const row of rows) {
          if (row.color) cSet.add(row.color);
          if (row.size)  sSet.add(row.size);
          stockMap[`${row.color}|${row.size}`] = Number(row.current_stock || 0);
        }
        setColors(Array.from(cSet).sort());
        setSizes(Array.from(sSet).sort((a, b) => {
          const na = parseFloat(a), nb = parseFloat(b);
          if (!isNaN(na) && !isNaN(nb)) return na - nb;
          return a.localeCompare(b);
        }));
        setExistingStock(stockMap);
      } catch {}
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isExtend, prefill]);

  function addFromInput(input, setInput, list, setList) {
    const parts = input.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean);
    if (!parts.length) return;
    const merged = Array.from(new Set([...list, ...parts]));
    setList(merged);
    setInput("");
  }
  function removeItem(list, setList, val) {
    setList(list.filter((x) => x !== val));
    setQtyMatrix((m) => {
      const next = { ...m };
      for (const k of Object.keys(next)) {
        if (k.startsWith(`${val}|`) || k.endsWith(`|${val}`)) delete next[k];
      }
      return next;
    });
  }

  const totalPairs = useMemo(() => Object.values(qtyMatrix).reduce((s, v) => s + Number(v || 0), 0), [qtyMatrix]);

  function fillAll(qty) {
    const m = {};
    for (const c of colors) for (const s of sizes) m[`${c}|${s}`] = qty;
    setQtyMatrix(m);
  }

  async function submit() {
    setError(""); setResult(null); setSaving(true);
    try {
      // Guardrails
      if (!meta.component_code.trim()) throw new Error("Component code is required");
      if (!meta.component_name.trim()) throw new Error("Component name is required");
      if (colors.length === 0 || sizes.length === 0)
        throw new Error("Provide at least one color and one size");
      // Warn on brand-new code collision
      if (!isExtend && existingCodes.includes(meta.component_code.trim())) {
        throw new Error(`Component code '${meta.component_code}' already exists — use "Add Stock" on that card to extend its matrix.`);
      }
      const rows = [];
      for (const c of colors) for (const s of sizes) {
        const q = Number(qtyMatrix[`${c}|${s}`] || 0);
        rows.push({ color: c, size: s, opening_qty: q });
      }
      const payload = {
        component_code:     meta.component_code.trim(),
        component_name:     meta.component_name.trim(),
        component_category: meta.component_category,
        vendor:             meta.vendor,
        unit:               meta.unit,
        reorder_level:      Number(meta.reorder_level) || 0,
        minimum_stock:      Number(meta.minimum_stock) || 0,
        lead_time_days:     Number(meta.lead_time_days) || 0,
        rows,
      };
      const r = await http.post(`/components/bulk-matrix`, payload);
      setResult(r.data);
      onDone();
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || e.message || "Save failed.");
    } finally { setSaving(false); }
  }

  return (
    <Drawer onClose={onClose}
      title={isExtend ? `Add Stock in Bulk — ${prefill.component_code}` : "Add Components in Bulk"}
      width="max-w-3xl">
      <div className="space-y-4 pb-24">
        {/* Metadata */}
        <div className="grid grid-cols-2 gap-3">
          <Input label="Component Code *" value={meta.component_code} disabled={isExtend}
            onChange={(e) => setMeta((m) => ({ ...m, component_code: e.target.value }))} />
          <Select label="Category *" value={meta.component_category} disabled={isExtend}
            onChange={(e) => setMeta((m) => ({ ...m, component_category: e.target.value }))}>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </Select>
        </div>
        <Input label="Component Name *" value={meta.component_name} disabled={isExtend}
          onChange={(e) => setMeta((m) => ({ ...m, component_name: e.target.value }))} />
        <div className="grid grid-cols-3 gap-3">
          <Input label="Vendor" value={meta.vendor}
            onChange={(e) => setMeta((m) => ({ ...m, vendor: e.target.value }))} />
          <Input label="Unit" value={meta.unit}
            onChange={(e) => setMeta((m) => ({ ...m, unit: e.target.value }))} />
          <Input label="Lead-Time Days" type="number" value={meta.lead_time_days}
            onChange={(e) => setMeta((m) => ({ ...m, lead_time_days: e.target.value }))} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Reorder Level" type="number" value={meta.reorder_level}
            onChange={(e) => setMeta((m) => ({ ...m, reorder_level: e.target.value }))} />
          <Input label="Minimum Stock" type="number" value={meta.minimum_stock}
            onChange={(e) => setMeta((m) => ({ ...m, minimum_stock: e.target.value }))} />
        </div>

        {/* Colors (row axis) */}
        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">Colors (row axis)</div>
          <div className="border-2 border-slate-300 bg-white px-2 py-2 flex flex-wrap items-center gap-1">
            {colors.map((c) => (
              <span key={c} className="inline-flex items-center gap-1 px-2 py-0.5 border border-slate-400 bg-slate-100 text-[11px] font-mono">
                {c}
                <button className="hover:text-red-600" onClick={() => removeItem(colors, setColors, c)}><X className="w-3 h-3" /></button>
              </span>
            ))}
            <input
              className="flex-1 min-w-[140px] outline-none text-sm font-mono px-1 py-0.5"
              placeholder="e.g. White, Black — Enter to add"
              value={colorInput}
              onChange={(e) => setColorInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addFromInput(colorInput, setColorInput, colors, setColors); }
              }}
              onBlur={() => colorInput && addFromInput(colorInput, setColorInput, colors, setColors)}
            />
          </div>
        </div>

        {/* Sizes (column axis) */}
        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1">Sizes (column axis)</div>
          <div className="border-2 border-slate-300 bg-white px-2 py-2 flex flex-wrap items-center gap-1">
            {sizes.map((s) => (
              <span key={s} className="inline-flex items-center gap-1 px-2 py-0.5 border border-slate-400 bg-slate-100 text-[11px] font-mono">
                {s}
                <button className="hover:text-red-600" onClick={() => removeItem(sizes, setSizes, s)}><X className="w-3 h-3" /></button>
              </span>
            ))}
            <input
              className="flex-1 min-w-[140px] outline-none text-sm font-mono px-1 py-0.5"
              placeholder="e.g. 6, 7, 8, 9 — Enter to add"
              value={sizeInput}
              onChange={(e) => setSizeInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addFromInput(sizeInput, setSizeInput, sizes, setSizes); }
              }}
              onBlur={() => sizeInput && addFromInput(sizeInput, setSizeInput, sizes, setSizes)}
            />
          </div>
        </div>

        {/* Matrix input */}
        {colors.length > 0 && sizes.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">
                {isExtend ? "Enter Stock to Add (Δ Qty)" : "Enter Opening Quantities"}
              </div>
              <div className="flex gap-1.5">
                <button className="text-[10px] uppercase tracking-wider font-bold border border-slate-300 px-2 py-1 hover:bg-slate-100"
                  onClick={() => fillAll(25)}>Fill 25</button>
                <button className="text-[10px] uppercase tracking-wider font-bold border border-slate-300 px-2 py-1 hover:bg-slate-100"
                  onClick={() => fillAll(100)}>Fill 100</button>
                <button className="text-[10px] uppercase tracking-wider font-bold border border-slate-300 px-2 py-1 hover:bg-slate-100"
                  onClick={() => fillAll(0)}>Clear</button>
              </div>
            </div>
            {isExtend && (
              <div className="text-[10px] text-slate-500 italic mb-1.5">
                Existing on-hand shown in grey above each cell. Quantities you enter are ADDED to the current stock via a purchase-in movement.
              </div>
            )}
            <div className="border border-slate-200 overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-2 py-1.5 text-left text-[10px] uppercase tracking-wider font-bold text-slate-500">Color \ Size</th>
                    {sizes.map((s) => (
                      <th key={s} className="px-2 py-1.5 text-center text-[10px] uppercase tracking-wider font-bold text-slate-500">{s}</th>
                    ))}
                    <th className="px-2 py-1.5 text-center text-[10px] uppercase tracking-wider font-bold bg-slate-800 text-white">Row Σ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {colors.map((c) => {
                    const rowSum = sizes.reduce((s, sz) => s + Number(qtyMatrix[`${c}|${sz}`] || 0), 0);
                    return (
                      <tr key={c}>
                        <td className="px-2 py-1.5 font-mono font-bold text-slate-800 whitespace-nowrap">{c}</td>
                        {sizes.map((s) => {
                          const existing = existingStock[`${c}|${s}`];
                          const hasExisting = existing !== undefined;
                          const addQty = Number(qtyMatrix[`${c}|${s}`] || 0);
                          return (
                            <td key={s} className="px-1 py-1">
                              {isExtend && hasExisting && (
                                <div
                                  className="text-[9px] text-center text-slate-400 font-mono leading-tight"
                                  title={`Existing stock for ${c} ${s}`}
                                  data-testid={`existing-stock-${c}-${s}`}
                                >
                                  was {existing}
                                  {addQty > 0 && (
                                    <span className="text-emerald-600 font-semibold"> → {existing + addQty}</span>
                                  )}
                                </div>
                              )}
                              <input
                                type="number"
                                className="w-full border border-slate-200 focus:border-[#0F172A] focus:outline-none px-1 py-0.5 text-center font-mono text-xs"
                                value={qtyMatrix[`${c}|${s}`] ?? ""}
                                onChange={(e) => setQtyMatrix((m) => ({ ...m, [`${c}|${s}`]: e.target.value }))}
                                placeholder="0"
                                data-testid={`bulk-qty-${c}-${s}`}
                              />
                            </td>
                          );
                        })}
                        <td className="px-2 py-1.5 text-center font-mono font-bold bg-slate-800 text-white">{rowSum}</td>
                      </tr>
                    );
                  })}
                  <tr className="bg-slate-100">
                    <td className="px-2 py-1.5 font-mono font-bold text-[10px] uppercase tracking-wider text-slate-600">Col Σ</td>
                    {sizes.map((s) => (
                      <td key={s} className="px-2 py-1.5 text-center font-mono font-bold">
                        {colors.reduce((sum, c) => sum + Number(qtyMatrix[`${c}|${s}`] || 0), 0)}
                      </td>
                    ))}
                    <td className="px-2 py-1.5 text-center font-mono font-bold bg-[#C27842] text-white">{totalPairs}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {error && (
          <div className="border-2 border-red-500 bg-red-50 text-red-800 px-3 py-2 text-xs font-bold flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> {error}
          </div>
        )}
        {result && (
          <div className="border-2 border-green-500 bg-green-50 text-green-900 px-3 py-2 text-xs font-mono">
            <div className="font-bold uppercase tracking-wider text-[10px] mb-1 flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" /> Applied
            </div>
            <div>
              New rows: <span className="font-bold">{result.created}</span>
              {" · "}
              Stock added to existing: <span className="font-bold">{result.updated ?? 0}</span>
              {" · "}
              Skipped (existing, 0 qty): <span className="font-bold">{result.skipped}</span>
            </div>
          </div>
        )}

        <div className="flex gap-2 pt-2 sticky bottom-0 bg-white py-2 border-t border-slate-200">
          <BtnPrimary onClick={submit} disabled={saving} className="flex-1">
            {saving ? "Saving…" : (
              <span className="flex items-center gap-2 justify-center">
                <Save className="w-4 h-4" /> Apply Matrix ({colors.length * sizes.length} cells)
              </span>
            )}
          </BtnPrimary>
          <BtnSecondary onClick={onClose}><X className="w-4 h-4" /></BtnSecondary>
        </div>
      </div>
    </Drawer>
  );
}
