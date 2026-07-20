import { useEffect, useState, useCallback, useMemo } from "react";
import { http, formatApiError } from "../lib/api";
import {
  PageHeader, Card, BtnPrimary, BtnSecondary,
  Input, Select, Badge, StatTile,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import ComponentBulkDrawer from "./ComponentBulkDrawer";
import {
  AlertTriangle, Plus, RefreshCw, History, Package, Boxes,
  ChevronRight, Layers, ShieldAlert, Trash2, PencilLine, Upload, Save, X,
} from "lucide-react";

/* ────────────────────────────────────────────────────────────
   Constants — mirror backend
   ──────────────────────────────────────────────────────────── */
const CATEGORIES = [
  "Upper", "Sole", "Insole", "Sockliner", "Bottom",
  "Lace", "Box", "Tag", "Label", "Packaging", "Other",
];

const METRICS = {
  current:   { label: "Current Stock",  field: "current_stock",  accent: "#0F172A" },
  reserved:  { label: "Reserved",       field: "reserved_stock", accent: "#2563EB" },
  available: { label: "Available",      field: "available_stock",accent: "#16A34A" },
};

const MOVEMENT_TYPES = [
  { value: "purchase_in",         label: "Purchase In",             hint: "+ current stock" },
  { value: "return_in",           label: "Return In",               hint: "+ current stock" },
  { value: "adjustment",          label: "Manual Adjustment",       hint: "signed +/- current" },
  { value: "production_reserve",  label: "Production Reserve",      hint: "+ reserved" },
  { value: "online_reserve",      label: "Online Reserve",          hint: "+ reserved" },
  { value: "unreserve",           label: "Un-reserve",              hint: "- reserved" },
  { value: "production_issue",    label: "Production Issue",        hint: "- current & reserved (consume)" },
  { value: "online_issue",        label: "Online Issue",            hint: "- current & reserved (consume)" },
];

const inr0 = (n) => new Intl.NumberFormat("en-IN").format(Number(n || 0));

const sortSizes = (sizes) => [...sizes].sort((a, b) => {
  const na = parseFloat(a), nb = parseFloat(b);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  if (!isNaN(na)) return -1;
  if (!isNaN(nb)) return  1;
  return String(a || "").localeCompare(String(b || ""));
});

/* ────────────────────────────────────────────────────────────
   MovementDrawer — post any movement type on one component row.
   ──────────────────────────────────────────────────────────── */
function MovementDrawer({ initial, components, onClose, onDone }) {
  const [form, setForm] = useState({
    component_id:   initial?.component_id || "",
    movement_type:  "purchase_in",
    quantity:       0,
    adjustment_dir: "increase",
    reference_type: "manual",
    reference_id:   "",
    style_id:       "",
    notes:          "",
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [styles, setStyles] = useState([]);

  useEffect(() => {
    http.get("/styles").then((r) => setStyles(r.data || [])).catch(() => {});
  }, []);

  const chosenComp = components.find((c) => c.id === form.component_id);
  const chosenType = MOVEMENT_TYPES.find((m) => m.value === form.movement_type);

  async function submit() {
    setError(""); setSaving(true);
    try {
      const payload = {
        component_id:   form.component_id,
        movement_type:  form.movement_type,
        quantity:       Number(form.quantity),
        reference_type: form.reference_type,
        reference_id:   form.reference_id,
        style_id:       form.style_id || "",
        notes:          form.notes,
      };
      if (form.movement_type === "adjustment") payload.adjustment_dir = form.adjustment_dir;
      await http.post("/components/movements", payload);
      onDone(); onClose();
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Movement failed.");
    } finally { setSaving(false); }
  }

  return (
    <Drawer onClose={onClose} title="Post Component Movement" width="max-w-xl">
      <div className="space-y-4 pb-6">
        <Select
          label="Component"
          value={form.component_id}
          onChange={(e) => setForm((f) => ({ ...f, component_id: e.target.value }))}
        >
          <option value="">— select component —</option>
          {components.map((c) => (
            <option key={c.id} value={c.id}>
              {c.component_code} · {c.color || "—"} / {c.size || "—"} · avail {c.available_stock}
            </option>
          ))}
        </Select>

        <div>
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1.5">Movement Type</div>
          <div className="grid grid-cols-2 gap-1.5">
            {MOVEMENT_TYPES.map((m) => (
              <button
                key={m.value}
                onClick={() => setForm((f) => ({ ...f, movement_type: m.value }))}
                className={`text-left px-2.5 py-1.5 border-2 text-[11px] font-bold ${
                  form.movement_type === m.value ? "bg-[#0F172A] text-white border-[#0F172A]" : "border-slate-300 text-slate-700 hover:border-slate-500"
                }`}
              >
                <div className="uppercase tracking-wider text-[10px]">{m.label}</div>
                <div className={`text-[10px] font-mono mt-0.5 ${form.movement_type === m.value ? "opacity-80" : "text-slate-500"}`}>{m.hint}</div>
              </button>
            ))}
          </div>
        </div>

        {form.movement_type === "adjustment" && (
          <div>
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600 mb-1.5">Direction</div>
            <div className="flex gap-1.5">
              {["increase", "decrease"].map((d) => (
                <button
                  key={d}
                  onClick={() => setForm((f) => ({ ...f, adjustment_dir: d }))}
                  className={`flex-1 px-3 py-1.5 border-2 text-[11px] font-bold uppercase ${
                    form.adjustment_dir === d
                      ? (d === "increase" ? "border-green-600 bg-green-600 text-white" : "border-red-600 bg-red-600 text-white")
                      : "border-slate-300 text-slate-700 hover:border-slate-500"
                  }`}
                >
                  {d === "increase" ? "+ Increase" : "− Decrease"}
                </button>
              ))}
            </div>
          </div>
        )}

        <Input label="Quantity" type="number" value={form.quantity}
          onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))} />

        <div className="grid grid-cols-2 gap-3">
          <Input label="Reference Type" value={form.reference_type}
            onChange={(e) => setForm((f) => ({ ...f, reference_type: e.target.value }))}
            placeholder="e.g. PO, production_job, online_order" />
          <Input label="Reference ID" value={form.reference_id}
            onChange={(e) => setForm((f) => ({ ...f, reference_id: e.target.value }))}
            placeholder="Optional" />
        </div>

        <Select label="Link to Style (optional)" value={form.style_id}
          onChange={(e) => setForm((f) => ({ ...f, style_id: e.target.value }))}>
          <option value="">— none —</option>
          {styles.map((s) => (
            <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
          ))}
        </Select>

        <div>
          <label className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">Notes</label>
          <textarea rows={2}
            className="w-full border-2 border-slate-300 bg-white px-2 py-1.5 text-sm font-mono focus:border-[#0F172A] focus:outline-none"
            value={form.notes}
            onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            placeholder="Optional context" />
        </div>

        {chosenComp && chosenType && (
          <div className="bg-slate-50 border border-slate-200 p-3 text-xs font-mono">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">Preview</div>
            <div className="text-slate-800">
              <span className="font-bold">{chosenComp.component_code}</span> ({chosenComp.color || "—"} / {chosenComp.size || "—"}):
              current <span className="font-bold">{chosenComp.current_stock}</span>,
              reserved <span className="font-bold">{chosenComp.reserved_stock}</span>,
              available <span className="font-bold">{chosenComp.available_stock}</span>
            </div>
            <div className="text-slate-500 mt-1">
              Applying <span className="text-slate-800 font-bold">{chosenType.label}</span> — {chosenType.hint}
            </div>
          </div>
        )}

        {error && (
          <div className="border-2 border-red-500 bg-red-50 text-red-800 px-3 py-2 text-xs font-bold flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> {error}
          </div>
        )}

        <div className="flex gap-2 pt-2 sticky bottom-0 bg-white py-2 border-t border-slate-200">
          <BtnPrimary onClick={submit} disabled={!form.component_id || !form.quantity || saving} className="flex-1">
            {saving ? "Saving…" : <span className="flex items-center gap-2 justify-center"><Save className="w-4 h-4" /> Post Movement</span>}
          </BtnPrimary>
          <BtnSecondary onClick={onClose}><X className="w-4 h-4" /></BtnSecondary>
        </div>
      </div>
    </Drawer>
  );
}

