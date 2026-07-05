import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { http, formatApiError } from "../lib/api";
import {
  PageHeader,
  Card,
  BtnPrimary,
  BtnSecondary,
  Input,
  Select,
  Badge,
  ConfirmDialog,
} from "../components/ui-kit";
import { Drawer } from "./Materials";
import {
  Plus, Trash2, Pencil, Save, X, ArrowLeftRight,
  Upload, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight,
} from "lucide-react";

// ── constants ──────────────────────────────────────────────
const ONLINE_CHANNELS = ["myntra", "flipkart", "nykaa", "website"];
const SOURCE_TYPE_LABELS = { b2b_client: "B2B Client", online_channel: "Online Channel" };

const emptyForm = {
  style_id: "", source_type: "b2b_client", source_name: "",
  external_sku: "", external_style_name: "",
  color_map: [], size_map: [],
};

// ── helpers ───────────────────────────────────────────────
function dictToRows(obj = {}) {
  return Object.entries(obj).map(([from, to]) => ({ from, to }));
}
function rowsToDict(rows = []) {
  const d = {};
  rows.forEach(({ from, to }) => { if (from.trim()) d[from.trim()] = to.trim(); });
  return d;
}

function KVPairs({ label, rows, onChange }) {
  const addRow = () => onChange([...rows, { from: "", to: "" }]);
  const removeRow = (i) => onChange(rows.filter((_, idx) => idx !== i));
  const edit = (i, field, val) =>
    onChange(rows.map((r, idx) => (idx === i ? { ...r, [field]: val } : r)));
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">{label}</div>
        <button type="button" onClick={addRow}
          className="text-[10px] font-bold uppercase tracking-wider text-blue-600 hover:text-blue-800 flex items-center gap-1">
          <Plus className="w-3 h-3" /> Add row
        </button>
      </div>
      {rows.length === 0 && <div className="text-xs text-slate-400 italic">No entries yet.</div>}
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-2">
          <input className="flex-1 border-2 border-slate-300 bg-white px-2 py-1.5 text-sm font-mono focus:border-blue-500 focus:outline-none"
            placeholder="External (from)" value={r.from} onChange={(e) => edit(i, "from", e.target.value)} />
          <span className="text-slate-400 font-bold">→</span>
          <input className="flex-1 border-2 border-slate-300 bg-white px-2 py-1.5 text-sm font-mono focus:border-blue-500 focus:outline-none"
            placeholder="Internal (to)" value={r.to} onChange={(e) => edit(i, "to", e.target.value)} />
          <button type="button" onClick={() => removeRow(i)} className="text-red-400 hover:text-red-600 transition-colors flex-shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

// ── Unmapped tab ──────────────────────────────────────────
function UnmappedTab({ styles, onDone }) {
  const [groups, setGroups]     = useState([]);
  const [loading, setLoading]   = useState(true);
  const [expanded, setExpanded] = useState({});

  // Map modal states
  const [mappingTarget, setMappingTarget] = useState(null);
  const [mapMode, setMapMode]             = useState("existing"); // "existing" | "new"
  const [selectedStyleId, setSelectedStyleId] = useState("");
  const [newStyleForm, setNewStyleForm]   = useState({
    code: "", name: "", category: "Footwear", description: "",
    base_size: "7", overhead_pct: 8, packing_cost: 12, margin_pct: 25, gst_pct: 5
  });
  const [styleSearch, setStyleSearch]     = useState("");
  const [submitError, setSubmitError]     = useState("");
  const [submitting, setSubmitting]       = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await http.get("/sku-map/unmapped");
      setGroups(r.data);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    if (mappingTarget) {
      setNewStyleForm({
        code: mappingTarget.external_sku,
        name: `Style ${mappingTarget.external_sku}`,
        category: "Footwear",
        description: `Created from unmapped SKU ${mappingTarget.external_sku}`,
        base_size: "7",
        overhead_pct: 8,
        packing_cost: 12,
        margin_pct: 25,
        gst_pct: 5
      });
      setSubmitError("");
      setSelectedStyleId("");
      setMapMode("existing");
    }
  }, [mappingTarget]);

  const filteredStylesList = useMemo(() => {
    if (!styleSearch) return styles;
    const s = styleSearch.toLowerCase();
    return styles.filter((st) =>
      st.code.toLowerCase().includes(s) ||
      st.name.toLowerCase().includes(s)
    );
  }, [styles, styleSearch]);

  const handleConfirmMapping = async () => {
    setSubmitError("");
    setSubmitting(true);
    try {
      let styleId = selectedStyleId;

      if (mapMode === "new") {
        if (!newStyleForm.code.trim() || !newStyleForm.name.trim()) {
          setSubmitError("Style Code and Name are required.");
          setSubmitting(false);
          return;
        }
        const styleRes = await http.post("/styles", {
          code: newStyleForm.code.trim(),
          name: newStyleForm.name.trim(),
          category: newStyleForm.category,
          description: newStyleForm.description,
          base_size: newStyleForm.base_size,
          overhead_pct: Number(newStyleForm.overhead_pct),
          packing_cost: Number(newStyleForm.packing_cost),
          margin_pct: Number(newStyleForm.margin_pct),
          gst_pct: Number(newStyleForm.gst_pct),
        });
        styleId = styleRes.data.id;
      }

      if (!styleId) {
        setSubmitError("Please select a style to map.");
        setSubmitting(false);
        return;
      }

      await http.post("/sku-map", {
        style_id: styleId,
        source_type: mappingTarget.source_type,
        source_name: mappingTarget.source_name,
        external_sku: mappingTarget.external_sku,
        external_style_name: "",
        color_map: {},
        size_map: {},
      });

      setMappingTarget(null);
      reload();
      if (onDone) onDone();
    } catch (e) {
      setSubmitError(e.response?.data?.detail || "Mapping failed.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="text-center py-20 text-slate-400">Loading unmapped items…</div>;

  if (groups.length === 0)
    return (
      <Card className="p-10 text-center">
        <CheckCircle2 className="w-10 h-10 text-green-400 mx-auto mb-3" />
        <div className="text-slate-600 font-semibold mb-1">All styles are mapped!</div>
        <div className="text-xs text-slate-400">No production jobs have unresolved style codes.</div>
      </Card>
    );

  return (
    <div className="space-y-3">
      {groups.map((g) => {
        const key = `${g.source_type}:${g.source_name}`;
        const isOpen = !!expanded[key];
        return (
          <Card key={key} className="overflow-hidden">
            <button
              className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-slate-50 transition-colors"
              onClick={() => setExpanded((e) => ({ ...e, [key]: !isOpen }))}
            >
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />
                <div>
                  <div className="font-bold text-slate-900">{g.source_name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    <Badge color="blue">{SOURCE_TYPE_LABELS[g.source_type] || g.source_type}</Badge>
                    <span className="ml-2">{g.job_count} job{g.job_count !== 1 ? "s" : ""} unresolved</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right hidden sm:block">
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">External SKUs</div>
                  <div className="text-xs font-mono text-slate-700 truncate max-w-[220px]">
                    {g.external_skus.slice(0, 4).join(", ")}{g.external_skus.length > 4 ? ` +${g.external_skus.length - 4} more` : ""}
                  </div>
                </div>
                {isOpen ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
              </div>
            </button>
            {isOpen && (
              <div className="border-t border-slate-100 p-4 space-y-4">
                <div className="bg-slate-50 p-3 border border-slate-200">
                  <div className="text-[10px] uppercase font-bold text-slate-500 mb-2">Unresolved SKUs:</div>
                  <div className="flex flex-wrap gap-2">
                    {g.external_skus.map((sku) => (
                      <div key={sku} className="flex items-center gap-2 bg-white border border-slate-300 px-2.5 py-1.5 font-mono text-xs">
                        <span className="font-bold text-slate-800">{sku}</span>
                        <button
                          onClick={() => setMappingTarget({
                            source_type: g.source_type,
                            source_name: g.source_name,
                            external_sku: sku,
                          })}
                          className="bg-[#0F172A] hover:bg-slate-800 text-white text-[10px] uppercase font-bold px-2 py-1 transition-colors"
                        >
                          Map to Style
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-left">
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">PO #</th>
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">External SKU</th>
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">Color</th>
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">Size</th>
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">Qty</th>
                        <th className="px-4 py-2 text-[10px] uppercase tracking-wider font-bold text-slate-500">Stage</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {g.jobs.map((j) => (
                        <tr key={j.id} className="hover:bg-amber-50 transition-colors">
                          <td className="px-4 py-2 font-mono text-xs">{j.po_number}</td>
                          <td className="px-4 py-2 font-mono font-bold text-red-700">{j.style_code}</td>
                          <td className="px-4 py-2 text-xs text-slate-600">{j.color || "—"}</td>
                          <td className="px-4 py-2 text-xs text-slate-600">{j.size || "—"}</td>
                          <td className="px-4 py-2 text-xs">{j.quantity}</td>
                          <td className="px-4 py-2">
                            <Badge color="yellow">{j.stage}</Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </Card>
        );
      })}

      {mappingTarget && (
        <Drawer onClose={() => setMappingTarget(null)} title="Map External Code to Style">
          <div className="space-y-4">
            <div className="bg-slate-100 p-3 border border-slate-200 font-mono text-xs space-y-1">
              <div><span className="text-slate-400 font-bold">SOURCE TYPE:</span> {SOURCE_TYPE_LABELS[mappingTarget.source_type]}</div>
              <div><span className="text-slate-400 font-bold">SOURCE NAME:</span> {mappingTarget.source_name}</div>
              <div><span className="text-slate-400 font-bold">EXTERNAL SKU:</span> {mappingTarget.external_sku}</div>
            </div>

            <div className="flex gap-4 border-b border-slate-200 pb-2">
              <button
                type="button"
                className={`text-xs uppercase tracking-wider font-bold pb-1 border-b-2 ${mapMode === "existing" ? "border-slate-900 text-slate-900" : "border-transparent text-slate-400"}`}
                onClick={() => setMapMode("existing")}
              >
                Map to Existing Style
              </button>
              <button
                type="button"
                className={`text-xs uppercase tracking-wider font-bold pb-1 border-b-2 ${mapMode === "new" ? "border-slate-900 text-slate-900" : "border-transparent text-slate-400"}`}
                onClick={() => setMapMode("new")}
              >
                Create New Style
              </button>
            </div>

            {mapMode === "existing" ? (
              <div className="space-y-3">
                <Input
                  label="Search Styles"
                  placeholder="Type style code or name..."
                  value={styleSearch}
                  onChange={(e) => setStyleSearch(e.target.value)}
                />
                <div className="space-y-1">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Select Style *</div>
                  <select
                    className="w-full border-2 border-slate-300 p-2 text-sm focus:outline-none bg-white"
                    value={selectedStyleId}
                    onChange={(e) => setSelectedStyleId(e.target.value)}
                  >
                    <option value="">— Select Style —</option>
                    {filteredStylesList.map((s) => (
                      <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
                    ))}
                  </select>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Style Code *"
                    value={newStyleForm.code}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, code: e.target.value })}
                  />
                  <Input
                    label="Style Name *"
                    value={newStyleForm.name}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, name: e.target.value })}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Category"
                    value={newStyleForm.category}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, category: e.target.value })}
                  />
                  <Input
                    label="Base Size"
                    value={newStyleForm.base_size}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, base_size: e.target.value })}
                  />
                </div>
                <Input
                  label="Description"
                  value={newStyleForm.description}
                  onChange={(e) => setNewStyleForm({ ...newStyleForm, description: e.target.value })}
                />
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <Input
                    label="Overhead%"
                    type="number"
                    value={newStyleForm.overhead_pct}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, overhead_pct: e.target.value })}
                  />
                  <Input
                    label="Packing₹"
                    type="number"
                    value={newStyleForm.packing_cost}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, packing_cost: e.target.value })}
                  />
                  <Input
                    label="Margin%"
                    type="number"
                    value={newStyleForm.margin_pct}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, margin_pct: e.target.value })}
                  />
                  <Input
                    label="GST%"
                    type="number"
                    value={newStyleForm.gst_pct}
                    onChange={(e) => setNewStyleForm({ ...newStyleForm, gst_pct: e.target.value })}
                  />
                </div>
              </div>
            )}

            {submitError && (
              <div className="bg-red-50 border border-red-300 p-2 text-xs text-red-700 font-semibold">{submitError}</div>
            )}

            <div className="flex gap-2 pt-2">
              <BtnPrimary onClick={handleConfirmMapping} disabled={submitting} className="flex-1">
                {submitting ? "Processing..." : "Confirm & Map"}
              </BtnPrimary>
              <BtnSecondary onClick={() => setMappingTarget(null)} disabled={submitting}>Cancel</BtnSecondary>
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
}

