import { useEffect, useState, useCallback, useMemo } from "react";
import { http, formatApiError } from "../lib/api";
import {
  PageHeader, Card, BtnPrimary, BtnSecondary,
  Input, Select, Badge, StatTile,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import AddStockDrawer from "./AddStockDrawer";
import { SafeImage } from "../components/ImageUploader";
import {
  AlertTriangle, Plus, RefreshCw, Package, History,
  Boxes, ImageOff, ChevronDown, ChevronRight, Upload, Hammer,
} from "lucide-react";
import AdHocProduceDrawer from "../components/AdHocProduceDrawer";
import ResponsiveTable from "../components/ResponsiveTable";

// ────────────────────────────────────────────────────────────
//  Metric definitions — the cell value & the color accent
// ────────────────────────────────────────────────────────────
const METRICS = {
  ready:       { label: "Ready",       field: "ready_stock_qty", accent: "#16A34A" },
  reserved:    { label: "Reserved",    field: "reserved_qty",    accent: "#2563EB" },
  available:   { label: "Available",   field: "available_qty",   accent: "#0F172A" },
  in_transit:  { label: "In Transit",  field: "in_transit_qty",  accent: "#D97706" },
  return_qty:  { label: "Return",      field: "return_qty",      accent: "#EA580C" },
  damaged:     { label: "Damaged",     field: "damaged_qty",     accent: "#DC2626" },
  liquidation: { label: "Liquidation", field: "liquidation_qty", accent: "#7C3AED" },
};

const MOVEMENT_TYPES = [
  { value: "production_in",    label: "Production In",       hint: "+ ready stock" },
  { value: "dispatched",       label: "Dispatched",          hint: "- ready & reserved" },
  { value: "reserved",         label: "Reserved (manual)",   hint: "+ reserved" },
  { value: "unreserved",       label: "Unreserved",          hint: "- reserved" },
  { value: "return_in",        label: "Return In",           hint: "+ return_qty" },
  { value: "return_restocked", label: "Return Restocked",    hint: "- return_qty, + ready" },
  { value: "return_damaged",   label: "Return Damaged",      hint: "- return_qty, + damaged" },
  { value: "liquidation_out",  label: "Move to Liquidation", hint: "- ready, + liquidation" },
  { value: "adjustment",       label: "Manual Adjustment",   hint: "signed delta on one field" },
];

const ADJUSTMENT_FIELDS = [
  "ready_stock_qty", "reserved_qty", "in_transit_qty",
  "return_qty",     "damaged_qty",  "liquidation_qty",
];

const inr0 = (n) => new Intl.NumberFormat("en-IN").format(Number(n || 0));

// Sort sizes: numeric first (natural), then string
const sortSizes = (sizes) => [...sizes].sort((a, b) => {
  const na = parseFloat(a), nb = parseFloat(b);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  if (!isNaN(na)) return -1;
  if (!isNaN(nb)) return  1;
  return String(a).localeCompare(String(b));
});

// Convert "Silver" → "SS", "Gold" → "GLD", etc. — used as the "Clr Code" column.
const colorCode = (c) => {
  if (!c) return "";
  const clean = c.toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (clean.length <= 3) return clean;
  // First letter of each token, or first 3 chars.
  const parts = c.split(/\s+/);
  if (parts.length >= 2) return parts.map((p) => p[0]).join("").toUpperCase().slice(0, 3);
  return clean.slice(0, 3);
};

// ═══════════════════════════════════════════════════════════
//  MovementDrawer  (same as before, with prefill support)
// ═══════════════════════════════════════════════════════════
function MovementDrawer({ initial = null, styles = [], onClose, onDone }) {
  const [form, setForm] = useState({
    style_id:         initial?.style_id || "",
    color:            initial?.color || "",
    size:             initial?.size || "",
    movement_type:    "production_in",
    quantity:         0,
    reference_type:   "manual",
    reference_id:     "",
    notes:            "",
    adjustment_field: "ready_stock_qty",
    online_order_id:  "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState("");
  const [result, setResult] = useState(null);

  const needsOnlineOrder = ["reserved", "unreserved", "dispatched"].includes(form.movement_type);
  const isAdjustment    = form.movement_type === "adjustment";

  async function submit() {
    setError(""); setResult(null);
    if (!form.style_id)     return setError("Please select a style.");
    if (!form.color.trim()) return setError("Color is required.");
    if (!form.size.trim())  return setError("Size is required.");
    if (!isAdjustment && Number(form.quantity) <= 0)
      return setError("Quantity must be greater than zero.");
    setSaving(true);
    try {
      const body = {
        style_id:       form.style_id,
        color:          form.color.trim(),
        size:           form.size.trim(),
        movement_type:  form.movement_type,
        quantity:       Number(form.quantity),
        reference_type: form.reference_type,
        reference_id:   form.reference_id.trim(),
        notes:          form.notes.trim(),
      };
      if (isAdjustment) body.adjustment_field = form.adjustment_field;
      if (needsOnlineOrder && form.online_order_id.trim())
        body.online_order_id = form.online_order_id.trim();

      const r = await http.post("/fg-inventory/movements", body);
      setResult(r.data);
      onDone();
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Movement failed.");
    } finally { setSaving(false); }
  }

  const selectedType   = MOVEMENT_TYPES.find((m) => m.value === form.movement_type);
  const selectedStyle  = styles.find((s) => s.id === form.style_id);

  return (
    <Drawer onClose={onClose} title="Post FG Movement">
      <div className="space-y-5">
        <div className="bg-slate-100 border-2 border-slate-200 px-4 py-3 text-xs text-slate-700">
          <div className="font-bold uppercase tracking-wider text-[10px] text-slate-500 mb-1">
            Every write to fg_inventory is a ledger entry
          </div>
          The engine blocks any movement that would push a quantity below zero.
        </div>

        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Style *</div>
          <select
            data-testid="mv-style"
            className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            value={form.style_id}
            onChange={(e) => setForm({ ...form, style_id: e.target.value })}
          >
            <option value="">— Select style —</option>
            {styles.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
          </select>
          {selectedStyle && (
            <div className="text-[11px] text-slate-500 mt-1 font-mono">{selectedStyle.name}</div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Input label="Color *" testId="mv-color" value={form.color}
            onChange={(e) => setForm({ ...form, color: e.target.value })} placeholder="e.g. Silver" />
          <Input label="Size *"  testId="mv-size"  value={form.size}
            onChange={(e) => setForm({ ...form, size: e.target.value })}  placeholder="e.g. 8" />
        </div>

        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Movement Type *</div>
          <select
            data-testid="mv-type"
            className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            value={form.movement_type}
            onChange={(e) => setForm({ ...form, movement_type: e.target.value })}
          >
            {MOVEMENT_TYPES.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
          {selectedType && (
            <div className="text-[11px] text-slate-500 mt-1 font-mono">{selectedType.hint}</div>
          )}
        </div>

        {isAdjustment && (
          <Select label="Adjustment Field *" testId="mv-field"
            value={form.adjustment_field}
            onChange={(e) => setForm({ ...form, adjustment_field: e.target.value })}>
            {ADJUSTMENT_FIELDS.map((f) => <option key={f} value={f}>{f}</option>)}
          </Select>
        )}

        <Input
          label={isAdjustment ? "Signed Delta (can be negative)" : "Quantity *"}
          testId="mv-qty"
          type="number"
          value={form.quantity}
          onChange={(e) => setForm({ ...form, quantity: e.target.value })}
        />

        {needsOnlineOrder && (
          <Input label="Online Order ID (optional)" testId="mv-order-id"
            placeholder="Links to inventory_reservations"
            value={form.online_order_id}
            onChange={(e) => setForm({ ...form, online_order_id: e.target.value })} />
        )}

        <div className="grid grid-cols-2 gap-3">
          <Select label="Reference Type" value={form.reference_type}
            onChange={(e) => setForm({ ...form, reference_type: e.target.value })}>
            <option value="manual">Manual</option>
            <option value="job">Job</option>
            <option value="online_order">Online Order</option>
            <option value="return">Return</option>
          </Select>
          <Input label="Reference ID" value={form.reference_id}
            onChange={(e) => setForm({ ...form, reference_id: e.target.value })} />
        </div>

        <Input label="Notes" value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })} />

        {error && (
          <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold">
            {error}
          </div>
        )}

        {result && (
          <div className="bg-green-50 border-2 border-green-300 px-4 py-3 text-sm text-green-800">
            <div className="font-bold">✓ Movement posted</div>
            <div className="font-mono text-xs mt-1">
              delta: {JSON.stringify(result.movement.delta)}
            </div>
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <BtnPrimary onClick={submit} disabled={saving} className="flex-1" id="btn-post-movement">
            {saving ? "Posting…" : "Post Movement"}
          </BtnPrimary>
          <BtnSecondary onClick={onClose} disabled={saving}>Close</BtnSecondary>
        </div>
      </div>
    </Drawer>
  );
}

// ═══════════════════════════════════════════════════════════
//  Ledger Drawer
// ═══════════════════════════════════════════════════════════
function LedgerDrawer({ styleId, styleCode, onClose }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (styleId)   p.append("style_id", styleId);
      if (filterType) p.append("movement_type", filterType);
      p.append("limit", "500");
      const r = await http.get(`/fg-inventory/movements?${p}`);
      setRows(r.data);
    } finally { setLoading(false); }
  }, [styleId, filterType]);

  useEffect(() => { load(); }, [load]);

  return (
    <Drawer onClose={onClose} title={`Movement Ledger${styleCode ? ` — ${styleCode}` : ""}`}>
      <div className="space-y-3">
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Select label="Filter by Type" value={filterType}
              onChange={(e) => setFilterType(e.target.value)}>
              <option value="">All Types</option>
              {MOVEMENT_TYPES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </Select>
          </div>
          <BtnSecondary onClick={load}>
            <span className="flex items-center gap-1"><RefreshCw className="w-3 h-3" /> Refresh</span>
          </BtnSecondary>
        </div>

        {loading ? (
          <div className="text-center py-10 text-slate-400 text-sm">Loading ledger…</div>
        ) : rows.length === 0 ? (
          <div className="text-center py-10 text-slate-400 text-sm">No movements yet.</div>
        ) : (
          <div className="border border-slate-200 max-h-[70vh] overflow-y-auto">
            <ResponsiveTable
              columns={[
                {
                  key: "created_at",
                  header: "Time",
                  primary: true,
                  className: "font-mono text-[10px] text-slate-500 whitespace-nowrap",
                  render: (r) => r.created_at?.slice(0, 19).replace("T", " ") || "—",
                },
                {
                  key: "style_code",
                  header: "Style",
                  primary: true,
                  className: "font-mono font-bold text-slate-900",
                  render: (r) => r.style_code,
                },
                {
                  key: "color",
                  header: "Color",
                  render: (r) => r.color,
                },
                {
                  key: "size",
                  header: "Size",
                  render: (r) => r.size,
                },
                {
                  key: "movement_type",
                  header: "Type",
                  render: (r) => (
                    <Badge color={
                      r.movement_type === "production_in"  ? "green"  :
                      r.movement_type === "dispatched"     ? "blue"   :
                      r.movement_type === "return_damaged" ? "red"    :
                      r.movement_type === "adjustment"     ? "yellow" : "slate"
                    }>{r.movement_type}</Badge>
                  ),
                },
                {
                  key: "quantity",
                  header: "Qty",
                  className: "font-mono font-bold",
                  render: (r) => r.quantity,
                },
                {
                  key: "delta",
                  header: "Delta",
                  className: "font-mono text-[10px] text-slate-600",
                  render: (r) => r.delta ? (
                    <div className="space-y-0.5">
                      {Object.entries(r.delta).map(([k, v]) => (
                        <div key={k}>
                          <span className="text-slate-400">{k.replace("_qty", "")}</span>{" "}
                          <span className={v > 0 ? "text-green-700" : "text-red-700"}>
                            {v > 0 ? `+${v}` : v}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : "—",
                },
                {
                  key: "reference",
                  header: "Ref",
                  className: "font-mono text-[10px] text-slate-500",
                  render: (r) => `${r.reference_type}${r.reference_id ? ` · ${r.reference_id}` : ""}`,
                },
                {
                  key: "by",
                  header: "By",
                  className: "font-mono text-[10px] text-slate-500",
                  render: (r) => r.by,
                },
              ]}
              rows={rows}
              rowKey={(r) => r.id}
              stickyHeader
              testId="ledger-table"
            />
          </div>
        )}
      </div>
    </Drawer>
  );
}

// ═══════════════════════════════════════════════════════════
//  Style Inventory Card — mirrors ProductionFloor ColorGroupCard
//  Matrix layout matches the PO PDF:
//    Rows    = Colors  (with Clr Code)
//    Columns = Sizes
//    Bottom  = Column totals (per size, across all colors)
//    Right   = Row totals    (per color, across all sizes)
//    Corner  = Grand total
// ═══════════════════════════════════════════════════════════
function StyleInventoryCard({ style, rows, metric, onCellClick, onAddMovement, onAddStock, onOpenLedger }) {
  const M = METRICS[metric];

  // Build (color, size) → row lookup and axes
  const { colors, sizes, cellMap, totals } = useMemo(() => {
    const cellMap = {};
    const colorSet = new Set();
    const sizeSet  = new Set();
    for (const r of rows) {
      colorSet.add(r.color || "—");
      sizeSet.add(r.size || "—");
      cellMap[`${r.color}|${r.size}`] = r;
    }
    const colors = Array.from(colorSet).sort();
    const sizes  = sortSizes(Array.from(sizeSet));

    const totals = {
      byColor:  {},   // color → sum over sizes
      bySize:   {},   // size  → sum over colors
      grand:    0,
      lowCells: 0,
      byColorReady:    {},  // used to compute row-level low flag
      byColorMinTotal: {},
    };
    for (const c of colors) {
      totals.byColor[c]         = 0;
      totals.byColorReady[c]    = 0;
      totals.byColorMinTotal[c] = 0;
    }
    for (const s of sizes) totals.bySize[s] = 0;

    for (const r of rows) {
      const v = Number(r[M.field] || 0);
      totals.byColor[r.color] = (totals.byColor[r.color] || 0) + v;
      totals.bySize[r.size]   = (totals.bySize[r.size]   || 0) + v;
      totals.grand            += v;
      if (r.is_low_stock) totals.lowCells++;
      totals.byColorReady[r.color]    += Number(r.ready_stock_qty || 0);
      totals.byColorMinTotal[r.color] += Number(r.min_stock_level || 0);
    }
    return { colors, sizes, cellMap, totals };
  }, [rows, M.field]);

  const hasData = colors.length > 0 && sizes.length > 0;

  return (
    <Card
      className={`border-l-4 hover:border-[#C27842] transition-colors ${totals.lowCells > 0 ? "ring-2 ring-red-500 ring-inset" : ""}`}
      style={{ borderLeftColor: M.accent }}
      data-testid={`style-card-${style.code}`}
    >
      {/* Low-stock banner strip */}
      {totals.lowCells > 0 && (
        <div className="bg-red-600 text-white px-3 py-1 flex items-center justify-between text-[10px] uppercase tracking-wider font-bold">
          <span className="flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> Low Stock</span>
          <span className="font-mono">{totals.lowCells} cell(s) below min</span>
        </div>
      )}

      {/* Header: image, style code, name, action buttons */}
      {style.image_url || style.image_display_url || style.image_thumbnail_url ? (
        <SafeImage
          image={{
            url: style.image_url,
            display_url: style.image_display_url,
            thumbnail_url: style.image_thumbnail_url,
          }}
          alt={style.name}
          aspectRatio="16/7"
          className="border-b border-slate-200"
          testId={`ready-stock-img-${style.code || style.style_code}`}
        />
      ) : (
        <div className="h-16 bg-slate-50 border-b border-slate-200 flex items-center justify-center">
          <ImageOff className="w-6 h-6 text-slate-300" />
        </div>
      )}

      <div className="p-3 pb-2 border-b border-slate-100">
        <div className="flex items-baseline justify-between mb-0.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">FG Inventory</div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">
            metric · <span className="text-slate-900">{M.label}</span>
          </div>
        </div>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-mono font-bold text-sm truncate">{style.code}</div>
            <div className="text-xs text-slate-600 truncate">{style.name}</div>
          </div>
          <div className="flex-shrink-0 flex items-center gap-2">
            <button
              onClick={() => onOpenLedger(style)}
              title="Movement ledger for this style"
              className="text-[10px] uppercase tracking-wider font-bold text-slate-700 hover:text-white hover:bg-[#0F172A] border border-slate-300 px-2 py-1 flex items-center gap-1"
              data-testid={`ledger-${style.code}`}
            >
              <History className="w-3 h-3" /> Ledger
            </button>
            <button
              onClick={() => onAddMovement({ style_id: style.id })}
              title="Post a single movement for this style"
              className="text-[10px] uppercase tracking-wider font-bold text-slate-700 hover:text-white hover:bg-[#0F172A] border border-slate-300 px-2 py-1 flex items-center gap-1"
              data-testid={`add-mv-${style.code}`}
            >
              <Plus className="w-3 h-3" /> Movement
            </button>
            <button
              onClick={() => onAddStock(style.id)}
              title="Add stock in bulk (matrix or CSV)"
              className="text-[10px] uppercase tracking-wider font-bold text-white bg-[#C27842] hover:bg-[#0F172A] border border-[#C27842] hover:border-[#0F172A] px-2 py-1 flex items-center gap-1"
              data-testid={`add-stock-${style.code}`}
            >
              <Upload className="w-3 h-3" /> Add Stock
            </button>
          </div>
        </div>
      </div>

      {/* Color × Size matrix (mirrors PO layout) */}
      <div className="p-3 overflow-x-auto">
        {!hasData ? (
          <div className="text-center py-8 text-xs text-slate-400 italic">
            No FG rows yet — post a movement to seed the first (color × size) cell.
          </div>
        ) : (
          <table className="w-full text-xs border border-slate-300" data-testid={`matrix-${style.code}`}>
            <thead className="bg-slate-100">
              <tr>
                <th className="px-2 py-1.5 text-left text-[10px] uppercase tracking-wider font-bold text-slate-700 border-r border-slate-300">
                  Color
                </th>
                <th className="px-2 py-1.5 text-center text-[10px] uppercase tracking-wider font-bold text-slate-500 border-r border-slate-300 w-14">
                  Clr Code
                </th>
                {sizes.map((sz) => (
                  <th
                    key={sz}
                    className="px-2 py-1.5 text-center font-mono text-[11px] font-bold text-slate-700 border-r border-slate-300 min-w-[52px]"
                  >
                    {sz}
                  </th>
                ))}
                <th className="px-2 py-1.5 text-right text-[10px] uppercase tracking-wider font-bold text-slate-900 bg-slate-200">
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {colors.map((clr) => {
                const rowLow = totals.byColorReady[clr] < totals.byColorMinTotal[clr] &&
                               totals.byColorMinTotal[clr] > 0;
                return (
                  <tr key={clr} className="border-t border-slate-300 hover:bg-slate-50/50">
                    <td className="px-2 py-1.5 font-bold text-slate-800 border-r border-slate-300 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="inline-block w-2.5 h-2.5 rounded-full border border-slate-300"
                          style={{ background: cssColor(clr) }}
                          title={clr}
                        />
                        {clr}
                      </div>
                    </td>
                    <td className="px-2 py-1.5 text-center font-mono text-[10px] text-slate-500 border-r border-slate-300">
                      {colorCode(clr)}
                    </td>
                    {sizes.map((sz) => {
                      const r = cellMap[`${clr}|${sz}`];
                      if (!r) {
                        return (
                          <td key={sz} className="px-1 py-1 text-center border-r border-slate-300">
                            <button
                              onClick={() => onCellClick({ style_id: style.id, color: clr, size: sz, row: null })}
                              className="w-full h-full py-1 text-slate-300 hover:text-slate-700 hover:bg-slate-50 font-mono"
                              title={`Seed ${clr} / ${sz}`}
                              data-testid={`cell-empty-${style.code}-${clr}-${sz}`}
                            >
                              —
                            </button>
                          </td>
                        );
                      }
                      const v = Number(r[M.field] || 0);
                      const low = r.is_low_stock;
                      return (
                        <td key={sz} className={`px-0 py-0 text-center border-r border-slate-300 ${low ? "bg-red-50" : ""}`}>
                          <button
                            onClick={() => onCellClick({ style_id: style.id, color: clr, size: sz, row: r })}
                            className={`w-full h-full py-1.5 px-2 font-mono font-bold hover:bg-[#0F172A]/5 relative ${v === 0 ? "text-slate-400" : ""}`}
                            style={{ color: v > 0 && !low ? M.accent : undefined }}
                            title={
`Ready:       ${r.ready_stock_qty}
Reserved:    ${r.reserved_qty}
Available:   ${r.available_qty}
In-Transit:  ${r.in_transit_qty || 0}
Return:      ${r.return_qty || 0}
Damaged:     ${r.damaged_qty || 0}
Liquidation: ${r.liquidation_qty || 0}
Min level:   ${r.min_stock_level}${low ? "\n⚠  LOW STOCK" : ""}`
                            }
                            data-testid={`cell-${style.code}-${clr}-${sz}`}
                          >
                            {v}
                            {low && (
                              <span className="absolute top-0 right-0 text-[7px] font-bold text-red-600 leading-none mt-0.5 mr-0.5">▲</span>
                            )}
                          </button>
                        </td>
                      );
                    })}
                    <td className={`px-2 py-1.5 text-right font-mono font-bold bg-[#0F172A] text-[#C27842] ${rowLow ? "border-l-2 border-red-500" : ""}`}>
                      {inr0(totals.byColor[clr])}
                    </td>
                  </tr>
                );
              })}
              {/* TOTAL row */}
              <tr className="border-t-2 border-slate-400 bg-slate-100">
                <td className="px-2 py-1.5 font-bold text-[10px] uppercase tracking-wider text-slate-900 border-r border-slate-300">
                  Total
                </td>
                <td className="px-2 py-1.5 border-r border-slate-300"></td>
                {sizes.map((sz) => (
                  <td key={sz} className="px-2 py-1.5 text-center font-mono font-bold text-slate-900 border-r border-slate-300">
                    {inr0(totals.bySize[sz] || 0)}
                  </td>
                ))}
                <td className="px-2 py-1.5 text-right font-mono font-bold bg-[#C27842] text-white">
                  {inr0(totals.grand)}
                </td>
              </tr>
            </tbody>
          </table>
        )}
      </div>

      {/* Foot strip — quick stats & actions */}
      <div className="px-3 pb-3 pt-1 flex items-center justify-between gap-2 flex-wrap border-t border-slate-100 bg-slate-50/60">
        <div className="text-[10px] text-slate-500 flex items-center gap-2 font-mono">
          <Boxes className="w-3 h-3" />
          {colors.length} colors × {sizes.length} sizes
          <span className="text-slate-300">·</span>
          <span className="text-slate-700">{rows.length} rows</span>
        </div>
        <div className="text-[10px] text-slate-500 flex items-center gap-3 font-mono">
          <span className="text-green-700">Ready:{inr0(rows.reduce((s, r) => s + Number(r.ready_stock_qty || 0), 0))}</span>
          <span className="text-blue-700">Rsv:{inr0(rows.reduce((s, r) => s + Number(r.reserved_qty || 0), 0))}</span>
          <span className="text-slate-900 font-bold">Avl:{inr0(rows.reduce((s, r) => s + Number(r.available_qty || 0), 0))}</span>
        </div>
      </div>
    </Card>
  );
}

// Best-effort CSS color from a common color name — for the tiny swatch dot.
function cssColor(name) {
  const map = {
    silver: "#C0C0C0", gold: "#D4AF37", black: "#111", white: "#F5F5F5",
    tan: "#C89A6B", brown: "#7B4F2A", cognac: "#9A5B32", beige: "#D8C7A6",
    navy: "#0F1E4A", blue: "#2563EB", red: "#DC2626", green: "#16A34A",
    grey: "#6B7280", gray: "#6B7280", cream: "#F1E7CE",
  };
  const key = String(name || "").toLowerCase().trim();
  return map[key] || "#E5E7EB";
}

// ═══════════════════════════════════════════════════════════
//  Main Page
// ═══════════════════════════════════════════════════════════
export default function ReadyStock() {
  const [rows, setRows]           = useState([]);
  const [stylesMeta, setStylesMeta] = useState({});
  const [loading, setLoading]     = useState(true);
  const [search, setSearch]       = useState("");
  const [lowOnly, setLowOnly]     = useState(false);
  const [metric, setMetric]       = useState("ready");
  const [mvOpen, setMvOpen]       = useState(false);
  const [mvInitial, setMvInitial] = useState(null);
  const [addStockOpen, setAddStockOpen]       = useState(false);
  const [addStockStyleId, setAddStockStyleId] = useState("");
  const [produceOpen, setProduceOpen]         = useState(false);
  const [produceStyle, setProduceStyle]       = useState(null);   // resolved style object
  const [ledger, setLedger]       = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (lowOnly) p.append("low_stock", "true");
      if (search)  p.append("search", search);
      const qs = p.toString() ? `?${p}` : "";
      const r = await http.get(`/fg-inventory${qs}`);
      setRows(r.data);
    } finally { setLoading(false); }
  }, [lowOnly, search]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    http.get("/styles").then((r) => {
      const m = {};
      r.data.forEach((s) => { m[s.id] = s; });
      setStylesMeta(m);
    }).catch(() => {});
  }, []);

  // Group by style_id
  const grouped = useMemo(() => {
    const map = new Map();
    for (const r of rows) {
      const key = r.style_id;
      if (!map.has(key)) map.set(key, { style_id: key, style_code: r.style_code, rows: [] });
      map.get(key).rows.push(r);
    }
    const arr = Array.from(map.values()).map((g) => {
      const meta = stylesMeta[g.style_id] || {};
      return {
        style: {
          id:        g.style_id,
          code:      g.style_code,
          name:      meta.name      || g.style_code,
          image_url: meta.image_url || "",
          image_display_url:   meta.image_display_url   || "",
          image_thumbnail_url: meta.image_thumbnail_url || "",
        },
        rows: g.rows,
      };
    });
    // Sort by style code
    arr.sort((a, b) => String(a.style.code).localeCompare(String(b.style.code)));
    return arr;
  }, [rows, stylesMeta]);

  // Aggregate stats for the top bar
  const totals = useMemo(() => {
    const t = { styles: new Set(), ready: 0, reserved: 0, available: 0,
                damaged: 0, liquidation: 0, in_transit: 0, low_rows: 0 };
    for (const r of rows) {
      t.styles.add(r.style_id);
      t.ready       += Number(r.ready_stock_qty  || 0);
      t.reserved    += Number(r.reserved_qty     || 0);
      t.available   += Number(r.available_qty    || 0);
      t.damaged     += Number(r.damaged_qty      || 0);
      t.liquidation += Number(r.liquidation_qty  || 0);
      t.in_transit  += Number(r.in_transit_qty   || 0);
      if (r.is_low_stock) t.low_rows++;
    }
    return t;
  }, [rows]);

  const stylesList = useMemo(() => Object.values(stylesMeta), [stylesMeta]);

  return (
    <div className="bg-[#F7F7F5]">
      <PageHeader
        title="Ready Stock"
        subtitle="Finished Goods Inventory — style-wise color × size matrix"
        testId="ready-stock-header"
        action={
          <div className="flex gap-2">
            <BtnSecondary id="btn-refresh-fg" onClick={load}>
              <span className="flex items-center gap-1.5"><RefreshCw className="w-4 h-4" /> Refresh</span>
            </BtnSecondary>
            <BtnSecondary id="btn-open-ledger" onClick={() => setLedger({ style_id: null, style_code: null })}>
              <span className="flex items-center gap-1.5"><History className="w-4 h-4" /> Full Ledger</span>
            </BtnSecondary>
            <BtnSecondary id="btn-add-movement" onClick={() => { setMvInitial(null); setMvOpen(true); }}>
              <span className="flex items-center gap-1.5"><Plus className="w-4 h-4" /> Movement</span>
            </BtnSecondary>
            <BtnSecondary id="btn-produce-stock" onClick={() => setProduceOpen(true)}>
              <span className="flex items-center gap-1.5"><Hammer className="w-4 h-4" /> Produce &amp; Add</span>
            </BtnSecondary>
            <BtnPrimary id="btn-add-stock" onClick={() => { setAddStockStyleId(""); setAddStockOpen(true); }}>
              <span className="flex items-center gap-2"><Upload className="w-4 h-4" /> Add Stock</span>
            </BtnPrimary>
          </div>
        }
      />

      {/* Stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 sm:gap-4 px-4 sm:px-8 py-5">
        <StatTile label="Styles" value={totals.styles.size} accent="#0F172A" />
        <StatTile label="Ready" value={inr0(totals.ready)} accent="#16A34A" />
        <StatTile label="Reserved" value={inr0(totals.reserved)} accent="#2563EB" />
        <StatTile label="Available" value={inr0(totals.available)} accent="#C27842" />
        <StatTile label="In-Transit" value={inr0(totals.in_transit)} accent="#D97706" />
        <StatTile label="Damaged" value={inr0(totals.damaged)} accent="#DC2626" />
        <StatTile label="Low-Stock" value={totals.low_rows} accent="#DC2626" testId="stat-low-rows" />
      </div>

      {/* Filter + metric toggle bar */}
      <div className="px-4 sm:px-8 py-3 bg-white border-y-2 border-slate-200 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[240px]">
          <Input label="Search" testId="search-fg" placeholder="Style code, color, size…"
            value={search} onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()} />
        </div>
        <label className="flex items-center gap-2 text-xs font-bold text-slate-700 pb-2">
          <input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)}
            className="accent-red-600" data-testid="chk-low-only" />
          Low-stock only
        </label>
        <BtnSecondary onClick={load}>Apply</BtnSecondary>
        <button
          className="text-xs text-slate-400 hover:text-slate-700 underline pb-1.5"
          onClick={() => { setSearch(""); setLowOnly(false); }}
        >Clear</button>

        {/* Metric selector — determines what cell values show across all cards */}
        <div className="ml-auto flex items-end gap-1 flex-wrap" data-testid="metric-toggle">
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500 pb-1 mr-2">
            View metric:
          </div>
          {Object.entries(METRICS).map(([k, m]) => (
            <button
              key={k}
              onClick={() => setMetric(k)}
              data-testid={`metric-${k}`}
              className={`text-[10px] uppercase tracking-wider font-bold px-2.5 py-1 border-2 transition-colors ${
                metric === k
                  ? "text-white border-[#0F172A]"
                  : "text-slate-600 border-slate-200 bg-white hover:border-slate-400"
              }`}
              style={metric === k ? { background: m.accent, borderColor: m.accent } : {}}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="px-4 sm:px-8 py-6">
        {loading ? (
          <div className="text-center py-20 text-slate-400">Loading finished-goods inventory…</div>
        ) : grouped.length === 0 ? (
          <Card className="p-10 text-center">
            <Package className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <div className="text-slate-500 font-semibold mb-1">No finished-goods rows yet.</div>
            <div className="text-xs text-slate-400 mb-4">
              Seed inventory via the Add Stock drawer (matrix entry or CSV upload), or post a single movement.
            </div>
            <div className="flex gap-2 justify-center">
              <BtnPrimary onClick={() => { setAddStockStyleId(""); setAddStockOpen(true); }}>
                <span className="flex items-center gap-2"><Upload className="w-4 h-4" /> Add Stock in Bulk</span>
              </BtnPrimary>
              <BtnSecondary onClick={() => { setMvInitial(null); setMvOpen(true); }}>
                <span className="flex items-center gap-2"><Plus className="w-4 h-4" /> Single Movement</span>
              </BtnSecondary>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-5" data-testid="style-cards-grid">
            {grouped.map((g) => (
              <StyleInventoryCard
                key={g.style.id}
                style={g.style}
                rows={g.rows}
                metric={metric}
                onCellClick={(sel) => { setMvInitial(sel); setMvOpen(true); }}
                onAddMovement={(sel) => { setMvInitial(sel); setMvOpen(true); }}
                onAddStock={(sid) => { setAddStockStyleId(sid); setAddStockOpen(true); }}
                onOpenLedger={(style) => setLedger({ style_id: style.id, style_code: style.code })}
              />
            ))}
          </div>
        )}
      </div>

      {mvOpen && (
        <MovementDrawer
          initial={mvInitial}
          styles={stylesList}
          onClose={() => setMvOpen(false)}
          onDone={() => load()}
        />
      )}
      {addStockOpen && (
        <AddStockDrawer
          styles={stylesList}
          initialStyleId={addStockStyleId}
          onClose={() => setAddStockOpen(false)}
          onDone={() => load()}
        />
      )}
      {ledger && (
        <LedgerDrawer
          styleId={ledger.style_id}
          styleCode={ledger.style_code}
          onClose={() => setLedger(null)}
        />
      )}

      {produceOpen && !produceStyle && (
        <StylePicker
          styles={stylesList}
          title="Pick a style to produce"
          onPick={(s) => setProduceStyle(s)}
          onClose={() => setProduceOpen(false)}
        />
      )}
      {produceStyle && (
        <AdHocProduceDrawer
          style={produceStyle}
          hasBom={true}
          onClose={() => { setProduceStyle(null); setProduceOpen(false); }}
          onDone={() => { setProduceStyle(null); setProduceOpen(false); load(); }}
          onEditBom={() => {
            // No inline BOM editor here — direct the operator to the Styles master.
            window.alert(
              "Open the Styles master and click the wrench icon on " +
              produceStyle.code + " to edit its Production Card, then come back."
            );
          }}
        />
      )}
    </div>
  );
}


// A minimal, keyboard-friendly style picker. Reused here since Ready Stock's
// Produce flow is the ONE place where the operator picks the style up front —
// most other flows already have the style in-context.
function StylePicker({ styles, title, onPick, onClose }) {
  const [q, setQ] = useState("");
  const filtered = (styles || []).filter((s) => {
    const term = q.trim().toLowerCase();
    if (!term) return true;
    return (s.code || "").toLowerCase().includes(term) || (s.name || "").toLowerCase().includes(term);
  }).slice(0, 60);
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose} data-testid="style-picker">
      <div className="bg-white w-full max-w-lg border-2 border-slate-900 shadow-ind-lg" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-3 border-b-2 border-slate-900 bg-slate-50 flex items-center justify-between">
          <div className="font-black">{title}</div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-900">×</button>
        </div>
        <div className="p-4 space-y-3">
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by code or name…"
            className="w-full border-2 border-slate-300 px-3 py-2 text-sm"
            data-testid="style-picker-search"
          />
          <div className="max-h-[50vh] overflow-y-auto border-2 border-slate-200 divide-y divide-slate-200">
            {filtered.length === 0 ? (
              <div className="p-4 text-center text-slate-400 text-sm">No matching styles.</div>
            ) : filtered.map((s) => (
              <button
                key={s.style_id || s.id}
                onClick={() => onPick({
                  id: s.style_id || s.id,
                  code: s.code || s.style_code || "—",
                  name: s.name || s.style_name || "",
                  image_url: s.image_url,
                  image_display_url: s.image_display_url,
                  image_thumbnail_url: s.image_thumbnail_url,
                })}
                className="w-full text-left px-3 py-2 hover:bg-slate-50 flex items-center gap-3"
                data-testid={`style-pick-${s.code || s.style_code}`}
              >
                <SafeImage
                  image={{ url: s.image_url, display_url: s.image_display_url, thumbnail_url: s.image_thumbnail_url }}
                  alt={s.code}
                  aspectRatio="1/1"
                  className="w-10 h-10 flex-shrink-0"
                />
                <div className="min-w-0">
                  <div className="font-mono font-bold text-sm">{s.code || s.style_code}</div>
                  <div className="text-xs text-slate-500 truncate">{s.name || s.style_name}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