/* ────────────────────────────────────────────────────────────
   LedgerDrawer — read-only movement history for one component code.
   ──────────────────────────────────────────────────────────── */
function LedgerDrawer({ code, componentIds, onClose }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        // Fetch ledger for each component_id and merge (Phase 1: no OR filter server-side)
        const results = await Promise.all(
          componentIds.map((id) => http.get(`/components/movements?component_id=${id}&limit=200`).then((r) => r.data).catch(() => []))
        );
        const merged = results.flat().sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
        setRows(merged);
      } finally { setLoading(false); }
    })();
  }, [componentIds]);

  return (
    <Drawer onClose={onClose} title={`Ledger — ${code}`} width="max-w-4xl">
      {loading ? (
        <div className="text-center py-10 text-slate-400">Loading ledger…</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-10 text-slate-400">No movements yet.</div>
      ) : (
        <div className="overflow-x-auto border border-slate-200">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-slate-50 border-b-2 border-slate-200">
              <tr>
                {["Time", "Color", "Size", "Type", "Qty", "Δ cur", "Δ res", "→ Cur", "→ Res", "Ref", "By"].map((h) => (
                  <th key={h} className="px-2 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500 text-left whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="px-2 py-1.5 font-mono text-[10px] text-slate-500 whitespace-nowrap">{r.created_at?.slice(0, 19).replace("T", " ")}</td>
                  <td className="px-2 py-1.5">{r.color || "—"}</td>
                  <td className="px-2 py-1.5">{r.size || "—"}</td>
                  <td className="px-2 py-1.5">
                    <Badge color={
                      r.movement_type === "purchase_in"        ? "green" :
                      r.movement_type === "return_in"          ? "green" :
                      r.movement_type === "production_issue"   ? "red"   :
                      r.movement_type === "online_issue"       ? "red"   :
                      r.movement_type === "adjustment"         ? "yellow" :
                      r.movement_type.endsWith("reserve")      ? "blue"  : "slate"
                    }>{r.movement_type}</Badge>
                  </td>
                  <td className="px-2 py-1.5 font-mono font-bold">{r.quantity}</td>
                  <td className={`px-2 py-1.5 font-mono ${r.current_delta > 0 ? "text-green-700" : r.current_delta < 0 ? "text-red-700" : "text-slate-400"}`}>
                    {r.current_delta > 0 ? `+${r.current_delta}` : r.current_delta}
                  </td>
                  <td className={`px-2 py-1.5 font-mono ${r.reserved_delta > 0 ? "text-blue-700" : r.reserved_delta < 0 ? "text-orange-700" : "text-slate-400"}`}>
                    {r.reserved_delta > 0 ? `+${r.reserved_delta}` : r.reserved_delta}
                  </td>
                  <td className="px-2 py-1.5 font-mono">{r.current_after}</td>
                  <td className="px-2 py-1.5 font-mono">{r.reserved_after}</td>
                  <td className="px-2 py-1.5 font-mono text-[10px] text-slate-500">
                    {r.reference_type}{r.reference_id ? ` · ${r.reference_id}` : ""}
                  </td>
                  <td className="px-2 py-1.5 font-mono text-[10px] text-slate-500">{r.by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Drawer>
  );
}

/* ────────────────────────────────────────────────────────────
   EditMetadataDrawer — update metadata for a single component row.
   ──────────────────────────────────────────────────────────── */
function EditMetadataDrawer({ row, onClose, onDone }) {
  const [form, setForm] = useState({
    component_name:     row.component_name || "",
    component_category: row.component_category,
    vendor:             row.vendor || "",
    unit:               row.unit || "pair",
    reorder_level:      row.reorder_level || 0,
    minimum_stock:      row.minimum_stock || 0,
    lead_time_days:     row.lead_time_days || 0,
    active:             row.active,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState("");
  async function save() {
    setError(""); setSaving(true);
    try {
      await http.put(`/components/${row.id}`, {
        ...form,
        reorder_level:  Number(form.reorder_level),
        minimum_stock:  Number(form.minimum_stock),
        lead_time_days: Number(form.lead_time_days),
      });
      onDone(); onClose();
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Save failed.");
    } finally { setSaving(false); }
  }
  return (
    <Drawer onClose={onClose} title={`Edit — ${row.component_code} · ${row.color || "—"}/${row.size || "—"}`}>
      <div className="space-y-3 pb-6">
        <Input label="Component Name" value={form.component_name}
          onChange={(e) => setForm((f) => ({ ...f, component_name: e.target.value }))} />
        <Select label="Category" value={form.component_category}
          onChange={(e) => setForm((f) => ({ ...f, component_category: e.target.value }))}>
          {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
        </Select>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Vendor" value={form.vendor} onChange={(e) => setForm((f) => ({ ...f, vendor: e.target.value }))} />
          <Input label="Unit" value={form.unit} onChange={(e) => setForm((f) => ({ ...f, unit: e.target.value }))} />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Input label="Reorder Level"  type="number" value={form.reorder_level}
            onChange={(e) => setForm((f) => ({ ...f, reorder_level: e.target.value }))} />
          <Input label="Minimum Stock"  type="number" value={form.minimum_stock}
            onChange={(e) => setForm((f) => ({ ...f, minimum_stock: e.target.value }))} />
          <Input label="Lead-Time Days" type="number" value={form.lead_time_days}
            onChange={(e) => setForm((f) => ({ ...f, lead_time_days: e.target.value }))} />
        </div>
        <label className="flex items-center gap-2 text-xs font-bold text-slate-700">
          <input type="checkbox" checked={form.active} onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))} />
          <span className="uppercase tracking-wider">Active</span>
        </label>
        {error && (
          <div className="border-2 border-red-500 bg-red-50 text-red-800 px-3 py-2 text-xs font-bold flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> {error}
          </div>
        )}
        <div className="flex gap-2 pt-2 sticky bottom-0 bg-white py-2 border-t border-slate-200">
          <BtnPrimary onClick={save} disabled={saving} className="flex-1">
            {saving ? "Saving…" : <span className="flex items-center gap-2 justify-center"><Save className="w-4 h-4" /> Save</span>}
          </BtnPrimary>
          <BtnSecondary onClick={onClose}><X className="w-4 h-4" /></BtnSecondary>
        </div>
      </div>
    </Drawer>
  );
}

/* ────────────────────────────────────────────────────────────
   ComponentGroupCard — one card per component_code with color x
   size matrix (Ready Stock pattern).
   ──────────────────────────────────────────────────────────── */
function ComponentGroupCard({ group, metric, onAddMovement, onOpenLedger, onEditRow, onAddMatrix }) {
  const M = METRICS[metric];
  const rows = group.rows;

  const { colors, sizes, cellMap, totals, lowCells } = useMemo(() => {
    const cellMap = {};
    const colorSet = new Set(), sizeSet = new Set();
    for (const r of rows) {
      colorSet.add(r.color || "—");
      sizeSet.add(r.size || "—");
      cellMap[`${r.color || "—"}|${r.size || "—"}`] = r;
    }
    const colors = Array.from(colorSet).sort();
    const sizes  = sortSizes(Array.from(sizeSet));
    const totals = { byColor: {}, bySize: {}, grand: 0 };
    let lowCells = 0;
    for (const c of colors) totals.byColor[c] = 0;
    for (const s of sizes)  totals.bySize[s]  = 0;
    for (const r of rows) {
      const v = Number(r[M.field] || 0);
      totals.byColor[r.color || "—"] += v;
      totals.bySize[r.size || "—"]   += v;
      totals.grand += v;
      const isLow = Number(r.minimum_stock || 0) > 0
        && Number(r.available_stock || 0) <= Number(r.minimum_stock || 0);
      if (isLow) lowCells += 1;
    }
    return { colors, sizes, cellMap, totals, lowCells };
  }, [rows, M.field]);

  const totalCurrent = rows.reduce((s, r) => s + Number(r.current_stock  || 0), 0);
  const totalReserved= rows.reduce((s, r) => s + Number(r.reserved_stock || 0), 0);
  const totalAvail   = totalCurrent - totalReserved;

  return (
    <Card
      className={`border-l-4 hover:border-[#C27842] transition-colors ${lowCells > 0 ? "ring-2 ring-red-500 ring-inset" : ""}`}
      style={{ borderLeftColor: M.accent }}
      data-testid={`comp-card-${group.code}`}
    >
      {lowCells > 0 && (
        <div className="bg-red-600 text-white px-3 py-1 flex items-center justify-between text-[10px] uppercase tracking-wider font-bold">
          <span className="flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Low Stock</span>
          <span className="font-mono">{lowCells} cell(s) below min</span>
        </div>
      )}
      <div className="p-3 pb-2 border-b border-slate-100">
        <div className="flex items-baseline justify-between mb-1">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
            Component · <span className="text-slate-800">{group.category}</span>
          </div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">
            metric · <span className="text-slate-900">{M.label}</span>
          </div>
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-mono font-bold text-sm">{group.code}</div>
            <div className="text-xs text-slate-600 truncate">
              {group.name}
              {group.vendor && <span className="text-slate-400"> · vendor {group.vendor}</span>}
            </div>
          </div>
          <div className="flex-shrink-0 flex items-center gap-1.5">
            <button
              onClick={() => onOpenLedger(group)}
              title="Ledger"
              className="text-[10px] uppercase tracking-wider font-bold text-slate-700 hover:text-white hover:bg-[#0F172A] border border-slate-300 px-2 py-1 flex items-center gap-1"
              data-testid={`ledger-${group.code}`}
            >
              <History className="w-3 h-3" /> Ledger
            </button>
            <button
              onClick={() => onAddMovement({ code: group.code, rows })}
              className="text-[10px] uppercase tracking-wider font-bold text-slate-700 hover:text-white hover:bg-[#0F172A] border border-slate-300 px-2 py-1 flex items-center gap-1"
              data-testid={`mv-${group.code}`}
            >
              <Plus className="w-3 h-3" /> Movement
            </button>
            <button
              onClick={() => onAddMatrix(group)}
              className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#C27842] hover:bg-[#0F172A] border border-[#C27842] hover:border-[#0F172A] px-2 py-1 flex items-center gap-1"
              data-testid={`bulk-${group.code}`}
            >
              <Upload className="w-3 h-3" /> Add Stock
            </button>
          </div>
        </div>
      </div>

      {/* matrix */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-2 py-1.5 text-left text-[10px] uppercase tracking-wider font-bold text-slate-500">Color</th>
              {sizes.map((s) => (
                <th key={s} className="px-2 py-1.5 text-center text-[10px] uppercase tracking-wider font-bold text-slate-500 whitespace-nowrap">{s}</th>
              ))}
              <th className="px-2 py-1.5 text-center text-[10px] uppercase tracking-wider font-bold bg-slate-800 text-white">Row Σ</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {colors.map((c) => (
              <tr key={c} className="hover:bg-slate-50/70">
                <td className="px-2 py-1.5 font-mono font-bold text-slate-800 whitespace-nowrap flex items-center gap-1.5">
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-full border border-slate-300"
                    style={{
                      background: c.toLowerCase() === "white" ? "#fff"
                                : c.toLowerCase() === "black" ? "#0F172A"
                                : c.toLowerCase() === "gold"  ? "#D4AF37"
                                : c.toLowerCase() === "silver"? "#C0C0C0"
                                : c.toLowerCase() === "tan"   ? "#D2B48C"
                                : c.toLowerCase() === "blue"  ? "#3B82F6"
                                : "#94A3B8"
                    }}
                  />
                  {c}
                </td>
                {sizes.map((s) => {
                  const row = cellMap[`${c}|${s}`];
                  const val = row ? Number(row[M.field] || 0) : null;
                  const isLow = row && Number(row.minimum_stock || 0) > 0
                    && Number(row.available_stock || 0) <= Number(row.minimum_stock || 0);
                  return (
                    <td key={s}
                      className={`px-2 py-1.5 text-center font-mono cursor-pointer ${
                        val == null ? "text-slate-300"
                        : isLow ? "bg-red-50 text-red-700 font-bold"
                        : val === 0 ? "text-slate-400"
                        : ""
                      }`}
                      onClick={() => row && onEditRow(row)}
                      title={row ? `Click to edit metadata — reserved ${row.reserved_stock}, min ${row.minimum_stock}, reorder ${row.reorder_level}` : "No row for this cell"}
                    >
                      {val == null ? "—" : inr0(val)}
                      {isLow && <sup className="text-red-500 ml-0.5">▲</sup>}
                    </td>
                  );
                })}
                <td className="px-2 py-1.5 text-center font-mono font-bold bg-slate-800 text-white">
                  {inr0(totals.byColor[c])}
                </td>
              </tr>
            ))}
            <tr className="bg-slate-100">
              <td className="px-2 py-1.5 font-mono font-bold text-[10px] uppercase tracking-wider text-slate-600">Col Σ</td>
              {sizes.map((s) => (
                <td key={s} className="px-2 py-1.5 text-center font-mono font-bold">{inr0(totals.bySize[s])}</td>
              ))}
              <td className="px-2 py-1.5 text-center font-mono font-bold bg-[#C27842] text-white">{inr0(totals.grand)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="px-3 py-2 border-t border-slate-100 flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-500">
        <span className="font-mono">{colors.length} colors × {sizes.length} sizes · {rows.length} rows</span>
        <span className="font-mono">
          <span className="text-slate-900">Current:{inr0(totalCurrent)}</span>{" "}
          <span className="text-blue-700">Rsv:{inr0(totalReserved)}</span>{" "}
          <span className="text-green-700">Avl:{inr0(totalAvail)}</span>
        </span>
      </div>
    </Card>
  );
}

/* ────────────────────────────────────────────────────────────
   MAIN PAGE
   ──────────────────────────────────────────────────────────── */
export default function ComponentInventory() {
  const [rows, setRows]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState("");
  const [category, setCategory] = useState("");
  const [metric, setMetric]     = useState("current");
  const [lowOnly, setLowOnly]   = useState(false);
  const [showBulk, setShowBulk] = useState(false);
  const [bulkPrefill, setBulkPrefill] = useState(null);
  const [showMovement, setShowMovement] = useState(false);
  const [movementInitial, setMovementInitial] = useState(null);
  const [ledger, setLedger] = useState(null);
  const [editRow, setEditRow] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (search)   p.append("search", search);
      if (category) p.append("category", category);
      if (lowOnly)  p.append("low_stock", "true");
      const qs = p.toString() ? `?${p}` : "";
      const r = await http.get(`/components${qs}`);
      setRows(r.data);
    } finally { setLoading(false); }
  }, [search, category, lowOnly]);

  useEffect(() => { load(); }, [load]);

  // Group by component_code
  const groups = useMemo(() => {
    const g = {};
    for (const r of rows) {
      if (!g[r.component_code]) {
        g[r.component_code] = {
          code:     r.component_code,
          name:     r.component_name,
          category: r.component_category,
          vendor:   r.vendor || "",
          rows:     [],
        };
      }
      g[r.component_code].rows.push(r);
    }
    return Object.values(g).sort((a, b) => a.code.localeCompare(b.code));
  }, [rows]);

  const stats = useMemo(() => {
    let cur = 0, rsv = 0, low = 0, byCat = {};
    for (const r of rows) {
      cur += Number(r.current_stock  || 0);
      rsv += Number(r.reserved_stock || 0);
      const isLow = Number(r.minimum_stock || 0) > 0
        && Number(r.available_stock || 0) <= Number(r.minimum_stock || 0);
      if (isLow) low += 1;
      byCat[r.component_category] = (byCat[r.component_category] || 0) + Number(r.current_stock || 0);
    }
    return { cur, rsv, avl: cur - rsv, low, byCat, codes: groups.length };
  }, [rows, groups.length]);

  return (
    <div className="bg-[#F7F7F5]">
      <PageHeader
        title="Component Inventory"
        subtitle="Global components — shared across styles. Every stock change is a ledger entry."
        testId="component-inventory-header"
        action={
          <div className="flex gap-2">
            <BtnSecondary onClick={load}>
              <span className="flex items-center gap-1.5"><RefreshCw className="w-4 h-4" /> Refresh</span>
            </BtnSecondary>
            <BtnPrimary onClick={() => { setBulkPrefill(null); setShowBulk(true); }} data-testid="btn-add-components">
              <span className="flex items-center gap-1.5"><Plus className="w-4 h-4" /> Add Components</span>
            </BtnPrimary>
          </div>
        }
      />

      <div className="px-4 sm:px-8 py-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatTile label="Component Codes"  value={stats.codes}         icon={Boxes}    accent="#0F172A" />
        <StatTile label="Current Stock"    value={inr0(stats.cur)}     icon={Package}  accent="#0F172A" />
        <StatTile label="Reserved"         value={inr0(stats.rsv)}     icon={Layers}   accent="#2563EB" />
        <StatTile label="Available"        value={inr0(stats.avl)}     icon={ShieldAlert} accent="#16A34A" />
        <StatTile label="Low-Stock Cells"  value={stats.low}           icon={AlertTriangle} accent={stats.low ? "#DC2626" : "#94A3B8"} />
      </div>

      {/* Filter + metric bar */}
      <div className="px-4 sm:px-8 py-3 bg-white border-y-2 border-slate-200 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[220px]">
          <Input label="Search" placeholder="Code, name, vendor…"
            value={search} onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            testId="component-search" />
        </div>
        <div className="w-52">
          <Select label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </Select>
        </div>
        <label className="flex items-center gap-2 pb-1.5 text-xs text-slate-700 font-bold">
          <input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} />
          <span className="uppercase tracking-wider">Low stock only</span>
        </label>
        <BtnSecondary onClick={load}>Apply</BtnSecondary>
        <button className="text-xs text-slate-400 hover:text-slate-700 underline pb-1.5"
          onClick={() => { setSearch(""); setCategory(""); setLowOnly(false); }}>Clear</button>

        <div className="ml-auto flex items-end gap-1.5">
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 pb-1.5">Metric</div>
          {Object.entries(METRICS).map(([k, m]) => (
            <button key={k} onClick={() => setMetric(k)}
              className={`px-2.5 py-1 text-[10px] uppercase tracking-wider font-bold border-2 ${
                metric === k ? "text-white border-transparent" : "text-slate-700 border-slate-300 hover:border-slate-500"
              }`}
              style={metric === k ? { backgroundColor: m.accent } : {}}
              data-testid={`metric-${k}`}
            >{m.label}</button>
          ))}
        </div>
      </div>

      {/* Groups */}
      <div className="p-4 sm:p-8 space-y-4">
        {loading ? (
          <div className="text-center py-20 text-slate-400">Loading components…</div>
        ) : groups.length === 0 ? (
          <Card className="p-10 text-center">
            <Package className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <div className="text-slate-500 font-semibold mb-1">No components yet.</div>
            <div className="text-xs text-slate-400">Click <span className="font-bold">Add Components</span> to create your first component with a color × size matrix.</div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {groups.map((g) => (
              <ComponentGroupCard
                key={g.code}
                group={g}
                metric={metric}
                onAddMovement={(payload) => { setMovementInitial({ component_id: payload.rows[0]?.id || "" }); setShowMovement(true); }}
                onOpenLedger={(group) => setLedger({ code: group.code, componentIds: group.rows.map((r) => r.id) })}
                onEditRow={setEditRow}
                onAddMatrix={(group) => { setBulkPrefill({
                  component_code: group.code,
                  component_name: group.name,
                  component_category: group.category,
                  vendor: group.vendor,
                }); setShowBulk(true); }}
              />
            ))}
          </div>
        )}
      </div>

      {showBulk && (
        <ComponentBulkDrawer
          prefill={bulkPrefill}
          existingCodes={[...new Set(rows.map((r) => r.component_code))]}
          onClose={() => setShowBulk(false)}
          onDone={() => { load(); setShowBulk(false); }}
        />
      )}
      {showMovement && (
        <MovementDrawer
          initial={movementInitial}
          components={rows}
          onClose={() => setShowMovement(false)}
          onDone={() => load()}
        />
      )}
      {ledger && (
        <LedgerDrawer code={ledger.code} componentIds={ledger.componentIds} onClose={() => setLedger(null)} />
      )}
      {editRow && (
        <EditMetadataDrawer row={editRow} onClose={() => setEditRow(null)} onDone={() => load()} />
      )}
    </div>
  );
}
