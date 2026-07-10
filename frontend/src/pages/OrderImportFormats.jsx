import { useEffect, useMemo, useState } from "react";
import { http } from "../lib/api";
import {
  PageHeader, Card, BtnPrimary, BtnSecondary, Input, Select, Badge,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import {
  Plus, Pencil, Save, FileSpreadsheet, X as XIcon, Info, Tag,
} from "lucide-react";

// Same platform enum as the backend Literal (kept in sync intentionally)
const PLATFORM_OPTIONS = [
  { value: "myntra",   label: "Myntra"   },
  { value: "flipkart", label: "Flipkart" },
  { value: "ajio",     label: "Ajio"     },
  { value: "nykaa",    label: "Nykaa"    },
  { value: "amazon",   label: "Amazon"   },
  { value: "website",  label: "Website"  },
  { value: "other",    label: "Other"    },
];

const SHEET_LOCATOR_TYPES = [
  { value: "fixed_name",      label: "Fixed sheet name" },
  { value: "name_contains",   label: "Sheet name contains substring" },
  { value: "first_sheet",     label: "First sheet in workbook" },
];

const HEADER_LOCATOR_TYPES = [
  { value: "fixed_row",         label: "Fixed row index" },
  { value: "scan_for_columns",  label: "Scan rows 0-10 for known column names" },
];

// Fallback if _meta call fails — matches ORDER_CANONICAL_FIELDS in server.py
const FALLBACK_ORDER_FIELDS = [
  "order_id", "order_item_id", "shipment_id",
  "order_date", "dispatch_by_date",
  "leaf_sku", "myntra_sku_code",
  "product_title", "qty",
  "selling_price", "invoice_amount",
  "order_state", "tracking_id",
  "buyer_name", "city", "state", "pincode",
  "bin_barcode",
];

// Fallback if _meta call fails — matches DISPATCH_CANONICAL_FIELDS in server.py
const FALLBACK_DISPATCH_FIELDS = [
  "order_id", "order_release_id",
  "leaf_sku", "channel_sku",
  "packed_on", "status",
  "mrp", "selling_value",
  "cgst", "sgst", "igst",
  "tracking_id",
  "destination_city", "destination_state", "destination_pincode",
  "store_packet_id",
  "product_title", "qty",
];

const FIELD_HELP = {
  // Order/picklist fields
  order_id:         "Marketplace order id. Leave blank for pure-picklist files (Myntra OP-xxxxx.csv).",
  order_item_id:    "Per-line order-item id. May carry a leading apostrophe (Excel text-safety) — stripped automatically.",
  shipment_id:      "Marketplace shipment id (Flipkart).",
  order_date:       "When the order was placed.",
  dispatch_by_date: "Marketplace-imposed dispatch SLA.",
  leaf_sku:         "REQUIRED. Our own catalogue SKU column (Flipkart: 'SKU', Myntra: 'sellerSkuCode'/'Seller_sku_code'). Prefix stripping + split_leaf_sku() normalise variants.",
  myntra_sku_code:  "Myntra's own SKU code (myntraSkuCode).",
  product_title:    "Product title / description.",
  qty:              "Units per row. For order/picklist files can be >1. For dispatch files defaults to 1 per row (each row = 1 unit packed).",
  selling_price:    "Per-unit selling price.",
  invoice_amount:   "Line-level invoice amount.",
  order_state:      "Marketplace order state.",
  tracking_id:      "Courier tracking id.",
  buyer_name:       "End customer name (Flipkart).",
  city:             "Buyer city.",
  state:            "Buyer state.",
  pincode:          "Buyer PIN code.",
  bin_barcode:      "Warehouse bin barcode (Myntra picklist).",
  // Dispatch-specific fields
  order_release_id:    "Marketplace's per-shipment release id (join key across Myntra's Packed / Monthly / Settlement files).",
  channel_sku:         "Platform's own SKU code (Myntra SKU code, Flipkart FSN).",
  packed_on:           "Date the unit was packed by the warehouse.",
  status:              "Status column in the dispatch file (typically 'PACKED').",
  mrp:                 "Maximum Retail Price per unit.",
  selling_value:       "Actual selling value (net of discount) per unit.",
  cgst:                "Central GST amount.",
  sgst:                "State GST amount.",
  igst:                "Integrated GST amount.",
  destination_city:    "Delivery city.",
  destination_state:   "Delivery state.",
  destination_pincode: "Delivery PIN code.",
  store_packet_id:     "Warehouse packet id (Myntra).",
};

const emptyConfig = {
  platform: "nykaa",
  role: "order",
  sheet_locator:  { type: "first_sheet" },
  header_locator: { type: "fixed_row", row: 0 },
  skip_rows_after_header: 0,
  column_map: {},
  known_sku_prefixes_to_strip: [],
  known_sku_prefix_replacements: {},
  is_picklist: false,
  active: true,
  notes: "",
};

function SheetLocatorEditor({ value, onChange }) {
  return (
    <div className="space-y-2">
      <Select
        label="Sheet locator"
        value={value?.type || "first_sheet"}
        onChange={(e) => {
          const t = e.target.value;
          const next = { type: t };
          if (t === "fixed_name")    next.name = value?.name || "";
          if (t === "name_contains") next.substring = value?.substring || "";
          onChange(next);
        }}
      >
        {SHEET_LOCATOR_TYPES.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </Select>
      {value?.type === "fixed_name" && (
        <Input label="Exact sheet name" value={value?.name || ""}
          onChange={(e) => onChange({ ...value, name: e.target.value })}
          placeholder="e.g. Orders" />
      )}
      {value?.type === "name_contains" && (
        <Input label="Substring the sheet name must contain" value={value?.substring || ""}
          onChange={(e) => onChange({ ...value, substring: e.target.value })}
          placeholder="e.g. _Orders_" />
      )}
    </div>
  );
}

function HeaderLocatorEditor({ value, onChange }) {
  const scanCsv = useMemo(
    () => (value?.must_contain_any || []).join(", "),
    [value],
  );
  return (
    <div className="space-y-2">
      <Select
        label="Header locator"
        value={value?.type || "fixed_row"}
        onChange={(e) => {
          const t = e.target.value;
          const next = { type: t };
          if (t === "fixed_row") next.row = value?.row ?? 0;
          if (t === "scan_for_columns")
            next.must_contain_any = value?.must_contain_any || [];
          onChange(next);
        }}
      >
        {HEADER_LOCATOR_TYPES.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </Select>
      {value?.type === "fixed_row" && (
        <Input label="Header row index (0-based)" type="number" min="0"
          value={value?.row ?? 0}
          onChange={(e) => onChange({ ...value, row: Number(e.target.value || 0) })} />
      )}
      {value?.type === "scan_for_columns" && (
        <Input label="Known column names (comma-separated)" value={scanCsv}
          onChange={(e) =>
            onChange({
              ...value,
              must_contain_any: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
            })
          }
          placeholder="e.g. Order Id, sellerSkuCode" />
      )}
    </div>
  );
}

function ColumnMapEditor({ value, canonicalFields, onChange }) {
  return (
    <div className="border border-neutral-200 rounded overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-neutral-100 text-[10px] uppercase tracking-wider text-neutral-600">
          <tr>
            <th className="text-left p-2 border-b border-neutral-200 w-52">Canonical field</th>
            <th className="text-left p-2 border-b border-neutral-200">Column name in this platform's file</th>
          </tr>
        </thead>
        <tbody>
          {canonicalFields.map((f) => (
            <tr key={f} className="border-b border-neutral-100 last:border-b-0">
              <td className="p-2 align-top">
                <div className="font-mono font-medium text-neutral-900">
                  {f}
                  {(f === "leaf_sku" || f === "qty") && (
                    <span className="ml-1.5 text-[10px] text-red-600 uppercase font-bold">req</span>
                  )}
                </div>
                <div className="text-[11px] text-neutral-500 leading-snug">
                  {FIELD_HELP[f] || ""}
                </div>
              </td>
              <td className="p-2 align-top">
                <input
                  type="text"
                  className="w-full h-9 px-2 rounded-md border border-neutral-300 bg-white text-sm focus:border-neutral-500 focus:outline-none"
                  value={value?.[f] || ""}
                  onChange={(e) => onChange({ ...(value || {}), [f]: e.target.value })}
                  placeholder={f === "leaf_sku" ? "REQUIRED" : "(leave blank if not present)"}
                  data-testid={`oif-col-map-${f}`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PrefixListEditor({ value, onChange }) {
  const [draft, setDraft] = useState("");
  const chips = Array.isArray(value) ? value : [];

  function add() {
    const v = draft.trim();
    if (!v) return;
    if (chips.includes(v)) { setDraft(""); return; }
    onChange([...chips, v]);
    setDraft("");
  }
  function remove(p) { onChange(chips.filter((x) => x !== p)); }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {chips.length === 0 && (
          <span className="text-xs text-neutral-400 italic">
            None configured. Add prefixes like "TH" so leaf_sku matching works despite platform prefixes.
          </span>
        )}
        {chips.map((p) => (
          <span key={p}
            className="inline-flex items-center gap-1 px-2 py-1 bg-amber-100 text-amber-900 border border-amber-300 rounded text-xs font-mono">
            <Tag className="w-3 h-3" /> {p}
            <button className="ml-1 hover:text-red-700" onClick={() => remove(p)}>
              <XIcon className="w-3 h-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          className="h-9 px-2 rounded-md border border-neutral-300 bg-white text-sm w-40 focus:border-neutral-500 focus:outline-none"
          placeholder="e.g. TH"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          data-testid="oif-prefix-input"
        />
        <BtnSecondary onClick={add} data-testid="oif-prefix-add">
          <Plus className="w-4 h-4 mr-1" /> Add prefix
        </BtnSecondary>
      </div>
    </div>
  );
}

// Editor for the replacement map (typo→correct). Keys are the wrong prefix,
// values the corrected prefix — the parser runs this BEFORE the strip list.
function PrefixReplacementEditor({ value, onChange }) {
  const [wrong, setWrong] = useState("");
  const [right, setRight] = useState("");
  const entries = Object.entries(value || {});

  function add() {
    const w = wrong.trim(); const r = right.trim();
    if (!w || !r) return;
    onChange({ ...(value || {}), [w]: r });
    setWrong(""); setRight("");
  }
  function remove(k) {
    const next = { ...(value || {}) }; delete next[k]; onChange(next);
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {entries.length === 0 && (
          <span className="text-xs text-neutral-400 italic">
            None configured. Add typo variants like "FLL" → "FL" so Myntra's doubled-L SKUs normalise correctly.
          </span>
        )}
        {entries.map(([k, v]) => (
          <span key={k}
            className="inline-flex items-center gap-1 px-2 py-1 bg-purple-100 text-purple-900 border border-purple-300 rounded text-xs font-mono">
            {k} <span className="text-purple-500">→</span> {v}
            <button className="ml-1 hover:text-red-700" onClick={() => remove(k)}>
              <XIcon className="w-3 h-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2 items-end">
        <input
          type="text"
          className="h-9 px-2 rounded-md border border-neutral-300 bg-white text-sm w-32 focus:border-neutral-500 focus:outline-none"
          placeholder="wrong (FLL)"
          value={wrong}
          onChange={(e) => setWrong(e.target.value)}
          data-testid="oif-replace-wrong"
        />
        <span className="text-neutral-400 pb-1">→</span>
        <input
          type="text"
          className="h-9 px-2 rounded-md border border-neutral-300 bg-white text-sm w-32 focus:border-neutral-500 focus:outline-none"
          placeholder="correct (FL)"
          value={right}
          onChange={(e) => setRight(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          data-testid="oif-replace-right"
        />
        <BtnSecondary onClick={add} data-testid="oif-replace-add">
          <Plus className="w-4 h-4 mr-1" /> Add mapping
        </BtnSecondary>
      </div>
    </div>
  );
}

export default function OrderImportFormats() {
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [canonicalOrder, setCanonicalOrder] = useState(FALLBACK_ORDER_FIELDS);
  const [canonicalDispatch, setCanonicalDispatch] = useState(FALLBACK_DISPATCH_FIELDS);
  const [roleFilter, setRoleFilter] = useState("all"); // "all" | "order" | "dispatch"
  const [open, setOpen] = useState(false);
  const [editingKey, setEditingKey] = useState(null); // {platform, role} when editing
  const [form, setForm] = useState(emptyConfig);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  // Canonical field list for the currently-editing form (swaps by role)
  const canonicalFields = useMemo(
    () => (form.role === "dispatch" ? canonicalDispatch : canonicalOrder),
    [form.role, canonicalOrder, canonicalDispatch]
  );

  const load = async () => {
    setLoading(true);
    try {
      const [listRes, metaOrderRes, metaDispatchRes] = await Promise.all([
        http.get("/order-import-format-configs"),
        http.get("/order-import-format-configs/_meta/canonical-fields?role=order"),
        http.get("/order-import-format-configs/_meta/canonical-fields?role=dispatch"),
      ]);
      setConfigs(listRes.data);
      if (metaOrderRes.data?.canonical_fields?.length) {
        setCanonicalOrder(metaOrderRes.data.canonical_fields);
      }
      if (metaDispatchRes.data?.canonical_fields?.length) {
        setCanonicalDispatch(metaDispatchRes.data.canonical_fields);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const filteredConfigs = useMemo(
    () => (roleFilter === "all"
      ? configs
      : configs.filter((c) => (c.role || "order") === roleFilter)),
    [configs, roleFilter]
  );

  const startCreate = (roleDefault = "order") => {
    setEditingKey(null);
    const fields = roleDefault === "dispatch" ? canonicalDispatch : canonicalOrder;
    setForm({
      ...emptyConfig,
      role: roleDefault,
      is_picklist: false,
      column_map: fields.reduce((acc, f) => ({ ...acc, [f]: "" }), {}),
    });
    setFormError("");
    setOpen(true);
  };

  const startEdit = (cfg) => {
    const cfgRole = cfg.role || "order";
    setEditingKey({ platform: cfg.platform, role: cfgRole });
    const fields = cfgRole === "dispatch" ? canonicalDispatch : canonicalOrder;
    const cm = { ...(cfg.column_map || {}) };
    fields.forEach((f) => {
      if (!(f in cm)) cm[f] = "";
      if (cm[f] === null) cm[f] = "";
    });
    setForm({
      platform: cfg.platform,
      role: cfgRole,
      sheet_locator:  cfg.sheet_locator  || { type: "first_sheet" },
      header_locator: cfg.header_locator || { type: "fixed_row", row: 0 },
      skip_rows_after_header: cfg.skip_rows_after_header ?? 0,
      column_map: cm,
      known_sku_prefixes_to_strip:   cfg.known_sku_prefixes_to_strip   || [],
      known_sku_prefix_replacements: cfg.known_sku_prefix_replacements || {},
      is_picklist: !!cfg.is_picklist,
      active: cfg.active !== false,
      notes: cfg.notes || "",
    });
    setFormError("");
    setOpen(true);
  };

  const save = async () => {
    setFormError("");
    const cmClean = {};
    Object.entries(form.column_map || {}).forEach(([k, v]) => {
      const val = (v || "").trim();
      cmClean[k] = val === "" ? null : val;
    });
    if (!cmClean.leaf_sku) {
      setFormError("column_map.leaf_sku is required — every order/picklist/dispatch file must expose our internal SKU column.");
      return;
    }
    if (form.sheet_locator?.type === "fixed_name" && !form.sheet_locator?.name?.trim()) {
      setFormError("Sheet locator: fixed_name requires a sheet name.");
      return;
    }
    if (form.sheet_locator?.type === "name_contains" && !form.sheet_locator?.substring?.trim()) {
      setFormError("Sheet locator: name_contains requires a substring.");
      return;
    }
    if (form.header_locator?.type === "scan_for_columns"
        && (!form.header_locator?.must_contain_any || form.header_locator.must_contain_any.length === 0)) {
      setFormError("Header locator: scan_for_columns requires at least one column name.");
      return;
    }

    const body = {
      sheet_locator:  form.sheet_locator,
      header_locator: form.header_locator,
      skip_rows_after_header: Number(form.skip_rows_after_header || 0),
      column_map: cmClean,
      known_sku_prefixes_to_strip:   form.known_sku_prefixes_to_strip   || [],
      known_sku_prefix_replacements: form.known_sku_prefix_replacements || {},
      is_picklist: !!form.is_picklist,
      active: !!form.active,
      notes: form.notes || "",
    };
    setSaving(true);
    try {
      if (editingKey) {
        await http.put(
          `/order-import-format-configs/${editingKey.platform}?role=${editingKey.role}`,
          body,
        );
      } else {
        await http.post("/order-import-format-configs", {
          platform: form.platform,
          role: form.role,
          ...body,
        });
      }
      setOpen(false);
      load();
    } catch (e) {
      const raw = e.response?.data?.detail;
      if (Array.isArray(raw)) setFormError(raw.map((r) => r.msg).join(" · "));
      else setFormError(raw || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="Order & Dispatch Import Formats"
        subtitle="Config-driven registry of platform ORDER / PICKLIST / DISPATCH file formats. Add a new marketplace's file format without touching parser code."
        action={
          <div className="flex gap-2">
            <BtnSecondary onClick={() => startCreate("dispatch")} data-testid="oif-add-dispatch">
              <Plus className="w-4 h-4 mr-1.5" /> Add dispatch config
            </BtnSecondary>
            <BtnPrimary onClick={() => startCreate("order")} data-testid="oif-add">
              <Plus className="w-4 h-4 mr-1.5" /> Add order config
            </BtnPrimary>
          </div>
        }
      />

      {/* Role filter tabs */}
      <div className="flex gap-1 border-b border-neutral-200">
        {[
          { key: "all",      label: "All",       count: configs.length },
          { key: "order",    label: "Order / Picklist", count: configs.filter((c) => (c.role || "order") === "order").length },
          { key: "dispatch", label: "Dispatch",  count: configs.filter((c) => c.role === "dispatch").length },
        ].map((tab) => (
          <button key={tab.key}
            onClick={() => setRoleFilter(tab.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              roleFilter === tab.key
                ? "border-neutral-900 text-neutral-900"
                : "border-transparent text-neutral-500 hover:text-neutral-800"
            }`}
            data-testid={`oif-role-tab-${tab.key}`}>
            {tab.label}
            <span className="ml-1.5 text-[10px] bg-neutral-100 px-1.5 py-0.5 rounded font-mono">
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      <Card>
        <div className="p-4 flex items-start gap-3 bg-amber-50/40 border-b border-neutral-200 text-xs text-neutral-700 leading-snug">
          <Info className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
          <div>
            Each config maps canonical fields (<span className="font-mono">order_id</span>,{" "}
            <span className="font-mono">leaf_sku</span>, <span className="font-mono">qty</span>,{" "}
            <span className="font-mono">packed_on</span>, <span className="font-mono">dispatch_by_date</span>, …) to the actual column
            names in that platform's file. <span className="font-semibold">leaf_sku</span> is required.
            A platform can have BOTH an <span className="font-semibold text-blue-700">order</span> (or picklist) config AND a{" "}
            <span className="font-semibold text-emerald-700">dispatch</span> config (Myntra ships both).
            Mark <span className="font-semibold">is_picklist</span> for files with no order_id
            (e.g. Myntra <span className="font-mono">OP-xxxxx.csv</span>) — the filename stem becomes the
            <span className="font-mono"> picklist_batch_id</span>. Use{" "}
            <span className="font-semibold">known_sku_prefixes_to_strip</span> for platform prefixes (Flipkart "TH")
            and <span className="font-semibold text-purple-700">known_sku_prefix_replacements</span> for typo variants (Myntra "FLL" → "FL").
          </div>
        </div>

        {loading ? (
          <div className="p-6 text-sm text-neutral-500 italic">Loading order-import configs…</div>
        ) : filteredConfigs.length === 0 ? (
          <div className="p-6 text-sm text-neutral-500 italic">
            {configs.length === 0 ? "No configs yet." : `No configs in the '${roleFilter}' filter.`}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-[10px] uppercase tracking-wider text-neutral-600">
                <tr>
                  <th className="text-left p-3 border-b">Platform</th>
                  <th className="text-left p-3 border-b">Role</th>
                  <th className="text-left p-3 border-b">Sheet locator</th>
                  <th className="text-left p-3 border-b">Header locator</th>
                  <th className="text-left p-3 border-b">Leaf SKU column</th>
                  <th className="text-left p-3 border-b">Prefix strips</th>
                  <th className="text-left p-3 border-b">Replacements</th>
                  <th className="text-left p-3 border-b">Type</th>
                  <th className="text-left p-3 border-b">Active</th>
                  <th className="text-right p-3 border-b w-24"></th>
                </tr>
              </thead>
              <tbody>
                {filteredConfigs.map((c) => (
                  <tr key={`${c.platform}-${c.role || 'order'}`}
                    className="border-b border-neutral-100 hover:bg-neutral-50"
                    data-testid={`oif-row-${c.platform}-${c.role || 'order'}`}>
                    <td className="p-3 font-semibold capitalize">
                      <span className="inline-flex items-center gap-1.5">
                        <FileSpreadsheet className="w-3.5 h-3.5 text-neutral-500" />
                        {c.platform}
                        {c.seeded && (
                          <span className="text-[9px] uppercase text-amber-800 bg-amber-100 border border-amber-200 rounded px-1 py-0.5">
                            seed
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="p-3">
                      {(c.role || "order") === "dispatch" ? (
                        <Badge color="green">dispatch</Badge>
                      ) : (
                        <Badge color="slate">order</Badge>
                      )}
                    </td>
                    <td className="p-3 text-xs">
                      <span className="font-mono text-neutral-700">
                        {c.sheet_locator?.type === "fixed_name" && `name="${c.sheet_locator.name}"`}
                        {c.sheet_locator?.type === "name_contains" && `contains "${c.sheet_locator.substring}"`}
                        {c.sheet_locator?.type === "first_sheet" && `first sheet`}
                      </span>
                    </td>
                    <td className="p-3 text-xs">
                      <span className="font-mono text-neutral-700">
                        {c.header_locator?.type === "fixed_row" && `row ${c.header_locator.row}`}
                        {c.header_locator?.type === "scan_for_columns" && `scan ${(c.header_locator.must_contain_any || []).length} col(s)`}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-xs">{c.column_map?.leaf_sku || "—"}</td>
                    <td className="p-3 text-xs">
                      {(c.known_sku_prefixes_to_strip || []).length === 0 ? (
                        <span className="text-neutral-400">—</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {(c.known_sku_prefixes_to_strip || []).map((p) => (
                            <span key={p} className="font-mono text-[10px] bg-amber-100 text-amber-900 px-1.5 py-0.5 rounded border border-amber-300">
                              {p}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="p-3 text-xs">
                      {Object.keys(c.known_sku_prefix_replacements || {}).length === 0 ? (
                        <span className="text-neutral-400">—</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(c.known_sku_prefix_replacements || {}).map(([k, v]) => (
                            <span key={k} className="font-mono text-[10px] bg-purple-100 text-purple-900 px-1.5 py-0.5 rounded border border-purple-300">
                              {k}→{v}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="p-3">
                      {c.is_picklist ? (
                        <Badge color="purple">picklist</Badge>
                      ) : (
                        <Badge color="blue">order</Badge>
                      )}
                    </td>
                    <td className="p-3">
                      {c.active ? <Badge color="green">active</Badge> : <Badge color="slate">inactive</Badge>}
                    </td>
                    <td className="p-3 text-right">
                      <button onClick={() => startEdit(c)}
                        className="text-xs text-neutral-700 hover:text-neutral-900 inline-flex items-center gap-1"
                        data-testid={`oif-edit-${c.platform}-${c.role || 'order'}`}>
                        <Pencil className="w-3.5 h-3.5" /> Edit
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {open && (
        <Drawer
          onClose={() => setOpen(false)}
          title={editingKey
            ? `Edit ${editingKey.platform} · ${editingKey.role} config`
            : `Add ${form.role} config`}
          width="max-w-4xl"
        >
          <div className="space-y-5">
            <div className="grid grid-cols-3 gap-3">
              {editingKey ? (
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-1">Platform</label>
                  <div className="h-10 px-3 flex items-center gap-2 rounded-md border border-neutral-200 bg-neutral-50 font-mono text-sm capitalize">
                    {form.platform}
                    <span className="ml-auto text-[10px] uppercase tracking-wider text-neutral-500 bg-white border border-neutral-200 rounded px-1.5 py-0.5">
                      immutable
                    </span>
                  </div>
                </div>
              ) : (
                <Select label="Platform" value={form.platform}
                  onChange={(e) => setForm({ ...form, platform: e.target.value })}
                  testId="oif-form-platform">
                  {PLATFORM_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </Select>
              )}

              {editingKey ? (
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-1">Role</label>
                  <div className="h-10 px-3 flex items-center gap-2 rounded-md border border-neutral-200 bg-neutral-50 font-mono text-sm">
                    {form.role}
                    <span className="ml-auto text-[10px] uppercase tracking-wider text-neutral-500 bg-white border border-neutral-200 rounded px-1.5 py-0.5">
                      immutable
                    </span>
                  </div>
                </div>
              ) : (
                <Select label="Role" value={form.role}
                  onChange={(e) => {
                    const newRole = e.target.value;
                    const fields = newRole === "dispatch" ? canonicalDispatch : canonicalOrder;
                    setForm({
                      ...form,
                      role: newRole,
                      // reset column_map when role changes (different fields)
                      column_map: fields.reduce((acc, f) => ({ ...acc, [f]: "" }), {}),
                      is_picklist: newRole === "dispatch" ? false : form.is_picklist,
                    });
                  }}
                  testId="oif-form-role">
                  <option value="order">Order / Picklist</option>
                  <option value="dispatch">Dispatch (daily "what got packed")</option>
                </Select>
              )}

              <div className="flex items-center gap-6 pt-6">
                {form.role === "order" && (
                  <label className="inline-flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={!!form.is_picklist}
                      onChange={(e) => setForm({ ...form, is_picklist: e.target.checked })}
                      data-testid="oif-form-picklist" />
                    <span>Picklist file</span>
                  </label>
                )}
                <label className="inline-flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!form.active}
                    onChange={(e) => setForm({ ...form, active: e.target.checked })}
                    data-testid="oif-form-active" />
                  <span>Active</span>
                </label>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card className="p-4 space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-600">Sheet locator</h4>
                <SheetLocatorEditor value={form.sheet_locator}
                  onChange={(v) => setForm({ ...form, sheet_locator: v })} />
              </Card>
              <Card className="p-4 space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-600">Header locator</h4>
                <HeaderLocatorEditor value={form.header_locator}
                  onChange={(v) => setForm({ ...form, header_locator: v })} />
                <Input label="Skip rows after header" type="number" min="0"
                  value={form.skip_rows_after_header}
                  onChange={(e) => setForm({ ...form, skip_rows_after_header: Number(e.target.value || 0) })} />
              </Card>
            </div>

            <Card className="p-4 space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-600">Known SKU prefixes to strip</h4>
              <p className="text-[11px] text-neutral-500 leading-snug">
                Non-numeric prefixes to REMOVE from leaf_sku BEFORE resolve_style() — e.g. Flipkart's
                "TH" prefix ("THFL_AK_048_BG_37" → "FL_AK_048_BG_37"). Runs AFTER the replacements
                below. Added at import time; no code change.
              </p>
              <PrefixListEditor value={form.known_sku_prefixes_to_strip}
                onChange={(v) => setForm({ ...form, known_sku_prefixes_to_strip: v })} />
            </Card>

            <Card className="p-4 space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-600">
                SKU prefix replacements <span className="text-purple-700">(typo variants)</span>
              </h4>
              <p className="text-[11px] text-neutral-500 leading-snug">
                Rewrite a leading token — used for TYPO variants of a real SKU token, e.g. Myntra
                sometimes ships "FLL_..." for our "FL_..." (doubled-L). Runs BEFORE the strip list
                above. Config-driven so new platform typos onboard without a code deploy.
              </p>
              <PrefixReplacementEditor value={form.known_sku_prefix_replacements}
                onChange={(v) => setForm({ ...form, known_sku_prefix_replacements: v })} />
            </Card>

            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-600 mb-2">
                Column map (canonical → platform column name)
              </h4>
              <ColumnMapEditor value={form.column_map} canonicalFields={canonicalFields}
                onChange={(v) => setForm({ ...form, column_map: v })} />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-1">Notes</label>
              <textarea
                className="w-full min-h-[70px] px-3 py-2 rounded-md border border-neutral-300 bg-white text-sm focus:border-neutral-500 focus:outline-none"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                placeholder="Format quirks, template version, contact person…" />
            </div>

            {formError && (
              <div className="text-xs bg-red-50 border border-red-200 rounded px-3 py-2 text-red-800">
                {formError}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-neutral-200">
              <BtnSecondary onClick={() => setOpen(false)}>
                <XIcon className="w-4 h-4 mr-1.5" /> Cancel
              </BtnSecondary>
              <BtnPrimary onClick={save} disabled={saving} data-testid="oif-save">
                <Save className="w-4 h-4 mr-1.5" /> {saving ? "Saving…" : "Save"}
              </BtnPrimary>
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
}
