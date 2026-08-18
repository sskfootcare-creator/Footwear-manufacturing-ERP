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
  Download, Copy, Check, FileSpreadsheet, RefreshCw, FileText, ExternalLink, Image as ImageIcon,
} from "lucide-react";

// ── constants ──────────────────────────────────────────────
const ONLINE_CHANNELS = ["myntra", "flipkart", "nykaa", "website"];
const SOURCE_TYPE_LABELS = { b2b_client: "B2B Client", online_channel: "Online Channel" };

const emptyForm = {
  style_id: "", source_type: "b2b_client", source_name: "",
  external_sku: "", external_style_name: "", image_url: "",
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

// ── Bulk import drawer ────────────────────────────────────
function BulkImportDrawer({ onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const fileRef = useRef();

  const STAGE2_CSV_SAMPLE = `style_code,color,size,external_sku,source_type,source_name,external_style_name,image_url
SSK-OXF-01,Tan,8 UK,MYN-OXF-TAN-8,online_channel,myntra,Classic Oxford Formal Shoes,https://www.dropbox.com/s/sample/shoe.jpg?dl=0
SSK-OXF-01,Tan,9 UK,MYN-OXF-TAN-9,online_channel,myntra,Classic Oxford Formal Shoes,
SSK-OXF-01,Black,8 UK,MYN-OXF-BLK-8,online_channel,myntra,Classic Oxford Formal Shoes,
SSK-MOC-02,Navy,7 UK,BAT-MOC-NAV-7,b2b_client,Bata India Ltd,Navy Suede Moccasin,`;

  function downloadCsvTemplate() {
    const blob = new Blob([STAGE2_CSV_SAMPLE], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "sku_mapping_template.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function downloadXlsxTemplate() {
    try {
      const res = await http.get("/sku-map/template?format=xlsx", { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "sku_mapping_template.xlsx";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch {
      // Fallback to CSV if network fails
      downloadCsvTemplate();
    }
  }

  async function submit() {
    setError("");
    if (!file) return setError("Please choose a .xlsx or .csv template file to upload.");
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await http.post("/sku-map/bulk", fd);
      setResult(r.data);
      if (onDone) onDone();
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer?.files?.[0]) {
      const f = e.dataTransfer.files[0];
      const name = f.name.toLowerCase();
      if (name.endsWith(".xlsx") || name.endsWith(".xlsm") || name.endsWith(".csv")) {
        setFile(f);
        setError("");
      } else {
        setError("Only .xlsx or .csv files are supported.");
      }
    }
  }

  function copyErrorsToClipboard() {
    if (!result?.errors?.length) return;
    const text = result.errors.map((e) => `Row ${e.row}: ${e.reason}`).join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function downloadErrorReport() {
    if (!result?.errors?.length) return;
    let csvContent = "row,reason\n";
    result.errors.forEach((e) => {
      csvContent += `${e.row},"${(e.reason || "").replace(/"/g, '""')}"\n`;
    });
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `sku_map_upload_errors_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function resetForNewUpload() {
    setFile(null);
    setResult(null);
    setError("");
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <Drawer onClose={onClose} title="Bulk Import SKU Mappings (Stage 2)">
      <div className="space-y-5">
        {/* Template Instructions & Downloads */}
        <div className="bg-slate-900 text-white p-4 border border-slate-800 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-wider font-bold text-amber-400">Stage 2 Template Format</div>
              <div className="text-xs text-slate-300 mt-1">
                Upload your marketplace or client SKU sheets (.xlsx or .csv). Rows are grouped by <span className="text-white font-semibold font-mono">style + source + color</span> into mapping documents.
              </div>
            </div>
          </div>

          <div className="text-[11px] text-slate-300 font-mono bg-slate-950/60 p-2.5 border border-slate-800 rounded space-y-1">
            <div><span className="text-emerald-400 font-bold">Required:</span> style_code, color, size, external_sku, source_type, source_name</div>
            <div><span className="text-blue-400 font-bold">Optional:</span> external_style_name, image_url</div>
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              id="btn-download-xlsx-template"
              onClick={downloadXlsxTemplate}
              className="inline-flex items-center gap-1.5 bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold text-xs px-3 py-1.5 transition-colors shadow-sm"
            >
              <FileSpreadsheet className="w-3.5 h-3.5" />
              Download Template (.xlsx)
            </button>
            <button
              type="button"
              id="btn-download-csv-template"
              onClick={downloadCsvTemplate}
              className="inline-flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs px-3 py-1.5 transition-colors border border-slate-700"
            >
              <Download className="w-3.5 h-3.5" />
              Download (.csv)
            </button>
          </div>
        </div>

        {/* Upload Dropzone */}
        {!result && (
          <div className="space-y-3">
            <div className="text-[10px] uppercase tracking-wider font-bold text-slate-600">Select or Drag File *</div>
            <div
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
                isDragging
                  ? "border-amber-500 bg-amber-50"
                  : file
                  ? "border-emerald-500 bg-emerald-50/40"
                  : "border-slate-300 hover:border-slate-500 bg-white"
              }`}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
            >
              <Upload className={`w-8 h-8 mx-auto mb-2 ${file ? "text-emerald-600" : "text-slate-400"}`} />
              {file ? (
                <div className="space-y-1">
                  <div className="text-sm font-mono font-bold text-slate-900">{file.name}</div>
                  <div className="text-xs text-slate-500 font-mono">
                    {(file.size / 1024).toFixed(1)} KB · Ready to import
                  </div>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); resetForNewUpload(); }}
                    className="text-xs text-red-600 hover:underline font-semibold mt-2"
                  >
                    Change file
                  </button>
                </div>
              ) : (
                <div className="space-y-1">
                  <div className="text-sm font-semibold text-slate-700">Click to browse or drag file here</div>
                  <div className="text-xs text-slate-400">Supports .xlsx, .xlsm, or .csv</div>
                </div>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xlsm,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.[0]) {
                  setFile(e.target.files[0]);
                  setError("");
                }
              }}
            />
          </div>
        )}

        {/* Global Error Banner */}
        {error && (
          <div className="bg-red-50 border-2 border-red-300 p-3 text-xs text-red-700 font-semibold flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
            <div>{error}</div>
          </div>
        )}

        {/* Upload Results Summary View */}
        {result && (
          <div className="space-y-4 bg-slate-50 p-4 border border-slate-200">
            <div className="flex items-center justify-between">
              <div className="text-xs uppercase tracking-wider font-bold text-slate-700">Import Results</div>
              <button
                type="button"
                onClick={resetForNewUpload}
                className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Upload Another
              </button>
            </div>

            {/* Counts Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="bg-emerald-50 border border-emerald-300 p-2.5 text-center">
                <div className="text-[10px] uppercase tracking-wider font-bold text-emerald-800">Created</div>
                <div className="text-2xl font-bold font-mono text-emerald-700">{result.created}</div>
              </div>
              <div className="bg-blue-50 border border-blue-300 p-2.5 text-center">
                <div className="text-[10px] uppercase tracking-wider font-bold text-blue-800">Updated</div>
                <div className="text-2xl font-bold font-mono text-blue-700">{result.updated}</div>
              </div>
              <div className={`p-2.5 text-center border ${result.warnings?.length ? "bg-amber-50 border-amber-300" : "bg-slate-100 border-slate-200"}`}>
                <div className="text-[10px] uppercase tracking-wider font-bold text-amber-800">Warnings</div>
                <div className="text-2xl font-bold font-mono text-amber-700">{result.warnings?.length || 0}</div>
              </div>
              <div className={`p-2.5 text-center border ${result.errors?.length ? "bg-red-50 border-red-300" : "bg-slate-100 border-slate-200"}`}>
                <div className="text-[10px] uppercase tracking-wider font-bold text-red-800">Errors</div>
                <div className="text-2xl font-bold font-mono text-red-700">{result.errors?.length || 0}</div>
              </div>
            </div>

            {/* Warnings Section */}
            {result.warnings?.length > 0 && (
              <div className="bg-amber-50 border border-amber-300 p-3 space-y-2">
                <div className="flex items-center gap-1.5 text-xs font-bold text-amber-900">
                  <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                  <span>{result.warnings.length} Warning{result.warnings.length !== 1 ? "s" : ""}</span>
                </div>
                <div className="space-y-1.5 max-h-36 overflow-y-auto text-xs font-mono text-amber-900 pr-1">
                  {result.warnings.map((w, i) => (
                    <div key={i} className="bg-white/80 p-1.5 border border-amber-200 rounded">
                      <span className="font-bold text-amber-700">Row {w.row}:</span> {w.reason}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Errors Section */}
            {result.errors?.length > 0 ? (
              <div className="bg-red-50 border border-red-300 p-3 space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-red-900">
                    <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
                    <span>{result.errors.length} Error{result.errors.length !== 1 ? "s" : ""} (Action Required)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={copyErrorsToClipboard}
                      className="inline-flex items-center gap-1 text-[11px] font-bold bg-white text-slate-700 hover:bg-slate-100 px-2 py-1 border border-slate-300 shadow-sm"
                      title="Copy errors to clipboard"
                    >
                      {copied ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                      {copied ? "Copied!" : "Copy Errors"}
                    </button>
                    <button
                      type="button"
                      onClick={downloadErrorReport}
                      className="inline-flex items-center gap-1 text-[11px] font-bold bg-white text-slate-700 hover:bg-slate-100 px-2 py-1 border border-slate-300 shadow-sm"
                      title="Download CSV report of error rows"
                    >
                      <Download className="w-3 h-3" />
                      Export CSV
                    </button>
                  </div>
                </div>

                <div className="overflow-x-auto max-h-52 overflow-y-auto border border-red-200 bg-white">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-red-100 text-red-900 sticky top-0 font-sans font-bold text-[10px] uppercase tracking-wider">
                      <tr>
                        <th className="px-3 py-1.5 w-16">Row</th>
                        <th className="px-3 py-1.5">Problem / Reason</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-red-100">
                      {result.errors.map((e, i) => (
                        <tr key={i} className="hover:bg-red-50/60">
                          <td className="px-3 py-1.5 font-bold text-red-700 align-top">#{e.row}</td>
                          <td className="px-3 py-1.5 text-slate-800">{e.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="text-[11px] text-slate-600 italic">
                  Tip: Fix the highlighted rows in your sheet and re-upload. Existing valid mappings will automatically merge and update without duplicate entries.
                </div>
              </div>
            ) : (
              <div className="bg-emerald-50 border border-emerald-300 p-3 text-xs text-emerald-800 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span>All valid rows were processed smoothly with 0 errors!</span>
              </div>
            )}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3 pt-2">
          {!result ? (
            <BtnPrimary id="btn-bulk-upload" onClick={submit} disabled={uploading || !file} className="flex-1">
              <span className="flex items-center justify-center gap-2">
                <Upload className="w-4 h-4" />
                {uploading ? "Importing…" : "Upload & Import"}
              </span>
            </BtnPrimary>
          ) : (
            <BtnPrimary
              id="btn-done-refresh"
              onClick={() => { if (onDone) onDone(); onClose(); }}
              className="flex-1"
            >
              <span className="flex items-center justify-center gap-2">
                <Check className="w-4 h-4" /> Done & View Mappings
              </span>
            </BtnPrimary>
          )}
          <BtnSecondary onClick={onClose} disabled={uploading}>
            {result ? "Close" : "Cancel"}
          </BtnSecondary>
        </div>
      </div>
    </Drawer>
  );
}

// ── main page ─────────────────────────────────────────────
export default function SkuMap() {
  const [tab, setTab] = useState("mappings");
  const [mappings, setMappings] = useState([]);
  const [styles, setStyles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [activeMapping, setActiveMapping] = useState(null);
  const [editId, setEditId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirm, setConfirm] = useState(null);
  const [filterType, setFilterType] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterType) params.append("source_type", filterType);
      if (filterSource.trim()) params.append("source_name", filterSource.trim());
      if (searchQuery.trim()) params.append("search", searchQuery.trim());

      const [resMap, resStyles] = await Promise.all([
        http.get(`/sku-map?${params.toString()}`),
        http.get("/styles"),
      ]);
      setMappings(resMap.data);
      setStyles(resStyles.data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filterType, filterSource, searchQuery]);

  useEffect(() => {
    load();
  }, [load]);

  function openCreate() { setEditId(null); setActiveMapping(null); setForm(emptyForm); setFormError(""); setOpen(true); }
  function openEdit(m) {
    setEditId(m.id);
    setActiveMapping(m);
    setForm({
      style_id: m.style_id, source_type: m.source_type, source_name: m.source_name,
      external_sku: m.external_sku, external_style_name: m.external_style_name || "",
      image_url: m.image_url || "",
      color_map: dictToRows(m.color_map), size_map: dictToRows(m.size_map),
    });
    setFormError(""); setOpen(true);
  }

  async function handleSave() {
    setFormError("");
    if (!form.style_id.trim()) return setFormError("Please select a style.");
    if (!form.source_name.trim()) return setFormError("Source name is required.");
    if (!form.external_sku.trim()) return setFormError("External SKU is required.");
    setSaving(true);
    try {
      if (editId) {
        await http.put(`/sku-map/${editId}`, {
          external_style_name: form.external_style_name,
          image_url: form.image_url.trim(),
          color_map: rowsToDict(form.color_map),
          size_map: rowsToDict(form.size_map),
        });
      } else {
        await http.post("/sku-map", {
          style_id: form.style_id, source_type: form.source_type,
          source_name: form.source_name.trim(), external_sku: form.external_sku.trim(),
          external_style_name: form.external_style_name.trim(),
          image_url: form.image_url.trim(),
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
      message: `Remove the mapping for "${m.external_sku || m.style_code}" (${m.source_name})? This cannot be undone.`,
      onConfirm: async () => { await http.delete(`/sku-map/${m.id}`); setConfirm(null); load(); },
      onCancel: () => setConfirm(null),
    });
  }

  const selectedStyle = styles.find((s) => s.id === form.style_id);

  const TAB_CLS = (t) =>
    `px-5 py-3 text-sm font-bold border-b-2 transition-colors ${tab === t
      ? "border-[#C27842] text-slate-900"
      : "border-transparent text-slate-500 hover:text-slate-900"
    }`;

  return (
    <div className="bg-[#F7F7F5]">
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
                  Add a mapping or use Bulk Import to link client/channel SKUs to internal styles.
                </div>
              </Card>
            ) : (
              <Card className="overflow-x-auto">
                <table className="w-full text-sm" id="sku-map-table">
                  <thead>
                    <tr className="border-b-2 border-slate-200 bg-slate-50 text-left">
                      {["Internal Style", "Source", "External SKU / Group", "Ext. Style Name", "Color / Color Map", "Size Map", "Unmapped Misses", "Actions"].map((h) => (
                        <th key={h} className="px-4 py-3 text-[10px] uppercase tracking-wider font-bold text-slate-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {mappings.map((m) => {
                      const colorEntries = Object.entries(m.color_map || {});
                      const sizeEntries = Object.entries(m.size_map || {});
                      const unmappedSizes = Object.entries(m.unmapped_encountered?.size || {});
                      const unmappedColors = Object.entries(m.unmapped_encountered?.color || {});
                      const hasUnmapped = unmappedSizes.length > 0 || unmappedColors.length > 0;
                      return (
                        <tr key={m.id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              {m.image_url ? (
                                <a
                                  href={m.image_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="w-10 h-10 rounded border border-slate-200 overflow-hidden bg-slate-100 flex-shrink-0 flex items-center justify-center hover:opacity-80 transition-opacity"
                                  title="View full image"
                                >
                                  <img
                                    src={m.image_url}
                                    alt={m.style_code}
                                    className="w-full h-full object-cover"
                                    onError={(e) => { e.target.style.display = "none"; }}
                                  />
                                </a>
                              ) : (
                                <div className="w-10 h-10 rounded border border-slate-200 bg-slate-50 flex-shrink-0 flex items-center justify-center text-slate-300">
                                  <ImageIcon className="w-4 h-4" />
                                </div>
                              )}
                              <div>
                                <div className="font-mono font-bold text-slate-900">{m.style_code}</div>
                                <div className="text-[10px] text-slate-400 font-mono">{m.style_id}</div>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <Badge color={m.source_type === "b2b_client" ? "blue" : "orange"}>
                              {SOURCE_TYPE_LABELS[m.source_type] || m.source_type}
                            </Badge>
                            <div className="text-xs text-slate-600 mt-1 font-semibold">{m.source_name}</div>
                          </td>
                          <td className="px-4 py-3">
                            <div className="font-mono font-bold text-slate-900">
                              {m.external_sku || (m.color ? `${m.color} Group` : "—")}
                            </div>
                            {m.color && (
                              <div className="text-[11px] text-slate-500 mt-0.5">
                                Color: <span className="font-semibold text-slate-700">{m.color}</span>
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-600">{m.external_style_name || <span className="text-slate-300">—</span>}</td>
                          <td className="px-4 py-3">
                            {m.color ? (
                              <span className="inline-block bg-slate-100 text-slate-800 text-xs font-semibold px-2 py-0.5 rounded border border-slate-200">
                                {m.color}
                              </span>
                            ) : colorEntries.length === 0 ? (
                              <span className="text-slate-300 text-xs">—</span>
                            ) : (
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
                              <div className="space-y-0.5 max-w-[200px]">
                                {sizeEntries.slice(0, 4).map(([k, v]) => (
                                  <div key={k} className="text-[11px] font-mono text-slate-600">
                                    <span className="text-slate-500 font-semibold">{k}</span>
                                    <span className="text-slate-400 mx-1">→</span>
                                    <span className="font-bold text-slate-800">{v}</span>
                                  </div>
                                ))}
                                {sizeEntries.length > 4 && (
                                  <div className="text-[10px] text-slate-400 italic">
                                    +{sizeEntries.length - 4} more sizes
                                  </div>
                                )}
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {!hasUnmapped ? <span className="text-slate-300 text-xs">—</span> : (
                              <div className="space-y-1">
                                {unmappedSizes.map(([sz, count]) => (
                                  <span key={sz} className="inline-block bg-amber-100 border border-amber-300 text-amber-900 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded mr-1" title={`${count} recent miss(es)`}>
                                    size "{sz}" ({count}×)
                                  </span>
                                ))}
                                {unmappedColors.map(([col, count]) => (
                                  <span key={col} className="inline-block bg-amber-100 border border-amber-300 text-amber-900 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded mr-1" title={`${count} recent miss(es)`}>
                                    color "{col}" ({count}×)
                                  </span>
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

            <div className="space-y-1">
              <Input
                label="Image URL (optional — Dropbox / Google Drive / Direct link)"
                id="form-image-url"
                placeholder="https://www.dropbox.com/... or https://drive.google.com/..."
                value={form.image_url}
                onChange={(e) => setForm({ ...form, image_url: e.target.value })}
              />
              {form.image_url && (
                <div className="flex items-center gap-2 pt-1">
                  <div className="w-8 h-8 rounded border border-slate-300 overflow-hidden bg-slate-100 flex-shrink-0">
                    <img
                      src={form.image_url}
                      alt="Preview"
                      className="w-full h-full object-cover"
                      onError={(e) => { e.target.style.display = "none"; }}
                    />
                  </div>
                  <a
                    href={form.image_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-600 hover:underline flex items-center gap-1 font-mono truncate max-w-xs"
                  >
                    <span>Test image link</span>
                    <ExternalLink className="w-3 h-3 flex-shrink-0" />
                  </a>
                </div>
              )}
            </div>

            {activeMapping?.unmapped_encountered && (
              (Object.keys(activeMapping.unmapped_encountered.size || {}).length > 0 ||
               Object.keys(activeMapping.unmapped_encountered.color || {}).length > 0) && (
                <div className="bg-amber-50 border-2 border-amber-300 p-3.5 space-y-3.5">
                  <div className="flex items-center justify-between text-amber-900 font-bold text-xs uppercase tracking-wider">
                    <span className="flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                      Unmapped Values Recently Encountered
                    </span>
                    {activeMapping.last_unmapped_at && (
                      <span className="text-[10px] text-amber-700 font-mono font-normal">
                        Last: {new Date(activeMapping.last_unmapped_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    )}
                  </div>

                  {/* Sizes */}
                  {Object.keys(activeMapping.unmapped_encountered.size || {}).length > 0 && (
                    <div className="space-y-1.5">
                      <div className="text-[11px] font-semibold text-amber-800">Unmapped Sizes:</div>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(activeMapping.unmapped_encountered.size).map(([val, count]) => {
                          const alreadyInForm = form.size_map.some((r) => r.from.trim() === val.trim());
                          return (
                            <div key={val} className="inline-flex items-center gap-2 bg-white border border-amber-300 px-2.5 py-1 text-xs font-mono text-amber-900 shadow-sm">
                              <span>size <strong>"{val}"</strong> ({count}×)</span>
                              {!alreadyInForm ? (
                                <button
                                  type="button"
                                  onClick={() => setForm((prev) => ({ ...prev, size_map: [...prev.size_map, { from: val, to: val }] }))}
                                  className="text-[10px] font-bold text-amber-700 hover:text-amber-900 underline ml-1"
                                >
                                  + Add to Size Map
                                </button>
                              ) : (
                                <span className="text-[10px] text-green-700 font-bold ml-1">✓ Added</span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Colors */}
                  {Object.keys(activeMapping.unmapped_encountered.color || {}).length > 0 && (
                    <div className="space-y-1.5">
                      <div className="text-[11px] font-semibold text-amber-800">Unmapped Colors:</div>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(activeMapping.unmapped_encountered.color).map(([val, count]) => {
                          const alreadyInForm = form.color_map.some((r) => r.from.trim() === val.trim());
                          return (
                            <div key={val} className="inline-flex items-center gap-2 bg-white border border-amber-300 px-2.5 py-1 text-xs font-mono text-amber-900 shadow-sm">
                              <span>color <strong>"{val}"</strong> ({count}×)</span>
                              {!alreadyInForm ? (
                                <button
                                  type="button"
                                  onClick={() => setForm((prev) => ({ ...prev, color_map: [...prev.color_map, { from: val, to: val }] }))}
                                  className="text-[10px] font-bold text-amber-700 hover:text-amber-900 underline ml-1"
                                >
                                  + Add to Color Map
                                </button>
                              ) : (
                                <span className="text-[10px] text-green-700 font-bold ml-1">✓ Added</span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )
            )}

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
