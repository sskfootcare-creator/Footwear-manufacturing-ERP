import { useEffect, useState, useCallback, useMemo } from "react";
import { http, formatApiError } from "../lib/api";
import {
  PageHeader, Card, BtnPrimary, BtnSecondary,
  Input, Select, Badge, StatTile,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import {
  Boxes, AlertTriangle, Plus, RefreshCw, Search, ChevronDown, ChevronRight,
  ArrowDownCircle, ArrowUpCircle, Package, History,
} from "lucide-react";

const MOVEMENT_TYPES = [
  { value: "production_in",    label: "Production In",     hint: "+ ready stock" },
  { value: "dispatched",       label: "Dispatched",        hint: "- ready & reserved" },
  { value: "reserved",         label: "Reserved (manual)", hint: "+ reserved" },
  { value: "unreserved",       label: "Unreserved",        hint: "- reserved" },
  { value: "return_in",        label: "Return In",         hint: "+ return_qty (pending inspection)" },
  { value: "return_restocked", label: "Return Restocked",  hint: "- return_qty, + ready" },
  { value: "return_damaged",   label: "Return Damaged",    hint: "- return_qty, + damaged" },
  { value: "liquidation_out",  label: "Move to Liquidation", hint: "- ready, + liquidation" },
  { value: "adjustment",       label: "Manual Adjustment", hint: "signed delta on one field" },
];

const ADJUSTMENT_FIELDS = [
  "ready_stock_qty", "reserved_qty", "in_transit_qty",
  "return_qty",     "damaged_qty",  "liquidation_qty",
];

const COL_ACCENT = {
  ready:        "bg-green-50  text-green-800  border-green-200",
  reserved:     "bg-blue-50   text-blue-800   border-blue-200",
  available:    "bg-slate-100 text-slate-900  border-slate-300 font-bold",
  in_transit:   "bg-amber-50  text-amber-800  border-amber-200",
  return_qty:   "bg-orange-50 text-orange-800 border-orange-200",
  damaged:      "bg-red-50    text-red-800    border-red-200",
  liquidation:  "bg-purple-50 text-purple-800 border-purple-200",
};

const inr0 = (n) => new Intl.NumberFormat("en-IN").format(Number(n || 0));

// ── Movement drawer ───────────────────────────────────────
function MovementDrawer({ initial = null, onClose, onDone }) {
  const [styles, setStyles]   = useState([]);
  const [form, setForm]       = useState({
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
  const [saving, setSaving]   = useState(false);
  const [error,  setError]    = useState("");
  const [result, setResult]   = useState(null);

  useEffect(() => {
    http.get("/styles").then((r) => setStyles(r.data));
  }, []);

  const needsOnlineOrder = ["reserved", "unreserved", "dispatched"].includes(form.movement_type);
  const isAdjustment    = form.movement_type === "adjustment";

  async function submit() {
    setError(""); setResult(null);
    if (!form.style_id)     return setError("Please select a style.");
    if (!form.color.trim()) return setError("Color is required.");
    if (!form.size.trim())  return setError("Size is required.");
    if (!isAdjustment && Number(form.quantity) <= 0) return setError("Quantity must be greater than zero.");
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
      if (isAdjustment)     body.adjustment_field = form.adjustment_field;
      if (needsOnlineOrder && form.online_order_id.trim())
        body.online_order_id = form.online_order_id.trim();

      const r = await http.post("/fg-inventory/movements", body);
      setResult(r.data);
      onDone();
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Movement failed.");
    } finally { setSaving(false); }
  }

  const selectedType = MOVEMENT_TYPES.find((m) => m.value === form.movement_type);

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
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Input label="Color *" testId="mv-color" value={form.color}
            onChange={(e) => setForm({ ...form, color: e.target.value })} placeholder="e.g. Tan" />
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

// ── Ledger drawer ─────────────────────────────────────────
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
          <div className="overflow-x-auto max-h-[70vh] overflow-y-auto border border-slate-200">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-50 border-b-2 border-slate-200">
                <tr className="text-left">
                  {["Time", "Style", "Color", "Size", "Type", "Qty", "Delta", "Ref", "By"].map((h) => (
                    <th key={h} className="px-2 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50">
                    <td className="px-2 py-2 font-mono text-[10px] text-slate-500 whitespace-nowrap">
                      {r.created_at?.slice(0, 19).replace("T", " ")}
                    </td>
                    <td className="px-2 py-2 font-mono font-bold text-slate-900">{r.style_code}</td>
                    <td className="px-2 py-2">{r.color}</td>
                    <td className="px-2 py-2">{r.size}</td>
                    <td className="px-2 py-2">
                      <Badge color={
                        r.movement_type === "production_in" ? "green" :
                        r.movement_type === "dispatched"    ? "blue"  :
                        r.movement_type === "return_damaged" ? "red"  :
                        r.movement_type === "adjustment"    ? "yellow" : "slate"
                      }>{r.movement_type}</Badge>
                    </td>
                    <td className="px-2 py-2 font-mono font-bold">{r.quantity}</td>
                    <td className="px-2 py-2 font-mono text-[10px] text-slate-600">
                      {r.delta ? Object.entries(r.delta).map(([k, v]) => (
                        <div key={k}><span className="text-slate-400">{k.replace("_qty","")}</span>{" "}<span className={v > 0 ? "text-green-700" : "text-red-700"}>{v > 0 ? `+${v}` : v}</span></div>
                      )) : "—"}
                    </td>
                    <td className="px-2 py-2 font-mono text-[10px] text-slate-500">
                      {r.reference_type}{r.reference_id ? ` · ${r.reference_id}` : ""}
                    </td>
                    <td className="px-2 py-2 font-mono text-[10px] text-slate-500">{r.by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Drawer>
  );
}

// ── Style expandable row (color × size matrix) ────────────
function StyleGroup({ style, rows, colors, sizes, onAdd, onOpenLedger }) {
  const [open, setOpen] = useState(true);

  const getRow = (color, size) =>
    rows.find((r) => r.color === color && r.size === size);

  const totals = rows.reduce((acc, r) => {
    acc.ready       += Number(r.ready_stock_qty || 0);
    acc.reserved    += Number(r.reserved_qty || 0);
    acc.available   += Number(r.available_qty || 0);
    acc.in_transit  += Number(r.in_transit_qty || 0);
    acc.return_qty  += Number(r.return_qty || 0);
    acc.damaged     += Number(r.damaged_qty || 0);
    acc.liquidation += Number(r.liquidation_qty || 0);
    return acc;
  }, { ready: 0, reserved: 0, available: 0, in_transit: 0, return_qty: 0, damaged: 0, liquidation: 0 });

  const lowStockCount = rows.filter((r) => r.is_low_stock).length;

  return (
    <Card className="overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 sm:px-5 py-3 sm:py-4 text-left hover:bg-slate-50 transition-colors"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="flex items-center gap-3 min-w-0">
          {open ? <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />}
          {style.image_url && (
            <img src={style.image_url} alt="" className="w-10 h-10 object-cover border border-slate-200 flex-shrink-0" />
          )}
          <div className="min-w-0">
            <div className="font-mono font-bold text-slate-900 truncate">{style.code}</div>
            <div className="text-xs text-slate-500 truncate">{style.name}</div>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          {lowStockCount > 0 && (
            <Badge color="red">
              <span className="flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> {lowStockCount} low</span>
            </Badge>
          )}
          <div className="hidden md:flex items-center gap-3 text-[11px] font-mono">
            <span className="text-green-700">R:{totals.ready}</span>
            <span className="text-blue-700">Rv:{totals.reserved}</span>
            <span className="text-slate-900 font-bold">A:{totals.available}</span>
            {totals.damaged > 0    && <span className="text-red-700">D:{totals.damaged}</span>}
            {totals.liquidation > 0 && <span className="text-purple-700">L:{totals.liquidation}</span>}
          </div>
        </div>
      </button>

      {open && (
        <div className="border-t border-slate-100">
          <div className="flex items-center justify-between px-4 sm:px-5 py-2 bg-slate-50 border-b border-slate-100">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-500">
              Color × Size Matrix
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => onOpenLedger(style)}
                className="text-[10px] uppercase font-bold text-slate-500 hover:text-slate-900 flex items-center gap-1"
              >
                <History className="w-3 h-3" /> Ledger
              </button>
              <button
                onClick={() => onAdd(style)}
                className="text-[10px] uppercase font-bold text-slate-900 hover:text-blue-600 flex items-center gap-1"
              >
                <Plus className="w-3 h-3" /> Movement
              </button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid={`matrix-${style.code}`}>
              <thead>
                <tr className="border-b border-slate-200 bg-white">
                  <th className="px-3 py-2 text-left text-[10px] uppercase font-bold text-slate-500 sticky left-0 bg-white z-10">
                    Color \ Size
                  </th>
                  {sizes.map((sz) => (
                    <th key={sz} className="px-2 py-2 text-center text-[11px] font-bold text-slate-700">{sz}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {colors.map((clr) => (
                  <tr key={clr} className="hover:bg-slate-50">
                    <td className="px-3 py-2 font-semibold text-slate-800 sticky left-0 bg-white z-10 border-r border-slate-100">
                      {clr}
                    </td>
                    {sizes.map((sz) => {
                      const r = getRow(clr, sz);
                      if (!r) return (
                        <td key={sz} className="px-2 py-2 text-center text-slate-300 border-r border-slate-100">—</td>
                      );
                      return (
                        <td key={sz} className={`px-1 py-1 text-center border-r border-slate-100 relative ${r.is_low_stock ? "bg-red-50/60" : ""}`}>
                          <div className="grid grid-cols-2 gap-0.5 font-mono text-[10px]">
                            <div className={`border ${COL_ACCENT.ready} px-1 py-0.5`} title="Ready">
                              <div className="text-[8px] uppercase font-bold opacity-70">Rdy</div>{r.ready_stock_qty}
                            </div>
                            <div className={`border ${COL_ACCENT.reserved} px-1 py-0.5`} title="Reserved">
                              <div className="text-[8px] uppercase font-bold opacity-70">Rsv</div>{r.reserved_qty}
                            </div>
                            <div className={`border ${COL_ACCENT.available} px-1 py-0.5`} title="Available (Ready-Reserved-Dmg-Liq)">
                              <div className="text-[8px] uppercase font-bold opacity-70">Avl</div>{r.available_qty}
                            </div>
                            <div className={`border ${COL_ACCENT.in_transit} px-1 py-0.5`} title="In transit">
                              <div className="text-[8px] uppercase font-bold opacity-70">Tr</div>{r.in_transit_qty || 0}
                            </div>
                            {(r.return_qty > 0 || r.damaged_qty > 0 || r.liquidation_qty > 0) && (
                              <>
                                <div className={`border ${COL_ACCENT.return_qty} px-1 py-0.5`} title="Return pending">
                                  <div className="text-[8px] uppercase font-bold opacity-70">Ret</div>{r.return_qty || 0}
                                </div>
                                <div className={`border ${COL_ACCENT.damaged} px-1 py-0.5`} title="Damaged">
                                  <div className="text-[8px] uppercase font-bold opacity-70">Dmg</div>{r.damaged_qty || 0}
                                </div>
                              </>
                            )}
                            {r.liquidation_qty > 0 && (
                              <div className={`col-span-2 border ${COL_ACCENT.liquidation} px-1 py-0.5`} title="Liquidation">
                                <div className="text-[8px] uppercase font-bold opacity-70">Liq</div>{r.liquidation_qty}
                              </div>
                            )}
                          </div>
                          {r.is_low_stock && (
                            <div className="absolute top-0 right-0 -mt-1 -mr-1">
                              <Badge color="red">LOW</Badge>
                            </div>
                          )}
                          <div className="text-[9px] text-slate-400 mt-0.5 font-mono">min:{r.min_stock_level}</div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

// ── Main page ─────────────────────────────────────────────
export default function ReadyStock() {
  const [rows, setRows]           = useState([]);
  const [loading, setLoading]     = useState(true);
  const [search, setSearch]       = useState("");
  const [lowOnly, setLowOnly]     = useState(false);
  const [mvOpen, setMvOpen]       = useState(false);
  const [mvInitial, setMvInitial] = useState(null);
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

  // Group by style_id
  const grouped = useMemo(() => {
    const map = new Map();
    for (const r of rows) {
      const key = r.style_id;
      if (!map.has(key)) {
        map.set(key, {
          style: { id: r.style_id, code: r.style_code, name: r.style_code, image_url: "" },
          rows:  [],
          colors: new Set(),
          sizes:  new Set(),
        });
      }
      const g = map.get(key);
      g.rows.push(r);
      if (r.color) g.colors.add(r.color);
      if (r.size)  g.sizes.add(r.size);
    }
    // Enrich with style meta from /styles (image + name) — fetched separately below
    return Array.from(map.values()).map((g) => ({
      ...g,
      colors: Array.from(g.colors).sort(),
      sizes:  Array.from(g.sizes).sort((a, b) => {
        const na = Number(a), nb = Number(b);
        if (!isNaN(na) && !isNaN(nb)) return na - nb;
        return String(a).localeCompare(String(b));
      }),
    }));
  }, [rows]);

  // Fetch style meta once for names/images
  const [stylesMeta, setStylesMeta] = useState({});
  useEffect(() => {
    http.get("/styles").then((r) => {
      const m = {};
      r.data.forEach((s) => { m[s.id] = s; });
      setStylesMeta(m);
    }).catch(() => {});
  }, []);

  const totals = rows.reduce((acc, r) => {
    acc.styles.add(r.style_id);
    acc.ready       += Number(r.ready_stock_qty || 0);
    acc.reserved    += Number(r.reserved_qty || 0);
    acc.available   += Number(r.available_qty || 0);
    acc.damaged     += Number(r.damaged_qty || 0);
    acc.liquidation += Number(r.liquidation_qty || 0);
    if (r.is_low_stock) acc.low_rows++;
    return acc;
  }, { styles: new Set(), ready: 0, reserved: 0, available: 0, damaged: 0, liquidation: 0, low_rows: 0 });

  return (
    <div className="min-h-screen bg-[#F7F7F5]">
      <PageHeader
        title="Ready Stock"
        subtitle="Finished Goods Inventory"
        testId="ready-stock-header"
        action={
          <div className="flex gap-2">
            <BtnSecondary id="btn-refresh-fg" onClick={load}>
              <span className="flex items-center gap-1.5"><RefreshCw className="w-4 h-4" /> Refresh</span>
            </BtnSecondary>
            <BtnSecondary id="btn-open-ledger" onClick={() => setLedger({ style_id: null, style_code: null })}>
              <span className="flex items-center gap-1.5"><History className="w-4 h-4" /> Ledger</span>
            </BtnSecondary>
            <BtnPrimary id="btn-add-movement" onClick={() => { setMvInitial(null); setMvOpen(true); }}>
              <span className="flex items-center gap-2"><Plus className="w-4 h-4" /> Post Movement</span>
            </BtnPrimary>
          </div>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4 px-4 sm:px-8 py-5">
        <StatTile label="Styles In Stock" value={totals.styles.size} accent="#0F172A" />
        <StatTile label="Ready" value={inr0(totals.ready)} accent="#16A34A" />
        <StatTile label="Reserved" value={inr0(totals.reserved)} accent="#2563EB" />
        <StatTile label="Available" value={inr0(totals.available)} accent="#C27842" />
        <StatTile label="Damaged" value={inr0(totals.damaged)} accent="#DC2626" />
        <StatTile label="Low-Stock Rows" value={totals.low_rows} accent="#DC2626" testId="stat-low-rows" />
      </div>

      {/* Filters */}
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
      </div>

      {/* Content */}
      <div className="px-4 sm:px-8 py-6 space-y-4">
        {loading ? (
          <div className="text-center py-20 text-slate-400">Loading finished-goods inventory…</div>
        ) : grouped.length === 0 ? (
          <Card className="p-10 text-center">
            <Package className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <div className="text-slate-500 font-semibold mb-1">No finished-goods rows yet.</div>
            <div className="text-xs text-slate-400 mb-4">
              Rows are auto-created when you post a movement, or on first Phase-3 "go-live" transition.
            </div>
            <BtnPrimary onClick={() => { setMvInitial(null); setMvOpen(true); }}>
              <span className="flex items-center gap-2"><Plus className="w-4 h-4" /> Post first movement</span>
            </BtnPrimary>
          </Card>
        ) : (
          grouped.map((g) => (
            <StyleGroup
              key={g.style.id}
              style={{
                ...g.style,
                name:      stylesMeta[g.style.id]?.name      || g.style.name,
                image_url: stylesMeta[g.style.id]?.image_url || "",
              }}
              rows={g.rows}
              colors={g.colors}
              sizes={g.sizes}
              onAdd={(style) => { setMvInitial({ style_id: style.id }); setMvOpen(true); }}
              onOpenLedger={(style) => setLedger({ style_id: style.id, style_code: style.code })}
            />
          ))
        )}
      </div>

      {mvOpen && (
        <MovementDrawer initial={mvInitial}
          onClose={() => setMvOpen(false)}
          onDone={() => load()} />
      )}
      {ledger && (
        <LedgerDrawer styleId={ledger.style_id} styleCode={ledger.style_code}
          onClose={() => setLedger(null)} />
      )}
    </div>
  );
}