// ── Bulk import drawer ────────────────────────────────────
function BulkImportDrawer({ onClose, onDone }) {
  const [srcType, setSrcType]   = useState("b2b_client");
  const [srcName, setSrcName]   = useState("");
  const [file, setFile]         = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult]     = useState(null);
  const [error, setError]       = useState("");
  const fileRef = useRef();

  const CSV_TEMPLATE = `external_sku,style_code,external_style_name,color_from,color_to,size_from,size_to
TC-001,SSK-OXF-01,Classic Oxford Brown,Tan,TAN01,8 UK,8
TC-002,SSK-MOC-02,Moccasin Navy,,,,`;

  async function submit() {
    setError(""); setResult(null);
    if (!file) return setError("Please select a CSV file.");
    if (!srcName.trim()) return setError("Source name is required.");
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("source_type", srcType);
      fd.append("source_name", srcName.trim());
      const r = await http.post("/sku-map/bulk", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(r.data);
      onDone();
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Upload failed.");
    } finally { setUploading(false); }
  }

  function downloadTemplate() {
    const blob = new Blob([CSV_TEMPLATE], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "sku_map_template.csv";
    a.click();
  }

  return (
    <Drawer onClose={onClose} title="Bulk Import SKU Mappings">
      <div className="space-y-5">
        <div className="bg-blue-50 border-2 border-blue-200 px-4 py-3 text-sm text-blue-800">
          Upload a CSV with columns: <span className="font-mono font-bold">external_sku</span>,{" "}
          <span className="font-mono font-bold">style_code</span> (required) +{" "}
          <span className="font-mono">external_style_name, color_from, color_to, size_from, size_to</span> (optional).{" "}
          <button onClick={downloadTemplate} className="underline font-bold ml-1">Download template</button>
        </div>

        {/* Source type */}
        <div className="space-y-2">
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Source Type *</div>
          <div className="flex gap-4">
            {[["b2b_client", "B2B Client"], ["online_channel", "Online Channel"]].map(([val, label]) => (
              <label key={val} className="flex items-center gap-2 cursor-pointer">
                <input type="radio" name="bulk-source-type" value={val} checked={srcType === val}
                  onChange={() => { setSrcType(val); setSrcName(""); }} className="accent-slate-900" />
                <span className="text-sm font-semibold text-slate-700">{label}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Source name */}
        {srcType === "online_channel" ? (
          <Select label="Channel *" id="bulk-source-name-channel" value={srcName}
            onChange={(e) => setSrcName(e.target.value)}>
            <option value="">— Select channel —</option>
            {ONLINE_CHANNELS.map((ch) => (
              <option key={ch} value={ch}>{ch.charAt(0).toUpperCase() + ch.slice(1)}</option>
            ))}
          </Select>
        ) : (
          <Input label="Client Name *" id="bulk-source-name"
            placeholder="e.g. Bata India Ltd — applies to all rows unless CSV has source_name column"
            value={srcName} onChange={(e) => setSrcName(e.target.value)} />
        )}

        {/* File picker */}
        <div className="space-y-1">
          <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">CSV File *</div>
          <div
            className="border-2 border-dashed border-slate-300 hover:border-slate-500 px-4 py-6 text-center cursor-pointer transition-colors"
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="w-6 h-6 text-slate-400 mx-auto mb-2" />
            {file
              ? <div className="text-sm font-mono font-bold text-slate-700">{file.name}</div>
              : <div className="text-sm text-slate-500">Click to choose a .csv file</div>}
          </div>
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden"
            onChange={(e) => setFile(e.target.files[0] || null)} />
        </div>

        {error && (
          <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold">{error}</div>
        )}

        {result && (
          <div className="space-y-2">
            <div className="bg-green-50 border-2 border-green-300 px-4 py-3 text-sm text-green-800 font-semibold">
              ✓ {result.created} created · {result.skipped_duplicate} duplicates skipped
            </div>
            {result.errors.length > 0 && (
              <div className="bg-amber-50 border-2 border-amber-300 px-4 py-3 text-sm text-amber-800 space-y-1 max-h-40 overflow-y-auto">
                <div className="font-bold">{result.errors.length} row error{result.errors.length !== 1 ? "s" : ""}:</div>
                {result.errors.map((e, i) => (
                  <div key={i} className="font-mono text-xs">Row {e.row}: {e.reason}</div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <BtnPrimary id="btn-bulk-upload" onClick={submit} disabled={uploading} className="flex-1">
            <span className="flex items-center justify-center gap-2">
              <Upload className="w-4 h-4" />
              {uploading ? "Uploading…" : "Upload & Import"}
            </span>
          </BtnPrimary>
          <BtnSecondary onClick={onClose} disabled={uploading}>Cancel</BtnSecondary>
        </div>
      </div>
    </Drawer>
  );
}

// ── main page ─────────────────────────────────────────────
export default function SkuMap() {
  const [mappings, setMappings]   = useState([]);
  const [styles, setStyles]       = useState([]);
  const [loading, setLoading]     = useState(true);
  const [open, setOpen]           = useState(false);
  const [bulkOpen, setBulkOpen]   = useState(false);
  const [editId, setEditId]       = useState(null);
  const [form, setForm]           = useState(emptyForm);
  const [formError, setFormError] = useState("");
  const [saving, setSaving]       = useState(false);
  const [confirm, setConfirm]     = useState(null);
  const [tab, setTab]             = useState("mappings"); // "mappings" | "unmapped"

  // filters
  const [filterType, setFilterType]     = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [searchQuery, setSearchQuery]   = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterType)   params.append("source_type", filterType);
      if (filterSource) params.append("source_name", filterSource);
      if (searchQuery)  params.append("search",      searchQuery);
      const qs = params.toString() ? `?${params}` : "";
      const [mRes, sRes] = await Promise.all([
        http.get(`/sku-map${qs}`),
        http.get("/styles"),
      ]);
      setMappings(mRes.data);
      setStyles(sRes.data);
    } finally { setLoading(false); }
  }, [filterType, filterSource, searchQuery]);

  useEffect(() => { load(); }, [load]);

  function openCreate() { setEditId(null); setForm(emptyForm); setFormError(""); setOpen(true); }
  function openEdit(m) {
    setEditId(m.id);
    setForm({
      style_id: m.style_id, source_type: m.source_type, source_name: m.source_name,
      external_sku: m.external_sku, external_style_name: m.external_style_name || "",
      color_map: dictToRows(m.color_map), size_map: dictToRows(m.size_map),
    });
    setFormError(""); setOpen(true);
  }

  async function handleSave() {
    setFormError("");
    if (!form.style_id.trim())     return setFormError("Please select a style.");
    if (!form.source_name.trim())  return setFormError("Source name is required.");
    if (!form.external_sku.trim()) return setFormError("External SKU is required.");
    setSaving(true);
    try {
      if (editId) {
        await http.put(`/sku-map/${editId}`, {
          external_style_name: form.external_style_name,
          color_map: rowsToDict(form.color_map),
          size_map:  rowsToDict(form.size_map),
        });
      } else {
        await http.post("/sku-map", {
          style_id: form.style_id, source_type: form.source_type,
          source_name: form.source_name.trim(), external_sku: form.external_sku.trim(),
          external_style_name: form.external_style_name.trim(),
          color_map: rowsToDict(form.color_map), size_map: rowsToDict(form.size_map),
        });
      }
      setOpen(false); load();
    } catch (e) {
      setFormError(formatApiError(e.response?.data?.detail));
    } finally { setSaving(false); }
  }

  function askDelete(m) {
    setConfirm({
      title: "Delete Mapping",
      message: `Remove the mapping for "${m.external_sku}" (${m.source_name})? This cannot be undone.`,
      onConfirm: async () => { await http.delete(`/sku-map/${m.id}`); setConfirm(null); load(); },
      onCancel: () => setConfirm(null),
    });
  }

  const selectedStyle = styles.find((s) => s.id === form.style_id);

  const TAB_CLS = (t) =>
    `px-5 py-3 text-sm font-bold border-b-2 transition-colors ${
      tab === t
        ? "border-[#C27842] text-slate-900"
        : "border-transparent text-slate-500 hover:text-slate-900"
    }`;

  return (
    <div className="min-h-screen bg-[#F7F7F5]">
      <PageHeader
        title="SKU Mapping"
        subtitle="Style ID ↔ External SKU"
        testId="sku-map-header"
        action={
          <div className="flex gap-2">
            <BtnSecondary id="btn-bulk-import" onClick={() => setBulkOpen(true)}>
              <span className="flex items-center gap-2"><Upload className="w-4 h-4" /> Bulk Import</span>
            </BtnSecondary>
            <BtnPrimary id="btn-add-sku-map" onClick={openCreate}>
              <span className="flex items-center gap-2"><Plus className="w-4 h-4" /> Add Mapping</span>
            </BtnPrimary>
          </div>
        }
      />

      {/* Tabs */}
      <div className="bg-white border-b-2 border-slate-200 flex px-4 sm:px-8">
        <button className={TAB_CLS("mappings")} onClick={() => setTab("mappings")}>All Mappings</button>
        <button className={TAB_CLS("unmapped")} onClick={() => setTab("unmapped")}>
          <span className="flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-500" /> Unmapped Jobs
          </span>
        </button>
      </div>

      {tab === "unmapped" ? (
        <div className="px-4 sm:px-8 py-6">
          <UnmappedTab styles={styles} onDone={load} />
        </div>
      ) : (
        <>
          {/* Filters */}
          <div className="px-4 sm:px-8 py-4 bg-white border-b-2 border-slate-200 flex flex-wrap gap-3 items-end">
            <div className="w-44">
              <Select label="Source Type" id="filter-source-type" value={filterType}
                onChange={(e) => setFilterType(e.target.value)}>
                <option value="">All Types</option>
                <option value="b2b_client">B2B Client</option>
                <option value="online_channel">Online Channel</option>
              </Select>
            </div>
            <div className="w-52">
              <Input label="Source Name" id="filter-source-name" placeholder="Filter by client / channel…"
                value={filterSource} onChange={(e) => setFilterSource(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && load()} />
            </div>
            <div className="flex-1 min-w-[200px]">
              <Input label="Search SKU / Style" id="filter-search" placeholder="External SKU, style code, name…"
                value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && load()} />
            </div>
            <BtnSecondary id="btn-apply-filters" onClick={load}>Search</BtnSecondary>
          </div>

          {/* Stats bar */}
          <div className="px-4 sm:px-8 pt-5 pb-2">
            <div className="text-xs text-slate-500 font-mono">
              {loading ? "Loading…" : `${mappings.length} mapping${mappings.length !== 1 ? "s" : ""}`}
            </div>
          </div>

          {/* Table */}
          <div className="px-4 sm:px-8 pb-10">
            {loading ? (
              <div className="text-center py-20 text-slate-400">Loading mappings…</div>
            ) : mappings.length === 0 ? (
              <Card className="p-10 text-center">
                <ArrowLeftRight className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                <div className="text-slate-500 font-semibold mb-1">No mappings found</div>
                <div className="text-xs text-slate-400">
                  Add a mapping to link a client's SKU code to an internal style.
                </div>
              </Card>
            ) : (
              <Card className="overflow-x-auto">
                <table className="w-full text-sm" id="sku-map-table">
                  <thead>
                    <tr className="border-b-2 border-slate-200 bg-slate-50 text-left">
                      {["Internal Style", "Source", "External SKU", "Ext. Style Name", "Color Map", "Size Map", "Actions"].map((h) => (
                        <th key={h} className="px-4 py-3 text-[10px] uppercase tracking-wider font-bold text-slate-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {mappings.map((m) => {
                      const colorEntries = Object.entries(m.color_map || {});
                      const sizeEntries  = Object.entries(m.size_map  || {});
                      return (
                        <tr key={m.id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-4 py-3">
                            <div className="font-mono font-bold text-slate-900">{m.style_code}</div>
                            <div className="text-[10px] text-slate-400 font-mono">{m.style_id}</div>
                          </td>
                          <td className="px-4 py-3">
                            <Badge color={m.source_type === "b2b_client" ? "blue" : "orange"}>
                              {SOURCE_TYPE_LABELS[m.source_type] || m.source_type}
                            </Badge>
                            <div className="text-xs text-slate-600 mt-1 font-semibold">{m.source_name}</div>
                          </td>
                          <td className="px-4 py-3 font-mono font-bold text-slate-900">{m.external_sku}</td>
                          <td className="px-4 py-3 text-xs text-slate-600">{m.external_style_name || <span className="text-slate-300">—</span>}</td>
                          <td className="px-4 py-3">
                            {colorEntries.length === 0 ? <span className="text-slate-300 text-xs">—</span> : (
                              <div className="space-y-0.5">
                                {colorEntries.map(([k, v]) => (
                                  <div key={k} className="text-[11px] font-mono text-slate-600">
                                    <span className="text-slate-400">{k}</span>
                                    <span className="text-slate-400 mx-1">→</span>
                                    <span className="font-bold">{v}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {sizeEntries.length === 0 ? <span className="text-slate-300 text-xs">—</span> : (
                              <div className="space-y-0.5">
                                {sizeEntries.map(([k, v]) => (
                                  <div key={k} className="text-[11px] font-mono text-slate-600">
                                    <span className="text-slate-400">{k}</span>
                                    <span className="text-slate-400 mx-1">→</span>
                                    <span className="font-bold">{v}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <button id={`btn-edit-${m.id}`} onClick={() => openEdit(m)}
                                className="text-slate-400 hover:text-slate-700 transition-colors" title="Edit">
                                <Pencil className="w-4 h-4" />
                              </button>
                              <button id={`btn-delete-${m.id}`} onClick={() => askDelete(m)}
                                className="text-slate-400 hover:text-red-600 transition-colors" title="Delete">
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </Card>
            )}
          </div>
        </>
      )}

      {/* Create / Edit Drawer */}
      {open && (
        <Drawer onClose={() => setOpen(false)} title={editId ? "Edit Mapping" : "New SKU Mapping"}>
          <div className="space-y-5">
            {/* Style selector */}
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Internal Style *</div>
              {editId ? (
                <div className="border-2 border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-700">
                  {selectedStyle ? `${selectedStyle.code} — ${selectedStyle.name}` : form.style_id}
                </div>
              ) : (
                <select id="form-style-id"
                  className="w-full border-2 border-slate-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  value={form.style_id} onChange={(e) => setForm({ ...form, style_id: e.target.value })}>
                  <option value="">— Select style —</option>
                  {styles.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
                </select>
              )}
            </div>

            {/* Source type */}
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Source Type *</div>
              <div className="flex gap-4">
                {[["b2b_client", "B2B Client"], ["online_channel", "Online Channel"]].map(([val, label]) => (
                  <label key={val} className="flex items-center gap-2 cursor-pointer select-none">
                    <input type="radio" name="source_type" value={val} disabled={!!editId}
                      checked={form.source_type === val}
                      onChange={() => setForm({ ...form, source_type: val, source_name: "" })}
                      className="accent-slate-900" id={`radio-${val}`} />
                    <span className="text-sm font-semibold text-slate-700">{label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Source name */}
            {editId ? (
              <div className="space-y-1">
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Source Name</div>
                <div className="border-2 border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-700">
                  {form.source_name}
                </div>
              </div>
            ) : form.source_type === "online_channel" ? (
              <Select label="Channel *" id="form-source-name-channel" value={form.source_name}
                onChange={(e) => setForm({ ...form, source_name: e.target.value })}>
                <option value="">— Select channel —</option>
                {ONLINE_CHANNELS.map((ch) => (
                  <option key={ch} value={ch}>{ch.charAt(0).toUpperCase() + ch.slice(1)}</option>
                ))}
              </Select>
            ) : (
              <Input label="Client Name *" id="form-source-name" placeholder="e.g. Bata India Ltd"
                value={form.source_name} onChange={(e) => setForm({ ...form, source_name: e.target.value })} />
            )}

            {/* External SKU */}
            {editId ? (
              <div className="space-y-1">
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">External SKU</div>
                <div className="border-2 border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-700">
                  {form.external_sku}
                </div>
              </div>
            ) : (
              <Input label="External SKU *" id="form-external-sku"
                placeholder="The code that the client / platform uses"
                value={form.external_sku} onChange={(e) => setForm({ ...form, external_sku: e.target.value })} />
            )}

            <Input label="External Style Name (optional)" id="form-external-style-name"
              placeholder="How this source describes the style"
              value={form.external_style_name}
              onChange={(e) => setForm({ ...form, external_style_name: e.target.value })} />

            <KVPairs label="Color Map (optional) — external → internal"
              rows={form.color_map} onChange={(rows) => setForm({ ...form, color_map: rows })} />
            <KVPairs label="Size Map (optional) — external → internal"
              rows={form.size_map} onChange={(rows) => setForm({ ...form, size_map: rows })} />

            {formError && (
              <div className="bg-red-50 border-2 border-red-300 px-4 py-3 text-sm text-red-700 font-semibold">
                {formError}
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <BtnPrimary id="btn-save-sku-map" onClick={handleSave} disabled={saving} className="flex-1">
                <span className="flex items-center justify-center gap-2">
                  <Save className="w-4 h-4" />
                  {saving ? "Saving…" : editId ? "Update Mapping" : "Create Mapping"}
                </span>
              </BtnPrimary>
              <BtnSecondary onClick={() => setOpen(false)} disabled={saving}>Cancel</BtnSecondary>
            </div>
          </div>
        </Drawer>
      )}

      {/* Bulk Import Drawer */}
      {bulkOpen && (
        <BulkImportDrawer onClose={() => setBulkOpen(false)} onDone={() => { load(); }} />
      )}

      <ConfirmDialog open={!!confirm} title={confirm?.title} message={confirm?.message}
        onConfirm={confirm?.onConfirm} onCancel={confirm?.onCancel} />
    </div>
  );
}
