import { useEffect, useMemo, useState } from "react";
import { http } from "../lib/api";
import {
  PageHeader,
  Card,
  BtnPrimary,
  BtnSecondary,
  Input,
  Select,
  Badge,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import {
  Plus,
  Pencil,
  Save,
  FileSpreadsheet,
  X as XIcon,
  Info,
} from "lucide-react";

// Options for the "platform" enum. Keep in sync with backend Literal.
const PLATFORM_OPTIONS = [
  { value: "myntra",   label: "Myntra"   },
  { value: "flipkart", label: "Flipkart" },
  { value: "ajio",     label: "Ajio"     },
  { value: "nykaa",    label: "Nykaa"    },
  { value: "website",  label: "Website"  },
  { value: "other",    label: "Other"    },
];

const SHEET_LOCATOR_TYPES = [
  { value: "fixed_name",      label: "Fixed sheet name"                    },
  { value: "name_contains",   label: "Sheet name contains substring"       },
  { value: "first_sheet",     label: "First sheet in workbook"             },
];

const HEADER_LOCATOR_TYPES = [
  { value: "fixed_row",         label: "Fixed row index"                       },
  { value: "scan_for_columns",  label: "Scan rows 0-10 for known column names" },
];

// Default canonical fields (fallback if the meta endpoint fails)
const FALLBACK_CANONICAL_FIELDS = [
  "group_id", "leaf_sku", "size",
  "color_primary", "color_family",
  "style_description", "mrp", "selling_price",
  "brand", "listing_status",
];

// Short help text shown next to each canonical field in the editor
const FIELD_HELP = {
  group_id:          "Marketplace's style+colour grouping id (e.g. Myntra 'Style Id'). Leave blank if platform has no native group.",
  leaf_sku:          "REQUIRED. The per-size unique SKU column (e.g. 'SellerSkuCode', 'Seller SKU Id', '*Item SKU').",
  size:              "Explicit size column. Leave blank if size is embedded inside leaf_sku.",
  color_primary:     "Primary colour column.",
  color_family:      "Broader colour family — optional (Ajio only).",
  style_description: "Product title / description.",
  mrp:               "MRP column.",
  selling_price:     "Platform's selling-price column.",
  brand:             "Brand column.",
  listing_status:    "Active/inactive listing flag column.",
};

const emptyConfig = {
  platform: "nykaa",
  sheet_locator:  { type: "first_sheet" },
  header_locator: { type: "fixed_row", row: 0 },
  skip_rows_after_header: 0,
  column_map: {
    group_id: "", leaf_sku: "", size: "",
    color_primary: "", color_family: "",
    style_description: "", mrp: "", selling_price: "",
    brand: "", listing_status: "",
  },
  has_native_group_id: false,
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
        <Input
          label="Exact sheet name"
          value={value?.name || ""}
          onChange={(e) => onChange({ ...value, name: e.target.value })}
          placeholder="e.g. styledashboard"
        />
      )}
      {value?.type === "name_contains" && (
        <Input
          label="Substring the sheet name must contain"
          value={value?.substring || ""}
          onChange={(e) => onChange({ ...value, substring: e.target.value })}
          placeholder="e.g. _Styles_"
        />
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
        <Input
          label="Header row index (0-based)"
          type="number"
          min="0"
          value={value?.row ?? 0}
          onChange={(e) => onChange({ ...value, row: Number(e.target.value || 0) })}
        />
      )}
      {value?.type === "scan_for_columns" && (
        <Input
          label="Known column names (comma-separated)"
          value={scanCsv}
          onChange={(e) =>
            onChange({
              ...value,
              must_contain_any: e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
          placeholder="e.g. *Style Code, *Item SKU"
        />
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
                  {f === "leaf_sku" && (
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
                  onChange={(e) =>
                    onChange({ ...(value || {}), [f]: e.target.value })
                  }
                  placeholder={f === "leaf_sku" ? "REQUIRED" : "(leave blank if not present)"}
                  data-testid={`col-map-${f}`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ListingFormats() {
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [canonicalFields, setCanonicalFields] = useState(FALLBACK_CANONICAL_FIELDS);
  const [open, setOpen] = useState(false);
  const [editingPlatform, setEditingPlatform] = useState(null); // null = create
  const [form, setForm] = useState(emptyConfig);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [listRes, metaRes] = await Promise.all([
        http.get("/listing-format-configs"),
        http.get("/listing-format-configs/_meta/canonical-fields"),
      ]);
      setConfigs(listRes.data);
      if (metaRes.data?.canonical_fields?.length) {
        setCanonicalFields(metaRes.data.canonical_fields);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const startCreate = () => {
    setEditingPlatform(null);
    setForm({
      ...emptyConfig,
      column_map: canonicalFields.reduce((acc, f) => ({ ...acc, [f]: "" }), {}),
    });
    setFormError("");
    setOpen(true);
  };

  const startEdit = (cfg) => {
    setEditingPlatform(cfg.platform);
    // Normalise column_map so every canonical field is a key (even if null)
    const cm = { ...(cfg.column_map || {}) };
    canonicalFields.forEach((f) => {
      if (!(f in cm)) cm[f] = "";
      if (cm[f] === null) cm[f] = "";
    });
    setForm({
      platform: cfg.platform,
      sheet_locator:  cfg.sheet_locator  || { type: "first_sheet" },
      header_locator: cfg.header_locator || { type: "fixed_row", row: 0 },
      skip_rows_after_header: cfg.skip_rows_after_header ?? 0,
      column_map: cm,
      has_native_group_id: !!cfg.has_native_group_id,
      active: cfg.active !== false,
      notes: cfg.notes || "",
    });
    setFormError("");
    setOpen(true);
  };

  const save = async () => {
    setFormError("");
    // Convert empty-string column values back to null so the backend stores
    // a proper "not present" marker instead of an empty string.
    const cmClean = {};
    Object.entries(form.column_map || {}).forEach(([k, v]) => {
      const val = (v || "").trim();
      cmClean[k] = val === "" ? null : val;
    });
    if (!cmClean.leaf_sku) {
      setFormError("column_map.leaf_sku is required — every platform must expose the per-size unique SKU column.");
      return;
    }
    // Sheet-locator sanity
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
      has_native_group_id: !!form.has_native_group_id,
      active: !!form.active,
      notes: form.notes || "",
    };
    setSaving(true);
    try {
      if (editingPlatform) {
        await http.put(`/listing-format-configs/${editingPlatform}`, body);
      } else {
        await http.post("/listing-format-configs", {
          platform: form.platform,
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
        title="Listing Formats"
        subtitle="Config-driven registry of platform listing-file formats. Add a new platform (Nykaa, Amazon, Ajio v2, …) without touching parser code."
        action={
          <BtnPrimary onClick={startCreate} data-testid="lf-add">
            <Plus className="w-4 h-4 mr-1.5" /> Add platform
          </BtnPrimary>
        }
      />

      <Card>
        <div className="p-4 flex items-start gap-3 bg-amber-50/40 border-b border-neutral-200 text-xs text-neutral-700 leading-snug">
          <Info className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
          <div>
            Each config maps the canonical fields (<span className="font-mono">group_id</span>,{" "}
            <span className="font-mono">leaf_sku</span>, <span className="font-mono">size</span>,{" "}
            <span className="font-mono">color_primary</span>, mrp, selling_price, …) to the actual
            column names in that platform's export file, and tells the parser where the data sheet
            lives and where the header row starts. <span className="font-semibold">leaf_sku</span> is
            required; everything else is optional and may be left blank if the platform doesn't
            expose it.
          </div>
        </div>

        {loading ? (
          <div className="p-6 text-sm text-neutral-500 italic">Loading platform configs…</div>
        ) : configs.length === 0 ? (
          <div className="p-6 text-sm text-neutral-500 italic">No platform configs yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-[10px] uppercase tracking-wider text-neutral-600">
                <tr>
                  <th className="text-left p-3 border-b">Platform</th>
                  <th className="text-left p-3 border-b">Sheet locator</th>
                  <th className="text-left p-3 border-b">Header locator</th>
                  <th className="text-left p-3 border-b">Skip after header</th>
                  <th className="text-left p-3 border-b">Group id</th>
                  <th className="text-left p-3 border-b">Leaf SKU column</th>
                  <th className="text-left p-3 border-b">Native group</th>
                  <th className="text-left p-3 border-b">Active</th>
                  <th className="text-right p-3 border-b w-24"></th>
                </tr>
              </thead>
              <tbody>
                {configs.map((c) => (
                  <tr
                    key={c.platform}
                    className="border-b border-neutral-100 hover:bg-neutral-50"
                    data-testid={`lf-row-${c.platform}`}
                  >
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
                        {c.header_locator?.type === "scan_for_columns" && `scan for ${(c.header_locator.must_contain_any || []).length} col(s)`}
                      </span>
                    </td>
                    <td className="p-3">{c.skip_rows_after_header ?? 0}</td>
                    <td className="p-3 font-mono text-xs">{c.column_map?.group_id || "—"}</td>
                    <td className="p-3 font-mono text-xs">{c.column_map?.leaf_sku || "—"}</td>
                    <td className="p-3">
                      {c.has_native_group_id ? (
                        <Badge color="green">yes</Badge>
                      ) : (
                        <Badge color="slate">derived</Badge>
                      )}
                    </td>
                    <td className="p-3">
                      {c.active ? <Badge color="green">active</Badge> : <Badge color="slate">inactive</Badge>}
                    </td>
                    <td className="p-3 text-right">
                      <button
                        onClick={() => startEdit(c)}
                        className="text-xs text-neutral-700 hover:text-neutral-900 inline-flex items-center gap-1"
                        data-testid={`lf-edit-${c.platform}`}
                      >
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
          title={editingPlatform ? `Edit ${editingPlatform} format` : "Add platform format"}
          width="max-w-4xl"
        >
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-3">
              {editingPlatform ? (
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-1">
                    Platform
                  </label>
                  <div className="h-10 px-3 flex items-center gap-2 rounded-md border border-neutral-200 bg-neutral-50 font-mono text-sm capitalize">
                    {form.platform}
                    <span className="ml-auto text-[10px] uppercase tracking-wider text-neutral-500 bg-white border border-neutral-200 rounded px-1.5 py-0.5">
                      immutable
                    </span>
                  </div>
                </div>
              ) : (
                <Select
                  label="Platform"
                  value={form.platform}
                  onChange={(e) => setForm({ ...form, platform: e.target.value })}
                  testId="lf-form-platform"
                >
                  {PLATFORM_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </Select>
              )}

              <div className="flex items-center gap-6 pt-6">
                <label className="inline-flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={!!form.has_native_group_id}
                    onChange={(e) =>
                      setForm({ ...form, has_native_group_id: e.target.checked })
                    }
                    data-testid="lf-form-native"
                  />
                  <span>Has native group id column</span>
                </label>
                <label className="inline-flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={!!form.active}
                    onChange={(e) => setForm({ ...form, active: e.target.checked })}
                    data-testid="lf-form-active"
                  />
                  <span>Active</span>
                </label>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card className="p-4 space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-600">
                  Sheet locator
                </h4>
                <SheetLocatorEditor
                  value={form.sheet_locator}
                  onChange={(v) => setForm({ ...form, sheet_locator: v })}
                />
              </Card>
              <Card className="p-4 space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-600">
                  Header locator
                </h4>
                <HeaderLocatorEditor
                  value={form.header_locator}
                  onChange={(v) => setForm({ ...form, header_locator: v })}
                />
                <Input
                  label="Skip rows after header"
                  type="number"
                  min="0"
                  value={form.skip_rows_after_header}
                  onChange={(e) =>
                    setForm({ ...form, skip_rows_after_header: Number(e.target.value || 0) })
                  }
                />
              </Card>
            </div>

            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-600 mb-2">
                Column map (canonical → platform column name)
              </h4>
              <ColumnMapEditor
                value={form.column_map}
                canonicalFields={canonicalFields}
                onChange={(v) => setForm({ ...form, column_map: v })}
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-500 mb-1">
                Notes
              </label>
              <textarea
                className="w-full min-h-[70px] px-3 py-2 rounded-md border border-neutral-300 bg-white text-sm focus:border-neutral-500 focus:outline-none"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                placeholder="Free-form notes: format quirks, template version, contact person…"
              />
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
              <BtnPrimary onClick={save} disabled={saving} data-testid="lf-save">
                <Save className="w-4 h-4 mr-1.5" /> {saving ? "Saving…" : "Save"}
              </BtnPrimary>
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
}
